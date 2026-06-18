"""Export a fine-tuned DeHateBERT checkpoint into a Hub-ready folder."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

DEFAULT_REPO_ID = "batinium/glimo-dehatebert-hsd"
DEFAULT_THRESHOLD = 0.850469


def build_model_card(
    *,
    repo_id: str,
    base_model: str | None,
    threshold: float,
) -> str:
    base_line = f"- Base model: `{base_model}`\n" if base_model else ""
    return f"""---
license: apache-2.0
tags:
- text-classification
- hate-speech-detection
- transformers
- pytorch
- privhsd
- glimo
pipeline_tag: text-classification
---

# {repo_id}

Fine-tuned DeHateBERT-style classifier developed during the PrivHSD Challenge
for harmful or hate speech detection in the Glimo privacy-preserving pipeline.

{base_line}- Default decision threshold: `{threshold}`
- Intended use: research, moderation assistance, admin triage, and pipeline
  scoring.
- Not intended use: fully automated enforcement without human review.

## Data Statement

Do not publish private challenge samples, raw admin uploads, or generated
outputs containing private source text in this repository.

## Limitations

The classifier can produce false positives and false negatives, especially for
dialectal language, reclaimed terms, counterspeech, quoted speech, contextual
ambiguity, and emerging coded language. Model outputs and restatements require
human/admin review before consequential action.

## Usage

```python
from transformers import pipeline

clf = pipeline("text-classification", model="{repo_id}")
print(clf("The comment uses abusive language toward a protected group."))
```
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--base-model")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--metrics-json", type=Path)
    parser.add_argument("--training-args-json", type=Path)
    return parser.parse_args()


def copy_optional(source: Path | None, destination: Path) -> None:
    if source is None:
        return
    if source.exists():
        shutil.copy2(source, destination)


def main() -> int:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except Exception as exc:
        raise SystemExit("Install transformers and torch before exporting.") from exc

    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    model = AutoModelForSequenceClassification.from_pretrained(args.checkpoint)
    model.config.id2label = {0: "non_hate", 1: "hate"}
    model.config.label2id = {"non_hate": 0, "hate": 1}
    model.config.problem_type = "single_label_classification"
    tokenizer.save_pretrained(args.out)
    model.save_pretrained(args.out, safe_serialization=True)

    (args.out / "label_mapping.json").write_text(
        json.dumps(
            {
                "id2label": model.config.id2label,
                "label2id": model.config.label2id,
                "default_threshold": args.threshold,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    metrics = {"default_threshold": args.threshold}
    if args.metrics_json and args.metrics_json.exists():
        metrics.update(json.loads(args.metrics_json.read_text(encoding="utf-8")))
    (args.out / "eval_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    copy_optional(args.training_args_json, args.out / "training_args.json")
    (args.out / "README.md").write_text(
        build_model_card(
            repo_id=args.repo_id,
            base_model=args.base_model,
            threshold=args.threshold,
        ),
        encoding="utf-8",
    )
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
