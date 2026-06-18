# Mobile App Runbook

Status: active
Last verified: 2026-06-18

The legacy FastAPI/Vite workbench has been removed. The product shell is now an
Expo mobile/web app under `mobile/`.

## Current Architecture

```text
CSV input
  -> locked no-simplify PII/style protection profile
  -> HF HSD sidecar classification for app/audit queues
  -> exact protected CSV plus manifest/audit sidecars
  -> admin-selected LLM restatement model
  -> restatement direct-identifier guard
  -> citizen swipe review deck
```

The reviewer-facing app must show restated evidence, not raw source text. The
admin surface may show protected text and audit metadata.

## CSV Pipeline Runtime Note

The default mobile/upload CSV path is intentionally simple to call:

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

It accepts any CSV with a configured text column, preserves row order, row
count, and all input columns, and writes an exact-format output CSV with only
the selected text column replaced. Manifest and audit JSON sidecars are written
next to the output when requested.

Measured on 2026-06-18 against `data/train/train_split.csv` (`1154` rows), the
locked scored no-simplify path completed in `1251.76s` wall time and produced a
valid output at
`data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv`.
This run keeps PII Assist and candidate selection enabled, leaves language
simplification disabled, generates `style_scrubbed` candidates for every row,
and runs the fine-tuned HF classifier sidecar with threshold `0.850469`. The
protected CSV is byte-identical to the saved `train_split.no_simplify.protected`
baseline, which scored `0.37` / `0.3721`.

Do not switch back to routed style-candidate generation. That path changed only
`554` rows on the train split and dropped the score to about `0.25`. The locked
profile changes `799` rows and selects `style_scrubbed` for `715` rows.

A deterministic-only smoke path is available with
`--no-pii-assist --no-candidate-selection`; it completed in `252.33s` on the
same data but should not be used for scored output.

## Run

```bash
cd mobile
npm install
npm run web
```

For mobile devices:

```bash
cd mobile
npm start
```

Then open the project with Expo Go or a development build.

## Verify

```bash
cd mobile
npm run lint
npx tsc --noEmit
```

## MVP Screens

- Admin: locked baseline status, output CSV path, model picker, privacy guard
  summary, review queue summary.
- Review: swipe-card citizen review over guarded restatements with
  `confirmed_hatred`, `not_hatred`, and `uncertain` decisions.

## Product Constraints

- Do not default to GPT verifier, DPMLM, semantic clustering, or broad TF-IDF
  masking.
- Keep Presidio/scrubadub PII Assist and candidate selection on for scored
  mobile upload batches; use deterministic-only mode only for smoke tests.
- Generate `style_scrubbed` candidates for every row when style scrub is enabled.
- Use the locked HF HSD sidecar classification parameters for local audit and
  queue metadata.
- Keep restatement model selection explicit in the admin UI.
- Run restatement leakage guard before any card reaches a citizen reviewer.
- Avoid cloning third-party app branding or trade dress; keep the swipe pattern
  familiar but visually original.
