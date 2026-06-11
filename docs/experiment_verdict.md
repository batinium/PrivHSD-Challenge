# Experiment Verdict

Date: 2026-06-11

Use this as the compact review table for current local evidence. Raw generated
LLM outputs and row-level reports remain under ignored `data/outputs/`.

| Path | Latest bounded evidence | Utility result | Privacy/authorship result | Runtime/dependency cost | Verdict |
| --- | --- | --- | --- | --- | --- |
| `balanced` exact-format | Full Dynahate submission validation passed: 41,144 rows, same columns/order, no helper columns. | Strong local utility; target retention 0.9994. | Residual IDs 3, residual quasi IDs 0. | Local deterministic, dependency-light. | First official submission candidate. |
| `rerank-candidates` | Full Dynahate rerank chose `balanced` for 37,506 rows, `style_scrubbed` for 3,615, `privacy` for 23. | Local macro-F1 delta +0.0019; cue checks stable. | Residual IDs 3, residual quasi IDs 0; extra style pressure on selected rows. | Local deterministic, slower than `balanced` but practical. | Strongest alternate if official scores reward style pressure. |
| HF utility probes | Dynabench/Cardiff sample 100; Toxic-BERT sample 25. | Agreement 1.0, negligible drift, no large utility-drop rows. | Evaluation only, not anonymization. | Optional heavy dependencies and HF cache. | Supports utility-retention story; do not make core. |
| Weak token-action tagger | Sample 5,000 rows, 67,415 tokens; weak labels from local detectors/cue protectors; dev macro-F1 0.8556. | Learns `PROTECT_HSD` well on weak labels; `PROTECT_TARGET` F1 0.7810; context generalization F1 0.5823. | Not official privacy supervision; only imitates current rules plus cue protectors. | Optional `scikit-learn`, 18.0s, 1.4 MB model. | Useful next detector/reranker feature, not a replacement anonymizer. |
| Presidio comparison | Sample 500: Presidio spans 174, PrivHSD spans 8, overlap 6. | 52 of 174 Presidio spans flagged as HSD cue/target false-positive risk. | Catches extra entity-like spans but risks overmasking. | Pulled `en_core_web_lg` 3.8.0, 400.7 MB; sample 500 runtime 1.4907s after setup. | Keep as baseline evidence, not product. |
| Local LLM candidates | LM Studio at `100.120.207.64:1234`; `openai/gpt-oss-20b` sample 10 accepted 3, rejected 7. | Accepted LLM candidates did not win reranking; output metrics match deterministic reranked baseline. | LLM candidates remain candidate-only and are rejected/reranked when cue or drift checks fail. | 18.2567s for 10 rows; larger runs are not justified without better acceptance/win rate. | Low-yield in current setup; useful harness, not a submission path. |
| `mistralai/ministral-3-3b` local LLM | Sample 3 parsed JSON but accepted 0; all rejected by checks. | Too much length drift or cue loss. | Candidate-only; no accepted rows. | Fast, about 2s for 3 rows. | Not useful without stronger prompting/model config. |
| `qwen/qwen3-4b-2507` local LLM | Sample 3 accepted 0; all rejected by checks. | Too much length drift or target cue loss. | Candidate-only; no accepted rows. | 5.3726s for 3 rows. | Not useful under current checks. |
| `google/gemma-4-e4b` local LLM | Sample 3 accepted 0; all rejected by checks. | Too much length drift or target cue loss. | Candidate-only; no accepted rows. | 10.8857s for 3 rows. | Not useful under current checks. |
| DPMLM | `dpmlm` 1.1.2 installed and importable after NLTK resources; spike detects backend but reports `adapter_not_implemented`. Tiny direct probe changed protected cues; protected-token probe preserved them. | Protected-token adapter concept can keep `immigrants should leave`, but tiny model output quality is poor. | Stochastic rewrite needs determinism, cue-freezing tests, and measured tradeoff gains before use. | Optional heavy deps; tiny probe 1.1-5.1s, real model would be slower/larger. | Promising research path, not submission-ready. |

## Next Step

When official files arrive, create and validate `balanced` exact-format output
first. If there is time after an official score, submit or compare
`rerank-candidates` as the alternate. Do not spend more compute on local LLM
generation unless a model produces a much higher accepted-and-selected rate on
a bounded sample. The next implementation bet is to use the weak token-action
tagger as a reranker/scorer feature, then test whether protected-token DPMLM can
beat deterministic reranking on a tiny audited sample.
