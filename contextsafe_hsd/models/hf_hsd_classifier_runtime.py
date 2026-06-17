"""Local Hugging Face binary HSD classifier runtime.

The runtime receives only post-cleaning text and writes sidecar classification
metadata. It never rewrites or masks text.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
import time
from pathlib import Path
from typing import Any


DEFAULT_HF_HSD_MODEL_PATH = "data/outputs/dehatebert_official_kfold_20260617/final_model"
DEFAULT_HF_HSD_THRESHOLD = 0.850469
DEFAULT_HF_HSD_MAX_LENGTH = 512
DEFAULT_HF_HSD_BATCH_SIZE = 64


@dataclass(frozen=True)
class HfHsdClassifierRow:
    row_id: str
    label: str
    hate: bool
    score: float
    threshold: float
    parse_status: str = "ok"

    def to_metadata(self) -> dict[str, Any]:
        return {
            "id": self.row_id,
            "label": self.label,
            "hate": self.hate,
            "score": round(self.score, 6),
            "threshold": round(self.threshold, 6),
            "hsd_reasons": ["model_score"] if self.hate else ["none"],
            "review_needed": self.hate,
            "parse_status": self.parse_status,
            "pii_suggestion_count": 0,
            "accepted_pii_suggestion_count": 0,
            "pii_suggestion_status_counts": {},
            "pii_suggestions": [],
        }


@dataclass(frozen=True)
class HfHsdClassifierResult:
    rows: tuple[HfHsdClassifierRow, ...]
    model_id: str
    model_path: str
    threshold: float
    max_length: int
    device: str
    elapsed_seconds: float

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def parsed_count(self) -> int:
        return sum(row.parse_status == "ok" for row in self.rows)

    @property
    def skipped_count(self) -> int:
        return self.row_count - self.parsed_count

    @property
    def status(self) -> str:
        if not self.rows:
            return "skipped"
        if self.parsed_count == self.row_count:
            return "ok"
        if self.parsed_count:
            return "partial"
        return "skipped"

    def summary(self) -> dict[str, Any]:
        prediction_counts = Counter(row.label for row in self.rows)
        reason_counts = Counter(
            reason
            for row in self.rows
            for reason in (["model_score"] if row.hate else ["none"])
        )
        return {
            "backend": "hf_classifier",
            "status": self.status,
            "row_count": self.row_count,
            "model_id": self.model_id,
            "model_path": self.model_path,
            "threshold": round(self.threshold, 6),
            "max_length": self.max_length,
            "device": self.device,
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "request_count": 0,
            "parse_count": self.parsed_count,
            "fallback_count": 0,
            "skipped_count": self.skipped_count,
            "prediction_counts": dict(sorted(prediction_counts.items())),
            "reason_tag_counts": dict(sorted(reason_counts.items())),
            "score_basis": "softmax_hate_probability",
            "pii_suggestion_count": 0,
            "accepted_pii_suggestion_count": 0,
            "validated_pii_suggestion_counts": {
                "total": 0,
                "accepted_for_review": 0,
                "rejected": 0,
            },
            "pii_suggestion_status_counts": {},
            "row_reviews": [row.to_metadata() for row in self.rows],
        }


class HfHsdClassifierRuntime:
    """Run a local Transformers sequence classifier for binary HSD labels."""

    def __init__(
        self,
        *,
        model_path: str | Path = DEFAULT_HF_HSD_MODEL_PATH,
        threshold: float = DEFAULT_HF_HSD_THRESHOLD,
        device: str = "auto",
        max_length: int = DEFAULT_HF_HSD_MAX_LENGTH,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("hf_hsd_threshold must be between 0 and 1")
        if max_length < 1:
            raise ValueError("hf_hsd_max_length must be positive")

        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        requested_device = device.strip().lower()
        if requested_device == "auto":
            selected_device = "cuda" if torch.cuda.is_available() else "cpu"
        elif requested_device in {"cpu", "cuda"}:
            selected_device = requested_device
        else:
            raise ValueError("hf_hsd_device must be auto, cpu, or cuda")

        self.model_path = str(model_path)
        self.threshold = float(threshold)
        self.max_length = int(max_length)
        self.device = selected_device
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
        self._model.float()
        self._model.eval()
        self._model.to(self.device)
        self.model_id = str(getattr(self._model.config, "_name_or_path", self.model_path))

    def status_metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_path": self.model_path,
            "threshold": round(self.threshold, 6),
            "max_length": self.max_length,
            "device": self.device,
            "score_basis": "softmax_hate_probability",
        }

    def classify_texts(
        self,
        rows: list[dict[str, str]],
        *,
        batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> HfHsdClassifierResult:
        if batch_size < 1:
            raise ValueError("hf_hsd_batch_size must be positive")

        started = time.perf_counter()
        reviews: list[HfHsdClassifierRow] = []
        total = len(rows)
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "hf_classifier",
                    "processed": 0,
                    "total": total,
                    "detail": "Running local HF HSD classifier on cleaned text.",
                }
            )
        for offset in range(0, total, batch_size):
            batch = rows[offset : offset + batch_size]
            scores = self._scores([str(row.get("text", "") or "") for row in batch])
            for row, score in zip(batch, scores, strict=True):
                hate = bool(score >= self.threshold)
                reviews.append(
                    HfHsdClassifierRow(
                        row_id=str(row.get("id", "")),
                        label="1" if hate else "0",
                        hate=hate,
                        score=float(score),
                        threshold=self.threshold,
                    )
                )
            if progress_callback is not None:
                progress_callback(
                    {
                        "stage": "hf_classifier",
                        "processed": min(offset + len(batch), total),
                        "total": total,
                        "detail": "Classified cleaned text rows.",
                    }
                )
        return HfHsdClassifierResult(
            rows=tuple(reviews),
            model_id=self.model_id,
            model_path=self.model_path,
            threshold=self.threshold,
            max_length=self.max_length,
            device=self.device,
            elapsed_seconds=time.perf_counter() - started,
        )

    def _scores(self, texts: list[str]) -> list[float]:
        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with self._torch.inference_mode():
            logits = self._model(**encoded).logits
        probs = self._torch.softmax(logits.float(), dim=-1)[:, 1]
        return [float(value) for value in probs.detach().cpu().tolist()]


__all__ = [
    "DEFAULT_HF_HSD_BATCH_SIZE",
    "DEFAULT_HF_HSD_MAX_LENGTH",
    "DEFAULT_HF_HSD_MODEL_PATH",
    "DEFAULT_HF_HSD_THRESHOLD",
    "HfHsdClassifierRuntime",
]
