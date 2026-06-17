"""K-fold fine-tune a binary HSD classifier on the official train split.

This script reports out-of-fold metrics, so every reported prediction is made
by a model that did not train on that row. It can then train a final checkpoint
on the full official dataset for deployment.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import StratifiedKFold
from torch.nn import CrossEntropyLoss
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from transformers import get_linear_schedule_with_warmup
from transformers.utils import logging as transformers_logging

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate_hf_hsd_classifiers import (  # noqa: E402
    compute_metrics,
    read_env_token,
    threshold_sweep,
)
from scripts.finetune_hsd_classifier import (  # noqa: E402
    SplitData,
    TextDataset,
    class_weights,
    evaluate,
    make_collate,
    normalize_text_series,
    prepare_training_frame,
    train_one_epoch,
)


def load_official(path: Path) -> tuple[SplitData, list[str], dict[str, Any]]:
    frame = pd.read_csv(path)
    ids = frame["ID"].astype(str).tolist() if "ID" in frame.columns else [str(i) for i in frame.index]
    texts = normalize_text_series(frame["text"]).tolist()
    labels = frame["hs"].astype(int).to_numpy(dtype=np.int64)
    report = {
        "path": str(path),
        "rows": int(len(frame)),
        "positive_count": int(labels.sum()),
        "negative_count": int(len(labels) - labels.sum()),
        "positive_ratio": round(float(np.mean(labels)), 4),
    }
    return SplitData(texts=texts, labels=labels), ids, report


def make_loaders(
    *,
    tokenizer: Any,
    train: SplitData,
    val: SplitData,
    batch_size: int,
    eval_batch_size: int,
    max_length: int,
    device: torch.device,
) -> tuple[DataLoader[dict[str, torch.Tensor]], DataLoader[dict[str, torch.Tensor]]]:
    collate = make_collate(tokenizer, max_length)
    train_loader = DataLoader(
        TextDataset(train.texts, train.labels),
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate,
        pin_memory=device.type == "cuda",
    )
    val_loader = DataLoader(
        TextDataset(val.texts, val.labels),
        batch_size=eval_batch_size,
        shuffle=False,
        collate_fn=collate,
        pin_memory=device.type == "cuda",
    )
    return train_loader, val_loader


def append_data(primary: SplitData, extra: SplitData | None) -> SplitData:
    if extra is None or not extra.texts:
        return primary
    return SplitData(
        texts=primary.texts + extra.texts,
        labels=np.concatenate([primary.labels, extra.labels]).astype(np.int64),
    )


def new_model(
    model_id: str,
    *,
    token: str | None,
    device: torch.device,
    ignore_mismatched_sizes: bool,
) -> torch.nn.Module:
    model = AutoModelForSequenceClassification.from_pretrained(
        model_id,
        num_labels=2,
        token=token,
        ignore_mismatched_sizes=ignore_mismatched_sizes,
    )
    model.config.id2label = {0: "NOT_HATE", 1: "HATE"}
    model.config.label2id = {"NOT_HATE": 0, "HATE": 1}
    model.float()
    model.to(device)
    return model


def train_model(
    *,
    model: torch.nn.Module,
    train_loader: DataLoader[dict[str, torch.Tensor]],
    labels: np.ndarray,
    epochs: int,
    learning_rate: float,
    weight_decay: float,
    warmup_ratio: float,
    device: torch.device,
    amp: str,
    max_grad_norm: float,
    log_every: int,
    fold_label: str,
) -> list[dict[str, Any]]:
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay,
    )
    total_steps = max(len(train_loader) * epochs, 1)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=round(total_steps * warmup_ratio),
        num_training_steps=total_steps,
    )
    loss_fn = CrossEntropyLoss(weight=class_weights(labels, device))
    history: list[dict[str, Any]] = []
    for epoch in range(1, epochs + 1):
        train_loss = train_one_epoch(
            model=model,
            loader=train_loader,
            optimizer=optimizer,
            scheduler=scheduler,
            loss_fn=loss_fn,
            device=device,
            amp=amp,
            max_grad_norm=max_grad_norm,
            epoch=epoch,
            log_every=log_every,
        )
        history.append({"epoch": epoch, "train_loss": round(train_loss, 6)})
        print(f"{fold_label} epoch {epoch} train_loss={train_loss:.4f}", flush=True)
    return history


def write_oof_predictions(
    *,
    path: Path,
    ids: list[str],
    texts: list[str],
    labels: np.ndarray,
    scores: np.ndarray,
    fold_indexes: np.ndarray,
    threshold: float,
) -> None:
    frame = pd.DataFrame(
        {
            "ID": ids,
            "fold": fold_indexes.astype(int),
            "gold": labels.astype(int),
            "score": np.round(scores, 6),
            "pred": (scores >= threshold).astype(int),
            "text": texts,
        }
    )
    frame.to_csv(path, index=False)


def render_markdown(report: dict[str, Any]) -> str:
    fixed = report["oof_fixed_threshold_0_5"]
    best = report["oof_threshold_sweep"]["best_f1"]
    balanced = report["oof_threshold_sweep"]["best_balanced_accuracy"]
    lines = [
        "# Official HSD K-Fold Fine-Tune",
        "",
        f"Base model: `{report['model_id']}`",
        f"Dataset: `{report['dataset']['path']}`",
        f"Rows: {report['dataset']['rows']} ({report['dataset']['positive_count']} hate, {report['dataset']['negative_count']} not-hate)",
        f"Folds: {report['folds']}",
        f"Epochs per fold: {report['epochs']}",
        f"Max length: {report['max_length']}",
        "",
        "## Out-of-Fold Results",
        "",
        "| Threshold | Accuracy | Precision | Recall | F1 | Balanced Acc | TP | FP | TN | FN |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| 0.5 | {fixed['accuracy']:.4f} | {fixed['precision']:.4f} | "
            f"{fixed['recall']:.4f} | {fixed['f1']:.4f} | {fixed['balanced_accuracy']:.4f} | "
            f"{fixed['tp']} | {fixed['fp']} | {fixed['tn']} | {fixed['fn']} |"
        ),
        (
            f"| best F1 ({best['threshold']:.6f}) | {best['accuracy']:.4f} | "
            f"{best['precision']:.4f} | {best['recall']:.4f} | {best['f1']:.4f} | "
            f"{best['balanced_accuracy']:.4f} | {best['tp']} | {best['fp']} | "
            f"{best['tn']} | {best['fn']} |"
        ),
        (
            f"| best balanced acc ({balanced['threshold']:.6f}) | {balanced['accuracy']:.4f} | "
            f"{balanced['precision']:.4f} | {balanced['recall']:.4f} | {balanced['f1']:.4f} | "
            f"{balanced['balanced_accuracy']:.4f} | {balanced['tp']} | {balanced['fp']} | "
            f"{balanced['tn']} | {balanced['fn']} |"
        ),
        "",
        "Every out-of-fold prediction is made by a model that did not train on that row.",
        "",
        "## Per-Fold F1",
        "",
        "| Fold | Val rows | Positives | F1 @0.5 | Best F1 | Best threshold |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for fold in report["fold_reports"]:
        lines.append(
            f"| {fold['fold']} | {fold['val_rows']} | {fold['val_positive_count']} | "
            f"{fold['fixed_threshold_0_5']['f1']:.4f} | "
            f"{fold['threshold_sweep']['best_f1']['f1']:.4f} | "
            f"{fold['threshold_sweep']['best_f1']['threshold']:.6f} |"
        )
    if report.get("final_model_dir"):
        lines.extend(
            [
                "",
                "## Final Model",
                "",
                f"Final checkpoint trained on all official rows: `{report['final_model_dir']}`",
                f"Suggested threshold from OOF best F1: `{best['threshold']:.6f}`",
            ]
        )
    if report.get("extra_training"):
        extra = report["extra_training"]
        lines.extend(
            [
                "",
                "## Extra Training Data",
                "",
                f"Extra CSV: `{extra['path']}`",
                f"Prepared extra rows: {extra['mapped_rows_after_filtering']} "
                f"({extra['positive_count']} hate, {extra['negative_count']} not-hate)",
                f"Dropped exact official-overlap rows: {extra['dropped_test_overlap_rows']}",
                f"Extra max rows: `{extra['max_train_rows']}`",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="Hate-speech-CNERG/dehatebert-mono-english")
    parser.add_argument("--input-csv", type=Path, default=Path("data/train/train_split.csv"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--eval-batch-size", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.0)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--extra-train-csv", type=Path)
    parser.add_argument("--extra-max-train-rows", type=int)
    parser.add_argument("--ignore-mismatched-sizes", action="store_true")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--amp", choices=("bf16", "fp16", "none"), default="bf16")
    parser.add_argument("--log-every", type=int, default=0)
    parser.add_argument("--save-fold-models", action="store_true")
    parser.add_argument("--skip-final-model", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    transformers_logging.set_verbosity_error()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    device = torch.device(args.device)
    token = read_env_token(Path(".env"))
    data, ids, dataset_report = load_official(args.input_csv)
    extra_data = None
    extra_report = None
    if args.extra_train_csv:
        extra_frame, extra_report = prepare_training_frame(
            train_path=args.extra_train_csv,
            test_texts=set(data.texts),
            seed=args.seed,
            max_train_rows=args.extra_max_train_rows,
            drop_test_overlap=True,
        )
        extra_data = SplitData(
            texts=extra_frame["text"].tolist(),
            labels=extra_frame["binary_label"].to_numpy(dtype=np.int64),
        )
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, token=token)

    splitter = StratifiedKFold(
        n_splits=args.folds,
        shuffle=True,
        random_state=args.seed,
    )
    oof_scores = np.zeros(len(data.labels), dtype=np.float64)
    oof_folds = np.zeros(len(data.labels), dtype=np.int64)
    fold_reports: list[dict[str, Any]] = []

    for fold_index, (train_index, val_index) in enumerate(
        splitter.split(data.texts, data.labels),
        start=1,
    ):
        print(f"fold {fold_index}/{args.folds} start", flush=True)
        train = SplitData(
            texts=[data.texts[index] for index in train_index],
            labels=data.labels[train_index],
        )
        train = append_data(train, extra_data)
        val = SplitData(
            texts=[data.texts[index] for index in val_index],
            labels=data.labels[val_index],
        )
        train_loader, val_loader = make_loaders(
            tokenizer=tokenizer,
            train=train,
            val=val,
            batch_size=args.batch_size,
            eval_batch_size=args.eval_batch_size,
            max_length=args.max_length,
            device=device,
        )
        model = new_model(
            args.model_id,
            token=token,
            device=device,
            ignore_mismatched_sizes=args.ignore_mismatched_sizes,
        )
        history = train_model(
            model=model,
            train_loader=train_loader,
            labels=train.labels,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            warmup_ratio=args.warmup_ratio,
            device=device,
            amp=args.amp,
            max_grad_norm=args.max_grad_norm,
            log_every=args.log_every,
            fold_label=f"fold {fold_index}",
        )
        val_gold, val_scores = evaluate(model=model, loader=val_loader, device=device, amp=args.amp)
        oof_scores[val_index] = val_scores
        oof_folds[val_index] = fold_index
        fixed = compute_metrics(val_gold, val_scores, threshold=0.5)
        sweep = threshold_sweep(val_gold, val_scores)
        fold_report = {
            "fold": fold_index,
            "train_rows": len(train.labels),
            "val_rows": len(val.labels),
            "train_positive_count": int(train.labels.sum()),
            "val_positive_count": int(val.labels.sum()),
            "history": history,
            "fixed_threshold_0_5": fixed,
            "threshold_sweep": sweep,
        }
        fold_reports.append(fold_report)
        print(
            f"fold {fold_index} done f1@0.5={fixed['f1']:.4f} "
            f"best_f1={sweep['best_f1']['f1']:.4f} "
            f"best_threshold={sweep['best_f1']['threshold']}",
            flush=True,
        )
        if args.save_fold_models:
            fold_model_dir = args.output_dir / f"fold_{fold_index}_model"
            model.save_pretrained(fold_model_dir)
            tokenizer.save_pretrained(fold_model_dir)
            fold_report["model_dir"] = str(fold_model_dir)
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()

    gold = data.labels.astype(bool)
    oof_fixed = compute_metrics(gold, oof_scores, threshold=0.5)
    oof_sweep = threshold_sweep(gold, oof_scores)

    final_model_dir = None
    if not args.skip_final_model:
        print("final model training start", flush=True)
        full_train = SplitData(texts=data.texts, labels=data.labels)
        full_train = append_data(full_train, extra_data)
        train_loader, _ = make_loaders(
            tokenizer=tokenizer,
            train=full_train,
            val=full_train,
            batch_size=args.batch_size,
            eval_batch_size=args.eval_batch_size,
            max_length=args.max_length,
            device=device,
        )
        final_model = new_model(
            args.model_id,
            token=token,
            device=device,
            ignore_mismatched_sizes=args.ignore_mismatched_sizes,
        )
        train_model(
            model=final_model,
            train_loader=train_loader,
            labels=full_train.labels,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            warmup_ratio=args.warmup_ratio,
            device=device,
            amp=args.amp,
            max_grad_norm=args.max_grad_norm,
            log_every=args.log_every,
            fold_label="final",
        )
        final_model_dir = args.output_dir / "final_model"
        final_model.save_pretrained(final_model_dir)
        tokenizer.save_pretrained(final_model_dir)
        print(f"final model saved {final_model_dir}", flush=True)

    report = {
        "model_id": args.model_id,
        "dataset": dataset_report,
        "folds": args.folds,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "eval_batch_size": args.eval_batch_size,
        "max_length": args.max_length,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "warmup_ratio": args.warmup_ratio,
        "ignore_mismatched_sizes": args.ignore_mismatched_sizes,
        "seed": args.seed,
        "device": args.device,
        "amp": args.amp,
        "fold_reports": fold_reports,
        "oof_fixed_threshold_0_5": oof_fixed,
        "oof_threshold_sweep": oof_sweep,
        "final_model_dir": str(final_model_dir) if final_model_dir else None,
        "extra_training": ({"path": str(args.extra_train_csv)} | extra_report)
        if extra_report is not None
        else None,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    write_oof_predictions(
        path=args.output_dir / "oof_predictions.csv",
        ids=ids,
        texts=data.texts,
        labels=data.labels,
        scores=oof_scores,
        fold_indexes=oof_folds,
        threshold=oof_sweep["best_f1"]["threshold"],
    )
    (args.output_dir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.output_dir / "summary.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
