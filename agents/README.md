# Agent Workspace

This folder is for coding-agent coordination. Agents should read this file
before making changes.

## Required Reading

1. `current_handoff.md`
2. `../docs/challenge_requirements.md`
3. `../docs/roadmap.md`
4. `../docs/pipeline_design.md`
5. `coding_rules.md`
6. `task_board.md`

## Current Objective

Build a reliable privacy-preserving text transformation pipeline for the
PrivHSD challenge.

The privacy target is broader than PII masking: reduce author-identifying
signals while preserving hate-speech detection cues.

Do not turn the project back into the old disability-only dashboard. The old
`ContextSafe-HSD` sibling repo can be used as reference, but this repository is
a fresh challenge-specific implementation.

## Agent Workflow

1. Pick one task from `task_board.md`.
2. Keep edits scoped to that task.
3. Add or update tests for behavior changes.
4. Run `python -m pytest -q`.
5. Update docs if the CLI contract, data contract, or task status changes.
6. Leave a handoff note using `handoff_template.md` when stopping.

## Non-Negotiables

- Core pipeline must run without external LLM calls.
- Preserve CSV row count and row order.
- Preserve labels and metadata.
- Add `privatized_text` by default.
- Keep audit output machine-readable.
- Avoid raw hateful examples in docs unless absolutely necessary.
- Treat external OSS/LLM/DP tools as optional support unless the project
  explicitly changes direction.
