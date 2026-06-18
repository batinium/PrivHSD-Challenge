# Mobile App User Flow

Status: current implementation
Last verified: 2026-06-18

This diagram reflects the Expo app in `mobile/src/app`. The app currently has
two routes: the admin console at `/` and the citizen review deck at `/review`.
Review data is still seeded from `mobile/src/data/review-data.ts`; the local
backend API exists but is not yet wired into the mobile screens.

```mermaid
flowchart TD
    Start([Open ContextSafe Expo app]) --> Tabs{Bottom tabs}

    Tabs -->|Admin tab| Admin[Admin dashboard]
    Tabs -->|Review tab| Review[Citizen review deck]

    Admin --> Metrics[View locked profile metrics<br/>rows, changed text, private score, queue size]
    Admin --> Baseline[Inspect locked run<br/>input CSV, protected CSV, sidecar steps]
    Admin --> Model[Pick restatement model<br/>local LLM, OSS model, manual mode]
    Admin --> GuardToggle[Toggle restatement PII leakage guard]
    Admin --> Queue[Inspect seeded citizen queue<br/>case id, source, class label, risk]
    Admin --> GuardAudit[Inspect privacy guard summary<br/>clean vs flagged restatements]

    Baseline --> AdminDecision{Admin ready to review?}
    Model --> AdminDecision
    GuardToggle --> AdminDecision
    Queue --> AdminDecision
    GuardAudit --> AdminDecision
    AdminDecision -->|Switch tab| Review
    AdminDecision -->|Stay| Admin

    Review --> LoadCard{Any card left?}
    LoadCard -->|Yes| Card[Show restated evidence card<br/>case id, risk level, guarded restatement]
    Card --> Guard[Apply client-side restatement guard<br/>email, URL, phone, handle, IP remasking]
    Guard --> UserChoice{Citizen action}

    UserChoice -->|Swipe right or YES| Confirm[Record confirmed_hatred]
    UserChoice -->|Swipe left or X| Reject[Record not_hatred]
    UserChoice -->|Tap ?| Uncertain[Record uncertain]
    UserChoice -->|Drag below threshold| Reset[Return card to deck]

    Reset --> Card
    Confirm --> Advance[Advance to next card<br/>update done, confirm, reject counters]
    Reject --> Advance
    Uncertain --> Advance
    Advance --> LoadCard

    LoadCard -->|No| Complete[Queue complete]
    Complete --> ExportReady[Votes ready for future admin export/audit]
    Complete -->|Restart demo queue| Review

    subgraph CurrentData[Current data source]
      Seed[Seeded review items<br/>mobile/src/data/review-data.ts]
      Privacy[Privacy guard helper<br/>mobile/src/utils/privacy.ts]
    end

    Seed -.feeds.-> Admin
    Seed -.feeds.-> Review
    Privacy -.used by.-> Admin
    Privacy -.used by.-> Guard
```

## Current Screen Responsibilities

- Admin dashboard: shows the locked baseline/profile state, allows model selection,
  toggles the guard, and previews the review queue/audit summary.
- Citizen review deck: shows guarded restatements only, collects
  `confirmed_hatred`, `not_hatred`, or `uncertain` decisions, and maintains
  local progress counters.
- Privacy guard: remasks direct identifiers in restatements before display and
  reports findings for admin audit.

## Not Wired Yet

- CSV upload from the app.
- Live fetch from `contextsafe_hsd.api_server`.
- Running restatement models from the admin UI.
- Persisting citizen votes to backend storage.
- Exporting reviewed labels back to CSV/audit files.
