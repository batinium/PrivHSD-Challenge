# Webinar Alignment

Date: 2026-06-13

Status: active
Owner area: challenge alignment and deliverables
Last verified: 2026-06-13

This note converts the PrivHSD webinar transcript into concrete project aims,
direction, and deliverables. It should guide what we build and what we show
during the hackathon.

## Webinar Context To Preserve

The webinar placed PrivHSD inside the Council of Europe's Democracy Hackathon
and the New Democratic Pact for Europe, launched in 2023 at the Reykjavik
Summit. The hackathon work is intended to feed a broader consultation process
that runs toward May 2027 recommendation packages for member states.

The Council of Europe framing matters for both the method and pitch:

- the Council of Europe is separate from the European Union and works across
  human rights, democracy, and the rule of law;
- the challenge should support democratic security while protecting free
  expression and trust in public space;
- relevant standards named in the webinar include ECHR Article 10 on freedom of
  expression, ECHR Article 8 on private life, ECHR Article 14 on
  non-discrimination, the Budapest Convention, the 2022 recommendation on
  combating hate speech, and the Framework Convention on Artificial
  Intelligence;
- the target output should be rights-based, practical, deployable, inclusive by
  design, transparent, explainable, auditable, and governable;
- No Hate Speech Week is a useful source of domain examples, civil-society
  contacts, and existing practice, especially sessions on LGBTI hate, racism,
  monitoring hate speech with AI, and networking/practice fairs.

## Updated Aim

Build a runnable text-to-text privatization system for hate-speech datasets.
The system takes the original text column, produces a privatized text column or
exact-format replacement, and maximizes the official privacy/HSD tradeoff:

- preserve hate-speech detection utility as close to the original text as
  possible;
- reduce re-identification risk and author-identifying signals as much as
  possible;
- push the official tradeoff score as high as possible; the webinar described
  leaderboard scores as ranging from negative one to one;
- remain efficient, reproducible, explainable, auditable, and deployable;
- protect free expression, non-discrimination, privacy, dignity, and human
  oversight.

The project should be presented as a privacy-preserving preprocessing system,
not as an automated takedown engine or legal hate-speech judge.

## Updated Direction

1. Start with the gap analysis from the webinar: what makes text private, what
   cues make hate-speech detection work, and where those signals overlap.
2. Prioritize exact-format CSV output that can be uploaded to the official
   evaluator. The leaderboard score is not the whole judging process, but it is
   the main empirical proof that the method works.
3. Treat the problem as a privacy/utility tradeoff, not generic PII redaction.
   Simple named-entity anonymization was called out as insufficient.
4. Keep deterministic, auditable masking as the reliable baseline. Optional
   Presidio, GLiNER, scrubadub, token-policy, DPMLM, or LLM candidates must
   pass cue, drift, and residual-identifier checks before they affect output.
5. Avoid broad zero-shot LLM rewriting as a direct solution. The webinar noted
   poor tradeoffs from generic prompting; any LLM use should be specialized,
   constrained, local or reproducible, and behind reranking.
6. Emphasize lightweight runtime and reproducibility. A large model call for
   every row is risky for scale, cost, privacy, and explainability.
7. Make the method easy to run. Package quality matters: judges should be able
   to install, run, inspect, and reproduce the system without reverse
   engineering a notebook.
8. Use the public-facing workbench as a judging asset. It should make the
   backend testable and legible, showing privatized text, changed spans,
   protected HSD cues, warnings, provider/model status, and downloadable audit
   artifacts.
9. Use the official development dataset first, then the second dataset to test
   generalization before final delivery. Treat official hate-speech datasets as
   sensitive material: expect offensive text, avoid committing raw examples, and
   keep generated reports out of the repository unless they are sanitized.
10. Use the official challenge site for empirical feedback. The webinar
   described a credentialed upload flow for privatized datasets, transformer
   models running evaluation in the background, optional publication of scores,
   and each team's best score appearing on the leaderboard.
11. Keep the Council of Europe framing visible: Article 10 free expression,
   Article 8 private life, Article 14 non-discrimination, the Budapest
   Convention, the 2022 combating hate speech recommendation, the Framework
   Convention on Artificial Intelligence, and transparent/governable AI.

## Deliverables To Focus On

### 1. Official Leaderboard Submission

Priority: critical.

Deliver:

- team credentials requested after the June 15 starter-kit/development-data
  release;
- exact-format privatized CSV created with `create-submission --replace-text`;
- no helper columns in the upload file;
- row count, column order, IDs, labels, source/split fields, author IDs, and
  metadata preserved;
- manifest with command, commit, input/output hashes, mode, provider/model
  status, validation, and aggregate metrics;
- official score screenshot or run note under ignored `data/outputs/`.

Success standard:

- upload succeeds;
- official privacy/HSD tradeoff is positive or competitive on the development
  dataset and still holds up on the second dataset;
- residual privacy failures and utility losses are known by row ID or slice.

### 2. Runnable Public Code

Priority: critical.

Deliver:

- clean repository entry points: `python -m privhsd.cli ...` and package API;
- install instructions for base and optional extras;
- smoke command that judges can run quickly on a small CSV;
- `python -m pytest -q` path fixed or documented with optional-extra skips;
- no raw challenge data, model weights, or generated sensitive reports staged.

Success standard:

- a judge can install, run a sample, validate output shape, and inspect the
  manifest without asking the team how the system works.

### 3. Demonstrable UI / Workbench

Priority: high.

Deliver:

- paste-text demo with changed-span highlighting;
- CSV upload path with exact-format replacement option;
- gauges for residual identifier risk, cue retention, and text retention;
- provider/model status so missing optional components are transparent;
- audit/manifest export;
- no raw sensitive text written to logs or committed docs.

Success standard:

- the UI makes the system understandable to technical judges, lawyers, NGOs,
  and civil-society participants in under two minutes.

### 4. Evidence Packet

Priority: high.

Deliver:

- source-aware regression report by available source, label, split, platform,
  type, and similar metadata;
- cue checks for target, action, negation, modality, and utility terms;
- rationale/span preservation when the dataset provides rationales;
- author-risk report when repeated author/user labels exist;
- metadata leakage scan for IDs, author IDs, handles, and source IDs;
- ablation table comparing `auto`, `balanced`, style scrub, Presidio/rerank,
  and any DPMLM/LLM/token-policy candidate path used.

Success standard:

- we can explain why the selected output is the least destructive option that
  improves privacy without sacrificing HSD utility.

### 5. Paper / Method Note

Priority: high after the first valid leaderboard result.

Deliver:

- concise method section describing text-to-text privatization, candidate
  generation, cue protection, reranking, and exact-format validation;
- privacy section covering direct identifiers, quasi-identifiers, metadata
  leakage, style/authorship risk, and limits;
- utility section covering HSD cue preservation and downstream score impact;
- rights/governance section covering free expression, non-discrimination,
  privacy, transparency, human review, and non-use as a takedown tool;
- limitations section with official-score caveats, author-label dependency,
  weak token labels, detector blind spots, and optional model risks.

Success standard:

- the paper can be read as a research contribution, not only a hackathon report.

### 6. Final Pitch

Priority: high after deliverables 1-4 are stable.

Deliver:

- one-sentence claim;
- live or recorded demo;
- official score plus local evidence table;
- clear explanation of why this is more than PII redaction;
- honest limitations and next steps beyond the hackathon.

Success standard:

- the pitch shows a working system, a measurable tradeoff, and a responsible
  deployment path.

## Operational Calendar

- June 15: starter kit and first development dataset expected; request team
  credentials for the leaderboard after this release.
- June 17: hackathon officially starts.
- June 18 afternoon: second dataset expected; use it to check generalization
  and avoid overfitting to the first data release.
- June 18 end of day: final deliverables due, including working code and
  system.
- June 19: final pitches and winner selection.

The transcript also notes that there are three main deliverable deadlines and
that work begins before the physical event. Treat the starter kit as the source
of truth for exact upload format and deadline mechanics.

## Current Focus Order

1. Fix the test/reproducibility blockers.
2. Request or confirm leaderboard credentials and starter-kit access.
3. Submit the strongest exact-format `auto` or `balanced` CSV and record the
   official score.
4. Run source-aware regression and cue checks on the submitted output.
5. Exercise the workbench on synthetic examples and one small CSV.
6. Prepare the evidence packet and paper skeleton from existing docs.
7. Re-tune only from official feedback, not from intuition.

## Claims To Avoid

- Do not claim that leaderboard rank alone wins the challenge.
- Do not claim true author-risk reduction unless repeated author/user labels
  were available and evaluated.
- Do not present token-policy, DPMLM, or LLM experiments as the final method
  unless their outputs passed exact validation and reranking.
- Do not say the system decides whether speech is illegal hate speech.
- Do not overstate generic named-entity redaction as privacy protection.
