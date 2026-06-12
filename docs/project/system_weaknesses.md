# System Weaknesses And Win Plan

Date: 2026-06-12

This note records the current weaknesses so they do not get buried in run logs.
It should be updated after official leaderboard feedback and after the demo
workbench is exercised by someone outside the project.

## Technical Weaknesses

| Weakness | Why it matters | Mitigation |
| --- | --- | --- |
| Official score unknown | Local metrics are proxies and may not match the challenge evaluator. | Submit `balanced` first, record official feedback, then test only narrow alternates. |
| Weak token labels | Token-policy models learn the current rule policy, not human privacy labels. | Use them as advisory/reranking evidence until official or human labels exist. |
| `PROTECT_TARGET` still imperfect | External target protection is better with the ensemble but not solved. | Add target-rich external data, report per-target metrics, and keep deterministic target preservation as the default. |
| Author-risk not proven on authorless data | True stylometric privacy needs repeated author/user IDs. | Run `evaluate-author-risk` only when official data has repeated author-like identifiers. |
| LLM/DPMLM candidates are low-yield | They can drift semantically or lose cues. | Keep them candidate-only behind validation and reranking. |
| Demo UX was missing | Policymakers and NGOs need to see responsible use, not just CLI output. | Build and rehearse the local Privacy Review Workbench. |
| Raw text handling risk | Demoing sensitive text can accidentally leak examples into logs or docs. | Use synthetic examples in public demos and keep generated reports under ignored `data/`. |

## Presentation Weaknesses

- The project can look like "just anonymization" unless the pitch explains
  authorship risk, target preservation, and human-rights tradeoffs.
- The transformer story can be misunderstood as replacing the deterministic
  anonymizer. The safer claim is: transformers learn token protection policy
  and supply advisory evidence under deterministic audit controls.
- Accuracy is not enough for this hackathon. Judges need to see deployability,
  limitations, governance, and a real user path.

## What Improves Winning Odds

1. Show exact-format baseline reliability first.
2. Show privacy/utility evidence without raw sensitive text.
3. Show grouped K-fold and external TweetEval results to prove the transformer
   work was real and checked for overfitting.
4. Show the workbench: paste text, privatize, inspect changed/protected spans,
   export audit.
5. Frame the target users as NGOs, journalists, researchers, and civil-society
   teams that need safer dataset sharing.
6. Be honest about limits: official score pending, author-risk pending on
   author IDs, weak labels are not human labels, and humans remain responsible
   for moderation consequences.

## Next Actions

- Run the workbench on synthetic stress examples before the pitch.
- Add CSV upload only after the paste-text path is stable.
- Prepare a 60-second workbench demo clip in case live networking or local
  servers fail.
- After official feedback, update this file with the actual weakness exposed by
  the evaluator and the chosen mitigation.
