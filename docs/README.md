# Project Docs

This folder is the stable project reference for the PrivHSD challenge build.
Use it before changing code.

## Reading Order

1. `challenge_requirements.md` - what the hackathon expects.
2. `roadmap.md` - current strategy and next technical bets.
3. `pipeline_design.md` - implementation contract and module map.
4. `quickstart.md` - commands for running the pipeline.
5. `methodology_justification.md` - why rules, lexicons, reranking, and
   author-risk evaluation are defensible.
6. `privhsd_system_design_paper.md` - concise shareable pipeline architecture,
   examples, inputs/outputs, dictionaries, and audit prompt. Rendered copy:
   `privhsd_system_design_paper.pdf`.
7. `dp_text_privacy_literature_notes.md` - mentor-adjacent DP NLP papers mapped
   to implementation choices.
8. `score_log_template.md` - reproducible official-submission score log.

Reference docs:

- `dataset_plan.md` - public and official dataset plan.
- `packaging.md` - pip install and wheel build notes.
- `research_oss_tech.md` - research appendix and OSS links.

## Source Of Truth

The implementation should stay aligned with these points:

- Build a text privatization pipeline, not primarily a hate speech classifier.
- Keep the core path local, deterministic, and runnable without LLM calls.
- Preserve row order, IDs, labels, and non-text columns.
- Add `privatized_text` by default instead of overwriting source text.
- Produce audit JSON for explainability.
- Optimize the privacy/utility tradeoff, not privacy alone.
- Reduce author-identifying signals, not only obvious PII.
- Preserve hate-speech cues needed by downstream classifiers.
