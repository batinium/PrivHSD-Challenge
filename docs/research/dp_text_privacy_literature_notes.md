# DP Text Privacy Literature Notes

Date: 2026-06-11

This note maps the mentor-adjacent DP NLP papers to PrivHSD design decisions.
The goal is practical: explain which ideas we adopt, which remain optional
baselines, and why the current submission path is not "just Presidio" or "just
DPMLM".

## Working Verdict

The literature supports a selective, measured text-privatization pipeline:

- use DP text rewriting as a serious baseline, not as an automatic winner;
- protect utility-bearing task cues before rewriting;
- allocate privacy pressure where text is actually sensitive;
- post-process and rerank candidates instead of trusting one mechanism;
- evaluate privacy empirically with adversaries, not only with PII counts.

That is close to the implemented PrivHSD shape: deterministic local masking and
style normalization first, optional Presidio/DPMLM/LLM candidates second, and
row-local reranking as the decision layer.

## Paper Map

| Paper | Main takeaway | PrivHSD decision |
| --- | --- | --- |
| Differential Privacy in NLP: The Story So Far | DP is attractive for NLP, but unstructured text makes adaptation non-trivial and evaluation-heavy. | Frame the system as privacy-enhancing text privatization, not a generic regex scrubber. Keep metrics, manifests, and exact-format validation central. |
| Comparative Analysis of Word-Level Metric DP | Word-level MLDP methods vary materially by algorithm, epsilon, task, and utility/privacy metric. | Do not claim one word-level DP method is enough. Treat DPMLM/Diffractor-style methods as measured candidates. |
| 1-Diffractor | Word-level MLDP can be made faster and more utility-preserving, but it still operates through perturbation and noise. | Possible future baseline if official scores demand a formal DP competitor; not a core dependency today. |
| DP-MLM | Encoder-only masked LMs provide contextual token rewriting and more customization than decoder-style generation. | Implemented as `generate-dpmlm-candidates` with protected-token freezing, per-row seeding, and reranking-only output. |
| Thinking Outside of the DP Box | DP prompting needs empirical comparison against non-DP prompting; DP restrictions can impose usability costs. | Keep local LLM prompting as a constrained candidate/evaluator path and reject outputs by cue, length, and privacy checks. |
| Just Rewrite It Again | Post-processing DP rewritten text can improve semantic similarity and empirical privacy against adversaries. | Reranking and post-processing are core, not cosmetic. The system chooses among deterministic, Presidio, LLM, and DPMLM candidates per row. |
| On the Impact of Noise | DP noise can cause substantial utility loss; non-DP methods may preserve utility better but cannot match DP privacy in empirical protections. | Use DP rewriting only when measured privacy/HSD tradeoff improves. Preserve HSD cues before adding noise. |
| Spend Your Budget Wisely | Not all tokens are equally sensitive; distributing privacy budget intelligently improves tradeoffs over naive epsilon allocation. | The protected-token/eligible-token policy is a task-aware budget proxy: target/action/negation cues are preserved, risky author/identifier spans get pressure. |
| Double-edged Sword of LLM Reconstruction | LLMs can exploit contextual vulnerability in DP-sanitized text, but can also be used adversarially to improve outputs. | Add future adversarial reconstruction/privacy-judge evaluation; do not trust word-level randomization without context checks. |
| LLM-as-a-Judge for Privacy Evaluation | Privacy sensitivity is hard to measure; LLM judges can model a broad human privacy perspective but have limits. | Use any LLM judge as secondary evidence only, behind deterministic leakage metrics, author-risk classifiers, and official scores. |
| User Perspectives on DP Text Privatization | Users are sensitive to utility and coherence of privatized text. | Preserve hate-speech target/action/negation context and keep readable typed placeholders instead of overmasking everything. |
| Collocation-based Word-Level Metric DP | Moving beyond single tokens to collocations can improve coherence in word-level DP outputs. | Supports protecting multi-token HSD cues and considering phrase-level rewrite eligibility later. |

## What Makes The Approach Novel

PrivHSD is not novel because it invented DP text rewriting. The novelty is in
the challenge-specific control layer around rewriting:

1. **Task-aware retention:** hate-speech utility cues are protected before any
   privacy mechanism can damage them.
2. **Selective privacy pressure:** identifiers, quasi-identifiers, and author
   style are targeted differently from target-group/action/negation cues.
3. **Candidate governance:** Presidio, DPMLM, and LLM outputs are candidates,
   not direct replacements.
4. **Reranking by tradeoff:** each row is scored for privacy gain, cue loss,
   semantic drift, and style risk.
5. **Adversarial evaluation hooks:** direct metadata leakage, author-risk
   classifiers, HSD cue checks, HF utility probes, and future LLM reconstruction
   tests align with the literature's empirical evaluation direction.

## Current Experimental Consequences

- DPMLM is implemented, but current bounded runs do not justify using it for
  submission. Safe settings accepted 0/8 candidates; looser settings accepted
  11/12 but reranking selected 0 DPMLM candidates.
- Filtered Presidio augmentation currently has the strongest local alternate
  evidence because it improves local macro-F1 delta while preserving utility
  cues and adding high-recall entity pressure.
- Local LLM generation is useful as a harness, but current LM Studio candidates
  are low-yield and do not beat deterministic candidates.
- The first official submission should still be exact-format `balanced`, with
  `rerank-candidates --presidio-augment` as the strongest alternate if official
  scoring rewards stronger masking.

## Defensible Future Work

| Future step | Why it is justified | Stop condition |
| --- | --- | --- |
| Add an LLM reconstruction/adversarial privacy report | Supported by contextual vulnerability and LLM-as-judge papers. It tests whether outputs still imply author or sensitive details. | Keep it secondary unless it correlates with official privacy scores. |
| Add DPMLM epsilon/eligibility sweeps on official data | Supported by DPMLM, noise, and budget-distribution work. | Stop if reranking continues to select 0 candidates or utility drops. |
| Add phrase-level rewrite eligibility | Supported by collocation-based DP and our HSD cue preservation needs. | Stop if phrase rules duplicate current cue checks without score gain. |
| Try 1-Diffractor or word-level MLDP baseline | Supported as an efficient formal-DP competitor. | Stop if runtime/dependency cost is high or HSD cues degrade. |
| Use weak token-action model as reranker feature | Aligns with selective budget allocation: learn which tokens are protect/mask/generalize candidates. | Stop if it only imitates deterministic rules and does not improve rerank choices. |

## Sources

- Consensus abstract search, core DP text privatization cluster:
  [DP-MLM](https://consensus.app/papers/details/ae4f820d0de653c8b399a49162dd5dbe/?utm_source=unknown),
  [Thinking Outside of the Differential Privacy Box](https://consensus.app/papers/details/ccd2a492dda85762bdbf8b4030a9a36f/?utm_source=unknown),
  [On the Impact of Noise](https://consensus.app/papers/details/fb2009ff00b25ff28b2a44f4ddc4433b/?utm_source=unknown),
  [Just Rewrite It Again](https://consensus.app/papers/details/43e7024ed7c15c67b12ddf008e01997b/?utm_source=unknown),
  [Spend Your Budget Wisely](https://consensus.app/papers/details/73e2f7083dce53a8a302de1b080ebce1/?utm_source=unknown),
  [1-Diffractor](https://consensus.app/papers/details/cf6921b37f855fa890bd498152a4befa/?utm_source=unknown),
  [Double-edged Sword of LLM Reconstruction](https://consensus.app/papers/details/e365fe6593255a0a886e961fd84e1fa9/?utm_source=unknown),
  [Differential Privacy in NLP: The Story So Far](https://consensus.app/papers/details/be04b568e7f65ffd979777a6c731d75e/?utm_source=unknown),
  [Comparative Word-Level Metric DP](https://consensus.app/papers/details/ad21be1969a15dfab3053ef05c6e4fb6/?utm_source=unknown), and
  [LLM-as-a-Judge for Privacy Evaluation](https://consensus.app/papers/details/bd5e5f1e8fbd5c06b5478153d3af725a/?utm_source=unknown).
- Primary paper pages checked:
  [ACL DP-MLM](https://aclanthology.org/2024.findings-acl.554/),
  [ACL/EMNLP Thinking Outside of the DP Box](https://aclanthology.org/2024.emnlp-main.324/),
  [arXiv Just Rewrite It Again](https://arxiv.org/abs/2405.19831),
  [ACM Spend Your Budget Wisely](https://dl.acm.org/doi/10.1145/3714393.3726504),
  [ACL On the Impact of Noise](https://aclanthology.org/2025.findings-naacl.32/),
  [arXiv Comparative Word-Level Metric DP](https://arxiv.org/abs/2404.03324),
  [arXiv 1-Diffractor](https://arxiv.org/abs/2405.01678),
  [arXiv Double-edged Sword of LLM Reconstruction](https://arxiv.org/abs/2508.18976),
  [arXiv LLM-as-a-Judge](https://arxiv.org/abs/2508.12158),
  [ACL User Perspectives](https://aclanthology.org/2025.privatenlp-main.8/),
  [ACL Story So Far](https://aclanthology.org/2022.privatenlp-1.1/), and
  [ACL Collocation-based Word-Level Metric DP](https://aclanthology.org/2024.privatenlp-1.5/).
