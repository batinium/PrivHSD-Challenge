"""Classifier-guided HSD evidence extraction after a baseline run."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .csv_pipeline import read_csv, write_csv, write_json
from .models.hf_hsd_classifier_runtime import (
    DEFAULT_HF_HSD_BATCH_SIZE,
    DEFAULT_HF_HSD_MAX_LENGTH,
    DEFAULT_HF_HSD_MODEL_PATH,
    DEFAULT_HF_HSD_THRESHOLD,
    HfHsdClassifierRuntime,
)
from .submission import sha256_file, validate_submission


DEFAULT_EVIDENCE_NEGATIVE_TEXT = "Context removed."
DEFAULT_EVIDENCE_MAX_ANCHORS = 3
DEFAULT_EVIDENCE_CONTEXT_RADIUS = 2
DEFAULT_EVIDENCE_ANCHOR_MIN_DELTA = 0.03
DEFAULT_EVIDENCE_ANCHOR_RELATIVE_MIN = 0.25
DEFAULT_POSITIVE_LABELS = frozenset({"1", "true", "yes", "hate"})


@dataclass(frozen=True)
class ImportanceToken:
    row_id: str
    row_index: int
    token_index: int
    token: str
    start: int
    end: int
    delta: float
    abs_delta: float
    baseline_hate_score: float


class EvidencePostprocessError(ValueError):
    """Raised when evidence extraction cannot preserve the CSV contract."""


def _bool_from_label(value: str, positive_labels: frozenset[str]) -> bool:
    return str(value).strip().lower() in {label.lower() for label in positive_labels}


def _classification_metrics(
    gold: list[bool],
    predicted: list[bool],
) -> dict[str, float | int]:
    tp = sum(1 for actual, pred in zip(gold, predicted, strict=True) if actual and pred)
    tn = sum(
        1 for actual, pred in zip(gold, predicted, strict=True) if not actual and not pred
    )
    fp = sum(
        1 for actual, pred in zip(gold, predicted, strict=True) if not actual and pred
    )
    fn = sum(
        1 for actual, pred in zip(gold, predicted, strict=True) if actual and not pred
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "accuracy": round((tp + tn) / len(gold), 6) if gold else 0.0,
        "balanced_accuracy": round((recall + specificity) / 2, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def _load_source_and_baseline(
    *,
    source_path: Path,
    baseline_path: Path,
    output_path: Path,
    text_col: str,
    id_col: str | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str], list[str]]:
    if baseline_path.resolve() == output_path.resolve():
        raise EvidencePostprocessError(
            "evidence output must be a separate file; refusing to overwrite baseline"
        )

    source_rows, source_fields = read_csv(source_path)
    baseline_rows, baseline_fields = read_csv(baseline_path)
    if len(source_rows) != len(baseline_rows):
        raise EvidencePostprocessError(
            "source and baseline row counts differ: "
            f"{len(source_rows)} != {len(baseline_rows)}"
        )
    if text_col not in source_fields:
        raise EvidencePostprocessError(f"{source_path}: missing text column {text_col!r}")
    if text_col not in baseline_fields:
        raise EvidencePostprocessError(
            f"{baseline_path}: missing text column {text_col!r}"
        )
    if id_col:
        if id_col not in source_fields:
            raise EvidencePostprocessError(
                f"{source_path}: missing id column {id_col!r}"
            )
        if id_col not in baseline_fields:
            raise EvidencePostprocessError(
                f"{baseline_path}: missing id column {id_col!r}"
            )
        for index, (source_row, baseline_row) in enumerate(
            zip(source_rows, baseline_rows, strict=True),
            start=1,
        ):
            if source_row[id_col] != baseline_row[id_col]:
                raise EvidencePostprocessError(
                    f"row {index}: source and baseline IDs differ: "
                    f"{source_row[id_col]!r} != {baseline_row[id_col]!r}"
                )
    return source_rows, baseline_rows, source_fields, baseline_fields


def _load_importance_tokens(path: Path) -> dict[str, list[ImportanceToken]]:
    tokens_by_key: dict[str, list[ImportanceToken]] = defaultdict(list)
    rows, _fields = read_csv(path)
    for row in rows:
        try:
            token = ImportanceToken(
                row_id=str(row.get("row_id") or "").strip(),
                row_index=int(row.get("row_index") or 0),
                token_index=int(row.get("token_index") or 0),
                token=str(row.get("token") or ""),
                start=int(row.get("start") or 0),
                end=int(row.get("end") or 0),
                delta=float(row.get("delta_hate_score") or 0.0),
                abs_delta=float(row.get("abs_delta_hate_score") or 0.0),
                baseline_hate_score=float(row.get("baseline_hate_score") or 0.0),
            )
        except ValueError:
            continue
        if token.row_id:
            tokens_by_key[token.row_id].append(token)
        if token.row_index:
            tokens_by_key[f"index:{token.row_index}"].append(token)

    return {
        key: sorted(values, key=lambda item: item.token_index)
        for key, values in tokens_by_key.items()
    }


def _row_importance_tokens(
    tokens_by_key: dict[str, list[ImportanceToken]],
    *,
    row_id: str,
    row_index: int,
) -> list[ImportanceToken]:
    return list(tokens_by_key.get(row_id) or tokens_by_key.get(f"index:{row_index}") or [])


def _choose_evidence_tokens(
    items: list[ImportanceToken],
    *,
    max_anchors: int,
    context_radius: int,
    anchor_min_delta: float,
    anchor_relative_min: float,
) -> tuple[list[ImportanceToken], list[ImportanceToken]]:
    if not items:
        return [], []
    by_index = {item.token_index: item for item in items}
    positive = [item for item in items if item.delta > 0.0]
    if not positive:
        positive = sorted(items, key=lambda item: item.abs_delta, reverse=True)[:1]

    ranked = sorted(
        positive,
        key=lambda item: (item.delta, item.abs_delta),
        reverse=True,
    )
    top_delta = ranked[0].delta if ranked else 0.0
    anchors: list[ImportanceToken] = []
    for item in ranked:
        if not anchors:
            anchors.append(item)
            continue
        if len(anchors) >= max_anchors:
            break
        if item.delta < anchor_min_delta:
            continue
        if item.delta < top_delta * anchor_relative_min:
            continue
        anchors.append(item)

    selected_indices: set[int] = set()
    for anchor in anchors:
        start = anchor.token_index - context_radius
        end = anchor.token_index + context_radius
        for token_index in range(start, end + 1):
            if token_index in by_index:
                selected_indices.add(token_index)
    return anchors, [by_index[index] for index in sorted(selected_indices)]


def _evidence_text(tokens: list[ImportanceToken], *, negative_text: str) -> str:
    if not tokens:
        return negative_text
    text = " ".join(token.token for token in tokens).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text or negative_text


def _sorted_count_dict(counter: Counter[int | str]) -> dict[str, int]:
    return {str(key): counter[key] for key in sorted(counter)}


def run_classifier_evidence_after_baseline(
    *,
    source_path: Path,
    baseline_path: Path,
    importance_path: Path,
    output_path: Path,
    text_col: str = "text",
    id_col: str | None = None,
    label_col: str | None = None,
    manifest_path: Path | None = None,
    validation_path: Path | None = None,
    hf_summary_path: Path | None = None,
    trace_path: Path | None = None,
    classifier_text_source: str = "baseline",
    hf_hsd_model_path: str = DEFAULT_HF_HSD_MODEL_PATH,
    hf_hsd_threshold: float = DEFAULT_HF_HSD_THRESHOLD,
    hf_hsd_device: str = "auto",
    hf_hsd_batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE,
    hf_hsd_max_length: int = DEFAULT_HF_HSD_MAX_LENGTH,
    max_anchors: int = DEFAULT_EVIDENCE_MAX_ANCHORS,
    context_radius: int = DEFAULT_EVIDENCE_CONTEXT_RADIUS,
    anchor_min_delta: float = DEFAULT_EVIDENCE_ANCHOR_MIN_DELTA,
    anchor_relative_min: float = DEFAULT_EVIDENCE_ANCHOR_RELATIVE_MIN,
    negative_text: str = DEFAULT_EVIDENCE_NEGATIVE_TEXT,
    positive_labels: frozenset[str] = DEFAULT_POSITIVE_LABELS,
) -> dict[str, Any]:
    """Write a classifier-guided HSD evidence CSV from a baseline output."""

    if classifier_text_source not in {"baseline", "source"}:
        raise EvidencePostprocessError(
            "classifier_text_source must be 'baseline' or 'source'"
        )
    if max_anchors < 1:
        raise EvidencePostprocessError("max_anchors must be at least 1")
    if context_radius < 0:
        raise EvidencePostprocessError("context_radius must be non-negative")
    if anchor_relative_min < 0:
        raise EvidencePostprocessError("anchor_relative_min must be non-negative")

    source_rows, baseline_rows, source_fields, baseline_fields = (
        _load_source_and_baseline(
            source_path=source_path,
            baseline_path=baseline_path,
            output_path=output_path,
            text_col=text_col,
            id_col=id_col,
        )
    )
    importance_by_key = _load_importance_tokens(importance_path)
    classification_input = (
        baseline_rows if classifier_text_source == "baseline" else source_rows
    )
    classifier_rows = [
        {
            "id": row[id_col] if id_col else str(index),
            "text": row[text_col],
        }
        for index, row in enumerate(classification_input, start=1)
    ]
    classifier = HfHsdClassifierRuntime(
        model_path=hf_hsd_model_path,
        threshold=hf_hsd_threshold,
        device=hf_hsd_device,
        max_length=hf_hsd_max_length,
    )
    baseline_result = classifier.classify_texts(
        classifier_rows,
        batch_size=hf_hsd_batch_size,
    )
    predicted_positive = [row.hate for row in baseline_result.rows]

    output_rows: list[dict[str, str]] = []
    changed_count = 0
    anchor_counts: Counter[int] = Counter()
    selected_counts: Counter[int] = Counter()
    word_counts: Counter[int] = Counter()
    trace_examples: list[dict[str, Any]] = []
    issue_examples: list[dict[str, Any]] = []

    for row_index, (source_row, baseline_row, is_positive) in enumerate(
        zip(source_rows, baseline_rows, predicted_positive, strict=True),
        start=1,
    ):
        row_id = str(source_row[id_col]) if id_col else str(row_index)
        output_row = dict(baseline_row)
        if is_positive:
            items = _row_importance_tokens(
                importance_by_key,
                row_id=row_id,
                row_index=row_index,
            )
            anchors, selected = _choose_evidence_tokens(
                items,
                max_anchors=max_anchors,
                context_radius=context_radius,
                anchor_min_delta=anchor_min_delta,
                anchor_relative_min=anchor_relative_min,
            )
            if not selected:
                issue_examples.append(
                    {
                        "id": row_id,
                        "issue": "positive row had no selected evidence tokens",
                    }
                )
            text = _evidence_text(selected, negative_text=negative_text)
            anchor_counts[len(anchors)] += 1
            selected_counts[len(selected)] += 1
            if len(trace_examples) < 30:
                trace_examples.append(
                    {
                        "id": row_id,
                        "anchors": [
                            {
                                "token": anchor.token,
                                "token_index": anchor.token_index,
                                "delta": round(anchor.delta, 6),
                                "abs_delta": round(anchor.abs_delta, 6),
                            }
                            for anchor in anchors
                        ],
                        "selected_tokens": [
                            {
                                "token": token.token,
                                "token_index": token.token_index,
                                "start": token.start,
                                "end": token.end,
                                "span_text": source_row[text_col][
                                    token.start : token.end
                                ],
                            }
                            for token in selected
                        ],
                        "output": text,
                    }
                )
        else:
            text = negative_text

        output_row[text_col] = text
        if output_row[text_col] != baseline_row[text_col]:
            changed_count += 1
        word_counts[len(text.split()) if text else 0] += 1
        output_rows.append(output_row)

    write_csv(output_path, output_rows, baseline_fields)
    validation = validate_submission(
        baseline_path,
        output_path,
        text_cols=[text_col],
        id_col=id_col,
        output_path=validation_path,
        allow_helper_columns=False,
    )

    final_classifier_rows = [
        {
            "id": row[id_col] if id_col else str(index),
            "text": row[text_col],
        }
        for index, row in enumerate(output_rows, start=1)
    ]
    final_result = classifier.classify_texts(
        final_classifier_rows,
        batch_size=hf_hsd_batch_size,
    )
    final_positive = [row.hate for row in final_result.rows]
    baseline_scores = [row.score for row in baseline_result.rows]
    final_scores = [row.score for row in final_result.rows]
    score_deltas = [
        final - baseline
        for final, baseline in zip(final_scores, baseline_scores, strict=True)
    ]
    gold: list[bool] | None = None
    if label_col and label_col in source_fields:
        gold = [_bool_from_label(row[label_col], positive_labels) for row in source_rows]

    hf_summary: dict[str, Any] = {
        "rows": len(output_rows),
        "model_path": hf_hsd_model_path,
        "threshold": round(hf_hsd_threshold, 6),
        "device": final_result.device,
        "classifier_text_source": classifier_text_source,
        "baseline_prediction_counts": dict(
            sorted(Counter("1" if flag else "0" for flag in predicted_positive).items())
        ),
        "final_prediction_counts": dict(
            sorted(Counter("1" if flag else "0" for flag in final_positive).items())
        ),
        "baseline_to_final_label_flips": sum(
            1
            for before, after in zip(predicted_positive, final_positive, strict=True)
            if before != after
        ),
        "positive_pred_rows": sum(predicted_positive),
        "positive_preserved_after_evidence": sum(
            1
            for before, after in zip(predicted_positive, final_positive, strict=True)
            if before and after
        ),
        "positive_missed_after_evidence": sum(
            1
            for before, after in zip(predicted_positive, final_positive, strict=True)
            if before and not after
        ),
        "score_delta_mean": round(sum(score_deltas) / len(score_deltas), 6)
        if score_deltas
        else 0.0,
        "score_delta_abs_mean": round(
            sum(abs(value) for value in score_deltas) / len(score_deltas),
            6,
        )
        if score_deltas
        else 0.0,
        "score_delta_min": round(min(score_deltas), 6) if score_deltas else 0.0,
        "score_delta_max": round(max(score_deltas), 6) if score_deltas else 0.0,
    }
    if gold is not None:
        hf_summary["baseline_vs_gold"] = _classification_metrics(
            gold,
            predicted_positive,
        )
        hf_summary["final_vs_gold"] = _classification_metrics(gold, final_positive)
    if hf_summary_path is not None:
        write_json(hf_summary_path, hf_summary)

    trace = {
        "rows": len(output_rows),
        "evidence_rows": sum(predicted_positive),
        "neutral_rows": len(output_rows) - sum(predicted_positive),
        "context_radius": context_radius,
        "max_anchors": max_anchors,
        "anchor_min_delta": anchor_min_delta,
        "anchor_relative_min": anchor_relative_min,
        "anchor_count_distribution": _sorted_count_dict(anchor_counts),
        "selected_token_count_distribution": _sorted_count_dict(selected_counts),
        "word_count_distribution": _sorted_count_dict(word_counts),
        "issue_examples": issue_examples[:20],
        "trace_examples": trace_examples,
        "valid_selected_tokens_from_source_importance_spans": not issue_examples,
    }
    if trace_path is not None:
        write_json(trace_path, trace)

    manifest: dict[str, Any] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "classifier_guided_hsd_evidence_phrase_abstraction",
        "risk_level": "experimental",
        "note": (
            "Uses HF classifier predictions, then keeps source evidence token "
            "anchors from the token-importance table plus a small source-token "
            "context window. No gold labels are used for replacement decisions."
        ),
        "source": str(source_path),
        "baseline": str(baseline_path),
        "importance_csv": str(importance_path),
        "output_csv": str(output_path),
        "validation_path": str(validation_path) if validation_path else None,
        "hf_utility_summary_path": str(hf_summary_path) if hf_summary_path else None,
        "source_token_trace_path": str(trace_path) if trace_path else None,
        "text_col": text_col,
        "label_col": label_col,
        "id_col": id_col,
        "classifier_text_source": classifier_text_source,
        "rows": len(output_rows),
        "positive_pred_rows": sum(predicted_positive),
        "negative_pred_rows": len(output_rows) - sum(predicted_positive),
        "changed_text_cells_vs_locked_baseline": changed_count,
        "context_radius": context_radius,
        "max_anchors": max_anchors,
        "anchor_min_delta": anchor_min_delta,
        "anchor_relative_min": anchor_relative_min,
        "negative_text": negative_text,
        "source_sha256": sha256_file(source_path),
        "baseline_sha256": sha256_file(baseline_path),
        "importance_sha256": sha256_file(importance_path),
        "output_sha256": sha256_file(output_path),
        "validation": validation,
        "hf_summary": hf_summary,
        "trace": trace,
    }
    if manifest_path is not None:
        write_json(manifest_path, manifest)
        manifest["manifest_path"] = str(manifest_path)
    return manifest


__all__ = [
    "DEFAULT_EVIDENCE_ANCHOR_MIN_DELTA",
    "DEFAULT_EVIDENCE_ANCHOR_RELATIVE_MIN",
    "DEFAULT_EVIDENCE_CONTEXT_RADIUS",
    "DEFAULT_EVIDENCE_MAX_ANCHORS",
    "DEFAULT_EVIDENCE_NEGATIVE_TEXT",
    "EvidencePostprocessError",
    "run_classifier_evidence_after_baseline",
]
