"""Token-policy advisory provider for automatic mode."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from contextsafe_hsd.models.token_policy_runtime import TokenPolicyRuntime
from contextsafe_hsd.token_policy import (
    ACTION_GENERALIZE,
    ACTION_MASK,
    ACTION_NORMALIZE,
    ACTION_PROTECT_HSD,
    ACTION_PROTECT_TARGET,
    ACTION_REVIEW,
)

from .base import (
    PRIVACY_CLASS_DIRECT,
    PRIVACY_CLASS_QUASI,
    UTILITY_CLASS_NONE,
    SpanCandidate,
    SpanProviderOutput,
)


@dataclass
class TokenPolicySpanProvider:
    runtime: TokenPolicyRuntime
    name: str = "token_policy_ensemble"

    def status_metadata(self) -> dict[str, Any]:
        return self.runtime.status_metadata()

    def propose(self, text: str) -> SpanProviderOutput:
        return self.propose_many([{"text": text}], text_col="text", batch_size=1)[0]

    def propose_many(
        self,
        rows: list[dict[str, str]],
        *,
        text_col: str,
        batch_size: int,
    ) -> list[SpanProviderOutput]:
        predictions = self.runtime.predict_batch(
            rows,
            text_col=text_col,
            batch_size=batch_size,
        )
        return [
            self._output_from_prediction(
                str(row.get(text_col, "") or ""),
                prediction,
            )
            for row, prediction in zip(rows, predictions)
        ]

    def _output_from_prediction(
        self,
        text: str,
        prediction: dict[str, Any],
    ) -> SpanProviderOutput:
        candidates: list[SpanCandidate] = []
        evidence_counts: Counter[str] = Counter()
        skipped_counts: Counter[str] = Counter()
        for span in prediction.get("spans", []):
            action = str(span.get("action", ""))
            evidence_counts[action] += 1
            try:
                start = int(span["start"])
                end = int(span["end"])
                confidence = float(span.get("confidence", 0.0) or 0.0)
            except (KeyError, TypeError, ValueError):
                skipped_counts["invalid_prediction_span"] += 1
                continue
            if start < 0 or end <= start or end > len(text):
                skipped_counts["out_of_bounds"] += 1
                continue
            if action == ACTION_MASK:
                candidates.append(
                    SpanCandidate(
                        start=start,
                        end=end,
                        text=text[start:end],
                        entity_type="IDENTIFIER",
                        privacy_class=PRIVACY_CLASS_DIRECT,
                        utility_class=UTILITY_CLASS_NONE,
                        provider=self.name,
                        score=confidence,
                        explanation_code=ACTION_MASK,
                        metadata={"source": f"{self.name}:{ACTION_MASK}"},
                    )
                )
            elif action == ACTION_GENERALIZE:
                candidates.append(
                    SpanCandidate(
                        start=start,
                        end=end,
                        text=text[start:end],
                        entity_type="LOCATION",
                        privacy_class=PRIVACY_CLASS_QUASI,
                        utility_class=UTILITY_CLASS_NONE,
                        provider=self.name,
                        score=confidence,
                        explanation_code=ACTION_GENERALIZE,
                        metadata={"source": f"{self.name}:{ACTION_GENERALIZE}"},
                    )
                )
            elif action in {
                ACTION_PROTECT_TARGET,
                ACTION_PROTECT_HSD,
                ACTION_NORMALIZE,
                ACTION_REVIEW,
            }:
                continue
            else:
                skipped_counts["unsupported_action"] += 1
        action_counts = Counter(prediction.get("action_counts", {}))
        audit = {
            "enabled": True,
            "provider": self.name,
            "raw_prediction_span_count": len(prediction.get("spans", [])),
            "accepted_span_count": len(candidates),
            "action_counts": dict(sorted(action_counts.items())),
            "evidence_counts": dict(sorted(evidence_counts.items())),
            "skipped_token_count": int(prediction.get("skipped_token_count", 0) or 0),
            "skipped_counts": dict(sorted(skipped_counts.items())),
            "style_evidence_count": action_counts.get(ACTION_NORMALIZE, 0),
            "review_evidence_count": action_counts.get(ACTION_REVIEW, 0),
            "protected_target_evidence_count": action_counts.get(ACTION_PROTECT_TARGET, 0),
            "protected_hsd_evidence_count": action_counts.get(ACTION_PROTECT_HSD, 0),
        }
        return SpanProviderOutput(
            provider=self.name,
            spans=tuple(candidates),
            audit=audit,
        )
