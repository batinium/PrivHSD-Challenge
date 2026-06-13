# Pipeline Reference

Status: active
Owner area: auto orchestration, deterministic masking, candidate selection
Last verified: 2026-06-13
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

## Auto Flow

```text
CSV
  -> schema/profile checks
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
  -> manifest + raw-text-free audit summary
```

`--mode auto` means the user does not manually choose providers. It does not
mean every heavy component runs on every row. Routing decides when optional
providers/models are useful, and deterministic balanced output is the fallback
on uncertainty, missing artifacts, model errors, or cue loss.

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

Candidate set for automatic mode:

- `balanced`: deterministic baseline, always present.
- `style_scrubbed`: deterministic plus style normalization, considered only
  when style risk exists.
- `privacy`: more aggressive target generalization, not the default official
  upload path.
- `provider_fusion_augmented`: deterministic plus accepted provider spans.
- `token_policy_candidate`: only when local token-policy artifacts exist.
- `dpmlm_candidate`, `santext_candidate`, `local_llm_candidate`: research or
  alternate paths only, never direct output.

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
