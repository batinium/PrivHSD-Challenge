# Mobile App Runbook

Status: active
Last verified: 2026-06-17

The legacy FastAPI/Vite workbench has been removed. The product shell is now an
Expo mobile/web app under `mobile/`.

## Current Architecture

```text
CSV input
  -> frozen deterministic PII baseline
  -> optional HF HSD sidecar classification for app/audit queues
  -> exact protected CSV plus manifest/audit sidecars
  -> admin-selected LLM restatement model
  -> restatement direct-identifier guard
  -> citizen swipe review deck
```

The reviewer-facing app must show restated evidence, not raw source text. The
admin surface may show protected text and audit metadata.

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

- Admin: frozen baseline status, output CSV path, model picker, privacy guard
  summary, review queue summary.
- Review: swipe-card citizen review over guarded restatements with
  `confirmed_hatred`, `not_hatred`, and `uncertain` decisions.

## Product Constraints

- Do not default to GPT verifier, DPMLM, semantic clustering, or broad TF-IDF
  masking.
- Use HF HSD sidecar classification only for local audit and queue metadata.
- Keep restatement model selection explicit in the admin UI.
- Run restatement leakage guard before any card reaches a citizen reviewer.
- Avoid cloning third-party app branding or trade dress; keep the swipe pattern
  familiar but visually original.
