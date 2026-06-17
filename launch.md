# Launch Guide

Status: active
Last verified: 2026-06-17

This repo now has two runtime pieces:

- `mobile/`: Expo Metro app for admin and citizen review.
- `contextsafe_hsd.api_server`: lightweight local JSON backend API.

The old FastAPI/Vite workbench backend was removed. The current backend is a
small standard-library API with health, frozen-baseline summary, and review seed
endpoints. The fuller CSV upload/restatement/export API is still the next build
step.

## 1. Launch Android Simulator From WSL

From the repo root:

```bash
python launch.py --target android
```

This starts:

- Backend: `http://127.0.0.1:8765`
- Android emulator API URL exposed to Expo:
  `http://10.0.2.2:8765`
- Expo Metro without requiring a Linux Android SDK

Use this when Android Studio, the Android SDK, and the emulator are installed
on the Windows side. Start the emulator from Windows, then open the app from
Expo Go using the Metro URL/QR code.

If the Windows emulator cannot reach Metro from WSL, retry with Expo tunnel
mode:

```bash
python launch.py --target android --expo-host tunnel
```

## 2. Auto-Open Android From Linux SDK

Only use this if Android SDK is installed inside Linux/WSL and `ANDROID_HOME`
points to that Linux SDK:

```bash
python launch.py --target android-auto
```

This passes `--android` through to Expo.

## 3. Start Expo Web

From the repo root:

```bash
python launch.py --target web
```

The current development URL is usually:

```text
http://localhost:8081
```

If that port is busy, pass another Expo port:

```bash
python launch.py --target web --expo-port 8082
```

## 4. Start Metro Only

```bash
python launch.py --target metro
```

## 5. Backend API Endpoints

```text
GET http://127.0.0.1:8765/health
GET http://127.0.0.1:8765/api/baseline
GET http://127.0.0.1:8765/api/review-seed
```

## 6. Run The Frozen Baseline Backend Batch

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

## 7. Verify Before Demo

```bash
python -m ruff check contextsafe_hsd tests
python -m pytest -q
cd mobile
npm run lint
npx tsc --noEmit
npx expo export --platform web
```

## Backend API Slot

The next backend expansion should expose:

- CSV upload and frozen baseline job launch.
- Protected CSV, manifest, and audit retrieval.
- Admin-selected restatement model execution over protected text only.
- Restatement direct-identifier guard before citizen review.
- Citizen vote export with `confirmed_hatred`, `not_hatred`, and `uncertain`.

Do not expose raw source text to citizen reviewer endpoints.
