# Documentation Index

This folder is split by purpose so local project documentation is not mixed
with hackathon policy, research notes, or agent history.

## Project Docs

Use these for running and modifying the local codebase:

- [project/quickstart.md](project/quickstart.md) - setup and common commands.
- [project/pipeline_design.md](project/pipeline_design.md) - module map and CLI contract.
- [project/real_data_playbook.md](project/real_data_playbook.md) - official CSV workflow.
- [project/roadmap.md](project/roadmap.md) - current technical strategy.
- [project/experiment_verdict.md](project/experiment_verdict.md) - compact evidence table.
- [project/methodology_justification.md](project/methodology_justification.md) - method rationale.
- [project/packaging.md](project/packaging.md) - install and build notes.

## Challenge Material

Use these for hackathon framing, submission rules, and presentation:

- [challenge/challenge_requirements.md](challenge/challenge_requirements.md)
- [challenge/official_submission_checklist.md](challenge/official_submission_checklist.md)
- [challenge/score_log_template.md](challenge/score_log_template.md)
- [challenge/human_rights_legal_test_plan.md](challenge/human_rights_legal_test_plan.md)
- [challenge/final_pitch_outline.md](challenge/final_pitch_outline.md)
- [challenge/dataset_plan.md](challenge/dataset_plan.md)
- [challenge/webinar_notes.txt](challenge/webinar_notes.txt)

## Research Notes

Use these as background only; they are not the operational workflow:

- [research/dataset_candidate_takeaways.md](research/dataset_candidate_takeaways.md)
- [research/dp_text_privacy_literature_notes.md](research/dp_text_privacy_literature_notes.md)
- [research/research_oss_tech.md](research/research_oss_tech.md)
- [research/sjmeis_repo_takeaways.md](research/sjmeis_repo_takeaways.md)

## Archive

Historical agent handoffs, task boards, and continuation prompts were moved to
[archive/agent_notes/](archive/agent_notes/). They are retained for provenance
but are not the current source of truth.

## Current Workflow

For testing a submission candidate:

1. Create an exact-format candidate with `create-submission --replace-text`.
2. Validate shape with `validate-submission`.
3. Run `source-regression-report` and `check-hsd-cues`.
4. Run `semantic-triage-report`.
5. Send only the `qwen_semantic_check` queue to Qwen if needed.
6. Compare official scores and record them in the score log template.
