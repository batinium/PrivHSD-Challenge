"""Local HSD classifier advisory runtime for auto candidate scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from privhsd.hf_utility import normalize_pipeline_output, positive_score, resolve_device


POSITIVE_LABEL_HINTS = ("hate", "offensive", "toxic", "abusive")


@dataclass
class HsdAdvisoryRuntime:
    """Batch hate-speech utility scorer.

    Scores are used only to preserve downstream HSD signal during
    privatization. They are not legal or moderation decisions.
    """

    classifier: Any
    model_id: str
    revision: str | None
    device: str
    decision_threshold: float
    large_drop_threshold: float
    max_abs_drift: float

    @classmethod
    def from_model_id(
        cls,
        model_id: str,
        *,
        allow_model_download: bool,
        device: str,
        decision_threshold: float,
        large_drop_threshold: float,
        max_abs_drift: float,
    ) -> "HsdAdvisoryRuntime":
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            pipeline,
        )

        device_arg, resolved_device = resolve_device(device)
        local_files_only = not allow_model_download
        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            local_files_only=local_files_only,
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            model_id,
            local_files_only=local_files_only,
        )
        classifier = pipeline(
            "text-classification",
            model=model,
            tokenizer=tokenizer,
            top_k=None,
            truncation=True,
            device=device_arg,
        )
        revision = getattr(getattr(model, "config", None), "_commit_hash", None)
        return cls(
            classifier=classifier,
            model_id=model_id,
            revision=str(revision) if revision else None,
            device=resolved_device,
            decision_threshold=decision_threshold,
            large_drop_threshold=large_drop_threshold,
            max_abs_drift=max_abs_drift,
        )

    def status_metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "device": self.device,
            "decision_threshold": self.decision_threshold,
            "large_drop_threshold": self.large_drop_threshold,
            "max_abs_drift": self.max_abs_drift,
            "approved_use": "auto candidate HSD-utility preservation advisory only",
        }

    def score_texts(self, texts: list[str], *, batch_size: int) -> list[float]:
        outputs = self.classifier(texts, batch_size=batch_size, truncation=True)
        normalized = normalize_pipeline_output(outputs)
        return [
            positive_score(scores, positive_label_hints=POSITIVE_LABEL_HINTS)
            for scores in normalized
        ]

    def compare(self, original_score: float, candidate_score: float) -> dict[str, Any]:
        delta = candidate_score - original_score
        abs_drift = abs(delta)
        score_drop = max(0.0, original_score - candidate_score)
        original_decision = original_score >= self.decision_threshold
        candidate_decision = candidate_score >= self.decision_threshold
        decision_changed = original_decision != candidate_decision
        large_drop = (
            original_decision and score_drop >= self.large_drop_threshold
        )
        large_abs_drift = abs_drift >= self.max_abs_drift
        return {
            "model_id": self.model_id,
            "original_score": round(float(original_score), 4),
            "candidate_score": round(float(candidate_score), 4),
            "score_delta": round(float(delta), 4),
            "score_drop": round(float(score_drop), 4),
            "abs_drift": round(float(abs_drift), 4),
            "original_decision": "positive" if original_decision else "negative",
            "candidate_decision": "positive" if candidate_decision else "negative",
            "decision_changed": decision_changed,
            "large_drop": large_drop,
            "large_abs_drift": large_abs_drift,
            "decision_threshold": self.decision_threshold,
            "large_drop_threshold": self.large_drop_threshold,
            "max_abs_drift": self.max_abs_drift,
        }
