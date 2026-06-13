"""Batch runtime for token-policy advisory ensembles."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from privhsd.token_policy import (
    ACTION_KEEP,
    DEFAULT_MAX_LENGTH,
    TOKEN_POLICY_ACTIONS,
    choose_ensemble_action,
    load_token_policy_ensemble,
    merge_prediction_spans,
    model_input_for_row,
    normalize_model_weights,
    token_spans_for_text,
)


def overlaps(start: int, end: int, other_start: int, other_end: int) -> bool:
    return start < other_end and end > other_start


class TokenPolicyRuntime:
    """Owns loaded token-policy ensemble members and batched inference."""

    def __init__(
        self,
        *,
        members: list[dict[str, Any]],
        model_weights: list[float],
        mode: str,
        device: str,
    ) -> None:
        self.members = members
        self.model_weights = model_weights
        self.mode = mode
        self.device = device

    @classmethod
    def from_model_dirs(
        cls,
        model_dirs: list[Path],
        *,
        mode: str = "mean_prob",
        device: str = "auto",
        model_weights: list[float] | None = None,
    ) -> "TokenPolicyRuntime":
        members = load_token_policy_ensemble(model_dirs)
        chosen_device = members[0]["device"] if members else "cpu"
        if device in {"cpu", "cuda"}:
            chosen_device = device
            for member in members:
                member["model"].to(device)
                member["device"] = device
        weights = normalize_model_weights(model_weights, len(members))
        return cls(
            members=members,
            model_weights=weights,
            mode=mode,
            device=chosen_device,
        )

    def status_metadata(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "mode": self.mode,
            "member_count": len(self.members),
            "model_dirs": [str(member["model_dir"]) for member in self.members],
        }

    def predict_batch(
        self,
        rows: list[dict[str, str]],
        *,
        text_col: str,
        batch_size: int = 16,
    ) -> list[dict[str, Any]]:
        predictions: list[dict[str, Any]] = []
        for start in range(0, len(rows), batch_size):
            chunk = rows[start : start + batch_size]
            predictions.extend(self._predict_chunk(chunk, text_col=text_col))
        return predictions

    def _predict_chunk(
        self,
        rows: list[dict[str, str]],
        *,
        text_col: str,
    ) -> list[dict[str, Any]]:
        token_spans_by_row = [
            token_spans_for_text(str(row.get(text_col, "") or ""))
            for row in rows
        ]
        distributions_by_member = [
            self._member_distributions_for_batch(
                member,
                rows,
                text_col=text_col,
                token_spans_by_row=token_spans_by_row,
            )
            for member in self.members
        ]
        outputs: list[dict[str, Any]] = []
        for row_index, token_spans in enumerate(token_spans_by_row):
            prediction_spans: list[dict[str, Any]] = []
            action_counts: Counter[str] = Counter()
            skipped_tokens = 0
            ensemble_actions: list[tuple[str, bool, float]] = []
            for token_index, (_token, token_start, token_end) in enumerate(token_spans):
                token_member_distributions = [
                    member_rows[row_index][token_index]
                    for member_rows in distributions_by_member
                ]
                action, confidence, covered_count = choose_ensemble_action(
                    token_member_distributions,
                    model_weights=self.model_weights,
                    mode=self.mode,
                )
                if covered_count == 0:
                    skipped_tokens += 1
                    ensemble_actions.append((ACTION_KEEP, False, confidence))
                    continue
                ensemble_actions.append((action, True, confidence))
                action_counts[action] += 1
                if action == ACTION_KEEP:
                    continue
                prediction_spans.append(
                    {
                        "start": token_start,
                        "end": token_end,
                        "action": action,
                        "confidence": confidence,
                        "model_count": covered_count,
                    }
                )
            outputs.append(
                {
                    "spans": merge_prediction_spans(prediction_spans),
                    "action_counts": dict(sorted(action_counts.items())),
                    "skipped_token_count": skipped_tokens,
                    "ensemble_actions": ensemble_actions,
                }
            )
        return outputs

    def _member_distributions_for_batch(
        self,
        member: dict[str, Any],
        rows: list[dict[str, str]],
        *,
        text_col: str,
        token_spans_by_row: list[list[tuple[str, int, int]]],
    ) -> list[list[tuple[list[float], bool]]]:
        metadata = member["metadata"]
        tokenizer = member["tokenizer"]
        model = member["model"]
        torch = member["torch"]
        device = member["device"]
        columns = metadata["columns"]
        input_texts: list[str] = []
        text_starts: list[int] = []
        for row in rows:
            model_row = dict(row)
            model_text_col = columns["text_col"]
            if model_text_col != text_col:
                model_row[model_text_col] = str(row.get(text_col, "") or "")
            for optional_col in (
                columns.get("source_col"),
                columns.get("label_col"),
                columns.get("target_col"),
            ):
                if optional_col and optional_col not in model_row:
                    model_row[optional_col] = ""
            input_text, text_start = model_input_for_row(
                model_row,
                text_col=model_text_col,
                source_col=columns.get("source_col"),
                label_col=columns.get("label_col"),
                target_col=columns.get("target_col"),
                metadata_prefix=bool(metadata.get("metadata_prefix", True)),
            )
            input_texts.append(input_text)
            text_starts.append(text_start)

        encoded = tokenizer(
            input_texts,
            truncation=True,
            padding="max_length",
            max_length=int(metadata.get("max_length", DEFAULT_MAX_LENGTH)),
            return_offsets_mapping=True,
            return_tensors="pt",
        )
        offsets_batch = encoded.pop("offset_mapping").tolist()
        with torch.no_grad():
            batch = {key: value.to(device) for key, value in encoded.items()}
            logits = model(**batch).logits
            probabilities_batch = torch.softmax(logits, dim=-1).detach().cpu().tolist()

        rows_distributions: list[list[tuple[list[float], bool]]] = []
        for row_index, token_spans in enumerate(token_spans_by_row):
            text_start = text_starts[row_index]
            model_pieces: list[tuple[int, int, list[float]]] = []
            for token_index, (start, end) in enumerate(offsets_batch[row_index]):
                if start == end or end <= text_start:
                    continue
                model_pieces.append(
                    (
                        max(0, int(start) - text_start),
                        max(0, int(end) - text_start),
                        probabilities_batch[row_index][token_index],
                    )
                )
            distributions: list[tuple[list[float], bool]] = []
            for _token, token_start, token_end in token_spans:
                covered = [
                    piece_probabilities
                    for piece_start, piece_end, piece_probabilities in model_pieces
                    if overlaps(token_start, token_end, piece_start, piece_end)
                ]
                if not covered:
                    distributions.append(([0.0] * len(TOKEN_POLICY_ACTIONS), False))
                    continue
                averaged = [
                    sum(probabilities[label_index] for probabilities in covered)
                    / len(covered)
                    for label_index in range(len(TOKEN_POLICY_ACTIONS))
                ]
                distributions.append((averaged, True))
            rows_distributions.append(distributions)
        return rows_distributions
