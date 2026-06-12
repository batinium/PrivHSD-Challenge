# Real Data Playbook

Use this when the official CSV arrives. The goal is to avoid improvising under
time pressure: profile first, run the conservative baseline, validate exact
format, then try alternates only when a report shows a specific weakness.

## 0. Keep Raw Data Isolated

Put official files under ignored `data/official/` or `data/public_dev/`.
Do not paste raw rows into docs, chat, commits, screenshots, or issue comments.
All reports should identify rows by ID only.

## 1. Profile The Incoming CSV

```bash
python -m privhsd.cli profile-dataset \
  --input data/official/OFFICIAL.csv \
  --output data/outputs/official.profile.json
```

Read the profile before choosing commands:

- confirm the likely text column;
- confirm the ID column, if any;
- identify label/source/split columns;
- check whether any `author`, `user`, `account`, or `handle` column has
  repeated values;
- check blank text, duplicate text, missing labels, and odd columns.

If the profiler guesses wrong, rerun with explicit columns:

```bash
python -m privhsd.cli profile-dataset \
  --input data/official/OFFICIAL.csv \
  --text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --label-col LABEL_COLUMN \
  --output data/outputs/official.profile.json
```

## 2. Make The First Baseline

Always create `balanced` first. It is deterministic, local, target-preserving,
and has the strongest audit story.

```bash
python -m privhsd.cli create-submission \
  --input data/official/OFFICIAL.csv \
  --output data/outputs/official.balanced.csv \
  --text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --replace-text \
  --mode balanced \
  --manifest data/outputs/official.balanced.manifest.json
```

Then validate shape:

```bash
python -m privhsd.cli validate-submission \
  --source data/official/OFFICIAL.csv \
  --submission data/outputs/official.balanced.csv \
  --text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --output data/outputs/official.balanced.validation.json
```

Do not tune before this exact-format baseline exists.

After validation, run the source-aware regression report so privacy and utility
tradeoffs are visible by source/label/split/platform/type slices instead of one
global average:

```bash
python -m privhsd.cli source-regression-report \
  --original data/official/OFFICIAL.csv \
  --protected data/outputs/official.balanced.csv \
  --original-text-col TEXT_COLUMN \
  --protected-text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --group-col SOURCE_COLUMN \
  --group-col LABEL_COLUMN \
  --group-col SPLIT_COLUMN \
  --output data/outputs/official.balanced.source_regression.json
```

Use only columns that exist in the official file. If rationale/span metadata is
present, keep it in the CSV so the report can measure source-aware rationale
preservation by row ID without printing raw text.

## 3. Run Local Evidence

If labels are available:

```bash
python -m privhsd.cli benchmark-utility \
  --input data/outputs/official.balanced.csv \
  --text-col TEXT_COLUMN \
  --privatized-col TEXT_COLUMN \
  --label-col LABEL_COLUMN \
  --id-col ID_COLUMN \
  --output data/outputs/official.balanced.utility.json
```

For cue retention, create an audit-style output with an added
`privatized_text` column or compare original and exact-format output with a
small helper file. The key metric is whether target/action/negation/modality
cues survive.

If an author/user column has repeated values:

```bash
python -m privhsd.cli evaluate-author-risk \
  --input data/outputs/official.with_privatized_text.csv \
  --text-col TEXT_COLUMN \
  --privatized-col privatized_text \
  --author-col AUTHOR_COLUMN \
  --id-col ID_COLUMN \
  --label-col LABEL_COLUMN \
  --output data/outputs/official.author_risk.json
```

If there is no repeated author/user column, record that author-risk evaluation
is not locally measurable on that file.

## 4. Submit In This Order

1. `balanced` exact-format output.
2. If official score says privacy is weak, try `balanced --style-scrub`.
3. If residual names/locations/dates are weak, try reranking with
   `--presidio-augment`.
4. If utility drops, do not add more masking. Inspect source/label/target slices
   and keep the least meaning-changing output.
5. Use token-policy ensemble predictions as advisory evidence or reranker
   candidates only after the exact-format baseline is already scored.

Do not submit `privacy` or `--generalize-targets` as the first choice. Those can
erase vulnerable-group evidence and make the legal story worse.

## 5. Decision Rules

Prefer the candidate that:

- passes exact-format validation;
- reduces direct identifiers and author-style signals;
- preserves target/action/negation/modality cues;
- does not collapse offensive, toxic, ambiguous, or counterspeech rows into
  presumed hate;
- has a manifest and reproducible command;
- can be explained as preprocessing plus evidence for human review, not an
  automated takedown decision.

## 6. What To Ignore Under Time Pressure

Do not start with:

- training a new transformer before the deterministic baseline is validated;
- using `source_id` as an author label;
- raw Presidio replacement;
- LLM rewriting as the direct output;
- global binary label remapping across heterogeneous sources;
- broad target generalization.

Those are research or alternate paths. The official-data path is baseline,
validate, score, diagnose, then narrowly tune.
