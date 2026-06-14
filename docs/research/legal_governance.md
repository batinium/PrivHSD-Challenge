# Legal And Governance Reference

Status: active
Owner area: research, governance, pitch constraints
Last verified: 2026-06-14
Primary code: docs and presentation material

This file records the stable governance position. Detailed challenge-specific
legal stress tests remain in
[human_rights_legal_test_plan.md](../challenge/human_rights_legal_test_plan.md).

## Core Position

ContextSafe-HSD is a privacy-preserving preprocessing system for safer dataset
sharing and review. It is not a moderation/takedown system and should not be
presented as one.

The system should preserve hate-speech detection evidence, including protected
target terms, hostile action cues, negation, modality, quotation/reporting,
counterspeech, and public-interest context. Overmasking target identity terms
can weaken human-rights analysis and downstream HSD evaluation.

## Governance Rules

- Use synthetic or consented examples in public demos.
- Keep raw official rows out of markdown, commits, screenshots, issues, and
  presentation material.
- Report skipped checks and residual risks honestly.
- Do not claim complete anonymization unless the evidence supports it.
- Do not claim token-policy or local LLM outputs are final moderation
  decisions.
- Record provider/model status and fallback behavior in manifests.
- Keep exact-format submissions separate from enriched local triage outputs
  that append prediction or audit columns.

## Related Docs

- [human_rights_legal_test_plan.md](../challenge/human_rights_legal_test_plan.md)
- [final_pitch_outline.md](../challenge/final_pitch_outline.md)
- [known_weaknesses.md](../planning/known_weaknesses.md)
