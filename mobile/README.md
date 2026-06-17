# ContextSafe Review Mobile

Expo mobile/web shell for the ContextSafe-HSD citizen review workflow.

## Get started

Install dependencies:

```bash
npm install
```

Start the app:

```bash
npm run web
```

The app currently runs with seeded data from the frozen baseline:

`data/outputs/frozen_final_baseline_20260617/train_split.frozen_baseline.protected.csv`

## Current screens

- Admin: frozen baseline status, restatement model selection, privacy guard summary.
- Review: swipe-card citizen review over guarded restated evidence.

## Product rules

- Citizen reviewers only see LLM-restated evidence, not raw source text.
- Restatements pass through a direct-identifier guard before entering the deck.
- Admin model selection is explicit; GPT/DPMLM/semantic masking are not default.
