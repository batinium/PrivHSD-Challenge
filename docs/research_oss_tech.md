# OSS Technology Research for PrivHSD

Date: 2026-06-10

## Scope

PrivHSD should remain a local, deterministic text privatization pipeline. The
research below treats classifiers and neural models as optional evaluators or
detector backends, not as the primary product. The default path should keep
working without external LLM APIs, preserve CSV row order and metadata, and
produce auditable `privatized_text`.

## Ranked OSS Shortlist

| Rank | Technology | Recommendation | Why it fits | Main risk |
| --- | --- | --- | --- | --- |
| 1 | scikit-learn TF-IDF classifier baseline | Integrate now | Lightweight local utility evaluator for original-vs-privatized label retention; BSD-3-Clause; good under hackathon constraints. | Proxy may diverge from official evaluator. |
| 2 | TAB-style anonymization metrics | Integrate now | Text Anonymization Benchmark focuses on privacy-oriented masking decisions, direct/quasi identifiers, and utility metrics; MIT code/data. | Domain is legal text, not hate-speech text. |
| 3 | Synthetic PII stress suite | Integrate now | Cheap deterministic regression tests for emails, handles, URLs, names, locations, dates, IDs, noisy formats, and quasi-identifier combinations. | Synthetic examples can miss real-world phrasing. |
| 4 | Microsoft Presidio | Integrate later as optional backend/evaluator | Mature MIT framework for PII detection/anonymization, custom recognizers, Python/Docker, structured data, and CSV-like workflows. | Heavy dependency path; automated PII detection is not complete. |
| 5 | spaCy NER | Integrate later as optional detector | Fast local NER, MIT, used by Presidio; useful for PERSON/ORG/LOCATION recall. | NER-only redaction is repeatedly shown to be insufficient. |
| 6 | Hugging Face Transformers + Dynabench/HateXplain models | Integrate later as optional utility evaluator | Local model inference can estimate whether hate-speech signal survives privatization. | Downloads are heavy; model licenses/cards must be checked before redistribution. |
| 7 | Detoxify / `unitary/toxic-bert` | Integrate later as optional toxicity evaluator | Apache-2.0 project/model, easy local API, multi-label toxicity outputs including threat and identity hate. | Toxicity is not the same construct as hate speech; documented bias risks. |
| 8 | sentence-transformers | Integrate later for semantic retention | Apache-2.0, standard embeddings for cosine similarity and semantic drift. | Adds PyTorch/model weight cost; similarity can reward unsafe leakage. |
| 9 | GLiNER | Integrate later as optional PII detector experiment | Apache-2.0, local zero-shot NER, CPU/consumer hardware focus. | Model weight/runtime cost; needs calibration on noisy challenge text. |
| 10 | OpenDP / diffprivlib / Opacus | Avoid for core, keep as research appendix | Strong for aggregate DP statistics or DP training, but not a drop-in deterministic text privatizer. | DP text sanitization is complex and stochastic; may hurt reproducibility. |
| 11 | Piiranha PII model | Avoid required integration | Strong reported PII detection, but model license is CC-BY-NC-ND-4.0 on Hugging Face. | Non-commercial/no-derivatives terms are risky for a reusable OSS challenge pipeline. |
| 12 | External LLM anonymizers / cloud DLP | Avoid required integration | Literature shows strong privacy-utility performance for some LLM methods. | Breaks local/offline requirement and deterministic auditability. |

## Academic Findings

NER-only redaction is not enough. The privacy search result [3] argues that
fixed NER categories miss disclosive terms and that disclosure depends on the
entity being protected, while the tooling search result [8] designed TAB
specifically to go beyond traditional de-identification by marking spans that
must be masked to conceal a protected person. PIIBench found very low span-level
F1 across several PII systems on a unified corpus, even for the best baseline,
which supports using independent leakage checks instead of trusting one detector
[12]. The PII masking accountability paper also stresses contextual, noisy, and
cross-lingual failure modes in PII masking models [15].

Typed replacement and generalization are better aligned than deletion. A
pseudonymization study found task quality gaps vary by anonymization technique
[2], and formal de-identification work found word-by-word replacement more
robust than simple redaction across downstream tasks [13]. This supports the
current PrivHSD use of typed placeholders rather than deleting spans. Named
entity replacement by type can improve text classification while preserving
privacy in some settings [4], but that should be treated as a utility-friendly
baseline, not a complete privacy guarantee.

Privacy-risk scoring is a useful next step. Neural text sanitization work uses
privacy-oriented entity recognition plus explicit re-identification risk
indicators [1], and related work masks spans through an optimization step that
balances estimated privacy risk and semantic loss [8]. A 2025 risk-explainability
method lowered re-identification risk for NER-based anonymization using a
k-anonymity framing [16]. For this project, the practical version is not a full
optimizer yet; it is an auditable leakage report with residual identifier counts,
placeholder density, and quasi-identifier flags.

Differential privacy for text is promising but not a 48-hour core feature.
Natural text sanitization with local DP [6], formal privacy guarantees for text
transformations [13], and CusText token-level DP sanitization [14] show that
text DP exists. The same literature also points to a hard privacy-utility
tradeoff and implementation complexity. DP libraries should therefore be used
later for aggregate reporting or optional experiments, not the default
privatizer.

Hate-speech utility needs multiple proxies. Hate-speech datasets use
incompatible definitions [1], abusive-language training data quality is a known
limiting factor [2], and cross-dataset generalization varies substantially [5].
Surveys also report continuing dataset, metric, and generalization challenges
[8], [12], [16]. Therefore, the local evaluator should include a simple
scikit-learn baseline, cue retention, and optional neural scores, rather than
claiming any one classifier is authoritative.

Target-group cues should usually survive in `balanced` mode. Dynabench's
"Learning from the Worst" dataset includes fine-grained hate type and target
labels and improves robustness through dynamic data generation [1]. Separately,
LLM hate-speech probing found target information can substantially affect
detection [17]. This supports the current default policy: preserve target-group
terms in `balanced` mode, and only generalize them in `privacy` mode or with an
explicit toggle.

## Integrate Now

1. Add a local `privhsd evaluate-utility` or `privhsd benchmark` path using
   scikit-learn. Train a TF-IDF + linear model or ComplementNB baseline on
   original text, score original and privatized text, and report macro-F1,
   accuracy, prediction agreement, label-specific recall, and confidence drift.

2. Add an ablation runner over `identity`, `regex_only`, `balanced`,
   `privacy`, `balanced --generalize-targets`, and optional detector backends.
   The output should be one JSON/CSV table suitable for a hackathon pitch.

3. Expand local metrics with TAB-inspired fields: mask density, placeholder
   density by type, direct identifier residual count, target cue retention,
   quasi-identifier flags, and over-masking warnings.

4. Add deterministic synthetic privacy tests. Include noisy handles, emails,
   phone numbers, URLs, IPs, dates, locations, context names, schools/orgs,
   aliases, and combinations like name + city + date.

5. Document the evaluation protocol in the quickstart so judges can reproduce
   public Dynahate runs without any external model downloads.

## Integrate Later

1. Presidio optional backend: `pip install privhsd[presidio]`, a detector
   adapter that maps Presidio entities to PrivHSD `Span`, and a compare mode
   that never replaces the deterministic default.

2. Optional local neural evaluators: Hugging Face pipeline support for
   `facebook/roberta-hate-speech-dynabench-r4-target`,
   `Hate-speech-CNERG/bert-base-uncased-hatexplain`, and/or Detoxify. Use these
   only for utility evaluation after model download, not required submission.

3. sentence-transformers semantic drift: add cosine similarity between original
   and privatized text, but report it alongside privacy leakage because high
   semantic similarity can also mean sensitive information survived.

4. GLiNER PII experiment: compare GLiNER spans against current regex/context
   spans and Presidio on synthetic PII and any public dev data.

5. DP appendix: use OpenDP/diffprivlib for aggregate metric release or Opacus
   only if the project later trains private classifiers. Do not make DP text
   generation part of the default pipeline before official submission.

## Avoid

1. Required external LLM APIs. They conflict with the local/offline pipeline,
   introduce data-egress concerns, and make outputs harder to reproduce.

2. Replacing the project with a moderation dashboard or classifier. Classifiers
   are evaluators here; the artifact is a privacy-preserving preprocessor.

3. Required stochastic DP text perturbation before the official evaluator.
   Stochastic outputs make row-level audit and debugging harder under time
   pressure.

4. Required integration of models with restrictive licenses, especially
   non-commercial/no-derivatives PII models, unless challenge rules explicitly
   allow them and the license is documented.

## Testing and Ablation Plan

Datasets:

- Current public Dynahate normalization in `data/public_dev/dynahate.csv`.
- Official PrivHSD dev/test data when released.
- TAB for anonymization-specific checks, using only public benchmark fields.
- A project-owned synthetic PII stress CSV committed under `tests/fixtures/`.
- Optional HateXplain for target/rationale sanity checks if licensing and data
  handling are acceptable.

Baselines:

- `identity`: no privatization.
- `regex_only`: direct regex detectors, no context, no target generalization.
- `balanced`: current default.
- `privacy`: current target generalization.
- `balanced_with_targets`: explicit `--generalize-targets`.
- `presidio_optional`: if optional dependency is installed.
- `neural_optional`: optional local hate/toxicity evaluator only.

Metrics:

- Privacy: identifier count before/after, residual identifier count from an
  independent detector, exact raw-PII leakage, placeholder density, direct vs
  quasi span counts, and quasi-identifier combinations.
- Utility: macro-F1 on original-trained local classifier, prediction agreement,
  label recall delta, cue retention, target-group retention, character/word
  similarity, and optional semantic embedding similarity.
- Over-masking: high placeholder density, high character-change ratio, large
  target-term loss in `balanced`, and classifier confidence collapse.
- Leakage: search for original direct-identifier strings in output, run current
  detector on privatized text, and optionally compare Presidio/GLiNER residuals.
- Hate-speech cue survival: track threat/violence verbs, dehumanization terms,
  negation around protected groups, and target categories.

Pitch-ready outputs:

- `metrics.json` with aggregate privacy and utility values.
- `ablation.csv` with one row per method and comparable metrics.
- A small table of representative synthetic examples only; do not expose
  official challenge examples in docs or screenshots.

## Risks and Fallbacks

Official metric mismatch: keep the evaluator modular and use official scorer
results as soon as the starter kit arrives. Fallback to current proxy metrics
plus ablations.

False negatives in PII detection: add independent residual checks and synthetic
edge-case tests. Fallback to stricter `privacy` mode for high-risk demos.

Over-masking hurts hate-speech utility: use `balanced` as submission default and
preserve target-group terms unless explicitly generalizing them.

Model bias in utility evaluators: report neural classifiers as proxy tools only.
Fallback to scikit-learn plus cue/target retention.

Heavy optional dependencies: isolate extras and keep the base package
dependency-free. Fallback to deterministic detectors and built-in metrics.

License uncertainty: do not vendor model weights. Fallback to documented
commands that users can run after accepting model/dataset terms.

## OSS Source Links

- [Microsoft Presidio](https://github.com/microsoft/presidio) and
  [Presidio docs](https://microsoft.github.io/presidio/): MIT; PII detection,
  anonymization, custom recognizers, Python/Docker.
- [spaCy](https://github.com/explosion/spaCy): MIT; local NER and NLP pipeline.
- [scikit-learn](https://scikit-learn.org/) and
  [TF-IDF text example](https://scikit-learn.org/stable/auto_examples/model_selection/plot_grid_search_text_feature_extraction.html):
  BSD-3-Clause; local text classifier baseline.
- [Transformers](https://github.com/huggingface/transformers): Apache-2.0;
  local model loading and text-classification pipelines.
- [facebook/roberta-hate-speech-dynabench-r4-target](https://huggingface.co/facebook/roberta-hate-speech-dynabench-r4-target):
  Dynabench hate-speech utility evaluator candidate.
- [HateXplain model](https://huggingface.co/Hate-speech-CNERG/bert-base-uncased-hatexplain)
  and [dataset](https://huggingface.co/datasets/Hate-speech-CNERG/hatexplain):
  explainable hate/offensive/normal benchmark; dataset CC-BY-4.0.
- [Detoxify](https://github.com/unitaryai/detoxify) and
  [unitary/toxic-bert](https://huggingface.co/unitary/toxic-bert):
  Apache-2.0; optional toxicity evaluator.
- [sentence-transformers](https://github.com/huggingface/sentence-transformers):
  Apache-2.0; semantic similarity and embedding drift.
- [GLiNER](https://github.com/urchade/GLiNER): Apache-2.0; local zero-shot NER.
- [OpenDP](https://github.com/opendp/opendp), [diffprivlib](https://github.com/IBM/differential-privacy-library),
  and [Opacus](https://github.com/meta-pytorch/opacus): DP libraries for later
  aggregate statistics or private training experiments.
- [Text Anonymization Benchmark](https://github.com/NorskRegnesentral/text-anonymization-benchmark):
  MIT; anonymization corpus and evaluation scripts.

## Academic References

Consensus privacy search:

- [1] [Neural text sanitization with privacy risk indicators: an empirical analysis](https://consensus.app/papers/details/60ee5e520d91580f8ef2f25ac07492f2/?utm_source=unknown) (Papadopoulou et al., 2026, Language Resources and Evaluation)
- [2] [Privacy- and Utility-Preserving NLP with Anonymized data: A case study of Pseudonymization](https://consensus.app/papers/details/138e7f30213b53f2890e920b887c3ae1/?utm_source=unknown) (Yermilov et al., 2023, arXiv)
- [3] [Utility-Preserving Privacy Protection of Textual Documents via Word Embeddings](https://consensus.app/papers/details/459b9c11c2f25731a5a77033cd8ee512/?utm_source=unknown) (Hassan et al., 2023, IEEE TKDE)
- [4] [Named Entity Recognition Utilized to Enhance Text Classification While Preserving Privacy](https://consensus.app/papers/details/1f390b98983a573db2a23538640609ba/?utm_source=unknown) (Kutbi, 2023, IEEE Access)
- [6] [Differential Privacy for Text Analytics via Natural Text Sanitization](https://consensus.app/papers/details/da98519771945342b39f3fd6843874f4/?utm_source=unknown) (Yue et al., 2021)
- [7] [How to keep text private? A systematic review of deep learning methods for privacy-preserving natural language processing](https://consensus.app/papers/details/c6ac6b8ea1615722b1d5ff1f298aa550/?utm_source=unknown) (Sousa et al., 2022, Artificial Intelligence Review)
- [8] [Neural Text Sanitization with Explicit Measures of Privacy Risk](https://consensus.app/papers/details/33900ce9223a547aa62c6fe25bca5993/?utm_source=unknown) (Papadopoulou et al., 2022)
- [13] [Privacy Guarantees for De-identifying Text Transformations](https://consensus.app/papers/details/c54a19b5bae3596ca37b95dcbfa9301d/?utm_source=unknown) (Adelani et al., 2020)
- [14] [A Customized Text Sanitization Mechanism with Differential Privacy](https://consensus.app/papers/details/6ddfe7ed60b659b09c9b47ba9679d597/?utm_source=unknown) (Chen et al., 2022)
- [16] [Enhancing text anonymization via re-identification risk-based explainability](https://consensus.app/papers/details/e611ac9e47c7540cb3ae544894b9ac72/?utm_source=unknown) (Manzanares-Salor et al., 2025)

Consensus tooling/anonymization search:

- [3] [RAT-Bench: A Comprehensive Benchmark for Text Anonymization](https://consensus.app/papers/details/6fb74629bb0d5bd6a0146258b6ec971c/?utm_source=unknown) (Krco et al., 2026, arXiv)
- [4] [Evaluation of an automated Presidio anonymisation model for unstructured radiation oncology electronic medical records in an Australian setting](https://consensus.app/papers/details/929a45263b9558e7bf0a31927df8bd22/?utm_source=unknown) (Kotevski et al., 2022, International Journal of Medical Informatics)
- [5] [Evaluating the accuracy of automated and semi-automated anonymization tools for unstructured health records](https://consensus.app/papers/details/5b68b85db5065d5fa2b7089e92ca0ed9/?utm_source=unknown) (Alrazihi et al., 2025, Surgical Neurology International)
- [8] [The Text Anonymization Benchmark (TAB): A Dedicated Corpus and Evaluation Framework for Text Anonymization](https://consensus.app/papers/details/79cb6dfd112057f4a0435983bdc732aa/?utm_source=unknown) (Pilan et al., 2022, Computational Linguistics)
- [12] [PIIBench: A Unified Multi-Source Benchmark Corpus for Personally Identifiable Information Detection](https://consensus.app/papers/details/1a1a5438a1535cbf95b3d925b9da63db/?utm_source=unknown) (Jha, 2026)
- [15] [Unmasking the Reality of PII Masking Models: Performance Gaps and the Call for Accountability](https://consensus.app/papers/details/86cdf3d121405b1ea844d94a2e41e616/?utm_source=unknown) (Singh et al., 2025, arXiv)
- [20] [Local Obfuscation by GLINER for Impartial Context Aware Lineage: Development and evaluation of PII Removal system](https://consensus.app/papers/details/f1a97a4f494d5ede9b9c973d2298462e/?utm_source=unknown) (Shivaprakash et al., 2025, arXiv)

Consensus hate-speech utility search:

- [1] [Toxic, Hateful, Offensive or Abusive? What Are We Really Classifying? An Empirical Analysis of Hate Speech Datasets](https://consensus.app/papers/details/17da148e805e575bac4c7df8691956a9/?utm_source=unknown) (Fortuna et al., 2020)
- [2] [Directions in abusive language training data, a systematic review: Garbage in, garbage out](https://consensus.app/papers/details/a83f0033ac585404bf41ce10bad78207/?utm_source=unknown) (Vidgen et al., 2020, PLoS ONE)
- [5] [How well do hate speech, toxicity, abusive and offensive language classification models generalize across datasets?](https://consensus.app/papers/details/4f220f9c059b5073ab511a8a38620c93/?utm_source=unknown) (Fortuna et al., 2021, Information Processing and Management)
- [8] [A Survey on Automatic Detection of Hate Speech in Text](https://consensus.app/papers/details/5d055001342954e1a0ba0e906b3cc23a/?utm_source=unknown) (Fortuna et al., 2018, ACM Computing Surveys)
- [12] [Towards generalisable hate speech detection: a review on obstacles and solutions](https://consensus.app/papers/details/34e1f96e667b53c6b9b40f3b1aaeaf20/?utm_source=unknown) (Yin et al., 2021, PeerJ Computer Science)
- [16] [Resources and benchmark corpora for hate speech detection: a systematic review](https://consensus.app/papers/details/2d758a36cae258f889528e4a2ecb359c/?utm_source=unknown) (Poletto et al., 2020, Language Resources and Evaluation)
- [17] [Probing LLMs for hate speech detection: strengths and vulnerabilities](https://consensus.app/papers/details/6b24ac0162165ad6a210e98054f6a1ff/?utm_source=unknown) (Roy et al., 2023, arXiv)

Consensus Dynabench search:

- [1] [Learning from the Worst: Dynamically Generated Datasets to Improve Online Hate Detection](https://consensus.app/papers/details/229cd46b0ae95c92a4ac9f92b78deadf/?utm_source=unknown) (Vidgen et al., 2021, arXiv/ACL)
- [3] [Robust Hate Speech Detection in Social Media: A Cross-Dataset Empirical Evaluation](https://consensus.app/papers/details/565076d28d3450b495428791c1a6545b/?utm_source=unknown) (Antypas et al., 2023, arXiv)
- [19] [ToxiGen: A Large-Scale Machine-Generated Dataset for Adversarial and Implicit Hate Speech Detection](https://consensus.app/papers/details/b34d6e7da84658728e634327b301e411/?utm_source=unknown) (Hartvigsen et al., 2022)
