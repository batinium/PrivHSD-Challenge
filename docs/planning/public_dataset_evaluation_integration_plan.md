# Public Dataset Evaluation Integration Plan

Status: active planning handoff
Owner area: public dataset adapters, deep evaluation, PII span benchmarks,
source-slice utility reports
Last verified: 2026-06-13
Primary code: `privhsd/datasets.py`, `privhsd/rationale_checks.py`,
`privhsd/source_report.py`, future `privhsd/pii_span_benchmark.py`, future
dataset-specific report modules

This file converts the public-dataset research into implementation tasks for
future agents. It focuses on datasets and metrics. Model-probe runtime work
belongs in `docs/planning/utility_probe_integration_plan.md`.

## Decision

Do not replace the current anonymization architecture.

The correct integration path is to add opt-in public evaluation datasets,
gold-span PII benchmarks, and targeted utility-drift reports. The deterministic
`balanced` baseline and `auto` routing should remain the official submission
foundation because they already preserve target, action, negation, modality,
quotation, counterspeech, and rationale cues.

The new work should answer these questions:

1. Does the privacy layer actually find known PII spans when gold spans exist?
2. Does it overmask benign or utility-critical text?
3. Does masking destroy HateXplain rationale evidence?
4. Does utility drift vary by HateCheck functionality or protected identity
   slice?
5. Do optional providers, especially GLiNER variants, improve gold-span privacy
   without increasing HSD cue loss?

## Non-Goals

- Do not add any new public dataset to the official exact-submission path by
  default.
- Do not train or tune the deterministic anonymizer directly on license-unclear
  datasets.
- Do not make model downloads implicit. Public dataset benchmarks remain local
  audit workflows under ignored `data/`.
- Do not paste raw rows, offensive examples, generated sensitive text, or raw
  official data into markdown, manifests, issues, or commits.
- Do not let a toxicity classifier decide that protected target terms should be
  masked.
- Do not use PIIMB or other non-commercial datasets for anything beyond
  license-compatible audit runs.
- Do not make aggressive target-group masking the default. Target terms are HSD
  utility evidence in `balanced` and `auto` unless an explicit privacy mode or
  calibrated policy says otherwise.

## Current Repo State

Already present:

- `privhsd/datasets.py` defines the common public dataset schema:
  `id,text,label,source,split,target,type,platform,source_id,severity,target_categories,rationale_spans,meta`.
- `prepare-recommended-datasets` already normalizes Dynahate, HateCheck,
  Hatemoji, Measuring Hate Speech, HateXplain, Toxic Spans, ConvAbuse, and
  Davidson.
- `prepare-tweet-eval-unseen` already fetches TweetEval hate/offensive test
  splits as external unseen data.
- `source-regression-report` already reports privacy, cue, context, and
  rationale preservation by source/label/split/platform/type.
- `rationale_checks.py` already parses HateXplain token-index style spans,
  Toxic Spans character offsets, and synthetic character spans.
- Optional Presidio, scrubadub, GLiNER, token-policy, semantic, and HSD
  advisory components already sit behind discovery, fusion, reranking, and
  fallback.

Main gaps:

- There is no gold PII span benchmark using public PII datasets.
- There is no label-aware or character-level provider precision/recall report.
- HateXplain rationale reporting is span-retention oriented but does not yet
  expose the exact destructive-interference ratio from privacy masking.
- HateCheck is normalized, but there is no functionality-level drift report.
- Jigsaw identity-slice fairness/utility drift is not integrated.
- ToxiGen, CONAN, CAD, and PIIMB are not integrated or license-gated.
- Optional GLiNER model choice is configurable in some paths, but Gretel
  PII-tuned GLiNER models are not benchmarked as provider replacements.

## Live Metadata Snapshot

These facts were checked through public Hugging Face API/Dataset Viewer calls
on 2026-06-13. Future agents must re-check dataset cards, license files, and
terms before implementation or full-data runs.

| Dataset | Current integration decision | Live metadata notes |
| --- | --- | --- |
| `ai4privacy/pii-masking-openpii-1.5m` | Add as large multilingual PII span benchmark after license review | Hub API reported `license=other`, languages across 30+ language codes, task categories `token-classification` and `text-generation`, splits `train` and `validation`. First-row fields include `source_text`, `masked_text`, `privacy_mask`, `language`, `region`, `script`, `mbert_tokens`, `mbert_token_classes`, `source_dataset`. |
| `ai4privacy/pii-masking-300k` | Add as smaller PII span benchmark and tokenizer-alignment reference after license review | Hub API reported `license=other`, languages `en/fr/de/it/es/nl`, size `100K<n<1M`. First-row fields include `source_text`, `target_text`, `privacy_mask`, `span_labels`, `mbert_text_tokens`, `mbert_bio_labels`, `id`, `language`, `set`. |
| `nvidia/Nemotron-PII` | Add as preferred permissive PII/PHI gold-span benchmark | Hub API reported `license=cc-by-4.0`, English, task `token-classification`, splits `train` and `test`. First-row fields include `uid`, `domain`, `document_type`, `document_description`, `document_format`, `locale`, `text`, `spans`, `text_tagged`. |
| `gretelai/gretel-pii-masking-en-v1` | Add as enterprise/domain PII benchmark and GLiNER-provider benchmark source | Hub API reported `license=apache-2.0`, English, splits `train/validation/test`. First-row fields include `uid`, `domain`, `document_type`, `document_description`, `entities`, `text`. |
| `piimb/pii-masking-benchmark` | Audit-only reference benchmark unless use is compatible with non-commercial license | Hub API reported `license=cc-by-nc-4.0`, configs `sentences` and `full_text`, test split only. First-row fields include `uid`, `task_name`, `source_dataset`, `source_uid`, `parent_id`, `sentence_index`, `text`, `entities`, `language`. |
| `Paul/hatecheck` | Already normalized; add functionality report | Hub API reported `license=cc-by-4.0`, English, test split. First-row fields include `functionality`, `case_id`, `test_case`, `label_gold`, `target_ident`, `direction`, `focus_words`, `focus_lemma`. |
| `Hate-speech-CNERG/hatexplain` | Already normalized; upgrade rationale interference metrics | Hub API reported `license=cc-by-4.0`, English, size `10K<n<100K`. Repository contains `hatexplain.py`; Dataset Viewer first-rows may not expose simple default rows. Existing repo code downloads from the upstream HateXplain GitHub data files. |
| `ucberkeley-dlab/measuring-hate-speech` | Already normalized; use as continuous target/identity slice dataset | Hub API reported `license=cc-by-4.0`, English. First-row fields include `hate_speech_score`, construct scores, many `target_*` booleans, and annotator demographic fields. |
| `google/jigsaw_unintended_bias` | Add as identity-slice utility drift benchmark | Hub API reported `license=cc0-1.0`, English, task `text-classification`, size `1M<n<10M`. Dataset Viewer split API returned `501`, so implementation should prefer `datasets.load_dataset` or parquet/Hub APIs after checking current availability. |
| `toxigen/toxigen-data` | Later implicit-hate audit only after license review | Hub API returned no license in card data. Dataset Viewer preview worked for configs `annotated` and `train`; `annotated` fields include `text`, `target_group`, `framing`, `stereotyping`, `intent`, `toxicity_ai`, `toxicity_human`. |
| `aps/dynahate` | Already covered through existing Dynahate downloader, not a new priority | Hub API returned no license in card data for the HF mirror. Current repo uses upstream CSV URL. |
| `tdavidson/hate_speech_offensive` | Already normalized from upstream; do not use as a hard utility gate | Hub API reported license `unknown`; current repo uses the upstream GitHub data. Treat as bias/legacy comparison evidence only. |

## Priority Summary

| Priority | Work | Why |
| --- | --- | --- |
| P0 | Add gold PII span benchmark for Nemotron and Gretel | Highest missing evidence for masking precision/recall; permissive licenses currently reported. |
| P0 | Add label-agnostic and label-aware character metrics | Needed for fair cross-dataset PII evaluation without tokenizer artifacts. |
| P1 | Add HateXplain destructive-interference metric | Directly measures when privacy masking deletes HSD rationale evidence. |
| P1 | Add HateCheck functionality drift report | Converts generic utility drift into debuggable functional categories. |
| P2 | Add Jigsaw identity-slice utility drift | Detects subgroup-specific false-positive/false-negative drift. |
| P2 | Benchmark Gretel PII-tuned GLiNER models as optional providers | Possible provider improvement, but must prove net gain before default use. |
| P3 | Add OpenPII and Ai4Privacy 300k after license review | Valuable multilingual/token-alignment coverage, but Hub API reports `license=other`. |
| P4 | Add ToxiGen, CONAN, CAD later | Useful robustness data, but licensing, schema, and contextual evaluation cost require separate review. |

## Shared Data Contracts

### Existing HSD Common Schema

Keep the current HSD common schema for hate/toxicity/counterspeech datasets:

```text
id,text,label,source,split,target,type,platform,source_id,severity,target_categories,rationale_spans,meta
```

Rules:

- Do not change this schema without updating `docs/reference/data_contract.md`
  and all affected tests.
- Use `meta` for source-specific fields that are not needed as common grouping
  columns.
- Store source labels and raw score fields in `meta`, not as new top-level
  columns unless multiple reports need the field.
- Keep normalized public data under ignored `data/public_dev/` or
  `data/public_eval/`.

### New PII Gold-Span Schema

Add a separate normalized schema for PII span benchmarks. Do not force PII
datasets into the HSD label schema.

Recommended field order:

```text
id,text,source,split,language,locale,region,script,domain,document_type,source_id,entity_spans,meta
```

`entity_spans` should be compact JSON:

```json
[
  {
    "start": 12,
    "end": 24,
    "label": "EMAIL",
    "source_label": "email",
    "source": "privacy_mask"
  }
]
```

Rules:

- `start` is inclusive and `end` is exclusive.
- Offsets are character offsets into `text`.
- `label` is the project-normalized entity type.
- `source_label` preserves the dataset-native label.
- `source` records the source field or parser path.
- Do not include raw span text in durable JSON reports. The normalized CSV under
  ignored `data/` may include raw `text` because it is local evaluation data.
- If a source only provides token labels, convert to character spans when
  possible and keep token metadata in `meta`.

## Label Mapping Policy

Add a central mapping for public PII labels. Recommended location:

```text
privhsd/pii_span_benchmark.py
```

or, if agents create a package:

```text
privhsd/evaluation/pii_spans.py
```

Use the existing top-level module style unless a broader evaluation package is
created intentionally.

Project-normalized entity labels should align with current detector types:

| Project label | Example source labels |
| --- | --- |
| `PERSON` | `PERSON`, `NAME`, `first_name`, `last_name`, `NAME_STUDENT`, `given_name`, `family_name` |
| `USER` | `USERNAME`, `user_name`, `online handle`, `account_name` |
| `EMAIL` | `EMAIL`, `email`, `email_address` |
| `PHONE` | `PHONE`, `phone_number`, `telephone` |
| `URL` | `URL`, `url`, `URL_PERSONAL`, `website` |
| `IP_ADDRESS` | `IP`, `ip_address`, `ipv4`, `ipv6` |
| `IDENTIFIER` | `ID`, `ID_NUM`, `ssn`, `passport`, `driver_license`, `student id`, `government id`, `case number` |
| `LOCATION` | `address`, `street_address`, `city`, `neighborhood`, `location`, `postcode`, `zip_code` |
| `ORGANIZATION` | `company`, `company_name`, `organization`, `school`, `university`, `workplace` |
| `DATE` | `date`, `date_of_birth`, `dob`, `birth_date` |
| `AGE` | `age` |
| `SENSITIVE_ATTRIBUTE` | `religious_belief`, `race_ethnicity`, `political_opinion`, `sexual_orientation`, `medical_condition` |

Do not blindly mask `SENSITIVE_ATTRIBUTE` in `balanced` mode. Many such labels
overlap with target-group evidence needed for HSD. The benchmark should report
them separately as `hsd_overlap_entity=true` and leave masking-policy decisions
to fusion/reranking.

## Phase 0: Dataset Adapter Foundation

Target code:

```text
privhsd/datasets.py
tests/test_prepare_public_eval_datasets.py
```

Recommended CLI:

```text
prepare-public-eval-datasets
```

Do not overload `prepare-recommended-datasets`. The current recommended bundle
is already used in runbooks and token-policy training. Keep the new deep
evaluation datasets separate.

Suggested paths:

```text
data/public_eval/
data/public_eval/raw/
data/public_eval/pii_gold/
data/public_eval/hsd_slice/
```

Suggested dataset choices:

```text
nemotron_pii
gretel_pii
openpii_1_5m
ai4privacy_300k
piimb_pii
jigsaw_unintended_bias
toxigen
```

Implementation checklist:

1. Add `PUBLIC_EVAL_DATASETS` choices separate from
   `DEFAULT_RECOMMENDED_DATASETS`.
2. Add `recommended_public_eval_paths(output_dir, raw_dir)` or similarly named
   helper.
3. Add normalizers for PII gold-span datasets that write the PII schema.
4. Add normalizers for Jigsaw/ToxiGen that write the existing HSD common schema.
5. Add `--max-rows` and `--page-size` for all large HF datasets.
6. Add `--no-download` behavior matching the existing public-dev downloader.
7. Write a manifest that includes dataset IDs, configs, splits, source URLs,
   license status as observed, row counts, schema, and skipped datasets.
8. Keep raw downloaded data and normalized outputs under ignored `data/`.

Acceptance tests:

- Fake rows for each adapter normalize into the expected field order.
- Missing optional dataset dependencies produce a clean error message.
- `--dataset nemotron_pii --max-rows 2` style tests can run without network by
  using local fixture rows.
- The current `prepare-recommended-datasets` tests continue to pass unchanged.

Focused command:

```bash
python -m pytest tests/test_prepare_dynahate.py tests/test_prepare_public_eval_datasets.py -q
```

## Phase 1: PII Dataset Normalizers

### Nemotron-PII

Dataset ID:

```text
nvidia/Nemotron-PII
```

Live fields observed:

```text
uid,domain,document_type,document_description,document_format,locale,text,spans,text_tagged
```

Implementation details:

- Use `text` as normalized `text`.
- Use `uid` as `id` and `source_id`.
- Copy `domain`, `document_type`, and `locale`.
- Parse `spans` with `json.loads` first, then `ast.literal_eval` as fallback.
- Preserve `text_tagged`, `document_description`, and `document_format` in
  `meta`.
- Normalize labels through the central PII label map.
- If `spans` contains stringified dictionaries, reject invalid entries with a
  counter rather than failing the whole dataset.

Report dimensions:

- `domain`;
- `document_type`;
- `locale`;
- normalized label;
- `hsd_overlap_entity`.

### Gretel PII Masking

Dataset ID:

```text
gretelai/gretel-pii-masking-en-v1
```

Live fields observed:

```text
uid,domain,document_type,document_description,entities,text
```

Implementation details:

- Use `text` as normalized `text`.
- Use `uid` as `id` and `source_id`.
- Copy `domain` and `document_type`.
- Parse `entities` with `json.loads`, then `ast.literal_eval` as fallback.
- Preserve `document_description` in `meta`.
- Gretel is the best first dataset for document-type stratification because it
  exposes enterprise-like `domain` and `document_type`.

Provider benchmark note:

- Use this dataset to evaluate `--gliner-model` alternatives, including Gretel
  PII-tuned GLiNER models, but do not promote any model to default until the
  provider benchmark proves improvement over deterministic plus Presidio.

### OpenPII 1.5M

Dataset ID:

```text
ai4privacy/pii-masking-openpii-1.5m
```

Live fields observed:

```text
source_text,masked_text,privacy_mask,split,uid,language,region,script,mbert_tokens,mbert_token_classes,source_dataset
```

Implementation details:

- Use `source_text` as normalized `text`.
- Use `uid` as `id` and `source_id`.
- Copy `language`, `region`, `script`, and `split`.
- Parse `privacy_mask` as the gold source.
- Preserve `masked_text`, `mbert_tokens`, `mbert_token_classes`, and
  `source_dataset` in `meta`.
- Because Hub metadata reported `license=other`, add a manifest warning:
  `license_requires_manual_review`.
- Start with validation split and a bounded sample. Do not run the full dataset
  by default.

Report dimensions:

- `language`;
- `region`;
- `script`;
- `source_dataset`;
- normalized label.

### Ai4Privacy 300k

Dataset ID:

```text
ai4privacy/pii-masking-300k
```

Live fields observed:

```text
source_text,target_text,privacy_mask,span_labels,mbert_text_tokens,mbert_bio_labels,id,language,set
```

Implementation details:

- Use `source_text` as normalized `text`.
- Use `id` as normalized `id` and `source_id`.
- Copy `language` and `set`.
- Prefer `privacy_mask` for gold character spans.
- Keep `span_labels`, `mbert_text_tokens`, and `mbert_bio_labels` in `meta`.
- Use mBERT BIO fields only as a secondary validation path; the benchmark
  should operate on character spans.
- Because Hub metadata reported `license=other`, add the same manual license
  warning as OpenPII.

### PIIMB

Dataset ID:

```text
piimb/pii-masking-benchmark
```

Live fields observed:

```text
uid,task_name,source_dataset,source_uid,parent_id,sentence_index,text,entities,language
```

Implementation decision:

- Add only as audit-only adapter.
- Do not include it in default public-eval runs.
- Emit a clear manifest warning:
  `license=cc-by-nc-4.0; audit-only unless project use is compatible`.

Useful implementation details:

- PIIMB already unifies several PII sources and has sentence/full-text configs.
- It is valuable as a metric sanity check because it uses character-level,
  label-agnostic masking concepts.
- Implement our own metrics rather than taking PIIMB code as a dependency
  unless license review allows it.

## Phase 2: Gold PII Span Benchmark

Target code:

```text
privhsd/pii_span_benchmark.py
tests/test_pii_span_benchmark.py
```

Recommended CLI:

```text
benchmark-pii-spans
```

Suggested inputs:

- normalized PII gold CSV from Phase 0/1;
- provider selection: deterministic, Presidio, scrubadub, GLiNER, or fused
  provider set;
- optional local GLiNER model path or approved model ID;
- max rows and sampling strategy;
- output JSON under `data/outputs/`.

Suggested CLI shape after implementation:

```bash
python -m privhsd.cli benchmark-pii-spans \
  --input data/public_eval/pii_gold/nemotron_pii.csv \
  --text-col text \
  --span-col entity_spans \
  --id-col id \
  --provider deterministic \
  --provider presidio \
  --provider gliner \
  --output data/outputs/pii_span_benchmark.nemotron.json
```

Benchmark target:

- Evaluate predicted privacy spans against gold spans.
- Do not use the generated masked text as the primary signal.
- Providers should emit spans. Final anonymized text is not needed for span
  precision/recall.

Prediction sources:

- deterministic: `detect_spans(text, include_context=True, include_targets=False)`;
- Presidio: `load_span_provider("presidio")`;
- scrubadub: `load_span_provider("scrubadub")`;
- GLiNER: `load_span_provider("gliner", gliner_model=...)`;
- fused: existing provider fusion if the implementation wants to benchmark the
  exact `auto` span stack.

Required metrics:

| Metric | Definition | Use |
| --- | --- | --- |
| `exact_match_precision/recall/f1` | Predicted span exactly matches gold start/end and, for label-aware mode, normalized label | Strict quality check |
| `char_precision/recall/f1/f2` | Character-overlap precision/recall over unioned spans | Main robust metric |
| `span_iou_mean` | Mean best-match IoU for gold spans | Partial-boundary quality |
| `gold_span_recall_by_label` | Recall per normalized gold label | Prevent easy labels from hiding hard failures |
| `predicted_span_precision_by_label` | Precision per normalized predicted label | Overmasking diagnosis |
| `macro_f1_by_label` | Mean label F1 with equal label weight | Required aggregate |
| `micro_f1` | Global character/span aggregate | Secondary aggregate only |
| `row_any_missed_gold_rate` | Fraction of rows with at least one missed gold span | User-facing risk |
| `row_any_false_positive_rate` | Fraction of rows with at least one false positive span | Overmasking risk |
| `overmask_char_ratio` | Predicted characters outside gold divided by text characters | Utility pressure |
| `hsd_overlap_entity_recall` | Recall for sensitive attributes that can also be HSD target evidence | Policy-risk view |

Use F2 for privacy-heavy summaries because missed identifiers are worse than
small boundary overreach. Use F1 and overmask ratios to prevent broad masking
from looking good.

Character metric sketch:

```python
gold_chars = set(range(gold.start, gold.end))
pred_chars = set(range(pred.start, pred.end))
tp = len(gold_chars & pred_chars)
fp = len(pred_chars - gold_chars)
fn = len(gold_chars - pred_chars)
precision = tp / (tp + fp) if tp + fp else 0.0
recall = tp / (tp + fn) if tp + fn else 0.0
```

Important details:

- Merge overlapping spans before character accounting to avoid double counts.
- Compute both label-agnostic and label-aware variants.
- Use macro averages by label/source/language/domain as the first reported
  aggregate.
- Keep micro averages, but never use micro alone because emails/URLs can
  dominate results.
- Report unknown/unmapped labels explicitly.
- Store row IDs for top missed/overmasked rows, but never raw row text.

Output JSON shape:

```json
{
  "artifact_type": "pii_span_benchmark",
  "input": "data/public_eval/pii_gold/nemotron_pii.csv",
  "providers": ["deterministic", "presidio"],
  "row_count": 1000,
  "license_warnings": [],
  "overall": {
    "char_precision": 0.0,
    "char_recall": 0.0,
    "char_f1": 0.0,
    "char_f2": 0.0,
    "macro_f1_by_label": 0.0
  },
  "by_source": [],
  "by_label": [],
  "by_language": [],
  "by_domain": [],
  "top_missed_gold_rows": [
    {"row_id": "abc", "label": "PERSON", "gold_span_count": 2}
  ],
  "top_false_positive_rows": [
    {"row_id": "def", "predicted_label": "LOCATION", "false_positive_count": 3}
  ],
  "notes": [
    "Raw text is intentionally omitted.",
    "Label-aware metrics use project-normalized labels."
  ]
}
```

Tests:

- exact match true positive;
- boundary-overlap partial credit;
- false-positive span outside gold;
- label-aware mismatch;
- overlapping predicted spans are merged;
- empty gold and empty prediction rows;
- report omits raw text.

Focused command:

```bash
python -m pytest tests/test_pii_span_benchmark.py tests/test_span_providers.py -q
```

## Phase 3: Provider Replacement Benchmark

Target code:

```text
privhsd/pii_span_benchmark.py
privhsd/span_providers/gliner.py
privhsd/auto/config.py
tests/test_span_providers.py
tests/test_auto_pipeline.py
```

Decision:

- Do not replace deterministic or Presidio paths yet.
- Benchmark Gretel PII-tuned GLiNER models as optional GLiNER alternatives.
- Promote a new GLiNER model only if it improves gold-span recall without
  materially increasing HSD cue loss or overmasking.

Implementation checklist:

1. Keep `DEFAULT_GLINER_MODEL` stable until benchmark evidence supports a
   change.
2. Ensure all CLI paths that load GLiNER accept `--gliner-model` or config
   equivalent.
3. Add provider benchmark metadata:
   - provider name;
   - model ID/path;
   - model local/download status;
   - thresholds;
   - accepted/rejected span counts;
   - runtime.
4. Run the same PII gold benchmark across:
   - deterministic;
   - deterministic plus Presidio;
   - deterministic plus current GLiNER;
   - deterministic plus Gretel GLiNER candidate;
   - fused auto provider stack.
5. Run `source-regression-report` on the same candidate outputs for HSD
   utility checks.

Promotion criteria:

- `char_recall` improves by at least 2 percentage points on hard labels such as
  `PERSON`, `LOCATION`, `IDENTIFIER`, and `SENSITIVE_ATTRIBUTE`.
- `row_any_false_positive_rate` does not increase by more than an agreed
  threshold.
- `target_cue_retention` remains at or above current baseline on HSD datasets.
- HateXplain destructive interference does not increase.
- Missing dependency/artifact behavior remains structured fallback.

Do not use a provider's already-masked text. Use provider spans only and route
them through existing fusion/candidate scoring.

## Phase 4: HateXplain Destructive-Interference Metric

Target code:

```text
privhsd/rationale_checks.py
privhsd/source_report.py
tests/test_rationale_checks.py
tests/test_source_report.py
```

Current limitation:

- `rationale_row_report()` reports preserved span counts and placeholder
  overlap counts.
- It does not yet report the percentage of rationale characters destroyed by
  placeholder-changing privacy edits.
- The normalized HateXplain writer emits token ranges like `1-3`; before
  relying on end-to-end normalized HateXplain reports, verify and, if needed,
  fix parser support for semicolon-delimited range strings. Existing parser
  support is stronger for JSON/list forms than for compact range strings.

Required new metrics:

```text
rationale_changed_char_ratio
rationale_placeholder_char_ratio
rationale_changed_span_ratio
rationale_placeholder_span_ratio
masked_rationale_char_count
changed_rationale_char_count
total_rationale_char_count
```

Definitions:

- `rationale_changed_char_ratio`: characters inside gold rationale spans that
  overlap any changed range divided by total rationale characters.
- `rationale_placeholder_char_ratio`: characters inside gold rationale spans
  that overlap changed ranges whose replacement contains a placeholder divided
  by total rationale characters.
- `rationale_changed_span_ratio`: rationale spans touched by any change divided
  by rationale span count.
- `rationale_placeholder_span_ratio`: rationale spans touched by placeholder
  replacement divided by rationale span count.

Implementation checklist:

1. Add helper `char_overlap_size(left_start, left_end, right_start, right_end)`.
2. Add helper to compute unioned changed-character overlap per rationale span.
3. Keep existing preserved-span metrics for backward compatibility.
4. Extend `aggregate_rationale_reports()` with weighted character totals and
   mean ratios.
5. Update `source-regression-report` notes to mention destructive-interference
   metrics.
6. Add grouping by `target_categories` when the caller passes that group column.

Output should still omit raw text. Row-level risky examples should include only:

```json
{
  "row_id": "hatexplain:123",
  "source": "hatexplain",
  "label": "hate",
  "rationale_placeholder_char_ratio": 0.75,
  "rationale_span_count": 2
}
```

Acceptance tests:

- a placeholder edit fully covering a rationale span yields
  `rationale_placeholder_char_ratio=1.0`;
- an edit outside rationale spans yields `0.0`;
- a partial boundary overlap yields fractional ratio;
- compact range strings such as `1-3;7` parse as token ranges, not as negative
  numbers;
- aggregate totals are weighted by characters, not by rows only;
- reports omit raw text.

Focused command:

```bash
python -m pytest tests/test_rationale_checks.py tests/test_source_report.py -q
```

## Phase 5: HateCheck Functionality Report

Target code:

```text
privhsd/hatecheck_report.py
privhsd/cli.py
tests/test_hatecheck_report.py
```

Current state:

- `normalize_hatecheck()` maps `functionality` to the common `type` field.
- `target_ident` is stored in `target` and `target_categories`.
- `focus_words` is stored in `meta`.
- Generic source-regression can already group by `type`, but a dedicated report
  should expose HateCheck-specific diagnostics.

Recommended CLI:

```text
hatecheck-functionality-report
```

Inputs:

- original normalized HateCheck CSV;
- protected/anonymized CSV;
- `id`, original text, protected text, label, type/functionality columns;
- optional utility-probe JSON if agents later want model-score deltas.

Required metrics by `functionality`:

- row count;
- label counts;
- target identity counts;
- target cue retention;
- utility cue retention;
- negation/modality cue retention from `focused_cue_report`;
- placeholder density;
- focus-word changed ratio;
- focus-word placeholder ratio;
- HSD model score delta if supplied by `evaluate-hf-utility`;
- risky row IDs with no raw text.

Focus-word overlap:

- Parse `meta.focus_words` from the normalized dataset.
- If parsing from `meta` is awkward, keep a source-specific helper that reads
  the raw `focus_words` field before normalization.
- Treat focus words as functional evidence, not privacy spans.
- Report when focus words are changed or replaced by placeholders.

Output JSON shape:

```json
{
  "artifact_type": "hatecheck_functionality_report",
  "row_count": 3728,
  "overall": {
    "target_cue_retention_mean": 1.0,
    "focus_word_placeholder_ratio": 0.0
  },
  "functionalities": [
    {
      "functionality": "example_functionality",
      "row_count": 100,
      "label_counts": {"hate": 50, "not_hate": 50},
      "focus_word_changed_ratio": 0.0,
      "focus_word_placeholder_ratio": 0.0,
      "target_cue_retention_mean": 1.0
    }
  ],
  "top_risky_functionalities": [],
  "notes": ["Raw text is intentionally omitted."]
}
```

Acceptance tests:

- report groups by functionality;
- focus-word placeholder ratio detects an edit over the focus word;
- negation/counterspeech rows are not collapsed into a single global score;
- raw text is omitted.

## Phase 6: Jigsaw Identity-Slice Utility Drift

Target code:

```text
privhsd/datasets.py
privhsd/identity_slice_report.py
privhsd/cli.py
tests/test_identity_slice_report.py
```

Dataset ID:

```text
google/jigsaw_unintended_bias
```

Decision:

- Add as opt-in deep evaluation.
- Do not include in `prepare-recommended-datasets`.
- Do not train default masking policy from it.
- Treat as fairness/identity-slice utility evidence.

Implementation checklist:

1. Add normalizer that writes existing HSD common schema.
2. Use `comment_text` or current text field as `text`.
3. Map fractional toxicity target to a label only for rough grouping:
   - `toxic` if target >= configured threshold, default `0.5`;
   - `not_hate` or `not_toxic` otherwise.
4. Preserve original fractional scores and subtypes in `meta`.
5. Extract boolean identity attributes into `target_categories` and `meta`.
6. Add `--max-rows`, `--sample-strategy`, and `--identity` filters.
7. Use optional `datasets` dependency or Hub parquet access. Dataset Viewer may
   not expose this dataset through simple split endpoints.

Likely identity fields:

- gender and sexuality attributes;
- religion attributes;
- race/ethnicity attributes;
- disability/mental-health attributes;
- toxicity subtype fields such as `identity_attack`, `insult`, `threat`,
  depending on current schema.

Recommended report:

```text
identity-slice-utility-report
```

Required metrics by identity attribute:

- row count;
- positive-label rate;
- average mask density;
- target cue retention;
- utility cue retention;
- optional utility model score mean before/after;
- score delta by original label;
- false-positive shift on benign identity mentions if utility model scores are
  supplied;
- false-negative shift on toxic/identity-attack rows if utility model scores
  are supplied.

If model probabilities are available, compute:

- AUC before and after by identity attribute when labels are valid;
- AUC delta;
- thresholded false-positive rate before/after for non-toxic rows mentioning
  the identity;
- thresholded false-negative rate before/after for toxic rows mentioning the
  identity;
- calibration caveat in report notes.

Report warnings:

- labels are subjective aggregates;
- raw comments are offensive;
- scores are probe evidence, not moderation decisions;
- identity terms may be HSD target evidence and should not be blindly masked.

Acceptance tests:

- fake rows with two identity attributes produce separate slice summaries;
- rows with multiple identities count in both relevant slices;
- optional model score columns are handled when present and skipped when absent;
- no raw text is written.

## Phase 7: Measuring Hate Speech Enhancements

Current state:

- `prepare_measuring_hate_speech()` already exists.
- The normalizer aggregates by `comment_id`.
- It stores construct scores and target information in `meta`.

Recommended additions:

1. Keep dataset ingestion as-is unless bugs are found.
2. Add a report mode that reads `hate_speech_score` and construct scores from
   `meta` and stratifies utility loss by:
   - `hate_speech_score` bucket;
   - `target_*` identity group;
   - construct scores such as dehumanization, violence, genocide, insult, and
     humiliation.
3. Connect continuous model runtime work to
   `docs/planning/utility_probe_integration_plan.md`.

Do not duplicate the continuous model implementation in this plan.

## Phase 8: ToxiGen Implicit-Hate Audit

Dataset ID:

```text
toxigen/toxigen-data
```

Decision:

- Add later, after license review.
- Use for implicit-hate false-negative drift and target-group stress.
- Do not treat as PII span data.

Live fields observed:

- `annotated` config: `text`, `target_group`, `framing`, `stereotyping`,
  `intent`, `toxicity_ai`, `toxicity_human`, `actual_method`.
- `train` config: `prompt`, `generation`, `generation_method`, `group`,
  `prompt_label`, `roberta_prediction`.

Implementation notes:

- Normalize `annotated` first.
- Use `target_group` as `target` and `target_categories`.
- Use toxicity fields for grouping in `meta`.
- Evaluate false-negative drift post-masking with optional utility probes.
- Keep as audit-only if license remains unclear.

Acceptance tests:

- annotated rows normalize correctly;
- target group metadata is preserved;
- report can group by framing/stereotyping without raw text.

## Phase 9: CONAN And CAD

Decision:

- Do not implement in the first pass.
- Create a separate legal/schema review before adding either dataset.

CONAN notes:

- Counter-narrative pairs are useful for checking whether masking collapses the
  distance between hate speech and counterspeech.
- Research-use or redistribution constraints may apply depending on source.
- If integrated, store only local ignored normalized outputs and document
  restrictions in the manifest.

CAD notes:

- Context-aware Reddit threads are useful for testing cross-turn entity
  consistency.
- Integration requires context-window support, not just row-level text.
- Add only after current row-level reports are stable.

Future CAD/CONAN report ideas:

- embedding distance before/after masking;
- paired hate/counterspeech separation;
- context entity consistency;
- coreference-sensitive target cue retention.

## Phase 10: CLI Registration

Add new CLI commands only after their modules have tests.

Suggested commands:

```text
prepare-public-eval-datasets
benchmark-pii-spans
hatecheck-functionality-report
identity-slice-utility-report
```

CLI rules:

- Commands must write outputs under caller-provided paths, usually
  `data/outputs/`.
- Commands must support bounded samples for large datasets.
- Commands must have clean skip/error messages for missing optional
  dependencies.
- Commands must not print raw text in normal JSON reports.
- Commands must not be required by official exact-submission workflows.

Update `docs/reference/cli.md` when commands are actually implemented.

## Phase 11: Documentation Updates After Implementation

When an agent implements a phase, update only the authoritative docs needed for
that phase:

- `docs/reference/evaluation.md` for stable metric/report definitions;
- `docs/reference/providers_and_models.md` if provider lifecycle or GLiNER
  model selection changes;
- `docs/runbooks/quickstart.md` only if the command becomes a routine workflow;
- `docs/runbooks/official_submission.md` only if an audit command should be
  mentioned as optional pre-submission evidence;
- `docs/planning/current_status.md` only with current measured results, not
  plans.

Do not move this planning file into reference until implementation stabilizes.

## Implementation Order

Recommended sequence:

1. Add PII gold-span schema helpers and synthetic adapter tests.
2. Add Nemotron and Gretel normalizers.
3. Add `benchmark-pii-spans` with deterministic provider only.
4. Add Presidio/scrubadub/GLiNER provider benchmark support.
5. Add HateXplain destructive-interference metrics and parser range fix.
6. Add HateCheck functionality report.
7. Add Jigsaw adapter and identity-slice report.
8. Add OpenPII/Ai4Privacy adapters after license review.
9. Add ToxiGen after license review.
10. Revisit CONAN/CAD as separate contextual-evaluation projects.

This order gives useful evidence early while keeping official submission paths
stable.

## Validation Matrix

Every phase:

```bash
python -m pytest -q
```

PII benchmark phases:

```bash
python -m pytest tests/test_pii_span_benchmark.py tests/test_span_providers.py -q
```

Dataset adapter phases:

```bash
python -m pytest tests/test_prepare_dynahate.py tests/test_prepare_public_eval_datasets.py -q
```

Rationale/source-report phase:

```bash
python -m pytest tests/test_rationale_checks.py tests/test_source_report.py -q
```

HateCheck/Jigsaw report phases:

```bash
python -m pytest tests/test_hatecheck_report.py tests/test_identity_slice_report.py -q
```

If CLI changes:

```bash
python -m pytest tests/test_public_api.py tests/test_submission.py -q
```

If auto/provider behavior changes:

```bash
python -m pytest tests/test_auto_pipeline.py tests/test_span_providers.py tests/test_submission.py -q
```

## Acceptance Criteria

The dataset integration work is ready when:

- current exact-format submission commands still work without new optional
  dependencies;
- public-eval data preparation is opt-in and writes under ignored `data/`;
- each public dataset manifest records source, split/config, observed license
  status, row count, schema, and caveats;
- PII span reports include character precision/recall/F1/F2, IoU, macro label
  metrics, and source/language/domain slices;
- PII span reports contain row IDs and aggregate counts only, not raw text;
- HateXplain reports include destructive-interference ratios;
- HateCheck reports group by functionality and focus-word preservation;
- Jigsaw reports group by identity attribute and separate benign identity
  mentions from toxic/identity-attack rows when labels permit;
- optional providers remain behind fusion/reranking and never directly rewrite
  final text;
- all custom datasets with unclear or restrictive licenses are audit-only until
  reviewed.

## Handoff Notes For Agents

- Start with Nemotron and Gretel. They currently have the cleanest license
  posture among the PII datasets checked.
- Treat Ai4Privacy OpenPII and 300k as important but license-gated because the
  Hub API currently reports `license=other`.
- Treat PIIMB as a metric reference and non-commercial audit dataset, not a
  default dependency.
- Use macro averages whenever labels or identity groups matter. Micro averages
  can hide failures on rare but high-risk PII labels.
- Use row IDs in reports. Do not include raw text snippets.
- Keep model-scoring changes in the utility-probe plan. This plan should stay
  focused on datasets, spans, and slice reports.
