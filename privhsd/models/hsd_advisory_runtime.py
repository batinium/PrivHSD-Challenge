"""Local HSD classifier advisory runtime for auto candidate scoring."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any

from privhsd.hf_utility import (
    APPROVED_MODELS,
    normalize_pipeline_output,
    positive_score,
    resolve_device,
)


POSITIVE_LABEL_HINTS = ("hate", "offensive", "toxic", "abusive")


def positive_label_hints_for_model(model_id: str) -> tuple[str, ...]:
    for model in APPROVED_MODELS:
        if model.model_id == model_id:
            return model.positive_label_hints
    return POSITIVE_LABEL_HINTS


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
    positive_label_hints: tuple[str, ...] = POSITIVE_LABEL_HINTS

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
            positive_label_hints=positive_label_hints_for_model(model_id),
        )

    def status_metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "device": self.device,
            "decision_threshold": self.decision_threshold,
            "large_drop_threshold": self.large_drop_threshold,
            "max_abs_drift": self.max_abs_drift,
            "positive_label_hints": list(self.positive_label_hints),
            "approved_use": "auto candidate HSD-utility preservation advisory only",
        }

    def score_texts(self, texts: list[str], *, batch_size: int) -> list[float]:
        outputs = self.classifier(texts, batch_size=batch_size, truncation=True)
        normalized = normalize_pipeline_output(outputs)
        return [
            positive_score(scores, positive_label_hints=self.positive_label_hints)
            for scores in normalized
        ]

    def score_texts_by_model(
        self,
        texts: list[str],
        *,
        batch_size: int,
    ) -> dict[str, list[float]]:
        return {self.model_id: self.score_texts(texts, batch_size=batch_size)}

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

    def compare_scores_by_model(
        self,
        original_scores: dict[str, float],
        candidate_scores: dict[str, float],
    ) -> dict[str, Any]:
        original_score = float(original_scores.get(self.model_id, 0.0) or 0.0)
        candidate_score = float(candidate_scores.get(self.model_id, 0.0) or 0.0)
        result = self.compare(original_score, candidate_score)
        result["model_count"] = 1
        result["models"] = {self.model_id: result.copy()}
        return result


@dataclass
class HsdAdvisoryEnsembleRuntime:
    """Mean-score ensemble over approved local Hugging Face HSD probes."""

    members: list[HsdAdvisoryRuntime]
    skipped_members: list[dict[str, Any]]
    decision_threshold: float
    large_drop_threshold: float
    max_abs_drift: float

    @classmethod
    def from_model_ids(
        cls,
        model_ids: tuple[str, ...],
        *,
        allow_model_download: bool,
        device: str,
        decision_threshold: float,
        large_drop_threshold: float,
        max_abs_drift: float,
    ) -> "HsdAdvisoryEnsembleRuntime":
        members: list[HsdAdvisoryRuntime] = []
        skipped_members: list[dict[str, Any]] = []
        for model_id in model_ids:
            try:
                members.append(
                    HsdAdvisoryRuntime.from_model_id(
                        model_id,
                        allow_model_download=allow_model_download,
                        device=device,
                        decision_threshold=decision_threshold,
                        large_drop_threshold=large_drop_threshold,
                        max_abs_drift=max_abs_drift,
                    )
                )
            except Exception as exc:
                skipped_members.append(
                    {
                        "model_id": model_id,
                        "status": "skipped",
                        "reason": "load_failed",
                        "error_class": type(exc).__name__,
                        "detail": str(exc),
                    }
                )
        if not members:
            detail = "; ".join(
                f"{item['model_id']}: {item['error_class']}"
                for item in skipped_members
            )
            raise RuntimeError(
                "no HSD advisory models could be loaded"
                + (f" ({detail})" if detail else "")
            )
        return cls(
            members=members,
            skipped_members=skipped_members,
            decision_threshold=decision_threshold,
            large_drop_threshold=large_drop_threshold,
            max_abs_drift=max_abs_drift,
        )

    @property
    def model_id(self) -> str:
        return "ensemble:" + ",".join(member.model_id for member in self.members)

    def status_metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_ids": [member.model_id for member in self.members],
            "member_count": len(self.members),
            "skipped_members": self.skipped_members,
            "devices": {
                member.model_id: member.device
                for member in self.members
            },
            "revisions": {
                member.model_id: member.revision
                for member in self.members
            },
            "decision_threshold": self.decision_threshold,
            "large_drop_threshold": self.large_drop_threshold,
            "max_abs_drift": self.max_abs_drift,
            "approved_use": "auto candidate HSD-utility preservation advisory only",
        }

    def score_texts_by_model(
        self,
        texts: list[str],
        *,
        batch_size: int,
    ) -> dict[str, list[float]]:
        return {
            member.model_id: member.score_texts(texts, batch_size=batch_size)
            for member in self.members
        }

    def score_texts(self, texts: list[str], *, batch_size: int) -> list[float]:
        scores_by_model = self.score_texts_by_model(texts, batch_size=batch_size)
        return [
            float(mean(scores[index] for scores in scores_by_model.values()))
            for index in range(len(texts))
        ]

    def compare(self, original_score: float, candidate_score: float) -> dict[str, Any]:
        return HsdAdvisoryRuntime(
            classifier=None,
            model_id=self.model_id,
            revision=None,
            device="ensemble",
            decision_threshold=self.decision_threshold,
            large_drop_threshold=self.large_drop_threshold,
            max_abs_drift=self.max_abs_drift,
            positive_label_hints=POSITIVE_LABEL_HINTS,
        ).compare(original_score, candidate_score)

    def compare_scores_by_model(
        self,
        original_scores: dict[str, float],
        candidate_scores: dict[str, float],
    ) -> dict[str, Any]:
        common_models = [
            member.model_id
            for member in self.members
            if member.model_id in original_scores and member.model_id in candidate_scores
        ]
        if not common_models:
            return self.compare(0.0, 0.0)
        original_mean = mean(float(original_scores[model_id]) for model_id in common_models)
        candidate_mean = mean(float(candidate_scores[model_id]) for model_id in common_models)
        result = self.compare(original_mean, candidate_mean)
        member_results = {
            member.model_id: member.compare(
                float(original_scores[member.model_id]),
                float(candidate_scores[member.model_id]),
            )
            for member in self.members
            if member.model_id in common_models
        }
        result["model_count"] = len(common_models)
        result["models"] = member_results
        result["member_large_drop_count"] = sum(
            bool(item.get("large_drop")) for item in member_results.values()
        )
        result["member_decision_drift_count"] = sum(
            bool(item.get("decision_changed")) for item in member_results.values()
        )
        return result
