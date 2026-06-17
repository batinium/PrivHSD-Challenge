# System Diagrams

Status: active
Last verified: 2026-06-17

Two compact diagrams cover the core data flow and the civilian review platform.
For the current Expo screen-by-screen flow, see
[mobile_user_flow.md](mobile_user_flow.md).

## Core Pipeline

```mermaid
flowchart TB
    A[Input CSV] --> B[PII + style protection]
    B --> C[HSD cue safeguards]
    C --> D[Protected text]
    D --> E[Output CSV<br/>same shape, text replaced]
    D --> F[Manifest + audit<br/>sidecars only]
    D --> G[HSD classifier<br/>cleaned text only]
    G --> H[Optional verifier<br/>positive rows only]
    G --> F
    H --> F
```

![Core pipeline](system_diagram_core.png)

## Civilian Review Platform

```mermaid
flowchart TB
    A[Positive + negative<br/>review rows] --> B[Protected-text<br/>restatement]
    B --> C[Similarity check<br/>or redacted fallback]
    C --> D[Citizen review queue]
    D --> E[Civilian review UI]
    E --> F[Structured labels<br/>export/cache]
```

![Civilian review platform](system_diagram_civilian_review.png)

## Boundaries

- Raw original text does not enter the civilian review UI.
- Citizen review can include both positive and negative HSD rows for broader
  validation data.
- The protected CSV keeps the original shape; helper data stays in sidecars.
- Classifier, verifier, civilian evidence, and reviewer votes are separate
  artifacts.
