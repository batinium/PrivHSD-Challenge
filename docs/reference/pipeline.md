# Pipeline Reference

Status: active
Last verified: 2026-06-18

The final public story is one command and one backend path:

```text
input CSV
  -> deterministic PII sanitization
  -> Presidio/scrubadub PII Assist
  -> cue-safe author style scrub and repeated author-group residual masking
  -> span fusion, residual cleanup, and candidate selection
  -> HSD target/action/negation/quote/counterspeech cue safeguards
  -> optional sidecar classification/review on cleaned text only
  -> optional second-pass verifier on positive HSD labels
  -> exact-format output CSV with only the text column replaced
  -> manifest/audit sidecars
```

For a simplified data-in to data-out architecture view, see
`docs/reference/system_diagram.md`.

Primary implementation:

- `contextsafe_hsd/cli.py`
- `contextsafe_hsd/simple_pipeline.py`
- `contextsafe_hsd/auto/`
- `contextsafe_hsd/pipeline.py`
- `contextsafe_hsd/detectors.py`
- `contextsafe_hsd/cue_checks.py`
- `contextsafe_hsd/rationale_checks.py`
- `contextsafe_hsd/span_providers/`
- `contextsafe_hsd/models/hf_hsd_classifier_runtime.py`
- `contextsafe_hsd/models/local_llm_hsd_review_runtime.py`
- `contextsafe_hsd/models/local_llm_hsd_verifier_runtime.py`

## Locked Public Command

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --hsd-classifier hf \
  --hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
  --hf-hsd-threshold 0.850469 \
  --llm-verifier off \
  --pii-assist \
  --candidate-selection \
  --no-style-simplify-language \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json \
  --progress
```

`--preset exact` is the hand-in path. `--preset audit` keeps the same CSV
contract and requests deeper sidecars. The locked 2026-06-18 profile keeps PII
Assist and candidate selection enabled, generates a `style_scrubbed` candidate
for every row, disables language simplification, runs the HF sidecar classifier,
and keeps the verifier off.

The current selected model is the official-train fine-tuned
`Hate-speech-CNERG/dehatebert-mono-english` checkpoint. Its 5-fold out-of-fold
best F1 is `0.8289` at threshold `0.850469`. Use `--hsd-classifier off` only
for upload-only/privacy-only runs without sidecar labels; the protected CSV text
is unchanged by the sidecar.

GPT/local LLM review and verifier runs are optional backup/audit extensions. To
enable the older local LLM sidecar path, pass `--llm-review local-llm`,
`--local-llm-endpoint`, `--local-llm-model`, and optionally
`--llm-verifier local-llm`. The verifier reviews only main sidecar positive
labels, uses cleaned text only, and writes disagreement/uncertainty as audit
metadata. It does not override labels or modify the output CSV.

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
- Cue-safe style scrubbing and conservative author-group masking are on by
  default. The locked profile generates a `style_scrubbed` candidate for every
  row before selection. Style scrubbing normalizes idiolect markers, casing,
  repeated punctuation/letters, hashtags, emoji, and signatures while preserving
  HSD cue terms and placeholders. Author-group masking only masks
  detector-backed direct/quasi identifier spans that repeat within the same
  author/user group.

Verification:

- Exact CSV shape is validated.
- Residual identifiers and privacy warnings are summarized.
- HF HSD classifier, when selected, receives cleaned text only and writes
  binary label, softmax score, threshold, and model metadata to sidecars only.
- Local LLM HSD review, when selected, receives cleaned text only.
- LLM labels, reason tags, parse/fallback counts, and PII suggestions go to
  sidecars only.
- Optional local LLM HSD verifier output is sidecar-only and scoped to positive
  labels from the main sidecar classifier.
- Normal logs and reports do not print raw row text.

Metric target:

- PrivHSD optimizes
  `TO = Utility_protected / Utility_original - Privacy_protected / Privacy_original`.
- Higher is better. The default path favors high-confidence direct and
  technical identifier masking, cue-safe style normalization, and minimal
  semantic rewriting so anonymization improves without collapsing HSD utility.

Verifier evaluation work:

- `mini-verifier-eval` compares small local verifier models around the
  sidecar HSD reviewer.
- It writes ignored artifacts under `data/outputs/mini_verifier_eval/`.
- Full-sample Qwen positive-verifier follow-ups were run as one-off research
  artifacts under ignored `data/outputs/` paths. The dedicated Qwen full
  comparison command is not retained in the public CLI.
- These experiments support the optional verifier sidecar, but automatic label
  overrides remain out of scope.

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
        "status": "skipped"
      },
      "hsd_classification": {
        "backend": "hf_classifier",
        "status": "ok",
        "parse_count": 3
      },
      "local_llm_hsd_verifier": {
        "status": "skipped",
        "label_override_applied": false
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
