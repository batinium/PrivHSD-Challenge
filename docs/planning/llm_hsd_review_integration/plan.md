# Local LLM HSD Review Integration Plan

Last updated: 2026-06-15

Status: implemented and live-smoke validated

## Decision

Keep deterministic PII removal as the core privacy authority. Add a local LLM review stage only after deterministic cleaning has produced the dashboard/review text.

The automatic pipeline should support two HSD classification backends:

1. `ml`: the current local Hugging Face HSD advisory/classifier path.
2. `local_llm`: a local OpenAI-compatible LLM path, expected to run through LM Studio, that classifies cleaned text as binary hate/not-hate and optionally emits residual PII suggestions.

The LLM must not rewrite text, directly remove spans, or see raw pre-PII text. It should only see post-deterministic-cleaning text. Its residual PII output is advisory metadata for later review flows, not an automatic masking authority.

## Why

The benchmark results support a hybrid design:

- Deterministic PII removal was faster and safer than LLM-only PII scrubbing.
- LLM HSD classification performed better than the current deterministic/local ML classifier on strict hate/not-hate metrics.
- LLM residual PII suggestions found some remaining privacy issues, but were too noisy to apply automatically.
- Council/reviewer concerns are easier to explain if AI assists classification and review triage while deterministic validation controls privacy-changing actions.

## Current Evidence

Artifacts from the 100-row stratified comparison:

- `data/outputs/llm_vs_deterministic_20260615/stratified100.strict_hsd_metrics.extended_comparison.json`
- `data/outputs/llm_vs_deterministic_20260615/stratified100.cleaned.gpt_oss_20b_hsd_pii_review.report.json`
- `data/outputs/llm_vs_deterministic_20260615/stratified100.cleaned.gpt_oss_20b_hsd_pii_review.analysis.json`
- `data/outputs/llm_vs_deterministic_20260615/stratified100.llm_only_gpt_oss_20b_tool.report.json`

Summary:

| Path | F1 | Precision | Recall | ROC AUC | Time | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Current ML HSD classifier | 0.6465 | 0.8205 | 0.5333 | 0.7571 | 18.11s | High precision, low recall. |
| `openai/gpt-oss-20b` strict HSD | 0.7358 | 0.8478 | 0.6500 | 0.7748 | 33.35s | Best practical MVP default. Parsed 100/100. |
| `gpt-oss-safeguard-20b` strict HSD | 0.7339 | 0.8163 | 0.6667 | 0.7581 | 96.64s | Similar quality, slower. |
| `qwen/qwen3-4b` strict HSD | 0.8197 | 0.8065 | 0.8333 | 0.7629 | 83.05s | Strong quality, slower than `gpt-oss-20b`. |
| `google/gemma-4-e2b` strict HSD | 0.8205 | 0.8421 | 0.8000 | 0.7960 | 193.20s | Strong quality, structurally less stable and slow. |
| `qwen/qwen3.5-9b` strict HSD | 0.6538 | 0.7727 | 0.5667 | 0.6842 | 557.02s | Not suitable here. |
| `shieldgemma-2-4b-it` | n/a | n/a | n/a | n/a | n/a | Failed structured tool-call parsing. |

PII findings:

- Deterministic baseline: 74 identifiers before, 0 identifiers after, 0 direct PII after, target retention 1.0.
- LLM-only PII scrub with `openai/gpt-oss-20b`: 24 identifiers left, including 13 direct PII and 8 high-confidence direct identifiers.
- Combined `gpt-oss-20b` HSD plus residual PII suggestions on cleaned text:
  - Parsed 100/100, no fallback, 68.92s.
  - HSD F1 0.7667, precision 0.7667, recall 0.7667.
  - 54 PII suggestions across 49 rows.
  - 35 suggestions survived basic exact-substring/non-placeholder/non-protected filtering.
  - Survivor precision against expected remaining privacy was about 0.3714.
  - Recall against expected remaining privacy was about 0.5.

Conclusion: use the LLM for opt-in HSD classification and review cues. Do not use it as an automatic PII scrubber.

## 800-Row Live Pipeline Validation

The local LLM backend was exercised end-to-end on
`workbench/demo/curated_hsd_training.csv` after implementation.

Command shape:

```bash
python -m contextsafe_hsd.cli sanitize-classify \
  --input workbench/demo/curated_hsd_training.csv \
  --output data/outputs/llm_hsd_review_integration/curated_hsd_training.local_llm.csv \
  --text-col text \
  --id-col author_id \
  --hsd-classification-backend local-llm \
  --local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
  --local-llm-model openai/gpt-oss-20b \
  --local-llm-batch-size 10 \
  --require-hate-classification \
  --manifest data/outputs/llm_hsd_review_integration/curated_hsd_training.local_llm.manifest.json
```

Live endpoint compatibility finding:

- LM Studio rejected object-form `tool_choice` and `response_format: json_object`.
- The runtime now sends `tool_choice: "required"` and uses JSON Schema for the
  non-tool fallback path.

Live run summary:

| Metric | Value |
| --- | ---: |
| Rows | 800 |
| Parse count | 800 |
| Skipped count | 0 |
| Request count | 100 |
| Batch fallback rows | 20 |
| LLM elapsed time | 280.907s |
| Output validation | valid |
| Prediction counts | 353 non-HSD, 447 HSD |
| PII suggestions | 2 accepted for review, 11 rejected placeholders, 6 rejected protected/HSD cues |

Against the fixture `hsd_answer`, the first deployed prompt was too aggressive:

| Prompt | Accuracy | Precision | Recall | F1 | FP | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial deployed prompt | 0.6225 | 0.3893 | 0.8571 | 0.5354 | 273 | 29 |

The dataset does contain the edge cases needed for this validation:

- 86 `manual_edge` rows.
- Direct protected-group attacks.
- Quoted or reported hateful phrases.
- Counterspeech and negation.
- Threat words attached to persons or locations.
- Handles, emails, phone-like strings, URLs, placeholders, case/card IDs.
- Long rows and very short rows.

Failure artifacts committed for tuning:

- `docs/planning/llm_hsd_review_integration/live_llm_failure_subsample.csv`
  - 302 rows where the initial local LLM prompt disagreed with `hsd_answer`.
  - Cleaned text only; no duplicated raw pre-cleaning text.
- `docs/planning/llm_hsd_review_integration/prompt_tuning_failure_subset.csv`
  - 99-row focused subset containing all manual-edge failures, all false
    negatives, and a spread of false positives by source.
- `docs/planning/llm_hsd_review_integration/prompt_tuning_results.json`
  - Failure-subset prompt comparison.
- `docs/planning/llm_hsd_review_integration/prompt_tuning_full_results.json`
  - Full 800-row prompt comparison for the best candidates.

## Selected Prompt Version

Four prompt variants were tested against the failure-focused subset. The best
subset fixer was `v2_context_first`, but it traded away too much recall on the
full 800-row evaluation.

Full cleaned-row comparison:

| Prompt | Accuracy | Precision | Recall | F1 | FP | FN | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Initial deployed prompt | 0.6225 | 0.3893 | 0.8571 | 0.5354 | 273 | 29 | High recall, too many quote/report false positives. |
| `v1_endorsement_rule` | 0.7325 | 0.4832 | 0.7783 | 0.5962 | 169 | 45 | Best F1 and much lower false-positive load. |
| `v2_context_first` | 0.7638 | 0.5289 | 0.6305 | 0.5753 | 114 | 75 | Best accuracy, but recall drop is too large. |
| `v1_endorsement_rule` final CLI run | 0.7225 | 0.4711 | 0.7635 | 0.5827 | 174 | 48 | Actual `sanitize-classify` run after wiring prompt into runtime. |

Selected prompt: `v1_endorsement_rule`.

```text
Classify cleaned text for a hate-speech dataset. Hate speech means the text
itself endorses, advocates, commands, or asserts abuse, inferiority, exclusion,
dehumanization, or violence against a protected identity group. Return
hate=false for quotations, reports, moderation requests, condemnation,
counterspeech, negation, hypotheticals, questions, or examples that mention
hateful words without endorsing them. Offensive profanity without a protected
target is not HSD. Return binary labels, allowed reason tags, exact residual
PII substrings only, and no confidence or explanation.
```

Reasoning:

- It improved F1 by about 0.061 in the isolated prompt sweep and about 0.047
  in the final CLI run, compared with the initial prompt.
- It reduces false positives by 104 while preserving better recall than the
  stricter `v2_context_first` variant.
- It explicitly encodes the key failure mode from the manual edge cases:
  quote/report/counterspeech text should not become HSD unless the speaker is
  endorsing the hateful content.
- The final CLI run with the selected prompt parsed 800/800 rows, skipped 0,
  and reached 0.9186 accuracy on the 86 manual edge rows.

## Non-Goals

- Do not replace deterministic PII removal.
- Do not send raw input text to the LLM.
- Do not ask the LLM to rewrite, sanitize, or mask the sentence.
- Do not apply residual PII suggestions automatically in this MVP.
- Do not use confidence scores from the LLM. Use structured reason tags, parse status, and downstream metrics instead.
- Do not make local LLM classification the default official submission path.
- Do not add external hosted API dependencies for official mode.

## Target Pipeline Shape

```text
raw input
  -> deterministic PII / target-aware cleaner
  -> sanitized output text
  -> HSD classification backend
       -> ml backend: existing HSD advisory classifier
       -> local_llm backend: binary HSD classification + reason tags + PII suggestions
  -> output CSV / manifest / audit
```

The local LLM receives only `sanitized output text`.

## Expected Product Behavior

Default behavior must remain unchanged:

- Existing automatic sanitization still runs deterministically.
- Token-policy ensemble remains disabled unless explicitly enabled for research.
- Existing ML HSD classification remains the default for `sanitize-classify`.

When `local_llm` is selected:

- The system calls the configured LM Studio endpoint.
- Each cleaned row receives a binary HSD classification:
  - `1` means hate speech.
  - `0` means not hate speech.
- Each classification can carry structured reason tags.
- Residual PII suggestions are stored as review metadata.
- Suggestions are never applied to the text in this phase.

## LLM Output Contract

Use structured tool calling when available. The model should return one item per input row.

Suggested schema:

```json
{
  "items": [
    {
      "id": "row-1",
      "hate": true,
      "hsd_reasons": ["protected_target", "identity_attack"],
      "pii_leftover": ["exact substring still visible in cleaned text"],
      "review_needed": true
    }
  ]
}
```

Allowed HSD reason tags:

- `protected_target`
- `identity_attack`
- `dehumanization`
- `threat`
- `exclusion`
- `inferiority_claim`
- `quote_or_report`
- `counterspeech`
- `ambiguous_context`
- `none`

Rules:

- `hate` is required and must be boolean.
- `id` is required and must match an input row id.
- `hsd_reasons` is required. Use `["none"]` when there is no hate-related reason.
- `pii_leftover` must contain exact substrings from the cleaned text only.
- Do not include explanations or rewritten text.
- Do not include confidence.

## Residual PII Suggestion Handling

The local LLM may propose residual PII strings, but the pipeline must validate and classify those suggestions deterministically.

Suggestion validation should produce one of:

- `accepted_for_review`
- `rejected_not_substring`
- `rejected_placeholder`
- `rejected_protected_or_hsd_cue`
- `rejected_too_broad`
- `rejected_duplicate`
- `rejected_empty`

Minimum filters:

- Reject suggestions that are not exact substrings of the cleaned text.
- Reject placeholders like `[NAME]`, `<EMAIL>`, `PERSON`, `PHONE`, or labels instead of actual visible substrings.
- Reject protected classes, local minority names, nationalities, religions, ethnic groups, political/identity target groups, slurs, hate actors, threat/action words, and HSD cue phrases.
- Reject suggestions that overlap already-known protected target spans or HSD cue spans.
- Reject suggestions that are too long or look like an entire sentence.
- Deduplicate suggestions per row.

For MVP:

- Store accepted suggestions as review metadata only.
- Do not change sanitized text.
- Do not add a reviewer approval UI yet.
- Preserve traceability so a future reviewer profile can decide whether to apply suggestions.

Future reviewer profile can add:

- `apply_accepted_pii_suggestions=false` by default.
- Reviewer-visible suggestion queue.
- Reviewer action: accept/reject suggestion.
- Audit trail with reviewer id, timestamp, suggestion phrase hash, action, and final text diff.

## Traceability Design

Store enough metadata to make later reviewer decisions possible without making the official audit leak raw input.

Per-row review metadata should include:

- row id
- HSD backend name
- HSD model id
- parsed status
- binary HSD label
- reason tags
- `review_needed`
- PII suggestion count
- suggestion records

Suggestion record fields:

- `text`: exact cleaned-text substring, only in local/debug review artifacts.
- `text_hash`: SHA-256 or existing project hash helper for summary/official artifacts.
- `start`: character offset in cleaned text when exact match exists.
- `end`: character offset in cleaned text when exact match exists.
- `validator_status`
- `rejection_reasons`
- `source`: `local_llm`
- `model_id`

Official or summary manifests should avoid raw suggestion text unless the existing audit level explicitly allows row/debug review artifacts. Prefer hashes and counts in official summaries.

## Configuration Plan

Extend `AutoPipelineConfig` with explicit backend and local LLM settings.

Suggested fields:

```python
hsd_classification_backend: str = "ml"
local_llm_endpoint: str = "http://localhost:1234/v1/chat/completions"
local_llm_model: str = "openai/gpt-oss-20b"
local_llm_timeout_seconds: float = 120.0
local_llm_batch_size: int = 10
local_llm_enable_pii_suggestions: bool = True
local_llm_require_structured_output: bool = True
```

Allowed `hsd_classification_backend` values:

- `ml`
- `local_llm`

Keep `local_llm_enabled` only if it remains useful internally, but derive behavior from `hsd_classification_backend == "local_llm"` where possible.

Discovery behavior:

- `local_llm` should be disabled unless selected.
- If selected, report endpoint/model configuration in `model_status`.
- Loading should be lazy.
- Runtime should fail closed into skipped classification unless `require_hate_classification=True`.

## CLI Plan

Add flags to the analysis/classification path, not to the official path by default.

Suggested flags:

```text
--hsd-classification-backend {ml,local-llm}
--local-llm-endpoint URL
--local-llm-model MODEL_ID
--local-llm-timeout-seconds FLOAT
--local-llm-batch-size INT
--disable-local-llm-pii-suggestions
```

Map CLI value `local-llm` to internal backend `local_llm`.

Existing `--require-hate-classification` should apply to both backends:

- If ML backend is selected and unavailable, fail.
- If local LLM backend is selected and unavailable/unparseable, fail when required.
- If not required, leave HSD columns empty and record skip reason.

## Code Integration Points

Likely files:

- `contextsafe_hsd/auto/config.py`
- `contextsafe_hsd/auto/context.py`
- `contextsafe_hsd/auto/model_registry.py`
- `contextsafe_hsd/simple_pipeline.py`
- `contextsafe_hsd/cli.py`
- `contextsafe_hsd/submission.py`
- `workbench/backend/app.py`
- `workbench/frontend/src/main.jsx`
- `workbench/frontend/src/styles.css`
- new `contextsafe_hsd/models/local_llm_hsd_review_runtime.py`
- new tests under `tests/`

Current facts:

- `AutoPipelineConfig.local_llm_enabled` exists but is not wired to a runtime.
- `discover_local_llm()` currently returns disabled/not_configured statuses.
- `AutoPipelineContext._load_model()` does not load `local_llm`.
- `append_hate_classification()` currently calls `context.ensure_hsd_advisory()` and scores original plus sanitized text.

Required behavior change:

- Add a backend router in `append_hate_classification()`.
- ML backend keeps existing behavior.
- Local LLM backend must classify sanitized text only.
- Local LLM backend should not score original text or compute original/sanitized drift.
- The candidate drift check inside the auto sanitization engine should continue using the existing ML advisory runtime for now, because it compares original/candidate text and the local LLM must not see raw original text.

## Runtime Design

Create a local LLM structured review runtime with an interface similar to:

```python
class LocalLlmHsdReviewRuntime:
    def review_texts(
        self,
        rows: list[dict[str, str]],
        *,
        batch_size: int,
    ) -> LocalLlmReviewResult:
        ...
```

Input rows should contain:

- stable row id
- cleaned text only

Output should contain:

- labels
- reason tags
- validated suggestion records
- model id
- parse counts
- fallback counts
- elapsed time
- errors/skips

Recommended request strategy:

- Use OpenAI-compatible `/v1/chat/completions`.
- Use tool calling schema first.
- Set temperature low or zero if supported.
- Batch small groups, for example 5-10 rows.
- If batch parsing fails, retry individual rows.
- If individual row parsing fails, mark row skipped and record error class.
- Do not put raw input text or raw original text in logs/manifests.

## Dashboard/Reviewer Output

The dashboard should show model-assisted signals without implying the LLM directly changed text.

Recommended columns/metadata:

- HSD label
- HSD backend
- HSD model id
- reason tags
- review needed
- PII suggestion count
- PII suggestion validation summary

Avoid:

- Free-form LLM explanations.
- LLM confidence.
- Automatic "remove this" actions.
- Showing protected group names as PII suggestions.

## Workbench GUI Plan

The local workbench must be updated with the pipeline feature. The workbench is
the public/demo surface for CSV review, so backend support alone is not enough.

Primary files:

- `workbench/backend/app.py`
- `workbench/frontend/src/main.jsx`
- `workbench/frontend/src/styles.css`
- `tests/test_workbench_csv.py`
- `docs/runbooks/workbench.md`
- `workbench/README.md`

Backend requirements:

- Add CSV request options for HSD classification backend:
  - `hsd_classification_backend`, accepting `ml` and `local_llm`.
  - local LLM endpoint/model/batch-size/timeout settings.
  - flag to disable residual PII suggestions.
- Include these options in the CSV cache key so ML and local LLM runs do not
  reuse each other's cached results.
- Pass the options into `AutoPipelineConfig`.
- Return backend/model/suggestion metadata in the CSV response, manifest, and
  platform insight payload.
- Keep raw original text out of review annotations and cache metadata.
- Keep local LLM disabled in default workbench options.
- Report local LLM availability/configuration from `/api/model-status` without
  making a live model call.

Frontend requirements:

- Add a backend selector in the CSV intake controls:
  - ML classifier/default.
  - Local LLM review.
- Show local LLM endpoint/model fields only when local LLM is selected.
- Add a toggle for residual PII suggestions when local LLM is selected.
- Show the selected HSD backend in the dashboard status area and technical audit
  strip.
- In the Review Queue, show HSD reason tags and residual PII suggestion counts
  for each queued row when present.
- In Reports, include local LLM parse/fallback/suggestion summaries when present.
- Do not add controls that let the reviewer apply LLM suggestions yet.
- Do not present LLM output as an automatic moderation or masking decision.

## Protected Target and Local Minority Handling

Protected target detection and retention should remain deterministic and lexicon/provider based where possible. The LLM can add `protected_target` as a reason tag, but it must not decide that a protected group name is PII to remove.

This matters for local groups and minority names such as Kurds, local Slavic groups, regional ethnic groups, religious groups, caste/tribal groups, and other protected or socially targeted identities.

Implementation requirements:

- Maintain or extend deterministic target lexicons separately from PII lexicons.
- Treat protected target terms as HSD context, not PII.
- Reject residual PII suggestions that are protected target terms or hate-cue terms.
- Keep target terms available to reviewers so they can understand why a row was classified as hate.

## Tests

Add tests with fake runtimes and mocked responses. Do not require a live LM Studio server in unit tests.

Minimum coverage:

- Default config still selects ML backend.
- `local_llm` backend is disabled unless explicitly selected.
- CLI flag maps `local-llm` to backend `local_llm`.
- Local LLM backend classifies sanitized text only.
- Raw original text is not passed to the local LLM runtime.
- Structured tool-call response parses correctly.
- Malformed batch response retries per row.
- Unparseable rows are skipped unless classification is required.
- Suggestions are not applied to sanitized text.
- Suggestion validator rejects placeholders.
- Suggestion validator rejects non-substrings.
- Suggestion validator rejects protected target/HSD cue strings.
- Suggestion validator deduplicates repeated suggestions.
- Manifest/audit include counts and hashes without leaking raw original text.
- Existing ML backend output remains unchanged.
- Workbench CSV requests can select the ML backend and keep current behavior.
- Workbench CSV requests can select the local LLM backend through a fake runtime.
- Workbench CSV cache keys differ between ML and local LLM runs.
- Workbench CSV response includes local LLM reason/suggestion metadata when
  present.
- Workbench review annotations still store structured labels only, not raw text.
- Frontend builds after adding backend selector and review/report summary UI.

Suggested test commands:

```bash
python -m pytest tests/test_auto_pipeline.py tests/test_simple_pipeline.py tests/test_submission.py -q
python -m pytest tests/test_local_llm_hsd_review_runtime.py tests/test_local_llm_hsd_suggestions.py -q
python -m pytest tests/test_workbench_csv.py -q
npm --prefix workbench/frontend run build
```

CSV smoke tests after implementation:

```bash
python -m contextsafe_hsd.cli sanitize-classify \
  --input workbench/demo/curated_hsd_training.csv \
  --output data/outputs/llm_hsd_review_integration/curated_hsd_training.ml.csv \
  --text-col text \
  --id-col author_id \
  --hsd-classification-backend ml \
  --manifest data/outputs/llm_hsd_review_integration/curated_hsd_training.ml.manifest.json
```

If LM Studio is running, also run:

```bash
python -m contextsafe_hsd.cli sanitize-classify \
  --input workbench/demo/curated_hsd_training.csv \
  --output data/outputs/llm_hsd_review_integration/curated_hsd_training.local_llm.csv \
  --text-col text \
  --id-col author_id \
  --hsd-classification-backend local-llm \
  --local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
  --local-llm-model openai/gpt-oss-20b \
  --local-llm-batch-size 10 \
  --require-hate-classification \
  --manifest data/outputs/llm_hsd_review_integration/curated_hsd_training.local_llm.manifest.json
```

## Dead Code Cleanup

After implementing the feature, run Python dead-code and unused-code tools over
the changed backend/pipeline areas.

Project dev dependencies already include:

- `ruff`
- `pyflakes`
- `vulture`

Suggested commands:

```bash
python -m ruff check contextsafe_hsd workbench/backend tests
python -m pyflakes contextsafe_hsd workbench/backend tests
python -m vulture contextsafe_hsd workbench/backend tests --min-confidence 90
```

Cleanup rules:

- Remove confirmed unused imports, variables, helper functions, and stale code
  introduced or made obsolete by the LLM backend work.
- Prefer targeted cleanup in touched modules.
- Do not perform broad refactors unrelated to this integration.
- Treat `vulture` output as review evidence, not an automatic delete list.
- If a finding is a false positive because of framework reflection, CLI entry
  points, tests, or Pydantic/FastAPI usage, leave it and note it in the handoff.

## Acceptance Criteria

- Existing default pipeline behavior is unchanged.
- `sanitize-classify` can run with the ML backend exactly as before.
- `sanitize-classify --hsd-classification-backend local-llm` uses cleaned text only.
- Local LLM backend emits binary HSD labels and reason tags.
- Local LLM residual PII suggestions are validated and stored, but never applied.
- Local LLM failures are visible in manifest/audit summaries.
- `--require-hate-classification` fails correctly for both backends.
- Workbench GUI exposes the backend choice and local LLM review metadata without
  allowing automatic suggestion application.
- Workbench CSV endpoint and cache behavior are covered by tests.
- A small CSV smoke run is executed for ML, and a local LLM CSV smoke run is
  executed when LM Studio is available.
- Python unused/dead-code checks are run, and confirmed dead code from the
  implementation is removed.
- Official submission mode remains deterministic unless explicitly expanded later.
- The implementation includes tests that do not require live LLM access.

## Commit And Push

After implementation and verification:

- Review `git status --short` and avoid committing unrelated existing changes.
- Run `git diff --check`.
- Commit only files touched for this integration.
- Use a clear commit message, for example
  `Add local LLM HSD review backend`.
- Push the branch.
- If push fails because the branch has no upstream or credentials are missing,
  report the exact command/output needed to finish.

## Open Follow-Ups

- Decide whether `qwen/qwen3-4b` should be the quality-oriented local LLM option after a larger benchmark.
- Add a larger multilingual/protected-group benchmark with local minority names.
- Re-evaluate the selected `v1_endorsement_rule` prompt on a larger holdout,
  especially false-negative-sensitive hate rows.
- Add a reviewer profile that can make deterministic decisions over accepted suggestions.
- Decide whether raw suggestion strings are allowed in local dashboard artifacts or only in debug audit mode.
- Add dashboard UX for suggestion review after MVP.
