# Pipeline Reference

Status: active
Owner area: auto orchestration, deterministic masking, candidate selection
Last verified: 2026-06-14
Primary code: `privhsd/auto/`, `privhsd/detectors.py`,
`privhsd/pipeline.py`, `privhsd/rerank.py`, `privhsd/span_providers/`

This is the authoritative architecture reference. Operational commands belong
in runbooks; readiness and open risks belong in planning docs.

## Mission

ContextSafe-HSD is a local, auditable CSV-in/CSV-out privatization system for
hate-speech detection datasets. It reduces direct identifiers,
quasi-identifiers, and author-style signals while preserving target,
hostility, negation, modality, quotation, counterspeech, and rationale cues.

It is preprocessing infrastructure. It is not a moderation decision system, a
legal decision system, a production hate-speech classifier, or a promise that
every identifier has been removed.

## Public Stage Model

```text
Input CSV
  -> Privacy Detection
  -> Meaning Protection
  -> Verification
  -> exact cleaned CSV + manifest
```

| Stage | Responsibility | Main implementation areas |
| --- | --- | --- |
| Privacy Detection | Find direct and quasi identifiers, build a deterministic baseline, and merge optional local PII Assist evidence. | `detectors.py`, `pipeline.py`, `metrics.py`, `span_providers/`, `auto/` |
| Meaning Protection | Reject or warn on candidates that erase HSD-relevant cues: targets, threats/actions, negation, modality, quotation, counterspeech, and reporting/rationale context. | `cue_checks.py`, `context.py`, `rationale_checks.py`, `rerank.py` |
| Verification | Check exact shape, residual identifiers, metadata leakage, HSD advisory drift when available, source slices, and author-risk hook status. | `submission.py`, `metrics.py`, `metadata_leakage.py`, `source_report.py`, `author_risk.py`, `models/hsd_advisory_runtime.py` |

Provider names, model names, load counts, and debug fields may remain in
manifests for auditability, but public summaries should lead with these three
stages.

## Public Entry Point

`protect` is the documented default command:

```bash
python -m privhsd.cli protect \
  --preset exact \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col id \
  --manifest OUTPUT.manifest.json
```

`--preset exact` calls the current exact `auto` path and preserves the input
CSV schema. It writes cleaned text only. HSD advisory output is a Verification
signal in the manifest, not appended prediction columns.

`--preset analysis` is the enriched local-analysis path. It may append
advisory HSD columns after sanitization and is not an exact-format upload path.

`--preset audit` keeps exact CSV shape and requests deeper sidecar/audit
reporting when the installed runtime supports it.

Compatibility commands remain available:

- `create-submission`: legacy exact-output interface. Use `--replace-text
  --mode auto` to reach the same routed auto path.
- `sanitize-classify`: enriched analysis output with optional advisory HSD
  columns.
- `anonymize`: deterministic/local transformation helper.

## Internal Auto Flow

```text
CSV
  -> schema validation
  -> AutoPipelineContext
  -> deterministic privacy baseline for every row
  -> cheap row risk features
  -> row routing decisions
  -> optional local PII Assist batches
  -> fused candidate spans
  -> candidate generation
  -> cue/privacy/drift validation
  -> row-local candidate selection
  -> residual direct-identifier cleanup
  -> exact-format CSV
  -> stage-first manifest
```

The deterministic baseline always runs. PII Assist is an internal grouping for
optional local helpers such as Presidio, scrubadub, and GLiNER. Presidio and
scrubadub may run when installed. GLiNER must only run when a local artifact or
explicit local configuration is present; it should not download models during
sensitive-data processing.

Routing decides when optional helpers are useful. Missing dependencies,
missing artifacts, model errors, or cue-loss failures must fall back to the
deterministic candidate and be recorded in the manifest.

## Candidate Policy

Automatic mode keeps several internal candidate sources while exposing only
one public pipeline:

- `balanced`: deterministic baseline, always present.
- `style_scrubbed`: deterministic plus style normalization when style risk is
  present.
- `pii_assist_augmented`: deterministic plus accepted PII Assist spans.
- `token_policy_candidate`: advisory research evidence only when local
  artifacts exist.

`utility`, `balanced`, and `privacy` remain deterministic modes for legacy
commands and tests. They are not separate public pipeline branches.

Research/debug candidate paths, including DPMLM and local LLM generation, must
go through reranking, cue checks, residual checks, and exact-format validation
before any output can be considered for sharing. They are not the public
default path.

Hard rejects:

- candidate loses protected target terms in exact/default mode;
- candidate loses action, negation, modality, quotation, counterspeech, or
  reporting/rationale cues;
- candidate introduces identifier-like strings;
- candidate has severe length or semantic drift when those checks are enabled;
- candidate depends on provider/model errors without a deterministic fallback.

## Manifest Contract

Manifests should be readable without knowing provider internals:

```json
{
  "pipeline": "auto",
  "preset": "exact",
  "stages": {
    "privacy_detection": {
      "baseline": "deterministic_balanced",
      "pii_assist": {
        "components": {
          "presidio": "ready",
          "scrubadub": "ready",
          "gliner": "missing_artifact"
        }
      }
    },
    "meaning_protection": {
      "protected_cue_policy": "target_action_negation_quote_counterspeech",
      "cue_loss_rejections": 0
    },
    "verification": {
      "residual_direct_identifier_count": 0,
      "hsd_advisory_status": "skipped",
      "metadata_leakage_status": "not_run",
      "author_risk": {
        "author_column_exists": false,
        "ran": false,
        "skipped_reason": "no_author_column"
      }
    }
  }
}
```

Detailed `providers`, `models`, route counts, and load counts can remain for
debug compatibility. Row-level audit fields should include the chosen
candidate, why it was chosen, privacy gain, meaning-protection rejections, and
whether residual review is required.

## HSD Advisory

HSD advisory models are Verification aids. In exact mode, they can check
original-vs-cleaned drift and write status to the manifest. If unavailable,
exact mode should still run and record a skipped status. In analysis mode,
they may append prediction columns, but those columns are local advisory
signals and not production hate-speech labels.

## Author-Risk Hook

Author doxxing risk belongs under Verification. The manifest should record
whether an author/user column exists, whether repeated-author evaluation ran,
and the skipped reason when it did not run. Do not infer author-risk behavior
from authorless data and do not mutate author metadata in exact submissions.

## Non-Negotiables

- Preserve the exact CSV contract in `docs/reference/data_contract.md`.
- Do not call external APIs on official data.
- Do not download models during sensitive-data processing.
- Do not load heavy models per row.
- Do not run deep cue/profanity/semantic scans in the default exact path.
- Do not mask protected HSD cues by default.
- Do not submit raw provider, research, DPMLM, SanText, or LLM output directly.
- Do not keep raw text in durable audits or committed docs.
- Do not treat advisory HSD predictions as legal or moderation truth.
