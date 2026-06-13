# Roadmap

Date: 2026-06-13

## Implementation Note

The first implementation pass added `--mode auto` for exact submission,
anonymize, rerank, and the workbench CSV path. Auto mode now uses
`privhsd/auto/` for run-level context, local provider/model discovery,
row-level routing, candidate fusion/reranking, raw-text-free audit summaries,
and token-policy advisory batching. Exact submissions default to
`--metric-depth fast`; `sampled` and `deep` remain explicit local audit choices.
Optional components are local-only by default and fall back to deterministic
balanced output when dependencies or artifacts are missing.

## Implementation Audit And Readiness Snapshot

Audit date: 2026-06-13.

Current readiness: **hackathon demo ready with caveats**. The exact-format auto
pipeline works on the local tests and the ignored external TweetEval unseen
CSV, preserves schema, records provider/model status, and loads optional heavy
components once per run. It is not privacy-perfect. The remaining risks are
known, measurable, and should be disclosed in the run note before any official
upload.

### Verification Commands Run

Core verification:

```bash
python -m compileall privhsd workbench/backend
python -m pytest -q
cd workbench/frontend && npm run build
```

Result:

- `pytest -q`: 164 passed, 1 skipped.
- frontend production build passed.
- compile check passed.

Hardware and optional component check:

- GPU: NVIDIA GeForce RTX 5090 Laptop GPU, 24 GB class VRAM.
- PyTorch: CUDA available, one CUDA device.
- Installed locally: Presidio, torch, transformers.
- Missing locally: scrubadub, GLiNER, sentence-transformers, Detoxify.
- Local token-policy artifacts present:
  - `data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda/`
  - `data/outputs/token_policy_hatebert.action_balanced_train30000.cuda/`

Exact unseen-data auto run:

```bash
python -m privhsd.cli create-submission \
  --input data/external_unseen/tweet_eval_hate_offensive_test.csv \
  --output data/outputs/tweet_eval_hate_offensive_test.auto.audit_run.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --manifest data/outputs/tweet_eval_hate_offensive_test.auto.audit_run.manifest.json
```

Result:

- Runtime: 2:43 with Presidio plus local RoBERTa/HateBERT token-policy
  ensemble active.
- Exact validation: passed.
- Rows: 3,830 in, 3,830 out.
- Columns: unchanged exact input schema.
- Metric depth: `fast` for all rows.
- Provider/model load counts: Presidio loaded once; token-policy ensemble
  loaded once.
- Provider/model status:
  - deterministic ready;
  - Presidio ready;
  - scrubadub missing dependency;
  - GLiNER missing dependency;
  - token-policy ensemble ready;
  - semantic missing dependency;
  - HSD advisory missing artifact;
  - local LLM disabled.
- Candidate choices:
  - balanced: 1,487 rows;
  - provider-fusion augmented: 111 rows;
  - style-scrubbed: 1,353 rows;
  - token-policy candidate: 879 rows.
- Fast metric identifier count: 4,223 before, 6 after.
- Conservative cue check: 6 of 3,830 rows flagged cue loss, mostly
  negation/modality; no raw text is required to inspect those row IDs under
  ignored `data/outputs/`.

No-optional auto fallback run:

```bash
python -m privhsd.cli create-submission \
  --input data/external_unseen/tweet_eval_hate_offensive_test.csv \
  --output data/outputs/tweet_eval_hate_offensive_test.auto.no_optional.audit_run.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --disable-provider presidio \
  --disable-provider scrubadub \
  --disable-provider gliner \
  --disable-model token_policy_ensemble \
  --disable-model semantic \
  --disable-model hsd_advisory \
  --manifest data/outputs/tweet_eval_hate_offensive_test.auto.no_optional.audit_run.manifest.json
```

Result:

- Runtime: 10.42 seconds.
- Exact validation: passed.
- Rows: 3,830 in, 3,830 out.
- Metric depth: `fast` for all rows.
- No optional provider/model loads.
- Fast metric identifier count: 4,223 before, 11 after.

Adversarial stress fixture:

- Exact four-column schema `source,author_id,text,is_hate_speech` remained
  exact after `--mode auto --replace-text`.
- Runtime: 6.14 seconds with local token-policy artifacts loaded.
- Fast metrics reported 18 identifiers before and 0 after on the fixture.
- The fixture still exposed detector blind spots that metrics did not count:
  obfuscated email forms, Telegram-style aliases, short standalone names in
  threat context, and one overmasking case where a leading determiner was
  treated as a person-like span.

### Confirmed Working

- `--mode auto` exists for exact submission, anonymize, rerank, and workbench
  CSV paths.
- Exact-format CSV output preserves row count, row order, column order, and
  non-text columns when `--replace-text` is used.
- The four-column exact-shape regression is covered by tests.
- Missing optional dependencies and artifacts degrade to deterministic
  balanced output with manifest status rather than failing the run.
- GLiNER is not downloaded by default; optional downloads require
  `--allow-model-download`.
- Token-policy artifacts are advisory only: they produce span evidence that
  still goes through fusion, candidate scoring, and cue/privacy checks.
- Heavy token-policy models are loaded once per command run and inference is
  batched.
- Default exact submission metrics use the fast tier and avoid deep
  target-variant/profanity scans.
- Generated outputs, manifests, comparison files, and reports are under
  ignored `data/outputs/`.

### Remaining Vulnerabilities

1. **Residual direct identifiers remain on unseen data.** Auto with optional
   local providers/models reduced the fast metric residual direct count to 6,
   but not 0. This is acceptable for a hackathon demo only if reported honestly;
   it should not be described as complete anonymization.
2. **Detector blind spots are broader than the fast metric sees.** The
   adversarial fixture showed obfuscated email/handle patterns and short
   standalone names can survive while fast metrics still report zero residual
   identifiers.
3. **Cue checks found 6 conservative loss rows on unseen data.** Most were
   negation/modality. These row IDs should be reviewed before choosing the
   final submitted output.
4. **Source regression is still too slow.** The exact submission path is fast,
   but `source-regression-report` on the 3,830-row unseen output was
   interrupted after several minutes. That report likely still calls deeper
   row metrics and needs the same metric-depth split.
5. **Auto with token-policy is practical but not fast.** The exact no-optional
   path is about 10 seconds on 3,830 rows; the local GPU token-policy path is
   about 2:43. That is usable for a hackathon run, but not ideal for rapid
   iteration.
6. **Audit row samples are capped in summary mode.** This protects output size
   and raw-text risk, but a final challenge run may need `--audit-level row`
   under ignored `data/outputs/` for full row-level decision review.
7. **Presidio is loaded at context startup when available.** This satisfies
   one-load lifecycle rules but can add startup cost even if few rows are
   routed to providers.

### Recommendations Before Final Hackathon Submission

Do before final upload:

- Review the 6 unseen rows with residual direct identifier metrics.
- Review the 6 cue-loss row IDs from
  `data/outputs/tweet_eval_hate_offensive_test.auto.audit_run.cue_checks.json`.
- Decide whether the optional token-policy output improves the official score
  enough to justify the 2:43 runtime and 6 residual direct IDs, compared with
  the 10-second no-optional fallback and 11 residual direct IDs.
- Add targeted deterministic patterns for obfuscated email forms such as
  `[at]` / `dot`, Telegram/contact aliases, and short name-in-threat contexts.
- Apply metric-depth support to `source-regression-report` so source-slice
  validation does not regress into deep scans by default.

Next engineering steps:

- Add an adversarial synthetic regression suite for obfuscated contact info,
  short names, protected-target overlap, and style/cue interactions.
- Add a row-level repair queue command that emits only row IDs, warning codes,
  and candidate names for residual identifier and cue-loss rows.
- Add optional provider batching where provider APIs support it; current model
  inference is batched, but provider calls are row-local.
- Add a calibrated candidate threshold that can prefer provider/token-policy
  candidates for high-risk direct identifiers even when length drift is high,
  while still rejecting target/cue loss.
- Add source-regression fast metrics or sampled/deep controls.

Hackathon readiness statement:

The pipeline is ready for a hackathon demonstration and for producing an
auditable exact-format candidate. It should be presented as a local,
best-effort, evidence-preserving CSV privatization pipeline with documented
fallbacks and known residual-risk review queues, not as a guarantee that every
identifier is removed.

## Purpose Of This Document

This is the implementation roadmap for the next engineering agent. It is
self-contained and should be treated as the source of truth for the desired
direction of ContextSafe-HSD.

The user wants a single automatic, self-deciding CSV privatization pipeline.
The user does **not** want to manually enable Presidio, GLiNER, scrubadub,
token-policy models, semantic models, or other components row by row or command
by command. The system should discover available local components, keep heavy
models alive for the run, decide what each row needs, and still preserve exact
CSV shape for official submissions.

Do not read this roadmap as a claim that everything below already exists.
Some foundation pieces exist, but the full automatic pipeline must still be
implemented and tested.

## Mission

Build a local, auditable CSV-in/CSV-out privatization system for hate-speech
detection datasets.

The system receives a CSV, identifies or is told the text column, and writes a
CSV with:

- the same row count;
- the same row order;
- the same column order for exact-format submissions;
- the same IDs, labels, source/split fields, author IDs, and metadata;
- the selected text column replaced in place for exact-format output;
- no raw official examples in durable docs, commits, logs, or reports.

The system must reduce:

- direct identifiers: names, emails, handles, phones, URLs, IPs, case IDs,
  government/student IDs, and similar direct PII;
- quasi-identifiers: dates, ages, locations, schools, workplaces,
  organizations, addresses, and rare combinations;
- author-style signals: signatures, repeated stylometry, emoji/hashtag
  fingerprints, punctuation/casing idiolects, and repeated author cues.

The system must preserve hate-speech detection evidence:

- protected or vulnerable target identity terms;
- hostile actions;
- threats;
- dehumanization;
- exclusion;
- negation;
- modality;
- quotation/reporting;
- counterspeech;
- public-interest or institutional context;
- rationale spans when the dataset provides them.

This remains a preprocessing and evidence system. It is not a legal decision
system, not a moderation/takedown system, and not a production hate-speech
classifier.

## Non-Negotiable CSV Contract

The official path must always satisfy this contract before any upload:

- Input is a CSV with at least one text column.
- Output has the same row count and row order.
- Output preserves every non-text column exactly unless an explicit
  non-official local audit mode is selected.
- Exact-format output replaces the original text column in place.
- Local audit output may add `privatized_text`, audit JSON, or manifest files,
  but this must be opt-in and must never be used for exact official upload.
- A four-column input such as
  `source,author_id,text,is_hate_speech` must produce a four-column exact
  output with those exact columns, in that exact order, when
  `--replace-text` or official exact mode is used.
- IDs, labels, source/split columns, author IDs, and other metadata are
  preserved byte-for-byte.
- A manifest records command, commit, hashes, mode, metrics, provider status,
  model status, validation, and warnings.
- Raw official examples, generated sensitive rows, provider model outputs, and
  detailed reports stay under ignored `data/` paths.

## Current State

The codebase currently has:

- deterministic masking logic in `privhsd/detectors.py` and `privhsd/pipeline.py`;
- CSV processing, exact submission creation, and validation;
- source-aware reports, cue checks, semantic triage, author-risk experiments,
  token-policy experiments, DPMLM/local-LLM candidate experiments;
- a span-provider foundation under `privhsd/span_providers/`;
- a filtered Presidio provider;
- optional GLiNER and scrubadub provider wrappers;
- resource TOML files for target cues, utility cues, and source schemas;
- provider-enabled reranking;
- a FastAPI/React workbench with CSV upload/download.

Important current problem:

- The full CSV exact-format command became too slow after the provider/fusion
  work because manifest metrics can call expensive target-cue variant and
  external profanity detection on every row.
- Profiling showed the hot path was target-cue detection inside metrics,
  especially spaced variants, compact variant generation, and
  `better_profanity.contains_profanity`.
- Fix this before adding more automatic model orchestration. A self-deciding
  pipeline that cannot process the existing testing CSV quickly is not usable.

Current optional dependency reality in the local environment may vary. The
automatic pipeline must discover what is installed and what local model
artifacts exist, then degrade safely. It must not fail exact baseline output
because GLiNER, scrubadub, SentenceTransformers, Detoxify, cleanlab, Opacus, or
metadata-privacy libraries are missing.

## Desired End State

The default official command should become:

```bash
python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --manifest OUTPUT.manifest.json
```

`--mode auto` is the desired default once it passes acceptance. Until then,
`balanced` remains the safe compatibility mode.

The automatic pipeline should:

1. Load resources, providers, and local models once per run.
2. Process rows in batches where models are involved.
3. Run the deterministic baseline for every row.
4. Compute cheap privacy and cue features for every row.
5. Decide which rows need extra providers or models.
6. Run optional providers/models only for rows that need them, unless a full
   audit mode explicitly requests all providers for all rows.
7. Generate candidates per row.
8. Fuse spans and rerank candidates.
9. Pick the least destructive candidate that materially improves privacy.
10. Fall back to deterministic `balanced` when optional components are missing,
    slow, uncertain, disagreeing, or utility-damaging.
11. Preserve exact CSV shape.
12. Write a manifest and audit that explain decisions without raw text.

The pipeline is "automatic" in the sense that the user should not need to know
which provider to enable. It is **not** automatic in the sense of blindly
running every heavy model on every row. The pipeline itself decides when extra
components are needed.

## Target Architecture

Implement a run-level orchestration layer:

```text
CSV
  -> SchemaProfile
  -> AutoPipelineContext
       - ResourceCache
       - ProviderManager
       - ModelManager
       - CandidateGenerator
       - FusionPolicy
       - Reranker
       - MetricsEngine
  -> deterministic baseline for every row
  -> cheap row risk features
  -> row routing decisions
  -> optional provider/model batches
  -> fused candidate spans
  -> candidate generation
  -> cue/drift/privacy validation
  -> row-local selection
  -> exact-format CSV
  -> manifest + audit summary
```

Proposed modules:

```text
privhsd/auto/
  __init__.py
  config.py              AutoPipelineConfig and thresholds.
  context.py             Run-level caches, providers, models, device policy.
  engine.py              CSV/run orchestration and row batching.
  row_state.py           Row features, risk state, decisions, candidate state.
  routing.py             Cheap row decision rules.
  model_registry.py      Local model artifact discovery.
  audit.py               Raw-text-free audit summaries.

privhsd/span_providers/
  base.py                SpanProvider protocol and normalized span schema.
  deterministic.py       Existing regex/context detector adapter.
  presidio.py            Filtered Presidio provider.
  gliner.py              GLiNER provider.
  scrubadub_provider.py  scrubadub provider.
  token_policy.py        Token-policy span provider wrapper.
  llm_review.py          Structured local LLM review provider, optional.
  fusion.py              Overlap, thresholds, voting, cue conflict policy.
  registry.py            Provider discovery and lazy construction.

privhsd/models/
  token_policy_runtime.py  Load token-policy models once and batch inference.
  semantic_runtime.py      Optional SBERT/BERTScore/classifier drift scorers.
  hsd_runtime.py           Optional Cardiff/Detoxify advisory scorers.

privhsd/candidates/
  deterministic.py       balanced/privacy/style candidates.
  providers.py           candidate application from fused provider spans.
  token_policy.py        token-policy candidate application.
  dpmlm.py               protected-token DPMLM candidate path.
  santext.py             SanText candidate path if dependency exists.
  local_llm.py           constrained local LLM candidate path.

privhsd/evaluation/
  fast_metrics.py        Cheap metrics for every row.
  deep_metrics.py        Expensive cue/semantic/profanity metrics for audit.
  pii_benchmarks.py      TAB and synthetic PII reports.
  hsd_benchmarks.py      HateCheck/Hatemoji/MHS reports.
  label_quality.py       cleanlab and weak-label diagnostics.
  metadata_privacy.py    structured metadata privacy reports.
```

Keep existing public APIs and commands as compatibility wrappers while adding
the automatic path.

## Model And Provider Lifecycle Rules

Heavy components must be loaded at most once per run.

Rules:

- Do not instantiate Presidio, GLiNER, scrubadub, token-policy models,
  SentenceTransformers, Detoxify, or any local LLM client inside a per-row loop.
- Build an `AutoPipelineContext` once at command startup.
- Keep loaded models/providers on the context until the run finishes.
- Run model inference in batches when the model API supports batching.
- Use GPU only for neural model inference/training. Do not move regex/string
  scanning to GPU.
- If CUDA is available and a compatible local PyTorch model is used, choose GPU
  automatically unless config says CPU.
- If GPU model load fails, fall back to CPU or skip the model according to
  configured severity.
- If a model is missing, record `status=missing_artifact` and continue.
- If an optional dependency is missing, record `status=missing_dependency` and
  continue.
- If a provider/model errors during a batch, record the error class and route
  those rows back to deterministic baseline or review.
- Do not download model weights during official runs unless
  `--allow-model-download` is explicitly passed. Default must be local-only.
- Do not unload/reload models between rows.
- Do not keep raw text in provider/model audit payloads.

Provider/model cache design:

```text
AutoPipelineContext
  resource_cache:
    compiled direct identifier regexes
    compiled target cue regexes
    compiled utility cue regexes
    normalized target term variants
  provider_manager:
    deterministic: always available
    presidio: available if dependency and spaCy model initialize
    gliner: available if dependency and local/download-allowed model exists
    scrubadub: available if dependency initializes
  model_manager:
    token_policy_ensemble: available if model dirs and torch/transformers work
    local_classifier: available if classifier artifact exists
    semantic_scorers: available if dependencies and artifacts exist
    hsd_advisory: available if dependencies and artifacts exist
```

Acceptance test:

- A fake provider/model that increments a load counter must show exactly one
  load per run, not one load per row.
- A batch of 100 rows must call model inference in batches, not 100 separate
  model loads.

## Performance Rules

The pipeline must have two metric tiers:

### Fast Metrics

Fast metrics run on every row and must avoid expensive variant/profanity scans.
They should include:

- row changed flag;
- deterministic direct identifier counts before/after;
- deterministic quasi identifier counts before/after;
- placeholder counts;
- cheap target cue retention for explicit dictionary terms;
- cheap utility cue retention;
- character retention;
- length drift;
- provider/model decision status.

Fast metrics are enough for:

- exact submission manifest;
- progress reporting;
- row routing;
- basic regression summaries.

### Deep Metrics

Deep metrics are expensive and must be opt-in, sampled, or run only on risky
rows. They may include:

- target typo/obfuscation variants;
- spaced variants;
- external profanity/slur lexicon checks;
- semantic similarity;
- classifier drift;
- rationale span preservation;
- provider disagreement detail;
- benchmark-specific reports.

Deep metrics must not block the exact-format submission command by default.

Commands should distinguish:

```bash
--metric-depth fast      # default for create-submission
--metric-depth deep      # explicit expensive audit
--metric-depth sampled   # deep metrics on a bounded sample/risky rows
```

Acceptance targets:

- `create-submission --mode balanced --metric-depth fast` on
  `data/external_unseen/tweet_eval_hate_offensive_test.csv` must complete in a
  practical time on CPU. Set an initial target of under 30 seconds for 3,830
  rows on the current workstation.
- The same command on `data/public_dev/recommended_merged.csv` should be
  practical enough for iteration. Set an initial target of under 10 minutes for
  159,668 rows on CPU.
- Deep metrics may be slower, but must be explicit and must report estimated
  runtime/sample size.

## Row Routing Policy

Every row starts with deterministic `balanced`.

Compute a cheap `RowRiskProfile`:

```text
row_id
text_length
baseline_changed
direct_identifier_count_before
direct_identifier_count_after
quasi_identifier_count_before
quasi_identifier_count_after
placeholder_count
target_cue_count_before_fast
target_cue_retention_fast
utility_cue_retention_fast
style_risk_count
author_metadata_available
source
label
provider_needed_reasons
model_needed_reasons
review_reasons
```

Routing rules:

- Always use deterministic spans for direct identifiers.
- If deterministic output leaves residual direct identifiers, escalate to
  provider fusion.
- If the row contains likely quasi identifiers that deterministic confidence is
  low on, escalate to provider fusion.
- If the row has location/school/org/date/address-like phrases near personal
  disclosure, escalate to provider fusion.
- If a provider span overlaps protected target/action/negation cues, reject or
  downgrade it unless explicit privacy mode allows target generalization.
- If provider disagreement is high, keep baseline unless a direct identifier is
  clearly detected.
- If author-style risk is high and target/utility retention remains safe, add a
  style candidate.
- If a trained token-policy ensemble is available, run it on rows with:
  - residual identifier risk;
  - provider disagreement;
  - target/profanity ambiguity;
  - source types where deterministic false positives are known.
- If semantic/advisory models are available, run them on rewrite candidates and
  rows with potential cue loss, not on every easy row.
- If all optional systems are missing or fail, use deterministic baseline and
  record fallback status.

Decision result:

```text
chosen_candidate
chosen_reason
rejected_candidates
provider_status
model_status
fallback_status
review_recommended
```

Do not use an LLM rewrite as direct output. Local LLMs may provide structured
review spans or candidate rewrites only if they pass reranking and cue checks.

## Automatic Provider Policy

The automatic pipeline should discover and use providers in this order:

1. Deterministic provider: always enabled.
2. Presidio provider: enabled automatically if optional dependency initializes.
3. scrubadub provider: enabled automatically if installed.
4. GLiNER provider: enabled automatically if installed and model is available
   locally or downloads are explicitly allowed.
5. Token-policy provider: enabled automatically if local model artifacts exist
   and dependencies initialize.
6. Semantic/HSD advisory models: enabled automatically only if dependencies and
   artifacts exist, and only for candidate validation or sampled/deep audit.
7. Local LLM reviewer: disabled by default for official mode unless explicitly
   configured as local-only and structured JSON only.

Automatic does not mean "run all providers on all rows." It means "the user
does not manually choose providers; routing chooses when to call them."

Provider status must be written to the manifest:

```json
{
  "providers": {
    "deterministic": {"status": "ready"},
    "presidio": {"status": "ready"},
    "gliner": {"status": "missing_dependency"},
    "scrubadub": {"status": "missing_dependency"},
    "token_policy_ensemble": {"status": "ready", "device": "cuda"}
  }
}
```

## Token-Policy Integration

Current token-policy models are advisory but should become automatic advisory
providers when local artifacts are present.

Expected local artifacts:

```text
data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda/
  token_policy_metadata.json
  model.safetensors

data/outputs/token_policy_hatebert.action_balanced_train30000.cuda/
  token_policy_metadata.json
  model.safetensors
```

Tasks:

- Add `privhsd/span_providers/token_policy.py`.
- Wrap existing token-policy inference into a provider that emits normalized
  span candidates/actions:
  - `MASK_IDENTIFIER` -> privacy span evidence;
  - `PROTECT_TARGET` -> protected target evidence;
  - `PROTECT_HSD` -> protected utility/rationale evidence;
  - `NORMALIZE_STYLE` -> style candidate evidence;
  - `REVIEW` -> review routing evidence.
- Load tokenizer/model once per run.
- Batch rows.
- Keep ensemble members alive.
- Record model dirs, weights, device, action counts, skipped tokens, and errors
  in audit without raw text.
- Do not let token policy directly overwrite the text without deterministic
  fusion/reranking.

Acceptance:

- Existing token-policy tests pass.
- New runtime tests prove model load happens once per run.
- When model artifacts are missing, exact submission still succeeds with
  fallback status.
- Token-policy outputs cannot mask protected target terms unless fusion and cue
  policy allow it.

## Candidate Generation And Reranking

Candidate set for automatic mode:

- `balanced`: deterministic baseline; always present.
- `style_scrubbed`: deterministic plus style normalization; only considered
  when style risk exists.
- `privacy`: more aggressive target generalization; not default for official
  upload.
- `provider_fusion_augmented`: deterministic plus accepted provider spans.
- `token_policy_candidate`: only when local token-policy artifacts exist.
- `dpmlm_candidate`: only if dependencies/model exist and row is eligible.
- `santext_candidate`: only if dependency exists and row is eligible.
- `local_llm_candidate`: only local structured candidate, never external API,
  and never direct output.

Reranker hard rejects:

- output has residual direct identifiers when a safer candidate exists;
- output loses protected target terms in official/balanced mode;
- output loses action/negation/modality cues;
- output introduces new identifier-like strings;
- output has large length drift;
- output has severe semantic/classifier drift when those scorers are enabled;
- output has provider/model errors without safe fallback.

Reranker preferences:

- prefer least destructive candidate;
- prefer direct identifier reduction;
- prefer quasi identifier reduction only when target/utility retention remains
  safe;
- prefer style reduction only when not erasing HSD evidence;
- prefer baseline on uncertainty.

Audit must explain:

```text
row_id
chosen_candidate
candidate_count
accepted_provider_spans_by_provider
rejected_provider_spans_by_reason
model_actions_by_type
hard_reject_reasons
review_recommended
```

No raw row text in audit.

## Exact-Format Four-Column Acceptance Test

Add a dedicated test fixture with exactly these columns:

```text
source,author_id,text,is_hate_speech
```

Rows should include:

- one direct identifier row with email/handle/name;
- one protected-target hate row;
- one no-PII offensive row;
- one author-style row.

Test commands:

```bash
python -m privhsd.cli create-submission \
  --input four_col.csv \
  --output four_col.out.csv \
  --text-col text \
  --replace-text \
  --mode auto \
  --manifest four_col.manifest.json

python -m privhsd.cli validate-submission \
  --source four_col.csv \
  --submission four_col.out.csv \
  --text-col text
```

Assertions:

- output columns are exactly `source,author_id,text,is_hate_speech`;
- same row count and row order;
- `source`, `author_id`, and `is_hate_speech` unchanged;
- direct identifiers are masked;
- protected target terms are preserved in official/balanced auto mode;
- manifest says exact-format validation passed.

## CLI Design

Keep compatibility commands, but add automatic mode:

```bash
python -m privhsd.cli create-submission --mode auto ...
python -m privhsd.cli anonymize --mode auto ...
python -m privhsd.cli rerank-candidates --mode auto ...
```

New optional flags:

```text
--auto-profile                    write provider/model discovery report
--metric-depth fast|sampled|deep   default fast for exact submissions
--allow-model-download             default false
--device auto|cpu|cuda             default auto
--max-model-batch-size N
--max-provider-rows N              debugging limit only
--disable-provider NAME            escape hatch, not normal workflow
--disable-model NAME               escape hatch, not normal workflow
--audit-level summary|row|debug    default summary for official mode
```

Manual `--provider` flags may remain for experiments, but official docs should
teach `--mode auto`, not manual provider selection.

## Workbench Design

The first screen should be:

```text
Upload CSV -> configure columns -> run auto masking -> inspect summary -> download CSV
```

Workbench behavior:

- Default mode is `auto`.
- Provider/model status is shown, but not required for the user to choose.
- Advanced toggles may disable specific providers for debugging.
- Exact-format output is a clear option:
  "Replace text column, preserve original schema."
- Local-audit output is a clear option:
  "Add privatized_text helper column."
- Display aggregate metrics and provider/model statuses.
- Do not log raw text.
- Do not call external APIs.
- Do not load large models per row.

## Weak Supervision And Label Quality

After automatic provider/runtime is stable:

- Add `privhsd/evaluation/label_quality.py`.
- Use cleanlab only when installed.
- Report likely label issues using model probabilities plus existing labels.
- Do not auto-relabel official data.
- Keep reports under ignored `data/outputs/`.

Weak supervision tasks:

- Add optional `skweak` aggregation if installed.
- Aggregate deterministic, Presidio, GLiNER, scrubadub, token-policy, rationale,
  metadata-derived targets, and local LLM review spans.
- Emit probabilistic span labels and disagreement counts.
- Use high-confidence weak labels for token-policy training.
- Route high-disagreement rows to review.

## Semantic And HSD Drift

After automatic provider/runtime is stable:

- Add optional semantic scorers:
  - SentenceTransformers cosine;
  - BERTScore;
  - local project classifier;
  - Cardiff Twitter RoBERTa hate/offensive if locally available;
  - Detoxify if installed.
- Use these only as drift checks and reranker features.
- Do not let classifiers decide that protected group terms should be masked.
- Hard reject candidates that lose target/action/negation cues even if
  semantic score is high.

## DP And Rewrite Candidates

Keep DP and generative rewriting behind candidate generation/reranking.

DPMLM:

- load model once per run;
- batch where possible;
- freeze target terms, action cues, negation, modality, placeholders, and
  repeated-letter cue variants;
- reject unchanged, cue-losing, length-drifting, or identifier-introducing
  candidates;
- record epsilon, seed, changed tokens, rejected predictions, and validation.

SanText:

- implement only if dependency/source is available and license is acceptable;
- protect HSD cue tokens before substitution;
- never submit direct SanText output;
- route through reranking.

Opacus:

- use only for private training of advisory models;
- report epsilon/delta, clipping, noise multiplier, epochs, and batch size;
- this protects training, not released text.

## Metadata Privacy

Text masking is not enough when metadata identifies people or tiny groups.

Add optional reports:

- k-anonymity style counts over structured columns;
- l-diversity style counts for label/source combinations;
- t-closeness-style summaries if meaningful;
- diffprivlib/OpenDP aggregate reporting only if dependencies exist;
- metadata leakage scan for literal metadata values in text.

Official exact-format output must preserve required metadata columns unless the
challenge rules explicitly allow transformation.

## Benchmarks

Use existing testing data first:

- `data/external_unseen/tweet_eval_hate_offensive_test.csv`
- synthetic PII fixture tests;
- any official-style challenge test CSV under ignored `data/`.

Then add external benchmarks only after schema/license review:

- TAB for anonymization;
- HateCheck;
- HatemojiCheck/HatemojiBuild;
- Measuring Hate Speech;
- HateXplain rationale preservation;
- TweetEval hate/offensive.

Required reports for meaningful changes:

- fast privacy metrics before/after;
- deep sampled cue retention;
- source/label/split slice regression;
- provider span precision/recall when gold spans exist;
- candidate selection counts;
- classifier/semantic drift if enabled;
- exact-format validation;
- runtime and model/provider load counts.

## Implementation Phases

### Phase A: Repair Performance

Tasks:

- Split fast metrics from deep metrics.
- Add `--metric-depth`.
- Ensure `create-submission` uses fast metrics by default.
- Cache compiled regexes and normalized cue variants.
- Avoid `better_profanity` and spaced-variant scans in fast metrics.
- Add performance tests for the existing testing dataset.

Acceptance:

- Focused tests pass.
- Full test suite passes.
- `create-submission --mode balanced --metric-depth fast` completes on
  `data/external_unseen/tweet_eval_hate_offensive_test.csv`.
- Exact-format four-column test passes.

### Phase B: Add AutoPipelineContext

Tasks:

- Add `privhsd/auto/config.py`, `context.py`, `model_registry.py`.
- Discover installed providers and local artifacts.
- Load providers/models once per run.
- Record provider/model statuses.
- Add fake provider/model tests proving one load per run.

Acceptance:

- Missing optional dependency does not fail exact submission.
- Available Presidio initializes once per run.
- Available token-policy model artifacts are detected but not loaded per row.

### Phase C: Add Auto Engine And Row Routing

Tasks:

- Add `privhsd/auto/row_state.py`, `routing.py`, `engine.py`.
- Run deterministic baseline on all rows.
- Compute cheap row features.
- Route rows to provider/model batches.
- Fuse spans and generate candidates.
- Rerank and select candidate per row.
- Fall back to baseline on uncertainty/errors.

Acceptance:

- Auto mode preserves exact CSV shape.
- Auto mode masks at least as many direct identifiers as balanced on fixtures.
- Auto mode does not reduce target/action/negation retention on fixtures.
- Provider/model audit explains decisions.

### Phase D: Token-Policy Runtime

Tasks:

- Wrap token-policy ensemble as an automatic advisory provider.
- Load ensemble once.
- Batch inference.
- Convert token actions to provider evidence/candidates.
- Gate final text through fusion/reranking.

Acceptance:

- Existing token-policy tests pass.
- New runtime load-count tests pass.
- Missing model artifacts produce safe fallback.

### Phase E: Workbench Auto UX

Tasks:

- Make CSV auto mode the default workbench path.
- Show provider/model status.
- Show exact-format vs local-audit output choice.
- Download CSV, audit JSON, and manifest.
- Do not expose raw text in logs.

Acceptance:

- Frontend builds.
- Backend workbench CSV endpoint tests pass.
- Exact four-column CSV round trip works through API.

### Phase F: Deep Evaluation And Research Paths

Tasks:

- Add deep metrics and benchmark reports.
- Add semantic drift scorers where dependencies exist.
- Add weak supervision reports.
- Add metadata privacy reports.
- Add DPMLM/SanText/LLM candidate runtimes only behind reranking.

Acceptance:

- Deep reports run under ignored `data/outputs/`.
- No deep report is required for basic exact-format submission.
- Official path remains fast and exact-format.

## Definition Of Done

The roadmap is complete when:

- `--mode auto` is available for exact-format submission.
- The user does not need to manually enable Presidio, GLiNER, scrubadub,
  token-policy models, or semantic models.
- Optional components are discovered and used automatically when installed and
  appropriate.
- Heavy models load once per run and batch inference.
- Missing optional components degrade safely.
- Four-column exact-format input returns four-column exact-format output.
- Fast exact-format submission works on the existing testing dataset.
- Source regression, cue checks, and validation pass for the selected outputs.
- Audits explain provider/model choices without raw text.
- Full tests pass.
- Generated datasets, model weights, and reports stay under ignored `data/`.

## Do Not Do

- Do not replace the pipeline with one LLM prompt.
- Do not call external APIs on official data.
- Do not load a model per row.
- Do not run expensive deep cue/profanity scans in the default exact submission
  manifest.
- Do not mask protected target terms by default.
- Do not submit raw Presidio, raw GLiNER, raw scrubadub, DPMLM, SanText, or LLM
  output directly.
- Do not treat unique row IDs as author labels.
- Do not commit raw data, model weights, generated reports, or official
  examples.
