# Agent Task Board

Status values:

- `todo`
- `in_progress`
- `done`
- `blocked`

## Current Tasks

| ID | Status | Owner | Task |
| --- | --- | --- | --- |
| A01 | done | Codex | Create fresh package, CLI, CSV pipeline, metrics, and tests. |
| A02 | todo | unassigned | Add official-dataset schema adapter once starter kit arrives. |
| A03 | todo | unassigned | Add Streamlit or NiceGUI demo for upload, preview, audit, and download. |
| A04 | todo | unassigned | Improve target-group handling with a safe preserve/generalize policy. |
| A05 | todo | unassigned | Add stronger local utility proxy using a small open classifier if allowed. |
| A06 | todo | unassigned | Add score log template for official leaderboard submissions. |
| A07 | done | Codex | Add packaging/install instructions for judges. |
| A08 | todo | unassigned | Add final pitch outline and demo script. |
| A09 | todo | unassigned | Run Consensus/academic search for OSS technologies, then update `docs/research_oss_tech.md` and convert findings into implementation tasks. |

## Next Recommended Task

Run A09 first if research context is available; otherwise build A03. A09 should
identify which OSS technologies are worth integrating before the UI and utility
evaluator become too fixed.

A03 is a minimal UI that calls the existing `privhsd` functions. The UI should
not reimplement the pipeline.

Expected UI controls:

- CSV upload
- text column selector
- ID column selector
- mode selector
- target generalization toggle
- preview table
- audit summary
- download privatized CSV

## A09 Consensus / Academic Search Prompt

Use this prompt with Consensus or another academic-search tool:

```text
I am building an open-source project for the PrivHSD challenge: Privacy-Preserving Hate Speech Detection.

Project goal:
Build a local, runnable text privatization pipeline that transforms input text into privacy-preserved text while preserving enough signal for downstream hate speech detection. The system is not primarily a hate speech classifier. It is a preprocessing layer.

Current implementation:
- Python package: privhsd
- Input: CSV with text column
- Output: same rows plus privatized_text
- Current method: deterministic regex/context span detection + typed placeholders like [USER], [EMAIL], [PERSON], [LOCATION], [ORG], [TARGET_GROUP:category]
- CLI commands: anonymize, evaluate, prepare-dynahate
- No required LLM calls
- Public test dataset: Dynamically Generated Hate Speech Dataset / Dynahate

Research task:
Find academic evidence and open-source technologies that can improve this project. Focus on privacy-preserving NLP, text anonymization, text sanitization, differential privacy for text, PII detection, utility-preserving redaction, hate speech detection robustness, and evaluation metrics for privacy/utility tradeoffs.

Please search academic literature and OSS ecosystem for:
1. Methods for privacy-preserving text transformation that preserve classification utility.
2. Evidence on whether named-entity redaction alone is insufficient.
3. Differential privacy or local privacy methods applicable to text privatization.
4. PII detection and anonymization libraries suitable for local/offline use.
5. Hate speech or toxicity classifiers useful as local utility evaluators.
6. Metrics for measuring privacy gain, utility retention, semantic preservation, and re-identification risk.
7. Open-source tools we can realistically integrate during a short hackathon.

Important constraints:
- Prefer local/offline OSS tools.
- Avoid required external LLM APIs.
- Python-first stack preferred.
- Must be lightweight enough for a hackathon prototype.
- Must be explainable and auditable.
- Must preserve row order, labels, IDs, and metadata.
- Must support CSV batch processing.
- Should align with human-rights framing: privacy, freedom of expression, non-discrimination, transparency, and human oversight.

Candidate technologies to evaluate:
- Microsoft Presidio
- spaCy NER
- Hugging Face Transformers
- small local hate speech/toxicity classifiers
- scikit-learn baselines
- OpenDP / diffprivlib / Opacus if relevant
- anonymization or text sanitization libraries
- sentence-transformers for semantic retention
- detoxify / toxic-bert / Dynabench hate speech models
- any strong OSS alternatives found in the literature

For each recommended technology, provide:
- What problem it solves
- Why it fits this project
- Academic support or empirical evidence
- OSS maturity and license if available
- Installation complexity
- Runtime cost
- Risks or limitations
- Whether to integrate now, later, or avoid

Also propose a further testing plan:
- Which datasets to test on
- What baselines to compare
- What metrics to calculate
- How to detect over-masking
- How to detect privacy leakage
- How to test whether hate-speech cues survive privatization
- How to prepare results for a hackathon pitch

Expected output:
1. Ranked OSS technology shortlist
2. Academic findings summary with citations
3. Recommended integration roadmap for the next 48 hours
4. Evaluation and ablation plan
5. Risks and fallback options
```

Expected A09 deliverables:

- Create `docs/research_oss_tech.md`.
- Add citation links and tool links.
- Add ranked recommendations: integrate now / later / avoid.
- Convert accepted recommendations into new task-board items.
- Keep core pipeline runnable without required external LLM APIs.
