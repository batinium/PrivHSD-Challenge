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

The app currently runs with seeded data from the locked baseline:

`data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv`

## Current screens

- Admin: locked baseline status, restatement model selection, privacy guard summary.
- Review: swipe-card citizen review over guarded restated evidence.

## Product rules

- Citizen reviewers only see LLM-restated evidence, not raw source text.
- Restatements pass through a direct-identifier guard before entering the deck.
- Admin model selection is explicit; GPT/DPMLM/semantic masking are not default.
