# Documentation Index

Status: active
Owner area: documentation navigation
Last verified: 2026-06-13

This directory is split so multiple agents can work without editing the same
markdown files. Use the authoritative doc for the area you are changing, then
link out instead of duplicating content.

## Start Here

- [agent_workstreams.md](agent_workstreams.md) - ownership map for parallel
  agents.
- [runbooks/quickstart.md](runbooks/quickstart.md) - install, test, prepare
  data, create an exact candidate.
- [reference/data_contract.md](reference/data_contract.md) - exact CSV contract
  that submission work must preserve.
- [reference/pipeline.md](reference/pipeline.md) - stable pipeline
  architecture.
- [planning/current_status.md](planning/current_status.md) - current evidence
  and readiness snapshot.

## Runbooks

Operational docs with commands:

- [runbooks/quickstart.md](runbooks/quickstart.md)
- [runbooks/official_submission.md](runbooks/official_submission.md)
- [runbooks/token_policy_training.md](runbooks/token_policy_training.md)
- [runbooks/workbench.md](runbooks/workbench.md)
- [runbooks/manual_fixture.md](runbooks/manual_fixture.md)

## Reference

Stable contracts and system design:

- [reference/data_contract.md](reference/data_contract.md)
- [reference/pipeline.md](reference/pipeline.md)
- [reference/providers_and_models.md](reference/providers_and_models.md)
- [reference/cli.md](reference/cli.md)
- [reference/evaluation.md](reference/evaluation.md)

## Planning

Current status, risks, and future work:

- [planning/current_status.md](planning/current_status.md)
- [planning/known_weaknesses.md](planning/known_weaknesses.md)
- [planning/roadmap.md](planning/roadmap.md)
- [planning/decisions.md](planning/decisions.md)

## Research And Governance

- [research/methodology.md](research/methodology.md)
- [research/legal_governance.md](research/legal_governance.md)

## Challenge Docs

Challenge-specific interpretation, legal stress tests, checklist, and pitch:

- [challenge/challenge_requirements.md](challenge/challenge_requirements.md)
- [challenge/webinar_alignment.md](challenge/webinar_alignment.md)
- [challenge/official_submission_checklist.md](challenge/official_submission_checklist.md)
- [challenge/human_rights_legal_test_plan.md](challenge/human_rights_legal_test_plan.md)
- [challenge/final_pitch_outline.md](challenge/final_pitch_outline.md)

## Editing Rules

1. Choose a workstream from [agent_workstreams.md](agent_workstreams.md).
2. Put commands in runbooks.
3. Put stable interfaces and architecture in reference docs.
4. Put current results and risks in planning docs.
5. Put detailed method/legal rationale in research or challenge docs.
6. Keep raw data and generated reports under ignored `data/`.
