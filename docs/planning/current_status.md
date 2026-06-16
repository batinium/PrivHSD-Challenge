# Current Status

Status: active
Last verified: 2026-06-16

ContextSafe-HSD is now reduced to the final exact CSV pipeline plus a compact
optional workbench demo.

## Public Runtime

- `protect`
- `validate-submission`
- `profile-dataset`

The final command is:

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

`--llm-review off` is supported for offline exact runs.

## Research-Only Verifier Ablation

The mini 4B verifier ablation is implemented as an isolated research command,
not part of the public hand-in runtime:

```bash
python -m contextsafe_hsd.cli mini-4b-verifier-ablation \
  --endpoint http://100.120.207.64:1234/v1/chat/completions \
  --timeout-seconds 180 \
  --batch-size 10 \
  --progress
```

Current result:

- Best safer small candidate: `qwen/qwen3-4b`
- Recommended next step: full-sample comparison as a sidecar-only positive
  verifier candidate
- Do not promote recall-router, combined-router, or uncensored-probe behavior to
  the default runtime yet

The detailed handoff is in
`docs/planning/mini_4b_verifier_ablation/prompt.md`.

## Cleanup Completed

Removed from the public package:

- reranker module and tests
- classifier module and tests
- HSD advisory runtime
- GLiNER provider
- semantic triage, source reports, utility benchmarks
- dataset prep helpers and scripts
- generated experiment artifacts

Retained:

- deterministic row-level sanitization
- Presidio/scrubadub PII Assist
- span fusion and residual cleanup
- cue safeguards
- local LLM sidecar review
- isolated mini 4B verifier ablation CLI for research only
- exact CSV validation
- author-group masking off by default
- optional workbench demo

## Verification To Keep Current

```bash
python -m ruff check contextsafe_hsd tests workbench/backend
python -m pytest -q
npm --prefix workbench/frontend run build
```

Run a small smoke before hand-in:

```bash
python -m contextsafe_hsd.cli protect \
  --input /tmp/contextsafe-smoke/input.csv \
  --output /tmp/contextsafe-smoke/output.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --llm-review off \
  --manifest /tmp/contextsafe-smoke/output.manifest.json \
  --audit /tmp/contextsafe-smoke/output.audit.json
```

Then validate:

```bash
python -m contextsafe_hsd.cli validate-submission \
  --source /tmp/contextsafe-smoke/input.csv \
  --submission /tmp/contextsafe-smoke/output.csv \
  --text-col text
```

Generated smoke files belong under `/tmp` or ignored `data/` paths.
