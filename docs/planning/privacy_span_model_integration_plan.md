# Privacy Span Model Integration Plan

Status: active
Owner area: planning handoff for optional privacy span models
Last verified: 2026-06-13
Primary code: `privhsd/span_providers/`, `privhsd/auto/`,
`privhsd/pipeline.py`, `privhsd/cli.py`, `privhsd/csv_pipeline.py`,
`privhsd/submission.py`, `privhsd/rerank.py`

This file is an implementation handoff for agents integrating newer privacy
span models into ContextSafe-HSD. It covers GLiNER PII models and
`openai/privacy-filter`, explains how they should fit into the existing
pipeline, and gives concrete acceptance gates.

The recommendation is intentionally conservative: integrate stronger privacy
models as optional span providers and benchmark them. Do not replace the
deterministic baseline, HSD cue protection, fusion, reranking, or exact-format
validation.

## Executive Decision

Do not replace the current pipeline with any single PII model.

Implement the following in order:

1. Expose the existing `gliner_model` configuration through the public CLI and
   Python APIs.
2. Add a first-class PII GLiNER profile, with `nvidia/gliner-PII` as the
   primary model to benchmark.
3. Add provider batching for span providers, especially GLiNER.
4. Benchmark the PII GLiNER path against `balanced`, filtered Presidio, and
   the current `auto` path.
5. Consider `openai/privacy-filter` only as a second optional provider after
   the GLiNER path is wired and benchmarked.

Keep the official output policy:

- deterministic `balanced` is always available;
- optional providers produce `SpanCandidate` evidence only;
- provider output goes through fusion and HSD cue protection;
- final text is selected by candidate scoring;
- exact CSV validation remains mandatory;
- raw provider/model output never directly overwrites final text.

## Why This Fits The Current Architecture

The repository already has the correct integration boundary.

Current facts:

- `privhsd/span_providers/gliner.py` already normalizes GLiNER output into
  `SpanCandidate` objects.
- `privhsd/pipeline.py` already accepts `provider_candidates` and fuses them
  with deterministic spans.
- `privhsd/span_providers/fusion.py` rejects invalid offsets, text mismatches,
  low-confidence spans, and protected HSD cue overlaps.
- `privhsd/auto/engine.py` already creates a deterministic baseline for every
  row, routes risky rows to optional providers/models, generates provider
  candidates, scores them, and falls back to baseline on uncertainty.
- `privhsd/auto/config.py` already has `gliner_model`, but the CLI and public
  APIs do not yet expose it.
- Token-policy artifacts already exist under `data/outputs/`, and the
  token-policy ensemble should remain advisory rather than being replaced by a
  generic PII detector.

The missing work is not a rewrite. It is provider selection, configuration
surface area, batching, and evaluation.

## Model Recommendations

### Primary: `nvidia/gliner-PII`

Use this as the first PII-specific GLiNER model to benchmark.

Model page:

- `https://huggingface.co/nvidia/gliner-PII`

Reasons to prioritize:

- Span-detection architecture fits the repo's `SpanCandidate` boundary.
- The model is intended for PII/PHI detection across many categories.
- It returns exact span fields such as text, label, start, end, and score
  through the GLiNER API.
- The model card explicitly lists content moderation over user-generated
  content as an intended use case.
- It can provide finer-grained evidence than the current generic GLiNER label
  set.

Risks and constraints:

- License is NVIDIA Open Model License, not Apache 2.0. Agents must record this
  in provider status and docs before recommending it for commercial use.
- It is still trained on synthetic/persona-grounded data. Benchmark on noisy
  HSD-style text before changing default behavior.
- It may over-detect public entities, target groups, or organizations. Fusion
  must preserve HSD cues and reranking must reject cue loss.

Implementation posture:

- Add it as an explicit profile or CLI-selected model.
- Do not silently change the default GLiNER model for all users until the
  benchmark gate passes.
- Prefer `--gliner-profile pii` plus `--gliner-model nvidia/gliner-PII`, or a
  single explicit `--gliner-model nvidia/gliner-PII` if profiles are deferred.

### Secondary: `openai/privacy-filter`

Use this only after the PII GLiNER path is implemented.

Model page:

- `https://huggingface.co/openai/privacy-filter`

Reasons to consider:

- Apache 2.0 license is operationally easier.
- The model is privacy-specific rather than a generic NER model.
- It uses token classification with constrained BIOES/Viterbi-style decoding,
  which may reduce boundary fragmentation compared with simple token heads.
- Its broad privacy classes are compatible with the repo's direct/quasi
  identifier policy.

Risks and constraints:

- It is not a GLiNER model. It needs a separate adapter.
- Its categories are broad, so it cannot replace the repo's more specific
  deterministic tags without a careful mapping.
- It should not replace the token-policy ensemble. The local token-policy model
  also predicts `PROTECT_TARGET`, `PROTECT_HSD`, `NORMALIZE_STYLE`, and
  `REVIEW`; `openai/privacy-filter` is only a privacy span detector.
- Agents must inspect the current model card and loading requirements before
  implementation. Do not assume remote custom code is acceptable in official
  mode.

Implementation posture:

- Add as a disabled-by-default optional provider, for example
  `privacy_filter`.
- Convert decoded privacy spans into `SpanCandidate` objects.
- Never use model-supplied masked text directly.
- Keep local-only loading by default and require `--allow-model-download` for
  remote weights.

### Tertiary: `knowledgator/gliner-pii-large-v1.0`

Model page:

- `https://huggingface.co/knowledgator/gliner-pii-large-v1.0`

Use this as a fallback PII GLiNER benchmark if `nvidia/gliner-PII` cannot be
used because of license, packaging, or runtime constraints.

Notes:

- The model is GLiNER-compatible and broad PII oriented.
- Apache 2.0 may be easier than NVIDIA Open Model License.
- Prioritize recall and HSD cue retention in evaluation. Do not adopt if it
  leaves residual direct identifiers or overmasks target/action terms.

### Current Generalist GLiNER: `urchade/gliner_medium-v2.1`

Model page:

- `https://huggingface.co/urchade/gliner_medium-v2.1`

Keep this as the generalist GLiNER option. It is useful for zero-shot labels,
but it should not be treated as the best PII default without benchmarking
against a PII-specific model.

## Non-Recommendations

Do not prioritize classic BERT/DistilBERT PII models for the main path.

Reasons:

- They often depend on token-level aggregation and are more likely to fragment
  spans in noisy social text.
- Many are trained on formal text, synthetic templates, or narrow PII formats.
- The current deterministic baseline already covers many high-precision direct
  identifiers faster and more explainably.

Do not replace typed placeholders with realistic dummy identifiers.

Examples to avoid:

- replacing a phone number with `555-0100`;
- replacing an email with `user@example.com`;
- replacing an address with a realistic-looking fake address.

Reason:

- The repo's metrics and likely challenge scoring treat phone-like, email-like,
  ID-like, and address-like strings as residual identifier signals. Typed
  placeholders such as `[PHONE]`, `[EMAIL]`, `[PERSON]`, `[LOCATION]`, and
  `[ID]` are safer for challenge scoring and auditability.

Do not submit a provider-only output.

Provider output is not HSD-aware. It must stay behind fusion, cue protection,
candidate scoring, and validation.

## Implementation Task 1: Expose GLiNER Model Selection

Problem:

`AutoPipelineConfig` has `gliner_model`, but normal users cannot select it from
`create-submission`, `anonymize`, or `rerank-candidates`.

Goal:

Make this command possible:

```bash
python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/INPUT.auto.gliner_pii.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --gliner-model nvidia/gliner-PII \
  --allow-model-download \
  --manifest data/outputs/INPUT.auto.gliner_pii.manifest.json
```

Files likely to change:

- `privhsd/cli.py`
- `privhsd/csv_pipeline.py`
- `privhsd/submission.py`
- `privhsd/rerank.py`
- `tests/test_auto_pipeline.py`
- `tests/test_submission.py`
- `tests/test_csv_pipeline.py`

Concrete code changes:

1. Add a `--gliner-model` argument in `add_auto_runtime_arguments()`.
   Suggested help text:

   ```text
   GLiNER model ID or local path for the optional GLiNER provider.
   Defaults to the built-in GLiNER provider default. Remote IDs require
   --allow-model-download unless already cached.
   ```

2. Add `gliner_model: str | None = None` to these public functions if missing:

   - `process_csv(...)`
   - `create_submission(...)`
   - `run_candidate_reranking(...)`

3. Pass `gliner_model=gliner_model` into `AutoPipelineConfig(...)` in every
   auto-mode code path.

4. Pass `args.gliner_model` from CLI dispatch into the corresponding function
   calls.

5. Ensure manifests/status include the configured model through existing
   `discover_gliner()` status.

6. Preserve local-only behavior:

   - local path exists: status should be `available`;
   - remote model ID with `--allow-model-download`: status should be
     `download_allowed`;
   - remote model ID without download permission and not local: status should
     be `missing_artifact`.

Acceptance tests:

- CLI parser accepts `--gliner-model nvidia/gliner-PII`.
- `create_submission(..., mode="auto", gliner_model="local/path")` passes the
  value into `AutoPipelineConfig`.
- Missing GLiNER dependency still yields deterministic fallback.
- Remote model without `--allow-model-download` is reported as
  `missing_artifact`, not fatal.
- Existing tests still pass when `--gliner-model` is absent.

Suggested focused commands:

```bash
python -m pytest tests/test_auto_pipeline.py tests/test_submission.py tests/test_csv_pipeline.py -q
```

## Implementation Task 2: Add GLiNER Profiles

Problem:

The current provider has one hard-coded label set and default model:

```text
DEFAULT_GLINER_MODEL = "urchade/gliner_medium-v2.1"
```

That is a generalist setup. PII-specific GLiNER models need a richer label set,
different thresholds, and model metadata.

Goal:

Support at least two profiles:

- `general`: existing behavior;
- `pii`: PII-oriented labels and thresholds, optimized for models such as
  `nvidia/gliner-PII` and `knowledgator/gliner-pii-large-v1.0`.

Files likely to change:

- `privhsd/span_providers/gliner.py`
- `privhsd/span_providers/registry.py`
- `privhsd/auto/config.py`
- `privhsd/auto/context.py`
- `privhsd/auto/model_registry.py`
- `tests/test_span_providers.py`
- `tests/test_auto_pipeline.py`

Suggested API:

```python
load_gliner_provider(
    model_name: str = DEFAULT_GLINER_MODEL,
    profile: str = "general",
) -> GlinerSpanProvider
```

Suggested config:

```python
gliner_model: str | None = None
gliner_profile: str = "general"
```

Suggested CLI:

```bash
--gliner-profile general
--gliner-profile pii
```

Keep `general` as the default until benchmarks prove `pii` is better for the
official path.

### PII Profile Labels

The exact label strings should be verified against the selected model card and
smoke-test output. Start with semantically clear prompts. GLiNER accepts
descriptive labels, so labels can be natural language.

Suggested `pii` labels:

```python
GLINER_PII_LABELS = (
    "person",
    "full name",
    "username",
    "online handle",
    "social media handle",
    "email address",
    "phone number",
    "street address",
    "home address",
    "ip address",
    "url",
    "personal url",
    "government id",
    "account number",
    "case number",
    "student id",
    "driver license number",
    "passport number",
    "date of birth",
    "age",
    "city",
    "neighborhood",
    "school",
    "university",
    "organization",
)
```

Suggested mapping:

```python
GLINER_PII_ENTITY_MAP = {
    "person": "PERSON",
    "full name": "PERSON",
    "username": "USER",
    "online handle": "USER",
    "social media handle": "USER",
    "email address": "EMAIL",
    "phone number": "PHONE",
    "street address": "LOCATION",
    "home address": "LOCATION",
    "ip address": "IP_ADDRESS",
    "url": "URL",
    "personal url": "URL",
    "government id": "IDENTIFIER",
    "account number": "IDENTIFIER",
    "case number": "IDENTIFIER",
    "student id": "IDENTIFIER",
    "driver license number": "IDENTIFIER",
    "passport number": "IDENTIFIER",
    "date of birth": "DATE",
    "age": "AGE",
    "city": "LOCATION",
    "neighborhood": "LOCATION",
    "school": "ORGANIZATION",
    "university": "ORGANIZATION",
    "organization": "ORGANIZATION",
}
```

Label normalization:

- Lowercase labels.
- Convert `_`, `-`, and repeated whitespace to a single space.
- Strip punctuation around labels.
- Keep the original raw label in metadata.

Suggested thresholds:

```python
GLINER_PII_THRESHOLDS = {
    "person": 0.55,
    "full name": 0.55,
    "username": 0.40,
    "online handle": 0.40,
    "social media handle": 0.40,
    "email address": 0.30,
    "phone number": 0.30,
    "street address": 0.50,
    "home address": 0.50,
    "ip address": 0.30,
    "url": 0.30,
    "personal url": 0.30,
    "government id": 0.40,
    "account number": 0.40,
    "case number": 0.40,
    "student id": 0.40,
    "driver license number": 0.40,
    "passport number": 0.40,
    "date of birth": 0.50,
    "age": 0.50,
    "city": 0.65,
    "neighborhood": 0.65,
    "school": 0.60,
    "university": 0.60,
    "organization": 0.65,
}
```

Rationale:

- Direct identifier forms with strong shape cues can use lower thresholds.
- `PERSON`, `LOCATION`, and `ORGANIZATION` are more likely to overlap HSD
  content and public entities, so keep them more conservative.
- Fusion still applies entity-level thresholds and HSD cue overlap checks.

Audit requirements:

Provider audit should include:

- `profile`;
- configured model name/path;
- raw span count;
- accepted span count;
- rejected counts by reason;
- labels;
- thresholds;
- raw label counts if easy to add;
- no raw row text.

Acceptance tests:

- `GlinerSpanProvider(profile="pii")` maps a fake `email address` result to
  `EMAIL`.
- Fake `username` and `social media handle` map to `USER`.
- Unsupported labels are rejected and counted.
- Text mismatches are caught by fusion.
- Protected target terms are rejected by fusion when a model labels them as
  `PERSON`, `LOCATION`, or `ORGANIZATION`.

## Implementation Task 3: Add Provider Batch Inference

Problem:

Auto mode batches token-policy inference, but optional span providers are
called one row at a time. GLiNER on GPU will be unnecessarily slow without
provider batching.

Goal:

Allow providers to implement `propose_many()` while keeping `propose()` as the
minimum protocol.

Files likely to change:

- `privhsd/span_providers/base.py`
- `privhsd/span_providers/gliner.py`
- `privhsd/auto/engine.py`
- `tests/test_auto_pipeline.py`
- `tests/test_span_providers.py`

Suggested protocol shape:

```python
class BatchedSpanProvider(Protocol):
    name: str

    def propose_many(
        self,
        texts: list[str],
        *,
        batch_size: int,
    ) -> list[SpanProviderOutput]:
        ...
```

Do not require every provider to implement it.

Suggested engine behavior:

1. Group routed states by provider.
2. If the provider has `propose_many`, call it once per provider for routed
   texts, respecting `config.max_model_batch_size` or a new
   `config.max_provider_batch_size`.
3. If not, fall back to current row loop.
4. If batched output count does not match input count, mark provider runtime
   error and do not use partial output.
5. Keep per-row audit outputs attached to each `AutoRowState`.

Suggested GLiNER implementation:

- If GLiNER exposes a batch API in the installed version, use it.
- Otherwise, implement a local loop inside `propose_many()` so the auto engine
  still has one interface.
- Keep `propose()` implemented as a one-row wrapper around `propose_many()`.

Acceptance tests:

- A fake batched provider records one batch call for several routed rows.
- A fake non-batched provider still works.
- Mismatched batched output count records a provider error and falls back.
- Provider load count remains one per run.
- Existing row-level provider errors still appear in audits.

Suggested focused command:

```bash
python -m pytest tests/test_auto_pipeline.py tests/test_span_providers.py -q
```

## Implementation Task 4: Optional `openai/privacy-filter` Provider

Only start this task after Tasks 1 to 3 are implemented or explicitly deferred.

Goal:

Add a provider that loads `openai/privacy-filter`, decodes privacy spans, and
returns normalized `SpanCandidate` objects.

Suggested provider name:

```text
privacy_filter
```

Suggested files:

- `privhsd/span_providers/privacy_filter.py`
- `privhsd/span_providers/registry.py`
- `privhsd/auto/context.py`
- `privhsd/auto/model_registry.py`
- `pyproject.toml` optional extra, if needed
- `tests/test_span_providers.py`
- `tests/test_auto_pipeline.py`

Loading policy:

- Local-only by default.
- Remote model downloads require `--allow-model-download`.
- If the model requires custom code, record that explicitly and do not enable
  it for official mode until reviewed.
- Missing dependencies or artifacts must produce structured status and
  deterministic fallback.

Mapping policy:

Map broad privacy categories into existing entity types. Agents must verify the
current model labels before implementation. A starting mapping is:

| Privacy-filter category | ContextSafe entity type |
| --- | --- |
| private_person | `PERSON` or `USER` depending on shape |
| private_address | `LOCATION` |
| private_email | `EMAIL` |
| private_phone | `PHONE` |
| account_number | `IDENTIFIER` |
| secret | `IDENTIFIER` |
| url-like category, if present | `URL` |
| ip-like category, if present | `IP_ADDRESS` |

Shape refinement:

- If a `private_person` span starts with `@`, map it to `USER`.
- If a `private_person` span looks like a platform handle without `@`, map it
  to `ALIAS` or `USER` only when context supports it.
- Do not create new realistic replacement strings.

Decoding requirements:

- Use the model's official decoding path if available.
- If decoding BIOES manually, enforce valid transitions.
- Merge contiguous spans only when label and category agree.
- Return exact character offsets.
- Verify `text[start:end]` equals the span text before creating candidates.

Audit requirements:

- model ID/path;
- local-only vs download-allowed;
- decoded span count;
- accepted span count;
- rejected counts by reason;
- threshold or calibration settings;
- no raw row text.

Acceptance tests:

- Fake decoded `private_email` span maps to `EMAIL`.
- Fake decoded `private_person` span over `@name` maps to `USER`.
- Invalid offsets are rejected.
- HSD target overlap is rejected by fusion.
- Missing model artifacts do not fail exact submission.

## Implementation Task 5: Keep Token-Policy Advisory

Do not replace the local token-policy ensemble with either GLiNER or
`openai/privacy-filter`.

Reason:

The token-policy ensemble is not just PII detection. It predicts challenge
specific token actions:

```text
KEEP
MASK_IDENTIFIER
GENERALIZE_CONTEXT
PROTECT_TARGET
PROTECT_HSD
NORMALIZE_STYLE
REVIEW
```

Current durable evidence in `data/outputs/` includes:

- external TweetEval ensemble macro F1: `0.8837`;
- `MASK_IDENTIFIER` F1: `0.9638`;
- `PROTECT_TARGET` F1: `0.8143`;
- `PROTECT_HSD` F1: `0.9808`.

Integration policy:

- GLiNER and privacy-filter provide supplemental privacy spans.
- Token-policy remains advisory evidence for privacy, protected HSD cues,
  style, and review.
- Final text still comes from candidate scoring and validation.

Implementation implication:

- Do not route token-policy through the GLiNER provider.
- Do not collapse token-policy actions into generic PII labels.
- If provider benchmarks compare models, report token-policy separately from
  PII providers.

## Implementation Task 6: Evaluation And Benchmark Gate

No model should become default or official-path influential without an audit
run.

### Dependency Setup

The active environment checked on 2026-06-13 was missing:

```text
gliner
torch
transformers
presidio_analyzer
scrubadub
```

The repo did contain local token-policy artifacts under `data/outputs/`.

Agents should not assume this remains true. Recheck locally:

```bash
python - <<'PY'
import importlib.util
for name in ["gliner", "torch", "transformers", "presidio_analyzer", "scrubadub"]:
    print(f"{name}: {bool(importlib.util.find_spec(name))}")
PY
```

Install only what the benchmark needs:

```bash
python -m pip install '.[gliner]'
```

If testing `openai/privacy-filter`, inspect the current model card first and
then install only the required optional dependencies.

### Smoke Tests

Run focused unit tests first:

```bash
python -m pytest tests/test_span_providers.py tests/test_auto_pipeline.py -q
```

Run a tiny GLiNER smoke with a row limit:

```bash
python -m privhsd.cli create-submission \
  --input data/public_dev/recommended_merged.csv \
  --output data/outputs/recommended_merged.auto.gliner_pii_smoke.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --gliner-model nvidia/gliner-PII \
  --gliner-profile pii \
  --allow-model-download \
  --max-provider-rows 100 \
  --metric-depth fast \
  --manifest data/outputs/recommended_merged.auto.gliner_pii_smoke.manifest.json
```

If the official or public-dev dataset has different columns, adapt only the
column names. Preserve exact-format rules.

### Full Comparison

Compare these variants:

1. `balanced` deterministic baseline.
2. `auto` with optional providers disabled.
3. `auto` with filtered Presidio if available.
4. `auto` with current general GLiNER.
5. `auto` with PII GLiNER profile and `nvidia/gliner-PII`.
6. Optional: `auto` with `knowledgator/gliner-pii-large-v1.0`.
7. Optional after implementation: `auto` with `privacy_filter`.

Suggested commands:

```bash
python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/INPUT.balanced.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode balanced \
  --metric-depth fast \
  --manifest data/outputs/INPUT.balanced.manifest.json

python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/INPUT.auto.no_optional.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --disable-provider presidio \
  --disable-provider scrubadub \
  --disable-provider gliner \
  --disable-model token_policy_ensemble \
  --disable-model semantic \
  --disable-model hsd_advisory \
  --metric-depth fast \
  --manifest data/outputs/INPUT.auto.no_optional.manifest.json

python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/INPUT.auto.gliner_pii.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --gliner-model nvidia/gliner-PII \
  --gliner-profile pii \
  --allow-model-download \
  --metric-depth fast \
  --manifest data/outputs/INPUT.auto.gliner_pii.manifest.json
```

Validate every exact-format output:

```bash
python -m privhsd.cli validate-submission \
  --source INPUT.csv \
  --submission OUTPUT.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/OUTPUT.validation.json
```

Run source-aware regression when metadata columns exist:

```bash
python -m privhsd.cli source-regression-report \
  --original INPUT.csv \
  --protected OUTPUT.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --group-col split \
  --group-col platform \
  --group-col type \
  --output data/outputs/OUTPUT.source_regression.json
```

### Metrics To Compare

Required:

- exact validation valid/invalid;
- row count and changed text cell count;
- direct identifier counts before/after;
- residual direct identifier count;
- quasi identifier counts before/after;
- residual quasi identifier count;
- target cue retention;
- utility cue retention;
- character utility retention;
- placeholder density;
- rows with privacy warnings;
- rows with overmasking warnings;
- chosen candidate counts;
- fallback counts;
- provider/model statuses;
- provider/model load counts;
- runtime if available.

Provider-specific:

- routed provider row count;
- raw span count;
- accepted span count;
- rejected counts by reason;
- accepted counts by entity type;
- accepted counts by provider;
- protected-cue overlap rejections;
- provider disagreement count.

Decision criteria:

- Must preserve exact CSV shape.
- Must not increase residual direct identifiers compared with `balanced`.
- Should reduce residual direct identifiers if any exist.
- Must keep target cue retention at or above the baseline.
- Must keep utility cue retention at or above the baseline.
- Must not introduce high overmasking on target/action/negation terms.
- Must not depend on model downloads unless the run explicitly opted in.
- Must produce raw-text-free manifest/audit summaries.

Promotion rule:

Do not make PII GLiNER default unless it improves residual identifier behavior
or manual review risk without measurable HSD cue regression. If it only changes
more rows but does not reduce residual identifiers, keep it optional.

## Suggested Provider Benchmark Command

If an agent implements a provider benchmark tool, include these variants:

```bash
python -m privhsd.cli benchmark-providers \
  --input INPUT.csv \
  --text-col text \
  --id-col id \
  --provider balanced \
  --provider presidio \
  --provider gliner:general:urchade/gliner_medium-v2.1 \
  --provider gliner:pii:nvidia/gliner-PII \
  --output data/outputs/INPUT.provider_benchmark.json
```

Benchmark requirements:

- include `balanced` as a baseline;
- record provider status and load counts;
- record aggregate metrics and row IDs only;
- no raw text by default;
- explicit `--include-text-debug` only for ignored local files;
- deterministic sampling with `--sample-size` and `--random-state`;
- compare changed-vs-balanced rows;
- compare privacy-improved rows;
- compare privacy-regressed rows;
- compare cue-regressed rows;
- compare extra overmask-warning rows.

## Fusion And Threshold Policy

Keep direct identifiers recall-oriented, but do not bypass HSD cue protection.

Direct types:

```text
ALIAS
USER
EMAIL
PHONE
URL
IP_ADDRESS
IDENTIFIER
PERSON
```

Quasi types:

```text
AGE
DATE
LOCATION
ORGANIZATION
```

Policy notes:

- Shape-stable direct types such as email, phone, URL, IP address, handle, and
  account-like IDs can use lower thresholds.
- `PERSON`, `LOCATION`, and `ORGANIZATION` need more conservative thresholds
  because they overlap public entities, protected target terms, and HSD
  context.
- Fusion should continue checking `text[start:end] == candidate.text`.
- Fusion should continue rejecting protected target/action/negation overlaps
  for non-high-precision direct types.
- Provider spans should never override deterministic target preservation.

If an agent adds runtime calibration:

- expose entity-type thresholds in config only after tests exist;
- keep defaults stable;
- write threshold values into audits;
- avoid making official outputs depend on unrecorded runtime knobs.

## Placeholder Policy

Keep current typed placeholders.

Allowed replacements:

```text
[PERSON]
[ALIAS]
[USER]
[EMAIL]
[PHONE]
[URL]
[ID]
[DATE]
[LOCATION]
[ORG]
[AGE]
```

Do not introduce category-preserving realistic dummy strings in the official
path. If a research branch needs realistic pseudonyms for a utility experiment,
it must be:

- opt-in;
- excluded from official exact-format defaults;
- evaluated for residual identifier warnings;
- documented in a separate research note.

## Risk Register

Licensing:

- `nvidia/gliner-PII` uses NVIDIA Open Model License. Record this before any
  commercial or public deployment claim.
- `openai/privacy-filter` is Apache 2.0, but agents must still verify current
  model-card terms before implementation.
- Any model card can change. Re-verify at implementation time.

Synthetic training data:

- PII models may overfit synthetic formats or over-detect common names.
- Benchmark on noisy HSD-style rows, not only clean PII examples.

Overmasking:

- PII models can label protected target terms, locations, or public
  organizations as private spans.
- Fusion and candidate scoring must reject cue loss.

Throughput:

- Row-by-row GLiNER inference will be slow.
- Batch provider inference before full-dataset benchmarking.

Operational safety:

- Do not log raw official rows.
- Keep generated reports under ignored `data/outputs/`.
- Do not add external API calls.
- Do not enable downloads by default.

## Recommended Agent Assignments

Agent 1: GLiNER config surface

- Add `--gliner-model`.
- Add `--gliner-profile` if doing profiles in the same pass.
- Thread config through CLI, public APIs, auto config, and rerank.
- Add parser and fallback tests.

Agent 2: PII GLiNER provider profile

- Add profile label/map/threshold structures.
- Normalize raw labels robustly.
- Add provider audit metadata.
- Add fake-model unit tests.

Agent 3: Provider batching

- Add optional `propose_many`.
- Batch routed provider rows in auto mode.
- Add fake batched provider tests.
- Keep fallback behavior for non-batched providers.

Agent 4: Benchmark runner or benchmark run

- Run smoke and full comparison commands.
- Produce ignored reports under `data/outputs/`.
- Update `docs/planning/current_status.md` only with durable aggregate
  conclusions, not raw examples.

Agent 5: Privacy-filter adapter

- Start only after GLiNER work is stable.
- Verify current model loading and decoding.
- Add disabled-by-default provider.
- Benchmark separately from GLiNER.

## Handoff Summary

Best immediate implementation:

1. Add `--gliner-model`.
2. Add `--gliner-profile pii`.
3. Implement `nvidia/gliner-PII` as an optional PII GLiNER profile.
4. Add provider batching.
5. Benchmark before changing defaults.

Do not:

- replace the deterministic baseline;
- replace token-policy advisory models;
- use realistic dummy identifiers;
- submit provider-only text;
- weaken HSD cue preservation to chase PII recall;
- commit raw model outputs or raw text examples.

Expected benefit:

- Better recall on social handles, names, addresses, IDs, and other PII spans
  that deterministic regexes or Presidio may miss.
- Better model-selection story for judges and future maintainers.
- Minimal risk to exact-format reliability because all model output remains
  optional, fused, audited, and fallback-safe.
