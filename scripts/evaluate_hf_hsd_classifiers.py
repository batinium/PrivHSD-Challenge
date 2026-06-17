"""Evaluate Hugging Face HSD classifiers on a binary hate/not-hate CSV.

This is a research helper. It treats only the challenge's positive label as
hate speech; profanity, toxicity, and offensive language labels are not
positive unless the selected model label is explicitly hate/identity attack.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from huggingface_hub import HfApi
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer


DEFAULT_MODELS: tuple[str, ...] = (
    "unitary/toxic-bert",
    "unitary/unbiased-toxic-roberta",
    "Hate-speech-CNERG/bert-base-uncased-hatexplain",
    "Hate-speech-CNERG/dehatebert-mono-english",
)


@dataclass(frozen=True)
class ModelRule:
    positive_labels: tuple[str, ...]
    activation: str
    mode: str
    note: str


RULES: dict[str, ModelRule] = {
    "unitary/toxic-bert": ModelRule(
        positive_labels=("identity_hate",),
        activation="sigmoid",
        mode="max_positive_label",
        note=(
            "Multilabel toxicity model. Only identity_hate is counted as hate; "
            "toxic/obscene/insult/threat are not counted as hate."
        ),
    ),
    "unitary/unbiased-toxic-roberta": ModelRule(
        positive_labels=("identity_attack",),
        activation="sigmoid",
        mode="max_positive_label",
        note=(
            "Multilabel toxicity/bias model. Only identity_attack is counted as "
            "hate; toxicity/obscene/insult/threat and demographic labels are not."
        ),
    ),
    "Hate-speech-CNERG/bert-base-uncased-hatexplain": ModelRule(
        positive_labels=("hate speech",),
        activation="softmax",
        mode="max_positive_label",
        note="Three-way HateXplain model. offensive and normal are counted as not-hate.",
    ),
    "Hate-speech-CNERG/dehatebert-mono-english": ModelRule(
        positive_labels=("HATE",),
        activation="softmax",
        mode="max_positive_label",
        note="Binary DeHateBERT model. HATE is positive; NON_HATE is negative.",
    ),
}


def read_env_token(path: Path) -> str | None:
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("HF_TOKEN="):
            return stripped.split("=", 1)[1].strip().strip("'\"")
        if stripped.startswith("HF_TOKEN:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    return None


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def truthy_label(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "hate"}


def sigmoid(logits: torch.Tensor) -> torch.Tensor:
    return torch.sigmoid(logits)


def softmax(logits: torch.Tensor) -> torch.Tensor:
    return torch.softmax(logits, dim=-1)


def compute_metrics(gold: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    pred = scores >= threshold
    tp = int(np.sum(pred & gold))
    tn = int(np.sum(~pred & ~gold))
    fp = int(np.sum(pred & ~gold))
    fn = int(np.sum(~pred & gold))
    n = int(len(gold))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    npv = tn / (tn + fn) if tn + fn else 0.0
    return {
        "n": n,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": round((tp + tn) / n, 4) if n else 0.0,
        "balanced_accuracy": round((recall + specificity) / 2, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "npv": round(npv, 4),
        "f1": round(f1, 4),
        "positive_rate_predicted": round(float(np.mean(pred)), 4) if n else 0.0,
    }


def threshold_sweep(gold: np.ndarray, scores: np.ndarray) -> dict[str, Any]:
    candidates = sorted(set(float(x) for x in scores))
    candidates = [0.0, *candidates, 1.0]
    best_f1: tuple[float, dict[str, Any]] | None = None
    best_balanced: tuple[float, dict[str, Any]] | None = None
    for threshold in candidates:
        metrics = compute_metrics(gold, scores, threshold)
        if best_f1 is None or metrics["f1"] > best_f1[1]["f1"]:
            best_f1 = (threshold, metrics)
        if (
            best_balanced is None
            or metrics["balanced_accuracy"] > best_balanced[1]["balanced_accuracy"]
        ):
            best_balanced = (threshold, metrics)
    assert best_f1 is not None
    assert best_balanced is not None
    return {
        "best_f1": {"threshold": round(best_f1[0], 6), **best_f1[1]},
        "best_balanced_accuracy": {
            "threshold": round(best_balanced[0], 6),
            **best_balanced[1],
        },
    }


def normalize_id2label(config: AutoConfig) -> dict[int, str]:
    id2label = getattr(config, "id2label", {}) or {}
    return {int(key): str(value) for key, value in id2label.items()}


def model_rule(model_id: str, labels: list[str]) -> ModelRule:
    if model_id in RULES:
        return RULES[model_id]
    lowered = {label.lower(): label for label in labels}
    for candidate in ("hate", "hate speech", "identity_hate", "identity_attack"):
        if candidate in lowered:
            return ModelRule(
                positive_labels=(lowered[candidate],),
                activation="softmax",
                mode="max_positive_label",
                note="Inferred positive label from model config.",
            )
    raise ValueError(f"no positive-label rule for {model_id}: {labels}")


def run_model(
    *,
    model_id: str,
    rows: list[dict[str, str]],
    text_col: str,
    label_col: str,
    id_col: str,
    batch_size: int,
    device: torch.device,
    token: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start = time.perf_counter()
    config = AutoConfig.from_pretrained(model_id, token=token)
    id2label = normalize_id2label(config)
    labels = [id2label[index] for index in sorted(id2label)]
    rule = model_rule(model_id, labels)
    positive_indexes = [
        index
        for index, label in id2label.items()
        if label.lower() in {item.lower() for item in rule.positive_labels}
    ]
    if not positive_indexes:
        raise ValueError(f"{model_id} positive labels {rule.positive_labels} not in {labels}")

    tokenizer = AutoTokenizer.from_pretrained(model_id, token=token)
    model = AutoModelForSequenceClassification.from_pretrained(model_id, token=token)
    model.to(device)
    model.eval()

    gold = np.array([truthy_label(row[label_col]) for row in rows], dtype=bool)
    scores: list[float] = []
    per_label_scores: list[dict[str, float]] = []

    with torch.inference_mode():
        for offset in range(0, len(rows), batch_size):
            batch_rows = rows[offset : offset + batch_size]
            encoded = tokenizer(
                [row[text_col] for row in batch_rows],
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            ).to(device)
            logits = model(**encoded).logits.detach().cpu()
            probs = sigmoid(logits) if rule.activation == "sigmoid" else softmax(logits)
            batch_scores = probs[:, positive_indexes].max(dim=1).values.numpy()
            scores.extend(float(value) for value in batch_scores)
            for row_probs in probs.numpy():
                per_label_scores.append(
                    {id2label[index]: round(float(row_probs[index]), 6) for index in sorted(id2label)}
                )

    score_array = np.array(scores)
    fixed = compute_metrics(gold, score_array, threshold=0.5)
    sweep = threshold_sweep(gold, score_array)
    elapsed = time.perf_counter() - start

    prediction_rows: list[dict[str, Any]] = []
    for row, score, gold_value, label_scores in zip(rows, score_array, gold, per_label_scores):
        prediction_rows.append(
            {
                id_col: row[id_col],
                "gold": int(gold_value),
                "score": round(float(score), 6),
                "pred_0_5": int(score >= 0.5),
                "pred_best_f1": int(score >= sweep["best_f1"]["threshold"]),
                "label_scores": json.dumps(label_scores, sort_keys=True),
                text_col: row[text_col],
            }
        )

    api = HfApi()
    info = api.model_info(model_id, token=token)
    license_tags = sorted(tag for tag in info.tags if tag.startswith("license:"))
    summary = {
        "model_id": model_id,
        "revision": info.sha,
        "license_tags": license_tags,
        "labels": labels,
        "positive_labels": list(rule.positive_labels),
        "activation": rule.activation,
        "rule_note": rule.note,
        "fixed_threshold_0_5": fixed,
        "threshold_sweep": sweep,
        "elapsed_seconds": round(elapsed, 3),
        "seconds_per_row": round(elapsed / len(rows), 5) if rows else 0.0,
    }
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return summary, prediction_rows


def write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/train/train_split.csv"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--text-col", default="text")
    parser.add_argument("--label-col", default="hs")
    parser.add_argument("--id-col", default="ID")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()

    rows = load_rows(args.input)
    token = read_env_token(args.env_file)
    device = torch.device(args.device)
    models = args.models or list(DEFAULT_MODELS)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for model_id in models:
        safe_name = model_id.replace("/", "__")
        print(f"running {model_id}", flush=True)
        summary, prediction_rows = run_model(
            model_id=model_id,
            rows=rows,
            text_col=args.text_col,
            label_col=args.label_col,
            id_col=args.id_col,
            batch_size=args.batch_size,
            device=device,
            token=token,
        )
        results.append(summary)
        write_predictions(args.output_dir / f"{safe_name}.predictions.csv", prediction_rows)
        (args.output_dir / f"{safe_name}.metrics.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    report = {
        "input": str(args.input),
        "row_count": len(rows),
        "label_counts": {
            "0": sum(1 for row in rows if not truthy_label(row[args.label_col])),
            "1": sum(1 for row in rows if truthy_label(row[args.label_col])),
        },
        "binary_policy": (
            "Only the CSV positive label is hate. Offensive/profane/toxic labels "
            "are treated as not-hate unless the model has an explicit hate or "
            "identity-attack label selected by the model rule."
        ),
        "results": results,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    rows_for_md = []
    for result in results:
        fixed = result["fixed_threshold_0_5"]
        best = result["threshold_sweep"]["best_f1"]
        rows_for_md.append(
            "| {model} | {license} | {fixed_acc:.4f} | {fixed_p:.4f} | {fixed_r:.4f} | {fixed_f1:.4f} | {best_t:.4f} | {best_acc:.4f} | {best_p:.4f} | {best_r:.4f} | {best_f1:.4f} |".format(
                model=result["model_id"],
                license=", ".join(result["license_tags"]),
                fixed_acc=fixed["accuracy"],
                fixed_p=fixed["precision"],
                fixed_r=fixed["recall"],
                fixed_f1=fixed["f1"],
                best_t=best["threshold"],
                best_acc=best["accuracy"],
                best_p=best["precision"],
                best_r=best["recall"],
                best_f1=best["f1"],
            )
        )
    md = "\n".join(
        [
            "# Hugging Face HSD Classifier Evaluation",
            "",
            f"Input: `{args.input}`",
            f"Rows: `{len(rows)}`",
            "",
            "Binary policy: only hate is positive; offensive/profane/toxic without an explicit hate or identity-attack label is negative.",
            "",
            "| Model | License | Acc @0.5 | P @0.5 | R @0.5 | F1 @0.5 | Best F1 threshold | Best Acc | Best P | Best R | Best F1 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            *rows_for_md,
            "",
        ]
    )
    (args.output_dir / "summary.md").write_text(md, encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
