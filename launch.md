# Launch Guide

Status: active
Last verified: 2026-06-17

This repo now has two runtime pieces:

- `mobile/`: Expo Metro app for admin and citizen review.
- `contextsafe_hsd`: Python backend pipeline for frozen baseline CSV generation.

The old FastAPI/Vite workbench backend was removed. A new API backend for CSV
upload, restatement jobs, and review exports has not been added yet. Until that
exists, run the Python pipeline as the backend batch step.

## 1. Start Expo Metro

From the repo root:

```bash
cd mobile
npm install
npm start
```

Metro will print QR/device options for Expo Go and development builds.

## 2. Start Expo Web

From the repo root:

```bash
cd mobile
npm run web
```

The current development URL is usually:

```text
http://localhost:8081
```

If that port is busy, Expo will pick another port. In the current local session,
the app is running at:

```text
http://localhost:8082
```

## 3. Run The Frozen Baseline Backend Batch

Use this when you need to generate a protected CSV before importing it into the
app flow:

```bash
python -m contextsafe_hsd.cli protect \
  --input data/train/train_split.csv \
  --output data/outputs/frozen_final_baseline_20260617/train_split.frozen_baseline.protected.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --hsd-classifier off \
  --llm-verifier off \
  --no-style-simplify-language \
  --manifest data/outputs/frozen_final_baseline_20260617/protect_result.json \
  --audit data/outputs/frozen_final_baseline_20260617/audit.json \
  --progress
```

For app/admin queue metadata, enable the HF sidecar classifier. It does not
change the output CSV text:

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.protected.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --hsd-classifier hf \
  --hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
  --hf-hsd-threshold 0.850469 \
  --llm-verifier off \
  --no-style-simplify-language \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

## 4. Verify Before Demo

```bash
python -m ruff check contextsafe_hsd tests
python -m pytest -q
cd mobile
npm run lint
npx tsc --noEmit
npx expo export --platform web
```

## Backend API Slot

The next backend service should expose:

- CSV upload and frozen baseline job launch.
- Protected CSV, manifest, and audit retrieval.
- Admin-selected restatement model execution over protected text only.
- Restatement direct-identifier guard before citizen review.
- Citizen vote export with `confirmed_hatred`, `not_hatred`, and `uncertain`.

Do not expose raw source text to citizen reviewer endpoints.
