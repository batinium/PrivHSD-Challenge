# Utility Probe Integration Plan

Status: active planning handoff
Owner area: deep evaluation, optional HSD advisory models, model-probe runtime
Last verified: 2026-06-13
Primary code: `privhsd/hf_utility.py`, `privhsd/models/`,
`privhsd/auto/`, `privhsd/rationale_checks.py`

This document converts the utility-probe research into implementation tasks for
future agents. The goal is to improve how ContextSafe-HSD measures semantic
utility after anonymization without replacing the deterministic privatization
pipeline.

## Decision

Keep the current anonymization architecture. Add a richer, opt-in utility-probe
layer and upgrade the optional HSD advisory path from a single classifier to a
small ensemble.

The existing core is already aligned with the research:

- deterministic and auto modes preserve target, hostility, action, negation,
  modality, quotation, counterspeech, and rationale cues;
- `source-regression-report` already measures rationale/span preservation when
  source datasets provide spans;
- Hugging Face classifiers are already treated as relative probes, not
  moderation decisions;
- optional providers/models already load once per run, batch inference where
  possible, and fall back to deterministic masking.

Do not replace this with a model-only rewrite/classification pipeline.

## Non-Goals

- Do not let an external classifier decide that protected target terms should
  be masked.
- Do not use toxicity or offensiveness models as final hate-speech truth.
- Do not make model downloads implicit in official submission paths.
- Do not write raw official or sensitive text into durable markdown, manifests,
  or audit reports.
- Do not execute remote model code blindly in official mode. Custom loaders must
  be audited local code or explicitly disabled.

## Current Repo State

Already present:

- `privhsd/hf_utility.py` has an approved model registry and a pipeline-based
  evaluator for original-vs-privatized score drift.
- `privhsd/auto/config.py` defaults the auto HSD advisory model to
  `facebook/roberta-hate-speech-dynabench-r4-target`.
- `privhsd/models/hsd_advisory_runtime.py` loads one
  `transformers.pipeline("text-classification")` model and compares original
  and candidate scores.
- `privhsd/rationale_checks.py` parses HateXplain token ranges, Toxic Spans
  character offsets, and synthetic character spans.
- `privhsd/datasets.py` already prepares Dynahate, HateCheck, Hatemoji,
  Measuring Hate Speech, HateXplain, Toxic Spans, ConvAbuse, Davidson, and
  TweetEval external unseen data.

Main gaps:

- `hf_utility.py` treats every compatible classifier as one positive scalar.
- The auto advisory runtime supports one model, not a calibrated ensemble.
- Cardiff multiclass target drift is not in the registry.
- Unbiased toxicity, Measuring Hate Speech continuous scores, MUDES spans, and
  HateXplain generated rationales need custom runtime support.
- Reports do not yet distinguish binary hate drift, target-class drift,
  continuous severity drift, identity-bias/toxicity drift, and span IoU.

## Probe Taxonomy

Use these categories in code and reports. Add a `probe_kind` field to registry
metadata instead of inferring behavior only from model IDs.

| Probe kind | Purpose | Output shape | Gate final candidates? |
| --- | --- | --- | --- |
| `binary_hate` | Broad hate/not-hate utility stability | positive score, decision, drop | Yes, but only with calibrated thresholds |
| `target_multiclass` | Check whether target-category probability mass moves after anonymization | full label distribution, top label, not-hate mass | Audit first; gate only after validation |
| `toxicity_bias` | Detect identity/profanity-bias artifacts and general toxicity drift | toxicity and identity-related scores | Audit only |
| `continuous_hate` | Measure small semantic severity changes | continuous scalar score | Audit first; later soft penalty |
| `token_span` | Verify toxic/rationale spans survive token/character perturbation | spans, IoU, span retention | Strong audit signal; gate only after local validation |
| `rationale_head` | Verify explanation spans survive anonymization | rationale spans plus label logits | Strong audit signal; custom-loader only |

## Model Recommendations

Model-card facts below were checked from public Hugging Face model cards on
2026-06-13. Re-check cards, licenses, and loading behavior before changing
defaults.

| Model | Integration decision | Notes |
| --- | --- | --- |
| `cardiffnlp/twitter-roberta-base-hate-latest` | Keep and promote as broad binary probe | Model card says it is binary hate-speech classification fine-tuned from `cardiffnlp/twitter-roberta-base-2022-154m` using 13 English hate-speech datasets. It reports overall accuracy `0.8766`, macro-F1 `0.7531`, weighted-F1 `0.8745`. Use as generalized social-media utility baseline. Source: https://huggingface.co/cardiffnlp/twitter-roberta-base-hate-latest |
| `facebook/roberta-hate-speech-dynabench-r4-target` | Keep as adversarial stress probe | Model card ties it to Learning from the Worst R4 Target. Use as a robustness check, especially against perturbed syntax. Do not rely on it alone. Source: https://huggingface.co/facebook/roberta-hate-speech-dynabench-r4-target |
| `cardiffnlp/twitter-roberta-base-hate-multiclass-latest` | Add to registry and evaluator | Classes are `sexism`, `racism`, `disability`, `sexual_orientation`, `religion`, `other`, `not_hate`. Model card reports accuracy `0.9419`, macro-F1 `0.5752`, weighted-F1 `0.9390`. The macro-F1 warning is important: use for diagnostic target-mass drift, not final truth. Source: https://huggingface.co/cardiffnlp/twitter-roberta-base-hate-multiclass-latest |
| `unitary/unbiased-toxic-roberta` | Add later as `toxicity_bias`, preferably through Detoxify | Model card warns Hugging Face model outputs differ from the Detoxify library and recommends Detoxify for up-to-date models. The card describes the 2019 Jigsaw unintended-bias setup and identity labels. Use only to audit identity/profanity bias artifacts, not as HSD utility truth. Source: https://huggingface.co/unitary/unbiased-toxic-roberta |
| `unitary/multilingual-toxic-xlm-roberta` | Optional multilingual toxicity audit | Detoxify card says the multilingual model should be tested only on English, French, Spanish, Italian, Portuguese, Turkish, or Russian. Use only when row language is known or configured. Source: https://huggingface.co/unitary/unbiased-toxic-roberta |
| `ucberkeley-dlab/hate-measure-roberta-large` | Add as custom `continuous_hate` runtime | Model card says it predicts a continuous hate speech score as described by Kennedy et al. 2020 and uses `ucberkeley-dlab/measuring-hate-speech`. Treat as continuous severity drift. Check whether the model has PyTorch or TensorFlow weights before implementation. Source: https://huggingface.co/ucberkeley-dlab/hate-measure-roberta-large |
| `Hate-speech-CNERG/bert-base-uncased-hatexplain` | Keep skipped unless a validated loader is added | Current repo marks generic pipeline inference as untrusted from local smoke tests. Keep as non-default until fixed. Source: https://huggingface.co/Hate-speech-CNERG/bert-base-uncased-hatexplain |
| `Hate-speech-CNERG/bert-base-uncased-hatexplain-rationale-two` | Add custom `rationale_head` runtime, not generic pipeline | Model card says to use `Model_Rational_Label` from `models.py` and warns hosted inference can be wrong due to class initializations. It outputs Abusive/Normal plus rationale predictions. Source: https://huggingface.co/Hate-speech-CNERG/bert-base-uncased-hatexplain-rationale-two |
| `mudes/en-large` | Add custom `token_span` runtime | Model card says to install `mudes` and use `MUDESApp("en-large", use_cuda=False)` for toxic spans. Use character-level span IoU and span retention. Source: https://huggingface.co/mudes/en-large |
| `mudes/multilingual-large` | Later multilingual span audit | Same role as `mudes/en-large`, but only after language routing exists. Source: https://huggingface.co/mudes/multilingual-large |
| `unitary/toxic-bert` | Keep as weak non-default baseline | Useful for showing lexical/profanity fragility. Never use as a hard reject gate. |
| Davidson/offensive-language fine-tunes | Avoid as utility gates | Can confuse dialect/style normalization with semantic utility loss. Use only for research comparison with clear bias warnings. |

## Phase 1: Registry Metadata

Modify `privhsd/hf_utility.py`.

Add fields to `HfUtilityModel`:

```python
probe_kind: str = "binary_hate"
default_suite: str | None = None
score_labels: tuple[str, ...] = ()
negative_label_hints: tuple[str, ...] = ("not", "non", "neutral", "normal", "clean", "none")
requires_custom_runtime: bool = False
runtime_package: str | None = None
source_url: str | None = None
bias_note: str | None = None
```

Keep backward compatibility:

- existing tests should still pass if they only inspect `model_id`, `task`,
  `default`, `positive_label_hints`, and `pipeline_compatible`;
- `as_dict()` must include the new fields;
- unknown model errors must still point users to `hf-model-registry`.

Add these registry entries:

```python
HfUtilityModel(
    model_id="cardiffnlp/twitter-roberta-base-hate-multiclass-latest",
    task="text-classification",
    default=False,
    probe_kind="target_multiclass",
    positive_label_hints=(
        "sexism",
        "racism",
        "disability",
        "sexual_orientation",
        "religion",
        "other",
    ),
    score_labels=(
        "sexism",
        "racism",
        "disability",
        "sexual_orientation",
        "religion",
        "other",
        "not_hate",
    ),
    runtime_note="Target-category drift probe for anonymization utility audits.",
    license_note="CC-BY 4.0. Review live model card before full runs.",
    source_url="https://huggingface.co/cardiffnlp/twitter-roberta-base-hate-multiclass-latest",
    bias_note="High weighted-F1 but much lower macro-F1; diagnostic only.",
)
```

Add later, initially non-default:

```python
unitary/unbiased-toxic-roberta
unitary/multilingual-toxic-xlm-roberta
ucberkeley-dlab/hate-measure-roberta-large
mudes/en-large
mudes/multilingual-large
```

For custom runtimes, set `pipeline_compatible=False` until implementation is
complete. This preserves current clean-skip behavior.

Tests:

- update `tests/test_hf_utility.py::test_hf_model_registry_writes_manifest`;
- add assertions that registry output includes `probe_kind` and `source_url`;
- add an unknown model test if one does not exist.

Acceptance:

- `python -m privhsd.cli hf-model-registry` prints the expanded registry;
- no model loads happen for custom-runtime entries unless their runtime exists.

## Phase 2: Rich HF Utility Metrics

Modify `privhsd/hf_utility.py` to route scoring by `probe_kind`.

Keep `positive_score()` for `binary_hate`, but add helpers:

```python
def score_distribution(scores: list[dict[str, Any]]) -> dict[str, float]
def l1_distribution_drift(left: dict[str, float], right: dict[str, float]) -> float
def top_label(distribution: dict[str, float]) -> str | None
def target_mass(distribution: dict[str, float], target_labels: tuple[str, ...]) -> float
def not_hate_mass(distribution: dict[str, float]) -> float
```

For `target_multiclass`, report:

- `original_top_label_mean_counts`;
- `privatized_top_label_mean_counts`;
- `top_label_agreement`;
- `not_hate_mass_mean_delta`;
- `target_mass_mean_delta`;
- `distribution_l1_mean`;
- `large_target_shift_rows`, without raw text.

Suggested row example shape:

```json
{
  "row_index": 17,
  "row_id": "abc",
  "original_top_label": "religion",
  "privatized_top_label": "not_hate",
  "not_hate_delta": 0.42,
  "target_mass_delta": -0.39,
  "distribution_l1": 0.81
}
```

For `toxicity_bias`, report:

- same scalar drift as binary where possible;
- `identity_attack_delta` if that label exists;
- warning that toxicity drift is not HSD utility drift;
- no hard pass/fail.

For `continuous_hate`, report:

- `original_mean`;
- `privatized_mean`;
- `mean_delta`;
- `mean_abs_drift`;
- `large_continuous_drop_rows`;
- thresholds must be configured separately from binary thresholds.

For `token_span` and `rationale_head`, do not force them through
`score_with_model()`. Add separate runtime hooks when ready:

```python
def score_with_custom_runtime(...)
```

Tests:

- fake classifier returns multiclass distributions and validates target drift;
- reports must not include `original_text` or `privatized_text`;
- binary existing fake tests must still pass.

Acceptance:

- `evaluate-hf-utility` can run binary and multiclass probes together;
- output clearly separates probe kinds;
- custom-runtime models skip cleanly until implemented.

## Phase 3: Auto HSD Advisory Ensemble

Current behavior uses one model in `HsdAdvisoryRuntime`. Upgrade this without
breaking callers.

Preferred approach:

1. Keep `HsdAdvisoryRuntime` as the single pipeline wrapper.
2. Add `HsdAdvisoryEnsembleRuntime` in
   `privhsd/models/hsd_advisory_runtime.py`.
3. Extend `AutoPipelineConfig` with both a backward-compatible single string
   and a tuple for new usage:

```python
DEFAULT_HSD_ADVISORY_MODELS = (
    "cardiffnlp/twitter-roberta-base-hate-latest",
    "facebook/roberta-hate-speech-dynabench-r4-target",
)

hsd_advisory_model: str = "facebook/roberta-hate-speech-dynabench-r4-target"
hsd_advisory_models: tuple[str, ...] = DEFAULT_HSD_ADVISORY_MODELS
```

If `hsd_advisory_models` is empty, fall back to `hsd_advisory_model`. This
keeps older code stable.

4. Add CLI support in `add_auto_runtime_arguments()`:

```text
--hsd-advisory-model MODEL_ID
```

Repeatable. Default remains config-driven. The CLI should not accept arbitrary
unknown remote IDs silently. It should either:

- require model IDs to exist in the approved HF registry, or
- record `status=unsupported_model` and skip.

5. Update `AutoPipelineContext._load_model("hsd_advisory")` to return the
ensemble runtime when multiple models are configured.

Ensemble scoring:

- `score_texts(texts, batch_size)` returns an aggregate positive score for
  backward compatibility.
- `compare(original_score, candidate_score)` remains available.
- Add `compare_text_scores(original_scores_by_model, candidate_scores_by_model)`
  or store per-model comparisons internally.

Suggested aggregate:

```python
aggregate_score = mean(member_scores)
```

Suggested candidate hard-reject logic:

- hard reject if at least two `binary_hate` probes report `large_drop`;
- hard reject if one probe reports `large_drop` and deterministic
  target/utility cue retention also dropped;
- do not hard reject on toxicity-only drops;
- do not hard reject on multiclass target shift until validated locally;
- always include per-model comparisons in audit metadata.

Audit shape:

```json
{
  "hsd_advisory": {
    "aggregate": {
      "original_score": 0.91,
      "candidate_score": 0.63,
      "score_drop": 0.28,
      "large_drop": true
    },
    "members": [
      {
        "model_id": "cardiffnlp/twitter-roberta-base-hate-latest",
        "probe_kind": "binary_hate",
        "original_score": 0.93,
        "candidate_score": 0.61,
        "large_drop": true
      },
      {
        "model_id": "facebook/roberta-hate-speech-dynabench-r4-target",
        "probe_kind": "binary_hate",
        "original_score": 0.89,
        "candidate_score": 0.65,
        "large_drop": false
      }
    ]
  }
}
```

Tests:

- update `tests/test_auto_pipeline.py::test_auto_hsd_advisory_scores_candidates_in_one_batch`;
- add a fake ensemble with two members and prove one load per run;
- verify candidates are rejected only when consensus rules trigger;
- verify model errors remain structured and do not fail exact CSV output.

Acceptance:

- auto mode still works when optional dependencies are missing;
- local-only default is preserved unless `--allow-model-download` is passed;
- model status lists member model IDs, device, load count, and skip/error state;
- audit remains raw-text-free.

## Phase 4: Custom Continuous Runtime

Target: `ucberkeley-dlab/hate-measure-roberta-large`

Add a new module:

```text
privhsd/models/continuous_hate_runtime.py
```

Implementation checklist:

1. Re-check model files. If only TensorFlow weights are present, use
   `TFAutoModelForSequenceClassification` and add a new optional dependency
   group rather than silently requiring TensorFlow in existing extras.
2. Keep official auto mode local-only.
3. Return one float per input text.
4. Do not apply a binary threshold by default.
5. Report continuous drift in `evaluate-hf-utility`; do not use it as a hard
   rejection gate until thresholds are calibrated.

Suggested optional extra in `pyproject.toml`:

```toml
continuous-utility = ["transformers>=4.40", "tensorflow>=2.15"]
```

Only add TensorFlow if the loader genuinely needs it. Do not add it to base
dependencies.

Tests:

- fake continuous model returns deterministic floats;
- evaluate original-vs-privatized mean delta and large drops;
- missing TensorFlow produces `skip_reason=missing_optional_dependency`.

Acceptance:

- continuous probe can be run explicitly through `evaluate-hf-utility`;
- no official path imports TensorFlow unless the runtime is requested.

## Phase 5: Custom Span Runtime

Target: `mudes/en-large`

Add a new module:

```text
privhsd/models/toxic_span_runtime.py
```

Suggested API:

```python
@dataclass
class SpanProbeResult:
    spans: list[tuple[int, int]]
    span_count: int

class ToxicSpanRuntime:
    @classmethod
    def from_model_name(cls, model_name: str, *, device: str) -> "ToxicSpanRuntime": ...
    def predict_spans(self, texts: list[str], *, batch_size: int) -> list[SpanProbeResult]: ...
```

MUDES model-card usage shows:

```python
from mudes.app.mudes_app import MUDESApp

app = MUDESApp("en-large", use_cuda=False)
app.predict_toxic_spans("text", spans=True)
```

Implementation details:

- normalize returned spans into character-offset ranges;
- merge overlapping ranges;
- compare original and privatized spans using character-level IoU;
- report whether changed ranges from `rationale_checks.changed_ranges()` overlap
  original toxic spans;
- reuse existing rationale aggregation concepts instead of inventing unrelated
  names.

Metrics to add:

- `span_iou_mean`;
- `span_retention_mean`;
- `changed_overlap_count`;
- `placeholder_overlap_count`;
- `lost_span_rows`;
- `new_span_rows`.

Tests:

- fake runtime returns spans for original and privatized text;
- IoU and retention calculations handle no-span rows;
- reports contain row IDs and metrics only, not raw text.

Acceptance:

- span probe runs only when `mudes` is installed;
- missing `mudes` is a structured skip;
- reports help answer whether anonymization touched the abusive predicate.

## Phase 6: HateXplain Rationale Runtime

Target: `Hate-speech-CNERG/bert-base-uncased-hatexplain-rationale-two`

Add a new module:

```text
privhsd/models/hatexplain_rationale_runtime.py
```

Important safety rule:

- Do not use `trust_remote_code=True` in official mode.
- Do not execute model-card `models.py` directly from the network at runtime.
- If the custom class is needed, vendor a minimal audited implementation or
  require a local trusted path and record that path in model status.

Suggested API:

```python
class HatexplainRationaleRuntime:
    @classmethod
    def from_model_id(
        cls,
        model_id: str,
        *,
        allow_model_download: bool,
        trusted_code_path: Path | None,
        device: str,
    ) -> "HatexplainRationaleRuntime": ...

    def predict(self, texts: list[str], *, batch_size: int) -> list[dict[str, Any]]: ...
```

Output should include:

- label logits or probabilities;
- rationale token indices or char spans;
- tokenizer offset mappings if available;
- model revision;
- code source status: `vendored`, `trusted_local_path`, or `skipped`.

Compare metrics:

- label agreement;
- abusive-score drop;
- rationale span IoU;
- rationale retention;
- changed-range overlap with original rationale.

Tests:

- fake rationale runtime with token indices;
- conversion to char spans;
- skip when custom class is unavailable;
- no raw text in reports.

Acceptance:

- generic pipeline path remains disabled for rationale-two;
- custom runtime is opt-in and auditable;
- generated rationales integrate with `source-regression-report` style metrics.

## Phase 7: Toxicity-Bias Runtime

Target: Detoxify `unbiased`, optionally `multilingual`.

Add a new module:

```text
privhsd/models/toxicity_bias_runtime.py
```

Because the Unitary model card warns that Hugging Face model outputs differ
from Detoxify and recommends Detoxify, prefer:

```python
from detoxify import Detoxify

model = Detoxify("unbiased")
```

Implementation notes:

- use only as audit evidence;
- expose labels available from Detoxify;
- for multilingual model, require `--language` or a known language column;
- do not hard-reject candidates only because toxicity decreases;
- include a report warning about profanity and dialect bias.

Metrics:

- `toxicity_delta`;
- `identity_attack_delta`;
- `insult_delta`;
- `threat_delta`;
- `toxicity_decision_agreement` if a threshold is configured;
- row examples by ID only.

Tests:

- fake Detoxify object;
- missing dependency skip;
- multilingual language gate.

Acceptance:

- toxicity-bias report is separated from HSD utility report;
- audit explicitly says it is not a hate-speech classifier.

## Phase 8: CLI And Documentation Updates

Update CLI help in `privhsd/cli.py`:

- `evaluate-hf-utility` should explain probe kinds in help text;
- add `--suite` if useful:
  - `default`: current default binary probes;
  - `research`: binary plus multiclass plus toxicity-bias where available;
  - `span`: custom span/rationale probes where available.

Do not overload official exact-submission commands with every research option.
Keep official commands simple and local-only by default.

Update docs:

- `docs/reference/evaluation.md`: add a short pointer to this plan once
  implementation begins;
- `docs/reference/providers_and_models.md`: document the ensemble lifecycle
  after implementation;
- `docs/runbooks/official_submission.md`: keep model-probe commands clearly
  marked as optional local audit.

Suggested command examples after Phase 2:

```bash
python -m privhsd.cli evaluate-hf-utility \
  --input data/outputs/INPUT_WITH_PRIVATIZED.csv \
  --text-col text \
  --privatized-col privatized_text \
  --id-col id \
  --label-col label \
  --model cardiffnlp/twitter-roberta-base-hate-latest \
  --model facebook/roberta-hate-speech-dynabench-r4-target \
  --model cardiffnlp/twitter-roberta-base-hate-multiclass-latest \
  --output data/outputs/hf_utility.research.json
```

Suggested command examples after Phase 3:

```bash
python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/SUBMISSION.auto.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --hsd-advisory-model cardiffnlp/twitter-roberta-base-hate-latest \
  --hsd-advisory-model facebook/roberta-hate-speech-dynabench-r4-target \
  --manifest data/outputs/SUBMISSION.auto.manifest.json
```

## Implementation Order

Recommended order for agents:

1. Registry and report metadata only. No custom runtimes.
2. Cardiff multiclass target-drift evaluator.
3. Binary HSD advisory ensemble.
4. Detoxify toxicity-bias audit runtime.
5. Continuous Measuring Hate Speech runtime.
6. MUDES span runtime.
7. HateXplain rationale runtime.

This order keeps early work small and reduces risk to exact-format submission.

## Validation Matrix

Every phase must run focused tests:

```bash
python -m pytest tests/test_hf_utility.py tests/test_auto_pipeline.py -q
```

If `privhsd/auto/` changes:

```bash
python -m pytest tests/test_auto_pipeline.py tests/test_submission.py tests/test_workbench_csv.py -q
```

Before merging broad changes:

```bash
python -m pytest -q
```

For manual local audit, use ignored `data/outputs/` paths only:

```bash
python -m privhsd.cli hf-model-registry \
  --output data/outputs/hf_model_registry.json
```

## Acceptance Criteria

An implementation is ready when:

- exact-format CSV creation still passes with all optional dependencies missing;
- model registry describes probe kind, runtime requirements, source URL, and
  warnings;
- binary, multiclass, continuous, toxicity-bias, and span reports have separate
  metric sections;
- candidate hard rejection uses only calibrated binary HSD probes plus existing
  deterministic cue checks;
- toxicity/offensiveness probes never decide final HSD utility by themselves;
- custom-runtime models skip cleanly when dependencies or trusted code are not
  available;
- model/provider load counters still prove one load per run;
- reports include row IDs and aggregate metrics, never raw text.

## Threshold Guidance

Keep current defaults conservative until local calibration exists:

- binary decision threshold: `0.5`;
- binary large drop threshold: `0.25`;
- binary max absolute drift threshold: `0.35`;
- target-multiclass large shift: start with `not_hate_mass_delta >= 0.25` or
  `distribution_l1 >= 0.5`, but audit only;
- continuous large drop: start with one standard deviation from the original
  sample distribution, not a fixed universal threshold;
- span IoU warning: start with `span_iou < 0.75` for rows with original spans,
  audit only.

Do not promote any threshold to a hard gate until it is validated on the local
recommended bundle and at least one external unseen dataset.

## Final Warning For Implementers

The point of these probes is to answer whether anonymization preserved HSD
utility. They are not production moderation systems. A drop in a toxicity score
may mean profanity was removed, dialect was normalized, or identity terms were
changed. That is not automatically semantic utility loss. Treat probe output as
structured evidence that must be read alongside deterministic cue retention,
rationale/span preservation, source slices, and author-risk metrics.
