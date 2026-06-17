"""Fine-tune a binary hate-speech classifier on a merged local CSV.

The label policy is strict: only ``hate`` is positive. Offensive, toxic, and
non-abuse labels are negative; ambiguous and abuse-only labels are skipped.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split
from torch.nn import CrossEntropyLoss
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate_hf_hsd_classifiers import (  # noqa: E402
    compute_metrics,
    read_env_token,
    threshold_sweep,
)


LABEL_MAP = {
    "hate": 1,
    "not_hate": 0,
    "offensive": 0,
    "toxic": 0,
    "not_abuse": 0,
    "not_abusive": 0,
}


@dataclass(frozen=True)
class SplitData:
    texts: list[str]
    labels: np.ndarray


class TextDataset(Dataset[dict[str, Any]]):
    def __init__(self, texts: list[str], labels: np.ndarray) -> None:
        self.texts = texts
        self.labels = labels.astype(np.int64)

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return {"text": self.texts[index], "label": int(self.labels[index])}


def positive_ratio(labels: np.ndarray) -> float:
    return float(np.mean(labels)) if len(labels) else 0.0


def normalize_text_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def prepare_training_frame(
    *,
    train_path: Path,
    test_texts: set[str],
    seed: int,
    max_train_rows: int | None,
    drop_test_overlap: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = pd.read_csv(train_path, low_memory=False)
    raw["text"] = normalize_text_series(raw["text"])
    raw["label_normalized"] = raw["label"].fillna("").astype(str).str.strip().str.lower()

    source_counts_raw = raw["source"].fillna("unknown").value_counts().to_dict()
    label_counts_raw = raw["label_normalized"].value_counts().to_dict()

    mapped = raw[raw["label_normalized"].isin(LABEL_MAP)].copy()
    mapped["binary_label"] = mapped["label_normalized"].map(LABEL_MAP).astype(int)
    mapped = mapped[mapped["text"] != ""].copy()

    overlap_rows = mapped["text"].isin(test_texts)
    overlap_count = int(overlap_rows.sum())
    if drop_test_overlap:
        mapped = mapped[~overlap_rows].copy()

    conflicting_texts = (
        mapped.groupby("text")["binary_label"].nunique().loc[lambda item: item > 1].index
    )
    conflict_count = int(mapped["text"].isin(conflicting_texts).sum())
    if len(conflicting_texts):
        mapped = mapped[~mapped["text"].isin(conflicting_texts)].copy()

    duplicate_count = int(mapped.duplicated(subset=["text", "binary_label"]).sum())
    mapped = mapped.drop_duplicates(subset=["text", "binary_label"]).copy()

    if max_train_rows is not None and len(mapped) > max_train_rows:
        positives = mapped[mapped["binary_label"] == 1]
        negatives = mapped[mapped["binary_label"] == 0]
        pos_target = round(max_train_rows * len(positives) / len(mapped))
        pos_target = min(max(pos_target, 1), len(positives))
        neg_target = min(max_train_rows - pos_target, len(negatives))
        mapped = pd.concat(
            [
                positives.sample(n=pos_target, random_state=seed),
                negatives.sample(n=neg_target, random_state=seed),
            ],
            ignore_index=True,
        ).sample(frac=1.0, random_state=seed)

    mapped = mapped.reset_index(drop=True)
    labels = mapped["binary_label"].to_numpy(dtype=np.int64)
    report = {
        "raw_rows": int(len(raw)),
        "raw_label_counts": label_counts_raw,
        "raw_source_counts": source_counts_raw,
        "mapped_rows_after_filtering": int(len(mapped)),
        "dropped_test_overlap_rows": overlap_count if drop_test_overlap else 0,
        "test_overlap_rows_seen": overlap_count,
        "dropped_conflicting_duplicate_rows": conflict_count,
        "dropped_same_label_duplicate_rows": duplicate_count,
        "max_train_rows": max_train_rows,
        "positive_count": int(labels.sum()),
        "negative_count": int(len(labels) - labels.sum()),
        "positive_ratio": round(positive_ratio(labels), 4),
        "source_counts_after_filtering": mapped["source"].fillna("unknown")
        .value_counts()
        .to_dict(),
        "label_counts_after_filtering": mapped["label_normalized"].value_counts().to_dict(),
    }
    return mapped, report


def load_challenge(path: Path) -> tuple[SplitData, dict[str, Any]]:
    frame = pd.read_csv(path)
    texts = normalize_text_series(frame["text"]).tolist()
    labels = frame["hs"].astype(int).to_numpy(dtype=np.int64)
    report = {
        "rows": int(len(frame)),
        "positive_count": int(labels.sum()),
        "negative_count": int(len(labels) - labels.sum()),
        "positive_ratio": round(positive_ratio(labels), 4),
    }
    return SplitData(texts=texts, labels=labels), report


def make_collate(tokenizer: Any, max_length: int):
    def collate(batch: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
        encoded = tokenizer(
            [item["text"] for item in batch],
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        encoded["labels"] = torch.tensor([item["label"] for item in batch], dtype=torch.long)
        return encoded

    return collate


def class_weights(labels: np.ndarray, device: torch.device) -> torch.Tensor:
    counts = np.bincount(labels.astype(np.int64), minlength=2).astype(np.float64)
    weights = counts.sum() / (2.0 * np.maximum(counts, 1.0))
    return torch.tensor(weights, dtype=torch.float32, device=device)


def autocast_context(device: torch.device, amp: str):
    if device.type != "cuda" or amp == "none":
        return nullcontext()
    dtype = torch.bfloat16 if amp == "bf16" else torch.float16
    return torch.autocast(device_type="cuda", dtype=dtype)


def evaluate(
    *,
    model: torch.nn.Module,
    loader: DataLoader[dict[str, torch.Tensor]],
    device: torch.device,
    amp: str,
) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    labels: list[int] = []
    scores: list[float] = []
    with torch.inference_mode():
        for batch in loader:
            batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
            gold = batch.pop("labels")
            with autocast_context(device, amp):
                logits = model(**batch).logits
            probs = torch.softmax(logits.float(), dim=-1)[:, 1]
            labels.extend(int(value) for value in gold.detach().cpu().numpy())
            scores.extend(float(value) for value in probs.detach().cpu().numpy())
    return np.array(labels, dtype=bool), np.array(scores, dtype=np.float64)


def train_one_epoch(
    *,
    model: torch.nn.Module,
    loader: DataLoader[dict[str, torch.Tensor]],
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    loss_fn: CrossEntropyLoss,
    device: torch.device,
    amp: str,
    max_grad_norm: float,
    epoch: int,
    log_every: int,
) -> float:
    model.train()
    total_loss = 0.0
    started = time.perf_counter()
    for step, batch in enumerate(loader, start=1):
        batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
        labels = batch.pop("labels")
        optimizer.zero_grad(set_to_none=True)
        with autocast_context(device, amp):
            logits = model(**batch).logits
            loss = loss_fn(logits.float(), labels)
        loss.backward()
        if max_grad_norm > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        optimizer.step()
        scheduler.step()
        total_loss += float(loss.detach().cpu())

        if log_every and step % log_every == 0:
            elapsed = max(time.perf_counter() - started, 1e-9)
            print(
                f"epoch {epoch} step {step}/{len(loader)} "
                f"loss {total_loss / step:.4f} "
                f"({step / elapsed:.2f} steps/s)",
                flush=True,
            )
    return total_loss / max(len(loader), 1)


def write_predictions(
    *,
    path: Path,
    texts: list[str],
    labels: np.ndarray,
    scores: np.ndarray,
    threshold: float,
) -> None:
    frame = pd.DataFrame(
        {
            "gold": labels.astype(int),
            "score": np.round(scores, 6),
            "pred": (scores >= threshold).astype(int),
            "text": texts,
        }
    )
    frame.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="Hate-speech-CNERG/dehatebert-mono-english")
    parser.add_argument("--train-csv", type=Path, required=True)
    parser.add_argument("--test-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--eval-batch-size", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.06)
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--max-train-rows", type=int)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--amp", choices=("bf16", "fp16", "none"), default="bf16")
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--keep-test-overlap", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device(args.device)
    token = read_env_token(Path(".env"))
    challenge, challenge_report = load_challenge(args.test_csv)
    train_frame, prep_report = prepare_training_frame(
        train_path=args.train_csv,
        test_texts=set(challenge.texts),
        seed=args.seed,
        max_train_rows=args.max_train_rows,
        drop_test_overlap=not args.keep_test_overlap,
    )

    train_rows, val_rows = train_test_split(
        train_frame,
        test_size=args.val_fraction,
        random_state=args.seed,
        stratify=train_frame["binary_label"],
    )
    train_split = SplitData(
        texts=train_rows["text"].tolist(),
        labels=train_rows["binary_label"].to_numpy(dtype=np.int64),
    )
    val_split = SplitData(
        texts=val_rows["text"].tolist(),
        labels=val_rows["binary_label"].to_numpy(dtype=np.int64),
    )

    print(
        "prepared",
        {
            "train": len(train_split.texts),
            "val": len(val_split.texts),
            "test": len(challenge.texts),
            "train_pos": int(train_split.labels.sum()),
            "val_pos": int(val_split.labels.sum()),
            "test_pos": int(challenge.labels.sum()),
        },
        flush=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_id, token=token)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_id,
        num_labels=2,
        token=token,
    )
    model.config.id2label = {0: "NOT_HATE", 1: "HATE"}
    model.config.label2id = {"NOT_HATE": 0, "HATE": 1}
    model.float()
    model.to(device)

    collate = make_collate(tokenizer, args.max_length)
    train_loader = DataLoader(
        TextDataset(train_split.texts, train_split.labels),
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate,
        pin_memory=device.type == "cuda",
    )
    val_loader = DataLoader(
        TextDataset(val_split.texts, val_split.labels),
        batch_size=args.eval_batch_size,
        shuffle=False,
        collate_fn=collate,
        pin_memory=device.type == "cuda",
    )
    test_loader = DataLoader(
        TextDataset(challenge.texts, challenge.labels),
        batch_size=args.eval_batch_size,
        shuffle=False,
        collate_fn=collate,
        pin_memory=device.type == "cuda",
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=math.ceil(total_steps * args.warmup_ratio),
        num_training_steps=total_steps,
    )
    loss_fn = CrossEntropyLoss(weight=class_weights(train_split.labels, device))

    started = time.perf_counter()
    history: list[dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        train_loss = train_one_epoch(
            model=model,
            loader=train_loader,
            optimizer=optimizer,
            scheduler=scheduler,
            loss_fn=loss_fn,
            device=device,
            amp=args.amp,
            max_grad_norm=args.max_grad_norm,
            epoch=epoch,
            log_every=args.log_every,
        )
        val_gold, val_scores = evaluate(model=model, loader=val_loader, device=device, amp=args.amp)
        val_sweep = threshold_sweep(val_gold, val_scores)
        val_fixed = compute_metrics(val_gold, val_scores, threshold=0.5)
        history.append(
            {
                "epoch": epoch,
                "train_loss": round(train_loss, 6),
                "val_fixed_threshold_0_5": val_fixed,
                "val_threshold_sweep": val_sweep,
            }
        )
        print(
            f"epoch {epoch} done train_loss={train_loss:.4f} "
            f"val_f1@0.5={val_fixed['f1']:.4f} "
            f"val_best_f1={val_sweep['best_f1']['f1']:.4f} "
            f"val_best_threshold={val_sweep['best_f1']['threshold']}",
            flush=True,
        )

    val_gold, val_scores = evaluate(model=model, loader=val_loader, device=device, amp=args.amp)
    val_sweep = threshold_sweep(val_gold, val_scores)
    threshold = float(val_sweep["best_f1"]["threshold"])
    test_gold, test_scores = evaluate(model=model, loader=test_loader, device=device, amp=args.amp)

    test_fixed = compute_metrics(test_gold, test_scores, threshold=0.5)
    test_val_threshold = compute_metrics(test_gold, test_scores, threshold=threshold)
    test_sweep = threshold_sweep(test_gold, test_scores)

    model_dir = args.output_dir / "model"
    model.save_pretrained(model_dir)
    tokenizer.save_pretrained(model_dir)
    write_predictions(
        path=args.output_dir / "challenge_predictions.csv",
        texts=challenge.texts,
        labels=challenge.labels,
        scores=test_scores,
        threshold=threshold,
    )

    report = {
        "model_id": args.model_id,
        "model_dir": str(model_dir),
        "train_csv": str(args.train_csv),
        "test_csv": str(args.test_csv),
        "label_policy": {
            "positive": ["hate"],
            "negative": ["not_hate", "offensive", "toxic", "not_abuse", "not_abusive"],
            "skipped": ["ambiguous", "abuse", "ambiguous_abuse"],
        },
        "args": vars(args) | {"train_csv": str(args.train_csv), "test_csv": str(args.test_csv), "output_dir": str(args.output_dir)},
        "preparation": prep_report,
        "challenge": challenge_report,
        "splits": {
            "train_rows": len(train_split.texts),
            "val_rows": len(val_split.texts),
            "test_rows": len(challenge.texts),
            "train_positive_count": int(train_split.labels.sum()),
            "val_positive_count": int(val_split.labels.sum()),
            "test_positive_count": int(challenge.labels.sum()),
        },
        "history": history,
        "selected_threshold_from_val": threshold,
        "test_fixed_threshold_0_5": test_fixed,
        "test_val_threshold": test_val_threshold,
        "test_threshold_sweep": test_sweep,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.output_dir / "summary.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


def render_markdown(report: dict[str, Any]) -> str:
    fixed = report["test_fixed_threshold_0_5"]
    val_threshold = report["test_val_threshold"]
    best = report["test_threshold_sweep"]["best_f1"]
    lines = [
        "# Fine-Tuned HSD Classifier",
        "",
        f"Base model: `{report['model_id']}`",
        f"Model directory: `{report['model_dir']}`",
        "",
        "Strict label policy: `hate` is positive; `offensive`, `toxic`, and non-abuse labels are negative.",
        "",
        "## Data",
        "",
        f"- Prepared training rows: {report['preparation']['mapped_rows_after_filtering']}",
        f"- Train / val / test: {report['splits']['train_rows']} / {report['splits']['val_rows']} / {report['splits']['test_rows']}",
        f"- Dropped exact test-overlap rows: {report['preparation']['dropped_test_overlap_rows']}",
        f"- Dropped conflicting duplicate rows: {report['preparation']['dropped_conflicting_duplicate_rows']}",
        f"- Dropped same-label duplicate rows: {report['preparation']['dropped_same_label_duplicate_rows']}",
        "",
        "## Challenge Split Results",
        "",
        "| Threshold | Accuracy | Precision | Recall | F1 | Balanced Acc | TP | FP | TN | FN |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| 0.5 | {fixed['accuracy']:.4f} | {fixed['precision']:.4f} | "
            f"{fixed['recall']:.4f} | {fixed['f1']:.4f} | "
            f"{fixed['balanced_accuracy']:.4f} | {fixed['tp']} | {fixed['fp']} | "
            f"{fixed['tn']} | {fixed['fn']} |"
        ),
        (
            f"| val best F1 ({report['selected_threshold_from_val']:.6f}) | "
            f"{val_threshold['accuracy']:.4f} | {val_threshold['precision']:.4f} | "
            f"{val_threshold['recall']:.4f} | {val_threshold['f1']:.4f} | "
            f"{val_threshold['balanced_accuracy']:.4f} | {val_threshold['tp']} | "
            f"{val_threshold['fp']} | {val_threshold['tn']} | {val_threshold['fn']} |"
        ),
        (
            f"| challenge best F1 ({best['threshold']:.6f}) | "
            f"{best['accuracy']:.4f} | {best['precision']:.4f} | {best['recall']:.4f} | "
            f"{best['f1']:.4f} | {best['balanced_accuracy']:.4f} | {best['tp']} | "
            f"{best['fp']} | {best['tn']} | {best['fn']} |"
        ),
        "",
        "The challenge-best threshold is an optimistic diagnostic because it uses test labels.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
