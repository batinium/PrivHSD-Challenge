# Pipeline Reference

Status: active
Last verified: 2026-06-15

The final public story is one command and one backend path:

```text
input CSV
  -> deterministic PII sanitization
  -> Presidio/scrubadub PII Assist
  -> span fusion, residual cleanup, and candidate selection
  -> HSD target/action/negation/quote/counterspeech cue safeguards
  -> local LLM sidecar review on cleaned text only
  -> exact-format output CSV with only the text column replaced
  -> manifest/audit sidecars
```

Primary implementation:

- `contextsafe_hsd/cli.py`
- `contextsafe_hsd/simple_pipeline.py`
- `contextsafe_hsd/auto/`
- `contextsafe_hsd/pipeline.py`
- `contextsafe_hsd/detectors.py`
- `contextsafe_hsd/cue_checks.py`
- `contextsafe_hsd/rationale_checks.py`
- `contextsafe_hsd/span_providers/`
- `contextsafe_hsd/models/local_llm_hsd_review_runtime.py`

## Public Command

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --llm-review local-llm \
  --local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
  --local-llm-model openai/gpt-oss-20b \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

`--preset exact` is the hand-in path. `--preset audit` keeps the same CSV
contract and requests deeper sidecars. `--llm-review off` skips the sidecar
review and records that skipped status.

## Stage Contract

Privacy detection:

- Deterministic direct/quasi identifier masking always runs.
- Presidio and scrubadub are optional local PII Assist providers.
- Provider output is fused and filtered before it can affect text.
- Missing provider dependencies are recorded and fall back to deterministic
  output.

Meaning protection:

- Candidate selection rejects or warns on target, action, negation, modality,
  quote, counterspeech, reporting, or rationale cue loss.
- High-confidence direct identifiers are still removed even when sidecar review
  later flags classification uncertainty.
- Author-group masking remains off by default.

Verification:

- Exact CSV shape is validated.
- Residual identifiers and privacy warnings are summarized.
- Local LLM HSD review, when selected, receives cleaned text only.
- LLM labels, reason tags, parse/fallback counts, and PII suggestions go to
  sidecars only.
- Normal logs and reports do not print raw row text.

## Manifest Shape

The manifest leads with stage summaries plus provider/model diagnostics:

```json
{
  "pipeline": "final_exact_csv",
  "preset": "exact",
  "row_count": 3,
  "stages": {
    "privacy_detection": {
      "baseline": "deterministic_balanced",
      "pii_assist": {
        "components": {
          "presidio": "ready",
          "scrubadub": "ready"
        }
      }
    },
    "meaning_protection": {
      "cue_loss_rejections": 0
    },
    "verification": {
      "local_llm_hsd_review": {
        "status": "ok",
        "parse_count": 3,
        "fallback_count": 0
      }
    }
  }
}
```

Row audit entries record row IDs, chosen candidate metadata, aggregate privacy
metrics, rejection reasons, residual warnings, and LLM review metadata without
raw original text.

## Removed Paths

The package no longer ships reranker modules, HSD advisory model ensembles,
GLiNER provider code, classifier training/evaluation commands, dataset prep
commands, or research benchmark CLIs. Reintroduce those as isolated research
work only if they are needed later.
