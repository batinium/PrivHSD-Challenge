# Research and OSS Appendix

Date: 2026-06-11

Use `docs/project/roadmap.md` for current priorities. This file is a compact research
appendix for agents that need source context.

## Current Interpretation

The challenge is not simple PII redaction. The privacy adversary is
authorship identification, while the utility target is hate-speech detection.
The method should reduce author-identifying signals while preserving HSD cues.

Practical implications:

- Presidio is a useful baseline/comparison, but not enough on its own.
- NER/PII tools miss style, syntax, idiolect, contextual, and author-specific
  topic signals.
- DPMLM-style rewriting is promising but complex, stochastic, and
  parameter-sensitive.
- LLMs should not be used as generic "anonymize this" prompts. Any LLM path
  needs constraints, cue preservation, residual checks, and reranking.
- Leaderboard score is not the whole hackathon evaluation.

## OSS Roles

| Tool | Role | Default? | Notes |
| --- | --- | --- | --- |
| scikit-learn | Local HSD and authorship classifiers for utility/privacy proxies. | Optional extra | Lightweight and already integrated for HSD baseline. |
| Presidio | Detector comparison and residual PII check. | No | Good evidence baseline; expected to miss many non-PII author cues. |
| spaCy | Optional NER support via Presidio or direct comparison. | No | Useful for PERSON/ORG/LOCATION recall only. |
| Hugging Face classifiers | Optional HSD/toxicity utility evaluator. | No | Check model licenses; do not commit weights. |
| sentence-transformers | Optional semantic drift metric. | No | Similarity can also preserve private info, so pair with leakage metrics. |
| GLiNER | Optional flexible entity detector experiment. | No | Compare against synthetic fixture and residual leakage. |
| DPMLM / DP-BART style methods | Advanced rewriting spike. | No | Run only as bounded experiment with epsilon/runtime reporting. |
| Local LLMs | Optional schema-constrained candidate generator. | No | Use LM Studio or llama.cpp only behind validators and reranking. |
| External LLM APIs | Avoid required path. | No | Data egress, reproducibility, and audit risks. |

## Research Claims To Carry Forward

- Named-entity redaction alone is insufficient for text privacy.
- Typed replacement/generalization is often more utility-preserving than
  deletion.
- Privacy evaluation needs independent residual checks.
- Authorship risk should be measured as an adversarial classification problem
  when author labels are available.
- HSD utility should use multiple proxies: local classifier, target/action cue
  retention, and optional neural evaluators.
- Target-group cues usually need to survive in balanced mode.

## Next Experiments

1. Author-risk evaluator: train an author classifier on original text and
   measure accuracy/F1 drop on privatized text.
2. Style scrubber: normalize punctuation, casing, emojis, elongations,
   signatures, and formatting habits.
3. HF utility evaluator: compare HSD/toxicity score drift on original vs
   privatized text using approved local Transformers models.
4. Candidate reranker: choose among balanced, style-scrubbed, privacy,
   Presidio-augmented, DP, or LLM candidates using privacy/HSD scores.
5. Presidio comparison: report overlap, unique spans, misses, false positives,
   and runtime.
6. DPMLM spike: small sample only; report epsilon, runtime, determinism,
   author-risk drop, and HSD utility.
7. Specialized LLM rewrite: schema-constrained, cue-preserving, locally checked,
   and optional.

## Source Links

- [Microsoft Presidio](https://github.com/microsoft/presidio)
- [Presidio docs](https://microsoft.github.io/presidio/)
- [spaCy](https://github.com/explosion/spaCy)
- [scikit-learn](https://scikit-learn.org/)
- [Transformers](https://github.com/huggingface/transformers)
- [facebook/roberta-hate-speech-dynabench-r4-target](https://huggingface.co/facebook/roberta-hate-speech-dynabench-r4-target)
- [cardiffnlp/twitter-roberta-base-hate-latest](https://huggingface.co/cardiffnlp/twitter-roberta-base-hate-latest)
- [HateXplain model](https://huggingface.co/Hate-speech-CNERG/bert-base-uncased-hatexplain)
- [HateXplain rationale model](https://huggingface.co/Hate-speech-CNERG/bert-base-uncased-hatexplain-rationale-two)
- [Detoxify](https://github.com/unitaryai/detoxify)
- [sentence-transformers](https://github.com/huggingface/sentence-transformers)
- [GLiNER](https://github.com/urchade/GLiNER)
- [DPMLM](https://github.com/sjmeis/DPMLM)
- [OpenDP](https://github.com/opendp/opendp)
- [diffprivlib](https://github.com/IBM/differential-privacy-library)
- [Opacus](https://github.com/meta-pytorch/opacus)
- [Text Anonymization Benchmark](https://github.com/NorskRegnesentral/text-anonymization-benchmark)

## Academic Pointers

The earlier research pass found support for these themes:

- neural text sanitization with privacy risk indicators
- pseudonymization and typed replacement preserving downstream task quality
- formal privacy guarantees for de-identifying text transformations
- customized text sanitization with differential privacy
- Text Anonymization Benchmark / TAB metrics
- PIIBench and PII masking accountability work showing detector gaps
- re-identification risk explainability
- hate-speech dataset and cross-dataset generalization issues

Do not add heavy dependencies based only on literature. Convert each idea into
a small optional experiment with runtime, license, and privacy/HSD tradeoff
measurements.
