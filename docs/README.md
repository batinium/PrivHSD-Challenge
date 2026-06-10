# Project Docs

This folder is the stable project reference for the PrivHSD challenge build.
Use it before changing code.

## Reading Order

1. `challenge_requirements.md` - what the hackathon expects.
2. `pipeline_design.md` - current implementation contract and module map.
3. `dataset_plan.md` - public dataset plan before official data arrives.
4. `quickstart.md` - commands for running the current pipeline.

## Source Of Truth

The implementation should stay aligned with these points:

- Build a text privatization pipeline, not primarily a hate speech classifier.
- Keep the core path local, deterministic, and runnable without LLM calls.
- Preserve row order, IDs, labels, and non-text columns.
- Add `privatized_text` by default instead of overwriting source text.
- Produce audit JSON for explainability.
- Optimize the privacy/utility tradeoff, not privacy alone.

