# Implementation Prompt: Local LLM HSD Review Backend

You are working in `/home/bati/projects/PrivHSD-Challenge`.

Read `docs/planning/llm_hsd_review_integration/plan.md` first. Implement the planned local LLM HSD review backend without changing the default official behavior.

## Objective

Add an opt-in local LLM backend for post-PII-cleaning HSD classification and residual PII suggestions.

The pipeline must support:

1. Deterministic PII removal first, always.
2. HSD classification backend `ml`, preserving the current classifier behavior.
3. HSD classification backend `local_llm`, using cleaned text only.
4. Advisory residual PII suggestions from the LLM, validated deterministically and stored for review metadata only.
5. Workbench GUI support for selecting the backend and viewing local LLM review metadata.

Do not implement reviewer approval UI yet. Keep suggestion records traceable so a future reviewer profile can decide whether to apply them.

## Constraints

- Do not send raw pre-cleaning text to the local LLM.
- Do not let the LLM rewrite text.
- Do not let the LLM directly remove or mask text.
- Do not apply PII suggestions automatically.
- Do not ask for or store LLM confidence.
- Use reason tags instead of confidence.
- Keep the default backend as the current ML classifier.
- Keep official submission behavior deterministic by default.
- Do not require LM Studio for unit tests.
- Do not break token-policy ensemble default-off behavior.

## Benchmarked Recommendation

Use `openai/gpt-oss-20b` as the practical MVP local LLM default because it parsed cleanly and improved strict hate/not-hate classification versus the current ML classifier in the 100-row benchmark.

Keep model and endpoint configurable. Do not hardcode the user's network endpoint as the only value.

After the 800-row live pipeline run, use the endorsement/context prompt below
as the default local LLM system prompt. It was selected over the initial prompt
because it improved full-set F1 from about 0.535 to 0.596 and reduced false
positives from 273 to 169 while keeping recall higher than the stricter
context-first prompt in the isolated prompt sweep. After wiring it into the CLI
runtime, the final live `sanitize-classify` run reached F1 0.5827 with 174
false positives, 48 false negatives, 800/800 parsed rows, and 0 skipped rows.

Follow-up testing with the Unsloth Qwen 3.5 4B checkpoint, exposed by LM Studio
as `qwen3.5-4b`, used the same prompt, 8k context, and temperature `0`. It
parsed 800/800 rows with only 10 fallback rows and improved accuracy/precision
over the GPT-OSS selected-prompt run, but full-set F1 was slightly lower
because recall dropped: accuracy 0.7538, precision 0.5116, recall 0.6502,
F1 0.5727, 126 false positives, 71 false negatives. Keep GPT-OSS as the
default until Qwen gets a prompt or validator pass, especially because Qwen
emitted 49 accepted residual PII suggestions versus 1 for the GPT-OSS final
run.

One additional Qwen candidate, `qwen/qwen3-4b-2507`, was tested only on the
99-row failure-focused gate. It parsed 99/99 rows but needed 20 fallback rows,
fixed only 38 prior failures, and scored F1 0.1867 on the failure subset, so no
full 800-row run was executed.

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

## Expected LLM Contract

The local LLM receives batches of cleaned rows only.

Use OpenAI-compatible `/v1/chat/completions` tool calling when available. The tool/function should return:

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

Allowed reason tags:

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

Validation rules:

- `hate` must be boolean.
- `id` must match an input row id.
- `hsd_reasons` must use only allowed tags.
- `pii_leftover` values must be exact substrings of cleaned text before they can be accepted for review.
- Suggestions that are placeholders, non-substrings, protected targets, HSD cues, slurs, hate actors, action words, or full-sentence spans must be rejected.

## Files To Inspect

Start with:

- `contextsafe_hsd/auto/config.py`
- `contextsafe_hsd/auto/context.py`
- `contextsafe_hsd/auto/model_registry.py`
- `contextsafe_hsd/simple_pipeline.py`
- `contextsafe_hsd/cli.py`
- `contextsafe_hsd/submission.py`
- `workbench/backend/app.py`
- `workbench/frontend/src/main.jsx`
- `workbench/frontend/src/styles.css`
- `tests/test_workbench_csv.py`
- existing tests under `tests/`

Likely new files:

- `contextsafe_hsd/models/local_llm_hsd_review_runtime.py`
- `tests/test_local_llm_hsd_review_runtime.py`
- `tests/test_local_llm_hsd_suggestions.py`

Do not reuse any existing local LLM rewrite path as-is if it asks the model to rewrite or sanitize text. This feature is structured review only.

## Implementation Steps

1. Add config fields:
   - `hsd_classification_backend: str = "ml"`
   - `local_llm_endpoint: str = "http://localhost:1234/v1/chat/completions"`
   - `local_llm_model: str = "openai/gpt-oss-20b"`
   - `local_llm_timeout_seconds: float = 120.0`
   - `local_llm_batch_size: int = 10`
   - `local_llm_enable_pii_suggestions: bool = True`
   - `local_llm_require_structured_output: bool = True`

2. Validate allowed backend values:
   - `ml`
   - `local_llm`

3. Extend model discovery:
   - Keep local LLM disabled unless selected.
   - Report endpoint/model config in raw-text-free status metadata.
   - Make loading lazy.

4. Add `AutoPipelineContext.ensure_local_llm_review()` and `_load_model("local_llm")`.

5. Implement `LocalLlmHsdReviewRuntime`:
   - Use OpenAI-compatible chat completions.
   - Prefer tool calling.
   - Send `tool_choice: "required"` for LM Studio compatibility.
   - Use JSON Schema response format for the non-tool fallback path.
   - Batch cleaned rows.
   - Retry malformed batch responses per row.
   - Return structured labels, reason tags, suggestion validation records, parse counts, fallback counts, and status metadata.
   - Keep tests isolated through an injectable client or request callable.

6. Add suggestion validator:
   - Accept only exact cleaned-text substrings for review.
   - Reject placeholders.
   - Reject protected targets and HSD cue terms.
   - Reject duplicate, empty, too-long, and full-sentence suggestions.
   - Do not apply suggestions to text.

7. Refactor `append_hate_classification()`:
   - Route by `context.config.hsd_classification_backend`.
   - Existing `ml` backend should preserve current behavior.
   - New `local_llm` backend should classify sanitized/output rows only.
   - Local LLM backend should not compute original/sanitized drift because that would require raw original text.

8. Add CLI flags:
   - `--hsd-classification-backend {ml,local-llm}`
   - `--local-llm-endpoint URL`
   - `--local-llm-model MODEL_ID`
   - `--local-llm-timeout-seconds FLOAT`
   - `--local-llm-batch-size INT`
   - `--disable-local-llm-pii-suggestions`

9. Preserve `--require-hate-classification` semantics:
   - If backend is unavailable and classification is required, fail.
   - If backend is unavailable and classification is optional, leave classification columns empty and record skip reason.

10. Add manifest/audit summaries:
    - backend
    - model id
    - endpoint host or endpoint string if existing policy allows it
    - parse count
    - fallback count
    - skipped count
    - HSD prediction counts
    - reason tag counts
    - PII suggestion counts by validator status
    - no raw original text

11. Update the workbench backend:
    - Add CSV request fields for HSD backend, local LLM endpoint/model/batch size/timeout, and PII suggestion toggle.
    - Include these settings in the CSV cache key.
    - Pass these settings into `AutoPipelineConfig`.
    - Return backend/model/reason/suggestion metadata in the CSV response, manifest, and platform insights.
    - Keep local LLM disabled by default.
    - Keep raw original text out of review annotations and cache metadata.
    - Extend `/api/model-status` so the GUI can display local LLM config/availability without making a live model call.

12. Update the workbench frontend:
    - Add a CSV intake backend selector for ML classifier/default versus local LLM review.
    - Show local LLM endpoint/model fields only when local LLM is selected.
    - Add a residual PII suggestion toggle for local LLM mode.
    - Show selected backend and model in dashboard/status/audit surfaces.
    - Show HSD reason tags and residual PII suggestion counts in the Review Queue when present.
    - Show parse/fallback/suggestion summaries in Reports when present.
    - Do not add accept/apply controls for suggestions yet.
    - Do not present LLM output as an automatic moderation or masking decision.

13. Run Python dead-code cleanup/checks:
    - Use `ruff`, `pyflakes`, and `vulture`; they are already in the project's dev dependencies.
    - Remove confirmed unused imports, variables, helpers, and stale paths introduced or made obsolete by this work.
    - Prefer targeted cleanup in touched modules.
    - Do not do broad unrelated refactors.
    - Treat `vulture` as review evidence, not an automatic delete list.
    - Leave framework/CLI/FastAPI/Pydantic false positives in place and note them in the final handoff.

14. Add tests. Unit tests must use fake clients/runtimes and must not require live LM Studio.

15. Commit and push after verification:
    - Check `git status --short`.
    - Do not commit unrelated pre-existing changes.
    - Run `git diff --check`.
    - Commit only files touched for this integration.
    - Use a clear commit message, for example `Add local LLM HSD review backend`.
    - Push the current branch.
    - If push fails because no upstream or credentials are configured, report the exact follow-up command/output.

## Tests To Add

Cover at least:

- Default config remains ML.
- `local-llm` CLI maps to `local_llm`.
- ML backend still calls the existing advisory runtime.
- Local LLM backend receives sanitized text only.
- Original raw text is not passed to the LLM fake runtime.
- Valid tool-call response parses into labels and reason tags.
- Malformed batch response retries per row.
- Parse failures skip rows unless `require_hate_classification=True`.
- PII suggestions are validated but not applied.
- Placeholder suggestions are rejected.
- Non-substring suggestions are rejected.
- Protected target or HSD cue suggestions are rejected.
- Duplicate suggestions are deduplicated.
- Manifest/audit contain counts/statuses without raw original text.
- Workbench CSV request can keep current ML behavior.
- Workbench CSV request can select local LLM using a fake runtime.
- Workbench CSV cache key changes when backend/model/endpoint options change.
- Workbench response includes local LLM reason and suggestion metadata when present.
- Workbench review annotations remain structured labels only, not raw text.
- Frontend build passes after adding controls and review/report summaries.

## Suggested Validation Commands

Run focused tests:

```bash
python -m pytest tests/test_auto_pipeline.py tests/test_simple_pipeline.py tests/test_submission.py -q
python -m pytest tests/test_local_llm_hsd_review_runtime.py tests/test_local_llm_hsd_suggestions.py -q
python -m pytest tests/test_workbench_csv.py -q
npm --prefix workbench/frontend run build
```

Run dead-code checks:

```bash
python -m ruff check contextsafe_hsd workbench/backend tests
python -m pyflakes contextsafe_hsd workbench/backend tests
python -m vulture contextsafe_hsd workbench/backend tests --min-confidence 90
```

Check CLI help:

```bash
python -m contextsafe_hsd.cli sanitize-classify --help
```

Optional live smoke test, only if LM Studio is running:

```bash
mkdir -p data/outputs/llm_hsd_review_integration

python -m contextsafe_hsd.cli sanitize-classify \
  --input workbench/demo/curated_hsd_training.csv \
  --output data/outputs/llm_hsd_review_integration/curated_hsd_training.ml.csv \
  --text-col text \
  --id-col author_id \
  --hsd-classification-backend ml \
  --manifest data/outputs/llm_hsd_review_integration/curated_hsd_training.ml.manifest.json

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

If the live smoke endpoint is unavailable, do not block the implementation. The ML CSV smoke and unit tests should still run.

Live prompt-tuning artifacts:

- `docs/planning/llm_hsd_review_integration/live_llm_failure_subsample.csv`
  contains all 302 initial local-LLM failures from the 800-row run.
- `docs/planning/llm_hsd_review_integration/prompt_tuning_failure_subset.csv`
  contains the 99-row focused tuning subset.
- `docs/planning/llm_hsd_review_integration/prompt_tuning_results.json`
  records prompt results on the failure subset.
- `docs/planning/llm_hsd_review_integration/prompt_tuning_full_results.json`
  records the complete 800-row comparison for the best prompt candidates.
- `docs/planning/llm_hsd_review_integration/qwen35_4b_results.json`
  records the `qwen3.5-4b` failure-subset and full-run comparison.
- `docs/planning/llm_hsd_review_integration/qwen35_4b_full_predictions.csv`
  records the cleaned-text-only full-run Qwen predictions.
- `docs/planning/llm_hsd_review_integration/qwen3_4b_2507_results.json`
  records the stopped-at-gate `qwen/qwen3-4b-2507` subset comparison.
- `docs/planning/llm_hsd_review_integration/qwen3_4b_2507_failure_subset_predictions.csv`
  records the cleaned-text-only gated subset predictions.

The selected default is `v1_endorsement_rule`, not `v2_context_first`, because
the latter won on accuracy but gave up too much HSD recall.

Author-group follow-up:

- Treat numeric `author` values as grouping keys, not direct names.
- Row-level masking remains the default privacy authority.
- Optional `--enable-author-group-masking` can be used on `protect`,
  `create-submission`, and `sanitize-classify`.
- The group pass should only mask detector-backed factual spans repeated across
  multiple rows from the same author and should preserve exact CSV shape.
- Do not use broad LLM batch rewriting for author style removal in MVP.
- If LLM author-batch review is explored later, keep it advisory: exact
  substrings only, deterministic validation, no automatic rewrite.

## Done Means

- Default runs are unchanged.
- The ML backend remains available as an alternative to LLM classification.
- The local LLM backend can classify cleaned rows and record validated PII suggestions.
- Residual PII suggestions are traceable but not applied.
- The workbench GUI exposes backend selection and local LLM metadata.
- CSV endpoint tests and at least one small CSV smoke run pass.
- Python dead-code and unused-code tools have been run; confirmed dead code has been removed.
- Tests pass without live LLM access.
- The manifest makes it clear which backend was used and whether parsing/fallback happened.
- The manifest records whether author-group masking was disabled, skipped, or
  applied when repeated author/user data exists.
- The integration commit has been created and pushed, or the push blocker is reported with exact next steps.
- The live endpoint compatibility fix and selected prompt are committed and
  pushed after the 800-row validation and failure-subset prompt tuning.
