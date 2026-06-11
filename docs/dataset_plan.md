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

Use `dataset_candidate_takeaways.md` for the broader shortlist and selection
criteria. The short version is: prefer datasets that help evaluate
privacy-preserving transformation, not just train another classifier.

Use these after the core flow works:

- HateXplain: target labels and rationales.
- HateCheck and Hatemoji: compact cue, protected-group, and emoji regression
  checks.
- Davidson hate speech/offensive language: short noisy social-media text.
- Measuring Hate Speech Corpus: rich target and harm dimensions. Use the
  Hugging Face `ucberkeley-dlab/measuring-hate-speech` release as an optional
  evaluation dataset, deduplicated or aggregated by `comment_id`.
- Jigsaw Toxic Comment: large toxicity benchmark.

## Recommended Public Bundle

The repo now includes a shared normalizer for the recommended public datasets:

```bash
python -m privhsd.cli prepare-recommended-datasets \
  --output-dir data/public_dev \
  --raw-dir data/public_dev/raw \
  --merged-output data/public_dev/recommended_merged.csv
```

Prepared outputs:

- `data/public_dev/dynahate.csv`
- `data/public_dev/hatecheck.csv`
- `data/public_dev/hatemoji.csv`
- `data/public_dev/measuring_hate_speech.csv`
- `data/public_dev/hatexplain.csv`
- `data/public_dev/toxic_spans.csv`
- `data/public_dev/convabuse.csv`
- `data/public_dev/davidson.csv`
- `data/public_dev/recommended_merged.csv`

The merged CSV uses this schema:

```text
id,text,label,source,split,target,type,platform,source_id,severity,target_categories,rationale_spans,meta
```

The command keeps raw downloads in ignored `data/public_dev/raw/`. For
Measuring Hate Speech, it prefers a raw CSV exported from the Hugging Face
parquet shard through `npx parquetlens` when available. If `npx` is unavailable,
install the optional parquet reader with:

```bash
python -m pip install '.[data-prep]'
```

## Official Dataset Procedure

When the official development dataset arrives:

1. Inspect the schema.
2. Convert it to `id,text,label,source,split,target,type` where possible.
3. Run `utility`, `balanced`, and `privacy`.
4. Submit outputs to the official evaluator.
5. Record scores in `data/outputs/score_log.md`.
6. Tune only after comparing official scores with local proxy metrics.
