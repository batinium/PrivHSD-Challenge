# Agent Task Board

Status values: `todo`, `in_progress`, `done`, `blocked`.

## Current Tasks

| ID | Status | Owner | Task |
| --- | --- | --- | --- |
| A01 | done | Codex | Create fresh package, CLI, CSV pipeline, metrics, and tests. |
| A02 | todo | unassigned | Add official-dataset schema adapter when starter kit/schema arrives. |
| A03 | todo | unassigned | Add minimal UI only after CLI pipeline, metrics, and demo story are stable. |
| A04 | done | Codex | Improve target-group handling with a safe preserve/generalize policy. |
| A05 | done | Codex | Add lightweight local utility proxy. |
| A06 | done | Codex | Add score-log template for official leaderboard submissions. |
| A07 | done | Codex | Add packaging/install instructions. |
| A08 | done | Codex | Add final pitch outline and demo script. |
| A09 | done | Codex | Research OSS and academic options; convert findings into tasks. |
| A10 | done | Codex | Add scikit-learn utility benchmark for original-vs-privatized text. |
| A11 | done | Codex | Add ablation runner for identity, regex-only, balanced, privacy, and target-generalized variants. |
| A12 | done | Copernicus | Add richer privacy/utility metrics and warnings. |
| A13 | done | Codex | Add synthetic PII stress fixtures and tests. |
| A14 | done | Codex | Add optional Presidio/spaCy comparison as a detector baseline, not a replacement. |
| A15 | done | Codex | Add optional neural utility evaluators after model-license checks. |
| A16 | done | Codex | Add local baseline classifier train/evaluate/predict workflows. |
| A17 | done | Codex | Add authorship-risk evaluator: train an author classifier when an `author` column exists and report accuracy/F1 drop after privatization. |
| A18 | done | Codex | Add style-scrubbing transformer for authorship cues: casing, punctuation bursts, emojis, repeated chars, spacing, signatures, and idiolect markers. |
| A19 | done | Codex | Add candidate reranking: compare deterministic, style-scrubbed, target-generalized, and optional rewrite outputs by privacy/HSD utility score. |
| A20 | blocked | Codex | Spike DPMLM-style rewriting on a tiny sample; document epsilon/runtime/utility tradeoffs before any integration. Blocked by no audited protected-cue adapter and weak tiny-model rewrite quality; A32 records the probe. |
| A21 | done | Codex | Prototype specialized local LLM rewriting with schema constraints and self-checks; no generic prompting and no required external API. |
| A22 | done | Codex | Add human-rights and judging narrative: leaderboard score is only one criterion. |
| A23 | done | Codex | Add official-submission checklist that verifies metadata preservation, no raw example leakage, and reproducible artifact paths. |
| A24 | done | Codex | Add approved model registry and license/runtime manifest for optional Hugging Face utility evaluators. |
| A25 | done | Codex | Add optional `evaluate-hf-utility` command for original-vs-privatized HSD/toxicity score drift on small samples and full runs. |
| A26 | done | Codex | Add HSD cue/rationale checks using HateXplain-style target/rationale models or conservative token occlusion when rationale models are unavailable. |
| A27 | done | Codex | Add DPMLM protected-cue rewrite spike: small samples, epsilon sweep, runtime report, and no core dependency. |
| A28 | done | Codex | Add exact-format submission validator/creator for leaderboard uploads with text columns privatized in place when required. |
| A29 | done | Codex | Add optional local LLM candidate generator through LM Studio or llama.cpp OpenAI-compatible endpoint with schema checks and reranking only. |
| A30 | done | Codex | Run optional Hugging Face utility evaluators with installed `transformers`/CPU `torch` on bounded Dynahate reranked samples; default probes passed on sample 25 and 100, Toxic-BERT passed on sample 25, HateXplain variants produced structured inference skips. |
| A31 | done | Codex | Run Presidio/spaCy comparison with optional dependencies installed on bounded Dynahate samples; sample 100 and 500 recorded overlap, detector-only spans, false-positive risk on HSD cues, runtime, and spaCy model-size cost. |
| A32 | done | Codex | Investigate a real DPMLM backend or reproducible adapter; `dpmlm` 1.1.2 installed/imported after NLTK resources, direct tiny probe rewrote protected cues, protected-token low-level probe preserved cues but remains unaudited. |
| A33 | done | Codex | Run local LLM candidate generation through LM Studio/OpenAI-compatible endpoint, then rerank accepted candidates and compare against deterministic reranking. Bounded `openai/gpt-oss-20b` sample accepted 3/10 candidates, but reranking selected no LLM candidates. |
| A34 | todo | unassigned | Run transformer fine-tuning or adapter-training experiment only as an evaluator/candidate scorer, not core anonymization; compare against local TF-IDF utility and HF utility probes. |
| A35 | todo | unassigned | Document whether any attention/fine-tuning approach improves the measured privacy/HSD tradeoff enough to justify complexity, dependencies, and rights/audit risks. |
| A36 | done | Codex | Add weak token-action tagger training experiment with optional scikit-learn extra, CLI, tests, and sample-5,000 Dynahate report. |

## Current Priority

Read `docs/roadmap.md` first. The key correction from the webinar is that the
task is not simple PII removal. The privacy adversary is authorship
identification, while the utility target is hate-speech detection. Presidio is
useful as a comparison baseline but fails as a complete solution. DPMLM-style
methods are promising but complex. LLMs may help only if specialized,
constrained, and evaluated against privacy/utility metrics.

Do not start by training a new attention model. Use existing models as optional
evaluators and candidate generators, then measure whether they improve the
privacy/HSD tradeoff over the deterministic baseline.

Recommended next sequence:

1. A36 follow-up: use the weak token-action tagger as a reranker/scorer feature
   or uncertainty detector, not as a direct anonymizer.
2. Optional A30 extension: run sample 500 HF utility only if CPU runtime,
   cache size, and model-card review are acceptable.
3. DPMLM follow-up: only build an adapter if protected-token freezing,
   determinism, and utility metrics can be audited with a real model.
4. A34/A35: run transformer fine-tuning/attention experiments only as optional
   evidence, then document whether they improve the tradeoff.
5. When official files arrive, return to exact-format submission and
   leaderboard-driven iterations.

## Non-Negotiables

- Core `privhsd anonymize` remains local and dependency-light.
- Preserve row count, row order, IDs, labels, and metadata.
- Do not commit official/raw challenge examples or downloaded datasets.
- Optimize the privacy/HSD tradeoff, not privacy alone.
- Treat pretrained HF models, DPMLM, LM Studio, and llama.cpp as optional
  support paths, not required runtime dependencies.
- Treat leaderboard score as evidence, not the whole hackathon result.
