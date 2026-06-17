"""Evaluate HF HSD classifiers across local binary-mappable HSD datasets."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from huggingface_hub import HfApi
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate_hf_hsd_classifiers import (  # noqa: E402
    DEFAULT_MODELS,
    compute_metrics,
    model_rule,
    normalize_id2label,
    read_env_token,
    sigmoid,
    softmax,
    threshold_sweep,
)


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    path: Path
    id_col: str
    text_col: str
    label_col: str
    positive_labels: frozenset[str]
    negative_labels: frozenset[str]
    split_values: frozenset[str] | None = None
    max_rows: int | None = None
    note: str = ""


DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        name="challenge_train_split",
        path=Path("data/train/train_split.csv"),
        id_col="ID",
        text_col="text",
        label_col="hs",
        positive_labels=frozenset({"1"}),
        negative_labels=frozenset({"0"}),
        note="Challenge train split; also used for threshold calibration.",
    ),
    DatasetSpec(
        name="curated_hsd_800",
        path=Path("data/evaluation/curated_hsd_training.csv"),
        id_col="author_id",
        text_col="text",
        label_col="hsd_answer",
        positive_labels=frozenset({"1"}),
        negative_labels=frozenset({"0"}),
        note="Local curated 800-row benchmark.",
    ),
    DatasetSpec(
        name="tweet_eval_unseen_test",
        path=Path("data/external_unseen/tweet_eval_hate_offensive_test.csv"),
        id_col="id",
        text_col="text",
        label_col="label",
        positive_labels=frozenset({"hate"}),
        negative_labels=frozenset({"not_hate", "offensive"}),
        split_values=frozenset({"test"}),
        note="TweetEval hate + offensive test; offensive is strict negative.",
    ),
    DatasetSpec(
        name="dynahate_test",
        path=Path("data/public_dev/archive/normalized/dynahate.csv"),
        id_col="id",
        text_col="text",
        label_col="label",
        positive_labels=frozenset({"hate"}),
        negative_labels=frozenset({"not_hate"}),
        split_values=frozenset({"test"}),
    ),
    DatasetSpec(
        name="hatecheck_test",
        path=Path("data/public_dev/archive/normalized/hatecheck.csv"),
        id_col="id",
        text_col="text",
        label_col="label",
        positive_labels=frozenset({"hate"}),
        negative_labels=frozenset({"not_hate"}),
        split_values=frozenset({"test"}),
    ),
    DatasetSpec(
        name="hatemoji_test",
        path=Path("data/public_dev/archive/normalized/hatemoji.csv"),
        id_col="id",
        text_col="text",
        label_col="label",
        positive_labels=frozenset({"hate"}),
        negative_labels=frozenset({"not_hate"}),
        split_values=frozenset({"test"}),
    ),
    DatasetSpec(
        name="hatexplain_test",
        path=Path("data/public_dev/archive/normalized/hatexplain.csv"),
        id_col="id",
        text_col="text",
        label_col="label",
        positive_labels=frozenset({"hate"}),
        negative_labels=frozenset({"not_hate", "offensive"}),
        split_values=frozenset({"test"}),
        note="HateXplain offensive label is strict negative.",
    ),
    DatasetSpec(
        name="davidson_all_stratified4000",
        path=Path("data/public_dev/archive/normalized/davidson.csv"),
        id_col="id",
        text_col="text",
        label_col="label",
        positive_labels=frozenset({"hate"}),
        negative_labels=frozenset({"not_hate", "offensive"}),
        split_values=frozenset({"all"}),
        max_rows=4000,
        note="Stratified sample; offensive is strict negative.",
    ),
    DatasetSpec(
        name="measuring_hate_speech_stratified4000",
        path=Path("data/public_dev/archive/normalized/measuring_hate_speech.csv"),
        id_col="id",
        text_col="text",
        label_col="label",
        positive_labels=frozenset({"hate"}),
        negative_labels=frozenset({"not_hate"}),
        split_values=frozenset({"train"}),
        max_rows=4000,
        note="Stratified sample; ambiguous rows dropped.",
    ),
)


def read_dataset(spec: DatasetSpec, *, seed: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows: list[dict[str, str]] = []
    skipped_label = 0
    skipped_split = 0
    with spec.path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if spec.split_values is not None and row.get("split", "") not in spec.split_values:
                skipped_split += 1
                continue
            label = row.get(spec.label_col, "").strip().lower()
            if label not in spec.positive_labels and label not in spec.negative_labels:
                skipped_label += 1
                continue
            rows.append(row)

    before_sample = len(rows)
    if spec.max_rows is not None and len(rows) > spec.max_rows:
        rows = stratified_sample(
            rows,
            label_col=spec.label_col,
            positive_labels=spec.positive_labels,
            max_rows=spec.max_rows,
            seed=seed,
        )

    positives = sum(
        1 for row in rows if row.get(spec.label_col, "").strip().lower() in spec.positive_labels
    )
    negatives = len(rows) - positives
    meta = {
        "path": str(spec.path),
        "row_count": len(rows),
        "row_count_before_sample": before_sample,
        "positive_count": positives,
        "negative_count": negatives,
        "skipped_label": skipped_label,
        "skipped_split": skipped_split,
        "max_rows": spec.max_rows,
        "note": spec.note,
    }
    return rows, meta


def stratified_sample(
    rows: list[dict[str, str]],
    *,
    label_col: str,
    positive_labels: frozenset[str],
    max_rows: int,
    seed: int,
) -> list[dict[str, str]]:
    rng = random.Random(seed)
    positives = [
        row for row in rows if row.get(label_col, "").strip().lower() in positive_labels
    ]
    negatives = [
        row for row in rows if row.get(label_col, "").strip().lower() not in positive_labels
    ]
    target_pos = round(max_rows * len(positives) / len(rows))
    target_pos = min(max(target_pos, 1 if positives else 0), len(positives))
    target_neg = min(max_rows - target_pos, len(negatives))
    sampled = rng.sample(positives, target_pos) + rng.sample(negatives, target_neg)
    rng.shuffle(sampled)
    return sampled


def gold_array(rows: list[dict[str, str]], spec: DatasetSpec) -> np.ndarray:
    return np.array(
        [
            row.get(spec.label_col, "").strip().lower() in spec.positive_labels
            for row in rows
        ],
        dtype=bool,
    )


def evaluate_loaded_model(
    *,
    model_id: str,
    rows: list[dict[str, str]],
    spec: DatasetSpec,
    tokenizer: Any,
    model: Any,
    id2label: dict[int, str],
    positive_indexes: list[int],
    activation: str,
    batch_size: int,
    device: torch.device,
) -> np.ndarray:
    scores: list[float] = []
    with torch.inference_mode():
        for offset in range(0, len(rows), batch_size):
            batch_rows = rows[offset : offset + batch_size]
            encoded = tokenizer(
                [row[spec.text_col] for row in batch_rows],
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            ).to(device)
            logits = model(**encoded).logits.detach().cpu()
            probs = sigmoid(logits) if activation == "sigmoid" else softmax(logits)
            batch_scores = probs[:, positive_indexes].max(dim=1).values.numpy()
            scores.extend(float(value) for value in batch_scores)
    return np.array(scores)


def write_summary_md(output_path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# HF HSD Multi-Dataset Evaluation",
        "",
        "Strict binary policy: hate is positive; offensive/toxic/abuse without a hate label is negative or skipped.",
        "",
        "| Model | Dataset | N | Pos | Acc @0.5 | P @0.5 | R @0.5 | F1 @0.5 | F1 @challenge-threshold | Best F1 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in report["models"]:
        for dataset in model["datasets"]:
            fixed = dataset["fixed_threshold_0_5"]
            calibrated = dataset["challenge_calibrated_threshold"]
            best = dataset["threshold_sweep"]["best_f1"]
            lines.append(
                "| {model} | {dataset} | {n} | {pos} | {acc:.4f} | {p:.4f} | {r:.4f} | {f1:.4f} | {cf1:.4f} | {best_f1:.4f} |".format(
                    model=model["model_id"],
                    dataset=dataset["dataset"],
                    n=dataset["row_count"],
                    pos=dataset["positive_count"],
                    acc=fixed["accuracy"],
                    p=fixed["precision"],
                    r=fixed["recall"],
                    f1=fixed["f1"],
                    cf1=calibrated["f1"],
                    best_f1=best["f1"],
                )
            )
    lines.append("")
    lines.extend(
        [
            "Notes:",
            "",
            "- `F1 @challenge-threshold` uses the model's best-F1 threshold from `challenge_train_split` and applies it to every other dataset.",
            "- `Best F1` is an optimistic per-dataset threshold sweep; use it as a ceiling, not as held-out performance.",
            "- Large single-split datasets are stratified samples where noted in `summary.json`.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    token = read_env_token(args.env_file)
    device = torch.device(args.device)
    models = args.models or list(DEFAULT_MODELS)

    datasets: list[tuple[DatasetSpec, list[dict[str, str]], dict[str, Any]]] = []
    for spec in DATASETS:
        if not spec.path.exists():
            continue
        rows, meta = read_dataset(spec, seed=args.seed)
        if rows:
            datasets.append((spec, rows, meta))

    api = HfApi()
    report: dict[str, Any] = {
        "binary_policy": (
            "Only explicit hate labels are positive. Offensive/toxic/abuse labels "
            "are treated as negative when the dataset supports that mapping; "
            "ambiguous-only rows are skipped."
        ),
        "seed": args.seed,
        "device": args.device,
        "batch_size": args.batch_size,
        "dataset_metadata": {spec.name: meta for spec, _rows, meta in datasets},
        "models": [],
    }

    for model_id in models:
        print(f"loading {model_id}", flush=True)
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
            raise ValueError(
                f"{model_id} positive labels {rule.positive_labels} not in {labels}"
            )
        tokenizer = AutoTokenizer.from_pretrained(model_id, token=token)
        model = AutoModelForSequenceClassification.from_pretrained(model_id, token=token)
        model.to(device)
        model.eval()
        info = api.model_info(model_id, token=token)
        license_tags = sorted(tag for tag in info.tags if tag.startswith("license:"))

        model_report: dict[str, Any] = {
            "model_id": model_id,
            "revision": info.sha,
            "license_tags": license_tags,
            "labels": labels,
            "positive_labels": list(rule.positive_labels),
            "activation": rule.activation,
            "rule_note": rule.note,
            "datasets": [],
        }
        challenge_threshold: float | None = None
        for spec, rows, meta in datasets:
            print(f"running {model_id} on {spec.name} ({len(rows)} rows)", flush=True)
            scores = evaluate_loaded_model(
                model_id=model_id,
                rows=rows,
                spec=spec,
                tokenizer=tokenizer,
                model=model,
                id2label=id2label,
                positive_indexes=positive_indexes,
                activation=rule.activation,
                batch_size=args.batch_size,
                device=device,
            )
            gold = gold_array(rows, spec)
            fixed = compute_metrics(gold, scores, threshold=0.5)
            sweep = threshold_sweep(gold, scores)
            if spec.name == "challenge_train_split":
                challenge_threshold = float(sweep["best_f1"]["threshold"])
            threshold = challenge_threshold if challenge_threshold is not None else 0.5
            calibrated = compute_metrics(gold, scores, threshold=threshold)
            model_report["datasets"].append(
                {
                    "dataset": spec.name,
                    "row_count": len(rows),
                    "positive_count": meta["positive_count"],
                    "negative_count": meta["negative_count"],
                    "fixed_threshold_0_5": fixed,
                    "challenge_threshold": round(threshold, 6),
                    "challenge_calibrated_threshold": calibrated,
                    "threshold_sweep": sweep,
                }
            )

        model_report["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        report["models"].append(model_report)
        (args.output_dir / f"{model_id.replace('/', '__')}.datasets.json").write_text(
            json.dumps(model_report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()

    (args.output_dir / "summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_summary_md(args.output_dir / "summary.md", report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
