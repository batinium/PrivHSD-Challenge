# Known Weaknesses

Status: active
Owner area: planning, risk tracking, presentation limits
Last verified: 2026-06-14
Primary code: all workstreams

This file keeps risks visible so they do not get buried in run logs.

## Technical Weaknesses

| Weakness | Why it matters | Mitigation |
| --- | --- | --- |
| Official score unknown | Local metrics are proxies and may not match the evaluator. | Submit the exact baseline first, record feedback, then test narrow alternates. |
| Residual identifiers remain possible | Auto reduced residual direct IDs on unseen data but did not prove zero leakage. | Maintain row-level review queues and add targeted patterns for missed identifier forms. |
| Public figures are ambiguous | The detector may count a public-figure surname as a residual person identifier even when preserving it helps HSD context. | Keep aggregate residual counts in manifests and review row IDs without committing raw text. |
| Fast metrics miss some adversarial forms | Obfuscated emails, handles, and short names can survive while fast metrics look clean. | Expand adversarial fixture coverage and keep deep/sampled audits for risky rows. |
| Source regression can be slow | A report that silently runs deep checks blocks iteration. | Keep metric-depth controls and fast source-slice reporting. |
| Weak token labels | Token-policy models learn the current rule policy, not human privacy labels. | Keep token-policy advisory until official or human labels exist. |
| Advisory hate predictions are not ground truth | OSS classifiers are useful for triage and drift checks but can be biased or wrong. | Keep prediction columns in enriched outputs only and preserve exact submission labels. |
| `PROTECT_TARGET` is imperfect | Target protection is legally and clinically important for HSD evidence. | Preserve deterministic target protection and add target-rich external evaluation. |
| Author-risk not proven on authorless data | True stylometric privacy needs repeated author/user IDs. | Use `bound-contributions` when filtering is allowed and run author-risk only when repeated author IDs exist. |
| LLM/DPMLM candidates are low-yield | They can drift semantically or lose cues. | Keep them candidate-only behind validation and reranking. |
| Raw text handling risk | Demos can leak sensitive examples into logs or docs. | Use synthetic examples publicly and keep reports under ignored `data/`. |

## Presentation Limits

- The project is not "just anonymization"; explain authorship risk, target
  preservation, and human-rights tradeoffs.
- The transformer story is advisory. It does not replace deterministic
  masking, validation, and reranking.
- Accuracy is not enough. Show deployability, limitations, governance, and a
  real user path.

## Next Actions

- Add adversarial regressions for obfuscated contact info, aliases, short names
  in threat context, and cue/style interactions.
- Add row-level repair queues that emit row IDs, warning codes, and candidate
  names without raw text.
- Add source-regression fast metrics or sampled/deep controls.
- Rehearse the workbench on synthetic examples before public demos.
