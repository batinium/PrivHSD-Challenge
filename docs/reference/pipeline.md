# Pipeline Reference

Status: active
Owner area: auto orchestration, deterministic masking, candidate selection
Last verified: 2026-06-14
Primary code: `privhsd/auto/`, `privhsd/detectors.py`,
`privhsd/pipeline.py`, `privhsd/rerank.py`, `privhsd/span_providers/`

This is the authoritative architecture reference. Put commands in runbooks and
current status in planning docs.

## Mission

ContextSafe-HSD is a local, auditable CSV-in/CSV-out privatization system for
hate-speech detection datasets. It reduces direct identifiers,
quasi-identifiers, and author-style signals while preserving target,
hostility, negation, modality, quotation, counterspeech, and rationale cues.

It is preprocessing infrastructure. It is not a moderation decision system, a
legal decision system, or a production hate-speech classifier.

## Layer Map

| Layer | Purpose | Main modules | Submission role |
| --- | --- | --- | --- |
| CSV and manifests | Preserve rows, IDs, labels, metadata, hashes, and provenance. | `csv_pipeline.py`, `submission.py` | Required |
| Auto orchestration | Discover local providers/models once, route risky rows, batch inference, select checked candidates. | `privhsd/auto/` | Default exact path |
| Deterministic privacy | Mask direct and quasi identifiers with typed placeholders. | `detectors.py`, `pipeline.py`, `metrics.py` | Required |
| HSD cue protection | Preserve target, action, negation, modality, counterspeech, and rationale cues. | `cue_checks.py`, `context.py`, `rationale_checks.py` | Required audit |
| Style pressure | Reduce author-style signals without erasing HSD meaning. | `style.py` | Optional candidate |
| Candidate reranking | Choose the best row-local privacy/utility tradeoff. | `rerank.py` | Optional alternate |
| Slice regression | Check privacy and utility by source/label/split/platform/type. | `source_report.py` | Required when columns exist |
| Author risk | Measure stylometric author predictability when repeated author IDs exist. | `author_risk.py` | Required when columns exist |
| Token policy | Fine-tune weak token-action models and ensembles. | `token_policy.py` | Advisory/reranking support |
| Enriched classification | Append local HSD advisory predictions after sanitization. | `simple_pipeline.py`, `models/hsd_advisory_runtime.py` | Local analysis only |

## Auto Flow

```text
CSV
  -> schema validation
  -> AutoPipelineContext
  -> deterministic baseline for every row
  -> cheap row risk features
  -> row routing decisions
  -> optional provider/model batches
  -> fused candidate spans
  -> candidate generation
  -> cue/privacy/drift validation
  -> row-local candidate selection
  -> exact-format CSV
  -> exact-submission manifest
```

The current primary exact path is `create-submission --replace-text --mode
auto --metric-depth fast`. The CLI default mode is still `balanced`, so official
runbooks should pass `--mode auto` explicitly when they want routed provider and
model orchestration.

`--mode auto` means the user does not manually choose row-level providers. It
does not mean every heavy component runs on every row. Routing decides when
optional providers/models are useful, and deterministic balanced output is the
fallback on uncertainty, missing artifacts, model errors, or cue loss. Optional
models are local-only by default unless `--allow-model-download` is passed.

`sanitize-classify` wraps the same auto flow for local analysis: it replaces the
selected text column in place, appends HSD prediction columns, and writes a
manifest with aggregate original-vs-sanitized advisory score drift. It can also
write row audit JSON with `--audit`. Because it adds columns, it is not an
exact-format submission path.

The trusted enriched path keeps the default routed auto behavior and requires
HSD classification when the output hate columns are part of the deliverable:

```bash
python -m privhsd.cli sanitize-classify \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col id \
  --manifest OUTPUT.manifest.json \
  --require-hate-classification \
  --max-model-batch-size 32
```

This path uses every ready local OSS component: deterministic masking,
Presidio, scrubadub, token-policy ensemble spans, and the two-model RoBERTa HSD
advisory ensemble. Optional GLiNER remains a structured provider status when
its dependency or local/allowed model is missing. The `semantic` model status is
currently discovery/reporting only; no semantic scorer is loaded by the auto
engine.

## Row Routing Inputs

The cheap row profile should contain only information that is safe for
manifest/audit summaries:

```text
row_id
text_length
baseline_changed
direct_identifier_count_before
direct_identifier_count_after
quasi_identifier_count_before
quasi_identifier_count_after
placeholder_count
target_cue_retention_fast
utility_cue_retention_fast
style_risk_count
provider_needed_reasons
model_needed_reasons
review_reasons
```

## Candidate Policy

Current candidate set for automatic mode:

- `balanced`: deterministic baseline, always present.
- `style_scrubbed`: deterministic plus style normalization, considered only
  when style risk exists.
- `provider_fusion_augmented`: deterministic plus accepted provider spans.
- `token_policy_candidate`: only when local token-policy artifacts exist.

`utility`, `balanced`, and `privacy` are deterministic modes for
`create-submission`/`anonymize`, not separate auto candidates. `privacy`
generalizes target-group terms by default and is not the default official upload
path.

DPMLM and local-LLM candidates are generated by separate research/helper
commands and must go through reranking and exact-format validation before they
can influence an upload. SanText is historical/proposed only; it is not a
current implemented command.

Hard rejects:

- candidate loses protected target terms in official/balanced mode;
- candidate loses action, negation, modality, or counterspeech cues;
- candidate introduces identifier-like strings;
- candidate has severe length or semantic drift when those checks are enabled;
- candidate depends on provider/model errors without a safe fallback.

## Non-Negotiables

- Preserve the exact CSV contract in `docs/reference/data_contract.md`.
- Do not call external APIs on official data.
- Do not load heavy models per row.
- Do not run deep cue/profanity/semantic scans in the default exact submission
  path.
- Do not mask protected target terms by default.
- Do not submit raw provider, DPMLM, SanText, or LLM output directly.
- Do not keep raw text in durable audits or committed docs.
- Do not treat advisory HSD predictions as legal or moderation truth.
