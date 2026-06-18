# ContextSafe-HSD Mobile

Expo mobile/web shell for the harmful-speech dataset review workflow.

## Get started

Install dependencies:

```bash
npm install
```

Start the app:

```bash
npm run web
```

Build a backend-free review package:

```bash
npm run export:static-review
```

This writes `dist-review/` with static review data bundled into the app. Static
review mode opens directly on the Review screen, hides the admin Console tab,
and does not call the local API.

To bundle a different reviewer-facing dataset before export:

```bash
cd ..
python scripts/export_static_review_pool.py \
  --protected-csv data/path/to/protected.csv \
  --validation-json data/path/to/manifest-or-validation.json \
  --limit 1000
cd mobile
```

Then run `npm run export:static-review`.

The checked-in static demo data is prepared for public review flows. Local
datasets and generated review pools should stay under ignored `data/` paths.

For live admin uploads, run the local backend API before opening the Console:

```bash
python -m contextsafe_hsd.api_server --port 8765 --admin-runs-dir data/admin_uploads
```

The Console uploads CSV text to `POST /api/admin/uploads`, starts processing
with `POST /api/admin/jobs`, polls job status, and can reload completed jobs
from the persistent `data/admin_uploads` cache.

## Current screens

- Console: backend bundle status, artifact paths, admin triage, source/scrubbed/restated comparison, classifier/deviation signals, reviewer vote summary, and lookup/training routing.
- Review: swipe-card citizen review over guarded restated evidence.
- Library: example learning material for hate-speech detection and review context.

## Product rules

- Citizen reviewers only see guarded restatements, not raw source text.
- Restatements pass through a direct-identifier guard before entering the deck.
- Admin model selection is explicit; GPT/DPMLM/semantic masking are not default.
