"""DeHateBERT classifier runtime adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ClassifierPrediction:
    label: str
    score: float
    threshold: float

    @property
    def hate(self) -> bool:
        return self.label == "1"


class HsdClassifier(Protocol):
    threshold: float

    def score_texts(self, texts: list[str]) -> list[float]:
        ...

    def predict_texts(self, texts: list[str]) -> list[ClassifierPrediction]:
        ...


class KeywordHsdClassifier:
    """Small deterministic classifier for tests and offline smoke runs."""

    threshold = 0.5
    _terms = {
        "hate",
        "hateful",
        "hostile",
        "attack",
        "attacks",
        "slur",
        "violent",
        "deport",
        "inferior",
        "vermin",
        "kill",
    }
    _word_pattern = re.compile(r"[a-z][a-z'-]+", re.I)

    def score_texts(self, texts: list[str]) -> list[float]:
        scores: list[float] = []
        for text in texts:
            tokens = {
                match.group(0).lower()
                for match in self._word_pattern.finditer(text)
            }
            overlap = len(tokens & self._terms)
            scores.append(min(0.99, 0.15 + 0.3 * overlap))
        return scores

    def predict_texts(self, texts: list[str]) -> list[ClassifierPrediction]:
        return [
            ClassifierPrediction(
                label="1" if score >= self.threshold else "0",
                score=score,
                threshold=self.threshold,
            )
            for score in self.score_texts(texts)
        ]


class TransformersHsdClassifier:
    """Transformers sequence-classification loader for the published checkpoint."""

    def __init__(
        self,
        *,
        model_id: str,
        revision: str | None,
        threshold: float,
        device: str,
        max_length: int,
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except Exception as exc:  # pragma: no cover - depends on optional extra.
            raise RuntimeError(
                "Install glimo-hsd[hf] to use classifier_backend='hf'."
            ) from exc

        requested_device = device.strip().lower()
        if requested_device == "auto":
            selected_device = "cuda" if torch.cuda.is_available() else "cpu"
        elif requested_device in {"cpu", "cuda"}:
            selected_device = requested_device
        else:
            raise ValueError("device must be auto, cpu, or cuda")

        self.model_id = model_id
        self.revision = revision
        self.threshold = float(threshold)
        self.device = selected_device
        self.max_length = int(max_length)
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model_id,
            revision=revision,
        )
        self._model.float()
        self._model.eval()
        self._model.to(self.device)
        self._hate_index = self._resolve_hate_index()

    def _resolve_hate_index(self) -> int:
        id2label = getattr(self._model.config, "id2label", {}) or {}
        normalized = {
            int(index): str(label).lower() for index, label in id2label.items()
        }
        for index, label in normalized.items():
            if label in {"1", "hate", "hateful", "hs", "label_1", "positive"}:
                return index
        return 1 if int(getattr(self._model.config, "num_labels", 2)) > 1 else 0

    def score_texts(self, texts: list[str]) -> list[float]:
        if not texts:
            return []
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
        probs = self._torch.softmax(logits.float(), dim=-1)[:, self._hate_index]
        return [float(value) for value in probs.detach().cpu().tolist()]

    def predict_texts(self, texts: list[str]) -> list[ClassifierPrediction]:
        return [
            ClassifierPrediction(
                label="1" if score >= self.threshold else "0",
                score=score,
                threshold=self.threshold,
            )
            for score in self.score_texts(texts)
        ]


def load_classifier(
    *,
    backend: str,
    model_id: str,
    revision: str | None = None,
    threshold: float = 0.850469,
    device: str = "auto",
    max_length: int = 512,
) -> HsdClassifier | None:
    normalized = backend.strip().lower().replace("_", "-")
    if normalized == "none":
        return None
    if normalized == "keyword":
        return KeywordHsdClassifier()
    if normalized == "hf":
        return TransformersHsdClassifier(
            model_id=model_id,
            revision=revision,
            threshold=threshold,
            device=device,
            max_length=max_length,
        )
    raise ValueError("classifier backend must be hf, keyword, or none")
