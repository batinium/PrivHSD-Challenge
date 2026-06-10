# Dataset Plan

## First Public Dataset

Use the Dynamically Generated Hate Speech Dataset first.

Source:

```text
https://github.com/bvidgen/Dynamically-Generated-Hate-Speech-Dataset
```

Why:

- English text.
- Binary `hate` / `nothate` labels.
- Synthetic content.
- Includes train/dev/test split.
- Includes hate type and target metadata.

Prepare it:

```bash
python -m privhsd.cli prepare-dynahate --download \
  --raw data/public_dev/dynahate_raw.csv \
  --output data/public_dev/dynahate.csv
```

Run the pipeline:

```bash
python -m privhsd.cli anonymize \
  --input data/public_dev/dynahate.csv \
  --output data/outputs/dynahate.privatized.csv \
  --text-col text \
  --id-col id \
  --audit data/outputs/dynahate.audit.json \
  --mode balanced
```

## Secondary Datasets

Use these after the core flow works:

- HateXplain: target labels and rationales.
- Davidson hate speech/offensive language: short noisy social-media text.
- Measuring Hate Speech Corpus: rich target and harm dimensions.
- Jigsaw Toxic Comment: large toxicity benchmark.

## Official Dataset Procedure

When the official development dataset arrives:

1. Inspect the schema.
2. Convert it to `id,text,label,source,split,target,type` where possible.
3. Run `utility`, `balanced`, and `privacy`.
4. Submit outputs to the official evaluator.
5. Record scores in `data/outputs/score_log.md`.
6. Tune only after comparing official scores with local proxy metrics.
