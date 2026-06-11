# Experiment Verdict

Date: 2026-06-11

Use this as the compact review table for current local evidence. Raw generated
LLM outputs and row-level reports remain under ignored `data/outputs/`.

| Path | Latest bounded evidence | Utility result | Privacy/authorship result | Runtime/dependency cost | Verdict |
| --- | --- | --- | --- | --- | --- |
| `balanced` exact-format | Full Dynahate submission validation passed: 41,144 rows, same columns/order, no helper columns. | Strong local utility; target retention 0.9994. | Residual IDs 3, residual quasi IDs 0. | Local deterministic, dependency-light. | First official submission candidate. |
| `rerank-candidates` | Full Dynahate rerank chose `balanced` for 37,506 rows, `style_scrubbed` for 3,615, `privacy` for 23. | Local macro-F1 delta +0.0019; cue checks stable. | Residual IDs 3, residual quasi IDs 0; extra style pressure on selected rows. | Local deterministic, slower than `balanced` but practical. | Strongest alternate if official scores reward style pressure. |
| HF utility probes | Dynabench/Cardiff sample 100; Toxic-BERT sample 25. | Agreement 1.0, negligible drift, no large utility-drop rows. | Evaluation only, not anonymization. | Optional heavy dependencies and HF cache. | Supports utility-retention story; do not make core. |
| Presidio comparison | Sample 100: Presidio spans 27, PrivHSD spans 1, overlap 1. | 9 of 27 Presidio spans flagged as HSD cue/target false-positive risk. | Catches extra entity-like spans but risks overmasking. | Pulled `en_core_web_lg` 3.8.0, 400.7 MB. | Keep as baseline evidence, not product. |
| Local LLM candidates | LM Studio at `100.120.207.64:1234`; `openai/gpt-oss-20b` sample 10 accepted 3, rejected 7. | Accepted LLM candidates did not win reranking; output metrics match deterministic reranked baseline. | LLM candidates remain candidate-only and are rejected/reranked when cue or drift checks fail. | 18.2567s for 10 rows; larger runs are not justified without better acceptance/win rate. | Low-yield in current setup; useful harness, not a submission path. |
| `mistralai/ministral-3-3b` local LLM | Sample 3 parsed JSON but accepted 0; all rejected by checks. | Too much length drift or cue loss. | Candidate-only; no accepted rows. | Fast, about 2s for 3 rows. | Not useful without stronger prompting/model config. |
| `qwen/qwen3-4b-2507` local LLM | Sample 3 accepted 0; all rejected by checks. | Too much length drift or target cue loss. | Candidate-only; no accepted rows. | 5.3726s for 3 rows. | Not useful under current checks. |
| `google/gemma-4-e4b` local LLM | Sample 3 accepted 0; all rejected by checks. | Too much length drift or target cue loss. | Candidate-only; no accepted rows. | 10.8857s for 3 rows. | Not useful under current checks. |
| DPMLM | Harness writes blocker report; no supported backend installed. | Not measured. | Potentially relevant but unaudited here. | Unknown backend/runtime. | Keep out of core. |

## Next Step

When official files arrive, create and validate `balanced` exact-format output
first. If there is time after an official score, submit or compare
`rerank-candidates` as the alternate. Do not spend more compute on local LLM
generation unless a model produces a much higher accepted-and-selected rate on
a bounded sample.
