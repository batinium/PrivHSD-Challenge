# Author-Aware Group Privacy Integration Plan

Status: active planning handoff
Owner area: author-aware privacy, contribution bounding, authorship-risk
evaluation, style-obfuscation candidates
Last verified: 2026-06-14
Primary code: `privhsd/contribution_bounding.py`, `privhsd/author_risk.py`,
`privhsd/rerank.py`, `privhsd/style.py`, `privhsd/auto/`,
future optional runtimes under `privhsd/models/`

This file turns the author-aware group privacy research into implementable
tasks. Contribution bounding, baseline author-risk evaluation, style scrub, and
reranking hooks are current; richer misattribution metrics and optional style
generators remain planned. Keep commands in `docs/runbooks/`, stable contracts
in `docs/reference/`, and current scores in `docs/planning/current_status.md`.

## Decision

Do not replace the current deterministic and auto privatization pipeline with a
large generative authorship-obfuscation system.

The repo already has the right backbone for the challenge:

- exact CSV preservation for official submissions;
- deterministic masking for direct and quasi identifiers;
- target, action, negation, modality, counterspeech, and rationale cue
  preservation;
- style scrub as a bounded deterministic candidate;
- author-risk evaluation when repeated author IDs exist;
- candidate reranking that can reject semantic drift and cue loss.

The implemented user-level control is contribution bounding: it limits how many
records any one author can dominate before release or training when row
filtering is allowed. The remaining research-backed layer is better
author-risk reporting and optional, candidate-only style obfuscators that must
pass the existing HSD utility gates.

## Non-Goals

- Do not drop rows in `create-submission` unless the official rules explicitly
  allow filtering. Exact-format challenge uploads preserve row count and schema.
- Do not claim formal differential privacy from contribution bounding alone.
  Bounding is a prerequisite for user-level privacy accounting, not a complete
  DP mechanism.
- Do not send official or sensitive rows to external APIs.
- Do not let a generative model directly overwrite final text.
- Do not use broad detoxification as anonymization. Hate-speech utility requires
  preserving abusive, threat, exclusion, target, and reporting cues.
- Do not vendor GPL-licensed code into this project without an explicit project
  license decision.
- Do not commit raw sensitive examples, generated reports, model weights, or
  run logs.

## Recommendation Ranking

| Rank | Recommendation | Integrate now? | Why |
| --- | --- | --- | --- |
| 1 | Contribution bounding by repeated author/user ID | Yes | Low dependency, directly addresses group privacy risk, safe for release/training datasets when row filtering is allowed. |
| 2 | Stronger author-risk and misattribution evaluation | Yes | Builds on existing `evaluate-author-risk`; gives measurable evidence for or against text-only author anonymity. |
| 3 | Task-aware candidate gates for any style rewrite | Yes | Prevents anonymization from erasing HSD utility. Needed before adding heavy obfuscators. |
| 4 | StyleRemix as optional local candidate generator | Later | Best research fit: interpretable LoRA style axes and Apache-2.0 code. Still GPU/model-heavy and should remain candidate-only. |
| 5 | Back-translation as optional baseline candidate | Later | Simple baseline but heavy and can sanitize toxicity; useful for comparison, not default. |
| 6 | JAMDEC as research-only candidate experiment | Later, isolated | Public code, inference-time constrained decoding, but slow multi-stage generation and no visible license from the GitHub page checked. |
| 7 | TAROT as research-only external experiment | Not in repo now | Strong task-oriented idea, but policy optimization is training-heavy and the public repo is GPL-3.0. Use separate environment and import candidate CSVs only. |
| 8 | ER-AE or formal DP text generation | Not now | Interesting mathematically, but complex to account, hard to keep coherent, and risky for HSD semantics. |

## Current Repo State

Already present:

- `privhsd/contribution_bounding.py` implements `bound_contributions`.
- `privhsd/cli.py` exposes `bound-contributions`.
- `tests/test_contribution_bounding.py` covers command registration, per-author
  caps, retained row order, stratified quotas, and blank-author behavior.
- `privhsd/author_risk.py` trains a local character n-gram author adversary and
  compares original vs privatized text.
- `privhsd/rerank.py` can include an author scorer when `--author-col` is
  provided and penalize true-author confidence for candidates.
- `privhsd/style.py` contains deterministic style normalization for signatures,
  emoji bursts, style markers, hashtags, punctuation, repeated letters, casing,
  and whitespace.
- `docs/reference/data_contract.md` warns that contribution bounding preserves
  schema among retained rows but drops rows, so it is not exact-format by
  default.

Phase 0 is implemented in the current tree. If an agent starts from an older
branch without these files, implement Phase 0 first.

## Source Notes

These sources were checked on 2026-06-13. Re-check before adding dependencies
or changing defaults.

| Source | Relevant fact for this repo |
| --- | --- |
| StyleRemix paper: https://aclanthology.org/2024.emnlp-main.241/ | Interpretable authorship obfuscation using fine-grained style perturbations and LoRA modules. The paper reports AuthorMix and DiSC resources. |
| StyleRemix repo: https://github.com/jfisher52/StyleRemix | Apache-2.0. README says implementation uses Llama-3 8B and GPU for quickstart. |
| TAROT paper: https://aclanthology.org/2025.privatenlp-main.2/ | Task-oriented authorship obfuscation using policy optimization over small language models to reduce attacker accuracy while preserving downstream utility. |
| TAROT repo: https://github.com/hornetsecurity/tarot | GPL-3.0. README points to PPO/DPO fine-tuning scripts and Hugging Face models. |
| JAMDEC paper: https://aclanthology.org/2024.naacl-long.87/ | Unsupervised inference-time authorship obfuscation with constrained decoding over small language models such as GPT2-XL. |
| JAMDEC repo: https://github.com/jfisher52/JAMDecoding | README describes keyword extraction, over-generation, and filtering; generation can take up to days depending on data/GPU. No visible license on the GitHub page checked. |
| Contribution bounding, ICML 2019: https://proceedings.mlr.press/v97/amin19a.html | User contribution limits are needed because more records from one user require more noise under DP. |
| Smooth contribution bounding, NeurIPS 2020: https://papers.nips.cc/paper_files/paper/2020/hash/a0dc078ca0d99b5ebb465a9f1cad54ba-Abstract.html | Supports treating contribution limits as an optimization/privacy-utility tradeoff, not just arbitrary truncation. |
| User-level DP for LLMs overview: https://research.google/blog/fine-tuning-llms-with-user-level-differential-privacy/ | User-level DP protects all of a user's examples, is stronger than example-level DP, and is harder because it needs more noise. |
| ER-AE paper: https://aclanthology.org/2021.naacl-main.314.pdf | DP text generation with a two-set exponential mechanism and semantic reward. Useful context, but not recommended for core implementation now. |

## Phase 0: Contribution Bounding

Status: implemented. Remaining useful follow-ups are report enrichment and
runbook examples.

Goal:

Limit repeated author/user contributions before release or model training when
row filtering is allowed. This is the practical user-level privacy primitive.

Primary files:

- `privhsd/contribution_bounding.py`
- `privhsd/cli.py`
- `privhsd/__init__.py`
- `tests/test_contribution_bounding.py`
- `docs/runbooks/quickstart.md`
- `docs/runbooks/official_submission.md`
- `docs/reference/data_contract.md`
- `docs/reference/cli.md`

Current expected behavior:

- Input is a CSV with an author-like column, such as `author`, `author_id`,
  `user`, `username`, `handle`, or `account_id`.
- Nonblank author groups are capped to `--max-records-per-author`.
- Output preserves original column names and column order.
- Output preserves original row order among retained rows.
- Blank author rows are kept by default and reported as unbounded.
- `--drop-missing-author` drops blank author rows explicitly.
- `--strategy random` samples deterministically with `--random-state`.
- `--strategy stratified` tries to preserve label/source slices within each
  author quota when `--stratify-col` is repeated.
- Report JSON includes input/output paths, selected columns, selection policy,
  before/after row counts, dropped counts, missing-author counts, author-count
  distributions, and dropped row examples by ID when `--id-col` exists.

Command shape:

```bash
python -m privhsd.cli bound-contributions \
  --input INPUT.csv \
  --output data/outputs/INPUT.bounded.csv \
  --author-col author_id \
  --id-col id \
  --text-col text \
  --max-records-per-author 25 \
  --strategy stratified \
  --stratify-col label \
  --stratify-col source \
  --report data/outputs/INPUT.bounded.report.json
```

Implementation details agents must preserve:

- Validate columns before reading/writing output.
- Reject `--max-records-per-author < 1`.
- Require `--text-col` for `longest` and `shortest` strategies.
- Use local `random.Random(random_state)` instead of global RNG.
- Never print raw text in the report.
- Never mutate the input rows in place when writing retained output.
- Make row examples ID-only or row-index-only.

Useful follow-up tasks:

1. Add `bound-contributions` examples to `docs/runbooks/official_submission.md`
   under a section named "When Row Filtering Is Allowed".
2. Add a profile hint in `profile-dataset` output when a candidate author column
   has repeated nonblank values and a heavy-tailed row distribution.
3. Add an optional report field named `recommended_max_records_per_author` only
   if the heuristic is transparent. Do not choose a hidden cap automatically.
4. Add `label_counts_before` and `label_counts_after` to the report when
   stratifying by a label column.
5. Add a small CSV fixture under `tests/fixtures/` only if tests become too
   verbose inline. Keep synthetic text harmless.

Acceptance tests:

```bash
python -m pytest -q tests/test_contribution_bounding.py tests/test_public_api.py
python -m py_compile privhsd/contribution_bounding.py privhsd/cli.py privhsd/__init__.py
```

Manual smoke:

```bash
python -m privhsd.cli bound-contributions --help
```

Do not call this command from `create-submission` by default. The exact CSV
contract must continue to preserve row count.

## Phase 1: Stronger Author-Risk Evaluation

Status: partially implemented. The current command is a local char n-gram
logistic adversary with accuracy, macro-F1, confidence, privacy-gain ratios,
and residual high-risk rows. Chance baselines, entropy, and misattribution harm
metrics below are proposed upgrades.

Goal:

Make `evaluate-author-risk` closer to the multifaceted authorship-obfuscation
evaluation described in the research without introducing heavy dependencies by
default.

Primary files:

- `privhsd/author_risk.py`
- `privhsd/rerank.py`
- `privhsd/metrics.py`
- `docs/reference/evaluation.md`
- `tests/test_author_risk.py`
- `tests/test_rerank.py`

Current behavior:

- Trains a character `TfidfVectorizer` plus `LogisticRegression` adversary on
  original text.
- Predicts author labels for original and privatized dev text.
- Reports accuracy, macro-F1, true-author confidence, max confidence, privacy
  gain ratios, and residual high-risk rows.

Recommended upgrades:

1. Add random-chance baseline fields.
   - `chance_accuracy = 1 / author_count`.
   - `chance_macro_f1 = 1 / author_count` as a simple readable proxy.
   - Report `distance_to_chance_accuracy` for original and privatized.
   - Do not overstate this as a calibrated statistical guarantee.

2. Add misattribution harm metrics.
   - For each dev row, if privatized prediction is wrong, report the wrong
     author's confidence bucket, not raw text.
   - Add `wrong_author_confidence_mean`.
   - Add `high_confidence_wrong_author_count` with default threshold `0.7`.
   - Add `top_misattributed_author_pairs` as counts of
     `true_author -> predicted_author`.
   - Keep examples as row ID, true author hash or label, predicted author hash
     or label, and confidence. Do not include text.

3. Add confidence entropy.
   - Compute normalized entropy over author probabilities.
   - Higher entropy after privatization is good because the classifier is less
     certain.
   - Report `entropy_mean` for original and privatized.

4. Add slice summaries when `label_col` exists.
   - Report author-risk comparison by label, for example hate vs not-hate.
   - This is important because style obfuscation can help non-hate rows while
     damaging toxic rows, or vice versa.
   - Keep small-slice handling explicit: if a slice cannot be stratified,
     report `status=skipped` for that slice.

5. Add optional adversary variants behind flags.
   - Default remains char n-gram logistic regression.
   - Add `--adversary word-char` to combine char and word features only if
     scikit-learn supports it without new dependencies.
   - Add `--adversary svm` only if it improves local signal and remains fast.
   - Do not add transformer authorship adversaries to the default path.

6. Add a train/test leakage check.
   - If exact duplicate normalized texts appear in both splits, report counts.
   - For author risk, duplicate text can make apparent privacy worse or better
     for the wrong reason.

Suggested report additions:

```json
{
  "chance": {
    "author_count": 3,
    "accuracy": 0.3333,
    "macro_f1_proxy": 0.3333
  },
  "original": {
    "entropy_mean": 0.12,
    "distance_to_chance_accuracy": 0.6667
  },
  "privatized": {
    "entropy_mean": 0.74,
    "distance_to_chance_accuracy": 0.1111
  },
  "misattribution": {
    "wrong_author_confidence_mean": 0.51,
    "high_confidence_wrong_author_count": 2,
    "top_author_pairs": [
      {"true_author": "author_a", "predicted_author": "author_b", "count": 4}
    ]
  }
}
```

Acceptance tests:

- Existing `tests/test_author_risk.py` keeps passing.
- Add a fixture where privatized text intentionally maps all authors to one
  style and verify entropy increases or true-author confidence decreases.
- Add a fixture with high-confidence wrong-author predictions and verify
  misattribution fields are present.
- Verify no raw `original_text` or `privatized_text` appears in JSON output.

Focused command:

```bash
python -m pytest -q tests/test_author_risk.py tests/test_rerank.py
```

## Phase 2: Task-Aware Gates For Style Rewrites

Goal:

Any future style obfuscator must preserve hate-speech detection utility. The
repo should reject candidates that erase target, abusive, threat, exclusion,
negation, quotation, or counterspeech cues.

Primary files:

- `privhsd/rerank.py`
- `privhsd/metrics.py`
- `privhsd/cue_checks.py`
- `privhsd/semantic_triage.py`
- `privhsd/auto/engine.py`
- `tests/test_rerank.py`
- `tests/test_cue_checks.py`
- `tests/test_semantic_triage.py`

Recommended candidate gate contract:

Every generated candidate should be converted into a `Candidate` object and
scored through the existing reranker or a shared validation helper. The helper
should return:

```python
CandidateValidation(
    accepted: bool,
    reject_reasons: tuple[str, ...],
    target_retention: float,
    utility_retention: float,
    direct_identifier_delta: int,
    style_risk_delta: int,
    length_drift: float,
    author_risk_confidence: float | None,
)
```

Hard reject reasons:

- `target_cue_loss`
- `utility_cue_loss`
- `negation_or_modality_loss`
- `counterspeech_context_loss`
- `direct_identifier_increase`
- `quasi_identifier_increase`
- `style_risk_increase`
- `max_length_drift_exceeded`
- `model_runtime_error`
- `unsafe_dependency_or_remote_code`

Soft penalties:

- small length drift;
- true-author confidence remains high;
- style markers remain;
- optional HSD utility score drops but cue checks pass.

Implementation guidance:

- Keep deterministic `balanced` candidate as fallback.
- Preserve placeholders before sending text to any model. If a model cannot
  safely handle `[PERSON]`, `[EMAIL]`, `[USER]`, etc., it must not process
  already-privatized text.
- Prefer generating from already-masked text instead of raw text.
- If raw text is needed for an obfuscation method, require local-only execution,
  disabled-by-default status, and no durable raw-text logs.
- Use `metric_depth=fast` in default flows and sampled/deep checks only in audit
  workflows.

Acceptance tests:

- A candidate that drops `refugees should leave` is rejected.
- A candidate that removes `do not` from counterspeech is rejected.
- A candidate that preserves cues but reduces style markers can be selected.
- Candidate audit reports contain reject reasons and no raw hidden model logs.

Focused command:

```bash
python -m pytest -q tests/test_rerank.py tests/test_cue_checks.py tests/test_semantic_triage.py
```

## Phase 3: StyleRemix Candidate Experiment

Goal:

Add StyleRemix as an optional, local, candidate-only style obfuscator after the
Phase 2 gates are reliable.

Why StyleRemix is the best future obfuscator fit:

- It targets fine-grained style axes instead of blindly paraphrasing.
- It uses LoRA modules over a frozen LLM, which is more controllable than
  generic prompting.
- Its public repo is Apache-2.0.
- It is interpretable enough for audit notes: agents can record which axes were
  perturbed.

Why not default:

- The public quickstart uses Llama-3 8B and expects GPU inference.
- It was evaluated on domains such as speeches, fiction, academic articles, and
  blogs, not short toxic microtexts.
- It can still alter tone, sarcasm, or intensity if configured poorly.
- It should not run on official data unless model artifacts are local and the
  operator explicitly enables it.

Suggested package extra:

```toml
[project.optional-dependencies]
style-remix = [
  "torch>=2.1",
  "transformers>=4.40",
  "peft>=0.10",
  "accelerate>=0.29",
]
```

Do not add this extra until the wrapper is implemented. If agents depend on the
upstream repo directly, check the exact requirements and pin only what is
needed.

Suggested files:

- `privhsd/models/style_remix_runtime.py`
- `privhsd/style_axes.py` or a small config inside the runtime
- `privhsd/rerank.py`
- `privhsd/auto/config.py`
- `privhsd/auto/context.py`
- `privhsd/auto/engine.py`
- `tests/test_style_remix_runtime.py`
- `tests/test_rerank.py`
- `docs/reference/providers_and_models.md`

Runtime API:

```python
@dataclass(frozen=True)
class StyleRemixConfig:
    model_path: Path
    adapter_dir: Path
    device: str = "auto"
    max_new_tokens: int = 192
    timeout_seconds: float = 30.0
    allowed_axes: tuple[str, ...] = ("length", "formality")
    blocked_axes: tuple[str, ...] = ("sentiment", "sarcasm", "toxicity")

@dataclass(frozen=True)
class StyleRemixOutput:
    text: str
    axes: dict[str, float]
    runtime_ms: int
    status: str
    error: str | None = None
```

Proposed CLI shape:

Do not add a direct "rewrite and output" command first. Add candidate
generation after the StyleRemix runtime exists:

```bash
python -m privhsd.cli generate-style-remix-candidates \
  --input INPUT.csv \
  --output data/outputs/INPUT.style_remix_candidates.csv \
  --text-col text \
  --id-col id \
  --candidate-col style_remix_candidate \
  --model-path data/models/style-remix/base \
  --adapter-dir data/models/style-remix/adapters \
  --sample-size 200 \
  --report data/outputs/INPUT.style_remix_candidates.report.json
```

Then feed candidates into the existing reranker:

```bash
python -m privhsd.cli rerank-candidates \
  --input data/outputs/INPUT.style_remix_candidates.csv \
  --output data/outputs/INPUT.style_remix_reranked.csv \
  --text-col text \
  --id-col id \
  --author-col author_id \
  --candidate-col style_remix_candidate \
  --audit data/outputs/INPUT.style_remix_reranked.audit.json
```

Routing policy:

- Only run on rows with style risk or residual author-risk pressure.
- Do not run on rows where deterministic output already has perfect privacy and
  no style risk.
- Do not run on very short texts by default. Short toxic posts have too little
  semantic slack.
- Do not run on rows with many placeholders unless placeholder preservation is
  proven.

Axis policy:

- Start with structural axes only: length, sentence structure, function-word
  style if available.
- Avoid axes that can change HSD meaning: sentiment, sarcasm, toxicity,
  profanity, target category, threat intensity.
- If upstream adapter names differ, map them explicitly and record the mapping
  in `docs/reference/providers_and_models.md`.
- If the runtime cannot identify safe axes, disable the provider and report
  `status=skipped`.

Candidate validation:

- Must pass Phase 2 gates.
- Must not reduce target or utility cue retention below the configured
  threshold.
- Must not increase direct identifiers.
- Must not add novel named entities.
- Must reduce style-risk count or author true-confidence on at least some
  sampled repeated-author rows before being considered for larger runs.

Acceptance metrics for a sample run:

- `author_risk.privatized.macro_f1` decreases versus `balanced` or
  `style_scrubbed`.
- `hsd_proxy.utility_cue_retention_mean >= 0.99`.
- `target_cue_retention_mean >= 0.99`.
- `changed_prediction_count` in `benchmark-utility` remains low or improves.
- Candidate acceptance rate is reported. Low acceptance is acceptable; silent
  fallback is not.

Focused tests:

```bash
python -m pytest -q tests/test_rerank.py tests/test_auto_pipeline.py
```

Proposed local smoke after implementation, only when model artifacts exist:

```bash
python -m privhsd.cli generate-style-remix-candidates \
  --input tests/fixtures/manual_privacy_expectations.csv \
  --output data/outputs/manual.style_remix_candidates.csv \
  --text-col text \
  --id-col id \
  --sample-size 5 \
  --report data/outputs/manual.style_remix_candidates.report.json
```

## Phase 4: Back-Translation Baseline Candidate

Goal:

Add a simple, auditable baseline candidate for comparison with StyleRemix and
deterministic style scrub.

Why useful:

- Easy to explain.
- Often removes idiosyncratic syntax.
- Does not require author labels.

Why risky:

- It can neutralize abusive wording.
- It can drop short text semantics.
- It is computationally heavy on large CSVs.
- It can mishandle placeholders and target terms.

Implementation approach:

- Candidate-only command: `generate-backtranslation-candidates`.
- Local models only. No remote translation APIs.
- Disabled by default in `auto`.
- Preserve placeholders with sentinel tokens before translation and restore
  after translation.
- Reject outputs that lose target/action/negation/counterspeech cues.

Suggested package extra:

```toml
[project.optional-dependencies]
translation = ["transformers>=4.40", "torch>=2.1", "sentencepiece"]
```

Suggested pivots:

- `en -> de -> en`
- `en -> fr -> en`

Do not add multilingual auto-detection unless the dataset has language metadata.

Suggested files:

- `privhsd/models/backtranslation_runtime.py`
- `privhsd/local_translation.py` if the project prefers non-model-specific code
- `tests/test_backtranslation_candidates.py`
- `docs/reference/providers_and_models.md`

Acceptance tests:

- Placeholders survive exactly.
- Target cues survive.
- `do not` and similar negation cues survive.
- Runtime reports skipped status when dependencies/models are missing.
- No model download happens unless `--allow-model-download` is passed.

## Phase 5: JAMDEC Research-Only Candidate

Goal:

Evaluate JAMDEC as a research baseline without making it part of default
pipeline or vendoring its code.

Why it is not first-line:

- The upstream README describes keyword extraction, over-generation, filtering,
  and generation that can take a long time depending on dataset/GPU.
- It uses GPT2-XL in the public experiments, which is weaker and slower than the
  current deterministic path for high-volume CSV processing.
- No visible license was found on the GitHub page checked. Agents must verify
  license before importing code.

Allowed integration shape:

- Separate local experiment under ignored `data/experiments/`.
- Export a CSV with an extra candidate column, for example `jamdec_candidate`.
- Feed that CSV into `rerank-candidates`.
- Record aggregate metrics only.

Do not:

- vendor upstream code into `privhsd/`;
- add a default optional extra;
- call JAMDEC inside `auto`;
- bypass reranking or cue checks.

Evaluation command pattern:

```bash
python -m privhsd.cli rerank-candidates \
  --input data/experiments/INPUT.jamdec_candidates.csv \
  --output data/outputs/INPUT.jamdec_reranked.csv \
  --text-col text \
  --id-col id \
  --author-col author_id \
  --candidate-col jamdec_candidate \
  --audit data/outputs/INPUT.jamdec_reranked.audit.json
```

Minimum report:

- rows attempted;
- rows with candidate;
- rows accepted by reranker;
- target/utility retention;
- author-risk change if author IDs exist;
- runtime estimate;
- license note.

## Phase 6: TAROT Research-Only External Experiment

Goal:

Use TAROT's task-oriented policy optimization idea as a research comparison,
not as in-repo code.

Why it is not an in-repo integration now:

- It requires policy optimization or consuming separately trained models.
- The public repo is GPL-3.0, which is not safe to vendor into this project
  without a deliberate license decision.
- Training loops add heavy operational complexity.
- The current repo needs robust exact-format preprocessing more than a new
  training stack.

Allowed shape:

- Run TAROT in a separate environment outside this repo.
- Generate candidate CSVs under ignored `data/experiments/`.
- Import candidates via `--candidate-col tarot_candidate`.
- Evaluate through the same reranker, utility benchmark, cue checks, and
  author-risk evaluator.

If an agent wants to borrow the idea without the code:

- Add a reward-like scoring function inside `rerank.py`, not a training loop.
- Reward privacy as direct identifier reduction, style-risk reduction, and
  lower true-author confidence.
- Reward utility as cue retention, label confidence stability, and low semantic
  drift.
- Penalize toxicity sanitization when the original row is labeled hate.

Do not implement PPO/DPO inside this repo until:

- exact submission and evaluation are stable;
- a licensing decision is documented;
- GPU budget is available;
- there is a small repeated-author benchmark with HSD labels.

## Phase 7: Formal DP Text Generation

Goal:

Avoid premature implementation of formal DP text generators while preserving a
clear path if the project later needs mathematical privacy guarantees.

Recommendation:

- Keep DP text generation research in `docs/research/methodology.md`.
- Do not put ER-AE or token-level exponential mechanisms into official
  preprocessing yet.
- If formal DP is required, start with training-time or aggregate-release DP,
  not full text rewriting.

Why:

- Text-level DP mechanisms are hard to tune for readability.
- Short toxic posts give very little room for perturbation.
- Noise can erase the exact terms needed to train/evaluate HSD models.
- User-level DP needs contribution bounds and privacy accounting across all
  per-user records.

Potential future path:

1. Bound contributions with `bound-contributions`.
2. Train a utility model with user-level DP using `opacus` or another audited
   library in a separate `dp-training` workstream.
3. Release aggregate metrics or synthetic examples only after explicit privacy
   accounting.
4. Keep raw text anonymization deterministic unless a DP rewrite passes HSD
   cue gates.

## Metadata Privacy Follow-Up

Problem:

If a release keeps `author_id`, the author is directly visible. Text
obfuscation can reduce style leakage but cannot hide an explicit author column.

Recommendation:

Add a future `pseudonymize-metadata` utility only for public release datasets
where metadata changes are allowed.

Suggested behavior:

- Input: CSV, metadata columns, secret salt or salt file, output path.
- Output: same schema but selected metadata values replaced by deterministic
  HMAC hashes or stable local pseudonyms.
- Report: columns transformed, nonblank counts, collision count, salt handling
  note, no raw values.
- Default: do not alter official challenge submissions.

Suggested future command:

```bash
python -m privhsd.cli pseudonymize-metadata \
  --input INPUT.bounded.auto.csv \
  --output data/outputs/INPUT.public_release.csv \
  --metadata-col author_id \
  --metadata-col user \
  --salt-env PRIVHSD_PSEUDONYM_SALT \
  --report data/outputs/INPUT.public_release.metadata_report.json
```

Acceptance tests:

- Same input value maps to same pseudonym within one run.
- Different salts produce different pseudonyms.
- Blank values stay blank or are handled according to explicit flag.
- Report contains no raw metadata values.
- Exact submission runbooks warn not to use this unless rules permit metadata
  changes.

## End-To-End Recommended Workflow

When row filtering is allowed:

```bash
python -m privhsd.cli profile-dataset \
  --input INPUT.csv \
  --output data/outputs/INPUT.profile.json

python -m privhsd.cli bound-contributions \
  --input INPUT.csv \
  --output data/outputs/INPUT.bounded.csv \
  --author-col author_id \
  --id-col id \
  --text-col text \
  --max-records-per-author 25 \
  --strategy stratified \
  --stratify-col label \
  --stratify-col source \
  --report data/outputs/INPUT.bounded.report.json

python -m privhsd.cli anonymize \
  --input data/outputs/INPUT.bounded.csv \
  --output data/outputs/INPUT.bounded.auto.csv \
  --text-col text \
  --id-col id \
  --mode auto \
  --metric-depth fast \
  --audit data/outputs/INPUT.bounded.auto.audit.json

python -m privhsd.cli evaluate-author-risk \
  --input data/outputs/INPUT.bounded.auto.csv \
  --text-col text \
  --privatized-col privatized_text \
  --author-col author_id \
  --id-col id \
  --label-col label \
  --output data/outputs/INPUT.bounded.auto.author_risk.json

python -m privhsd.cli benchmark-utility \
  --input data/outputs/INPUT.bounded.auto.csv \
  --text-col text \
  --privatized-col privatized_text \
  --label-col label \
  --id-col id \
  --output data/outputs/INPUT.bounded.auto.utility.json
```

When exact-format challenge submission is required:

```bash
python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/INPUT.auto.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --manifest data/outputs/INPUT.auto.manifest.json

python -m privhsd.cli validate-submission \
  --source INPUT.csv \
  --submission data/outputs/INPUT.auto.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/INPUT.auto.validation.json
```

In exact-format mode, run `evaluate-author-risk` only if the output contains
both original and privatized text columns or if a separate comparison file is
constructed under ignored `data/`. Do not change the submitted CSV shape just
to run an audit.

## Agent Task Cards

### Task A: Harden Contribution Bounding Reports

Workstream:

Author-aware group privacy.

Files:

- `privhsd/contribution_bounding.py`
- `tests/test_contribution_bounding.py`
- `docs/runbooks/official_submission.md`

Steps:

1. Add label/source before/after counts when `--stratify-col` is provided.
2. Add `blank_author_policy` to the report.
3. Add tests for `first`, `last`, `longest`, `shortest`, and `random`
   strategies.
4. Add official runbook warning that row filtering is non-submission unless
   rules allow it.

Done when:

- focused tests pass;
- report contains no raw text;
- docs explain exact-format incompatibility.

### Task B: Add Misattribution Harm Metrics

Workstream:

Metrics and evaluation.

Files:

- `privhsd/author_risk.py`
- `tests/test_author_risk.py`
- `docs/reference/evaluation.md`

Steps:

1. Compute wrong-author confidence and high-confidence wrong-author counts.
2. Add top true-author to predicted-author pairs.
3. Add normalized entropy.
4. Add chance baseline.
5. Add tests with synthetic style markers.

Done when:

- existing author-risk tests pass;
- report remains raw-text-free;
- docs explain that high-confidence wrong-author predictions are a harm, not a
  privacy win.

### Task C: Centralize Candidate Validation

Workstream:

Candidate generation and reranking.

Files:

- `privhsd/rerank.py`
- `privhsd/auto/engine.py`
- `tests/test_rerank.py`
- `tests/test_auto_pipeline.py`

Steps:

1. Extract shared validation from existing candidate scoring.
2. Make reject reasons stable strings.
3. Use the same helper for supplied candidate columns and future model
   candidates.
4. Add tests for target loss, negation loss, style improvement, and identifier
   increase.

Done when:

- all current rerank behavior is preserved;
- future candidate generators can call one validation function;
- audit reports list reject reasons.

### Task D: Prototype StyleRemix Candidate Wrapper

Workstream:

Candidate generation and optional model runtime.

Files:

- `privhsd/models/style_remix_runtime.py`
- `privhsd/cli.py`
- `privhsd/rerank.py`
- `tests/test_style_remix_runtime.py`
- `docs/reference/providers_and_models.md`

Steps:

1. Add a runtime that reports `status=skipped` when dependencies or local
   artifacts are missing.
2. Add a candidate-generation command that writes an extra candidate column.
3. Preserve placeholders and reject unsafe axes.
4. Feed generated candidates into reranking, not direct output.
5. Run only on a sampled fixture first.

Done when:

- no dependency is required for normal install;
- no model download happens unless explicit;
- missing artifacts produce structured skipped report;
- candidate output passes existing cue tests on accepted rows.

### Task E: Back-Translation Baseline

Workstream:

Candidate generation and optional model runtime.

Files:

- `privhsd/models/backtranslation_runtime.py`
- `privhsd/cli.py`
- `tests/test_backtranslation_candidates.py`
- `docs/reference/providers_and_models.md`

Steps:

1. Add placeholder sentinel protection.
2. Add local-only model loading.
3. Add candidate command and structured skipped status.
4. Gate through reranking.
5. Compare against `style_scrubbed` and StyleRemix, not against no privacy.

Done when:

- placeholders survive exactly;
- cue retention tests pass;
- runtime is disabled unless dependencies and local models are present.

## Required Verification Matrix

Agents should run the smallest relevant set first, then broader checks.

| Change type | Minimum tests |
| --- | --- |
| Contribution bounding | `python -m pytest -q tests/test_contribution_bounding.py tests/test_public_api.py` |
| Author-risk metrics | `python -m pytest -q tests/test_author_risk.py tests/test_rerank.py` |
| Candidate validation | `python -m pytest -q tests/test_rerank.py tests/test_auto_pipeline.py tests/test_cue_checks.py` |
| Optional model runtime | runtime-specific tests plus `tests/test_auto_pipeline.py` |
| Docs-only change | `python -m pytest -q tests/test_public_api.py` if code paths were not touched |

Known environment caveat:

`tests/test_token_policy.py` imports `torch` unconditionally in the current
tree. If `torch` is not installed, full test collection can fail before
reaching unrelated tests. In that environment, either install the token-policy
extra or run:

```bash
python -m pytest -q --ignore=tests/test_token_policy.py
```

Do not hide unrelated failures. Report them separately with exact test names.

## Reporting Rules

All reports for author-aware privacy work must:

- include command/configuration fields;
- include row counts before and after when rows are dropped;
- include author-group counts, not raw author text unless the original column is
  already a non-sensitive challenge identifier;
- include raw-text-free examples by row ID only;
- state whether the run is exact-format compatible;
- state whether model artifacts were local, downloaded, skipped, or errored;
- state that local author-risk metrics are proxy evidence, not a formal
  anonymity guarantee.

## Stop Conditions

Stop and ask for a project decision before:

- vendoring GPL code;
- changing exact submission row count or metadata by default;
- enabling remote model/API calls;
- adding a heavy model to default install dependencies;
- claiming formal DP without a privacy accountant and documented epsilon/delta;
- publishing public examples derived from sensitive raw rows.

## Success Criteria

This work is successful when:

- release/training workflows can cap repeated authors with a raw-text-free
  report;
- exact submissions remain exact-format;
- author-risk reports show whether text-only author signal dropped toward
  chance;
- misattribution harm is visible, not hidden as a privacy win;
- optional style generators are candidate-only and rejected when HSD cues drift;
- docs clearly separate stable contracts, operational runbooks, and planning
  handoffs.
