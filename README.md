# ContextSafe-HSD

ContextSafe-HSD is the working repository for Glimo's PrivHSD Challenge code.
It contains the local CSV pipeline, review API, Expo review app, and the source
tree used to publish the `glimo-hsd` Python package.

The project is for privacy review and research workflows around harmful-speech
datasets. It is not a moderation product, and its classifier output should not
be used for automated enforcement.

## What Is In This Repo

```text
contextsafe_hsd/   Working pipeline and local API used during the challenge
tests/             Regression tests for CSV shape, masking, sidecars, and API behavior
docs/              Runbooks, reference notes, and planning records
mobile/            Expo mobile/web review app
glimo-hsd/         PyPI package source for reusable package users
scripts/           Evaluation, export, and experiment helpers
data/              Local datasets, model weights, outputs, and job state; ignored by Git
```

`contextsafe_hsd` is the main working code in this repository. The published
package lives under `glimo-hsd/` and is also available from PyPI.

## Published Artifacts

- PyPI package: <https://pypi.org/project/glimo-hsd/0.1.1/>
- Hugging Face model: <https://huggingface.co/batinium/glimo-dehatebert-hsd>

The PyPI package is `glimo-hsd==0.1.1`. It supports Python `>=3.10` and does
not include model weights. With the HF extra installed, it can load the
published DeHateBERT checkpoint from Hugging Face.

```bash
python -m pip install "glimo-hsd[hf]==0.1.1"
```

Package CLI example:

```bash
glimo-hsd process input.csv \
  --text-col text \
  --label-col hs \
  --out outputs/run_001 \
  --model-id batinium/glimo-dehatebert-hsd \
  --classifier-backend hf \
  --restatement-backend none \
  --final-scrub
```

## Local Data

The repository expects local data under `data/`, but the directory is ignored.
That directory is where challenge datasets, downloaded model checkpoints,
admin uploads, generated CSVs, manifests, audit files, and review bundles live.

Do not commit raw datasets, admin uploads, generated outputs containing source
text, local model weights, or `.env` files.

If you need to reproduce a local run, restore the relevant files under `data/`
first. The public repository intentionally does not ship those files.

## Install For Development

```bash
python -m pip install -e '.[dev]'
python -m pip install -e '.[presidio,scrubadub,hf]'
```

The optional second command installs the local PII and Hugging Face helpers.

Run the Python checks:

```bash
python -m ruff check contextsafe_hsd tests
python -m pytest -q
```

Run the Expo checks:

```bash
cd mobile
npm install
npm run lint
npx tsc --noEmit
```

## Run The Working Pipeline

The root package exposes the challenge pipeline as `contextsafe-hsd`:

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --hsd-classifier hf \
  --hf-hsd-model-path batinium/glimo-dehatebert-hsd \
  --hf-hsd-threshold 0.850469 \
  --allow-model-download \
  --llm-verifier off \
  --pii-assist \
  --candidate-selection \
  --no-style-simplify-language \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json \
  --progress
```

The command preserves row order, row count, and all input columns. Only the
configured text column is replaced. Diagnostics belong in JSON/CSV sidecars,
not in the protected CSV.

For local runs with an already-downloaded checkpoint, replace the model ID with
the local path, for example:

```text
data/outputs/dehatebert_official_kfold_20260617/final_model
```

## Local API And Review App

Start the local API for admin uploads and review cases:

```bash
python -m contextsafe_hsd.api_server \
  --host 127.0.0.1 \
  --port 8765 \
  --admin-runs-dir data/admin_uploads \
  --hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
  --hf-hsd-threshold 0.850469
```

Run the Expo app:

```bash
cd mobile
npm run web
```

Build a backendless static review export:

```bash
cd mobile
npm run export:static-review
```

The static export writes `mobile/dist-review/`, which is ignored. It is a local
review bundle, not a source-controlled artifact.

## Model Notes

`batinium/glimo-dehatebert-hsd` is a text-classification checkpoint based on
`Hate-speech-CNERG/dehatebert-mono-english`. The local pipeline uses threshold
`0.850469` for the HF sidecar classifier. The classifier is a review and
scoring helper; it does not make the protected CSV private by itself.

The pipeline's privacy behavior comes from deterministic masking, optional
Presidio/scrubadub assist, candidate selection, author-group masking, and
sidecar audits. Review outputs should still be checked before public release.

## Useful Docs

- `docs/runbooks/quickstart.md`
- `docs/runbooks/mobile_app.md`
- `docs/reference/pipeline.md`
- `docs/reference/data_contract.md`
- `docs/reference/system_diagram.md`

## Before Making The Repository Public

- Confirm `git status --ignored data .env mobile/dist-review` shows `data/`,
  `.env`, and `mobile/dist-review/` as ignored, not tracked.
- Confirm no generated datasets or model weights are tracked with
  `git ls-files data`.
- Rotate any tokens that were ever committed or shared outside the local
  machine.
- Review `mobile/src/data/` before publishing. It is source-controlled and can
  contain bundled review data if a static review pool was generated.
