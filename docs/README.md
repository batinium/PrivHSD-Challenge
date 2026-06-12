# Documentation Index

The documentation is intentionally small. Keep operational instructions,
methodology, evidence, and pitch material here; keep raw data and generated run
logs under ignored `data/`.

## Project Docs

- [project/quickstart.md](project/quickstart.md) - setup and common commands.
- [project/pipeline_design.md](project/pipeline_design.md) - architecture and CLI map.
- [project/real_data_playbook.md](project/real_data_playbook.md) - official CSV workflow.
- [project/roadmap.md](project/roadmap.md) - current technical strategy.
- [project/experiment_verdict.md](project/experiment_verdict.md) - current evidence table.
- [project/methodology_justification.md](project/methodology_justification.md) - detailed method rationale.

## Challenge Docs

- [challenge/challenge_requirements.md](challenge/challenge_requirements.md) - challenge interpretation and timeline.
- [challenge/official_submission_checklist.md](challenge/official_submission_checklist.md) - pre-upload checks.
- [challenge/human_rights_legal_test_plan.md](challenge/human_rights_legal_test_plan.md) - legal and governance acceptance tests.
- [challenge/final_pitch_outline.md](challenge/final_pitch_outline.md) - five-minute Dragon's Den story and demo plan.

## Current Workflow

1. Profile the dataset and verify text, ID, label, source, and author columns.
2. Create `balanced` exact-format output with `create-submission --replace-text`.
3. Validate shape with `validate-submission`.
4. Run `source-regression-report`, cue checks, and author-risk checks when the
   required columns exist.
5. Compare alternates only after the baseline exists: style scrub, filtered
   Presidio reranking, and token-policy advisory candidates.
6. Record commands, commit hash, manifest paths, and official scores in a
   dated run note under ignored `data/outputs/`, not in committed markdown.
