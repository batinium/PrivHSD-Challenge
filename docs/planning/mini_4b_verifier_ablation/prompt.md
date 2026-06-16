# Mini 4B Verifier Ablation Prompt

## Objective

Run a limited ablation to decide whether a small local model, roughly 3B-4B,
should be used as a cheap verifier/router around the main local LLM HSD review
model.

The current main model is:

- Endpoint: `http://100.120.207.64:1234/v1/chat/completions`
- Model: `openai/gpt-oss-20b`
- Batch size: `10`
- Temperature: `0`
- Context window: keep the current LM Studio/server setting unchanged

Do not run the whole dataset for this ablation. Use selective samples from known
main-model errors and controls. Keep all generated artifacts under
`data/outputs/`.

## Background

The full local LLM review run on `data/train/train_split.csv` produced:

- Output directory:
  `data/outputs/train_split_full_pipeline_fixed_20260615_233312`
- Rows: `1154`
- Accuracy: `0.7686`
- Balanced accuracy: `0.7675`
- Precision: `0.6065`
- Recall: `0.7644`
- F1: `0.6764`
- Confusion matrix:
  - TP: `279`
  - TN: `608`
  - FP: `181`
  - FN: `86`

The precision is low enough that predicted-positive rows need a verifier. The
false-negative count is also high enough that a separate recall route should be
tested for model-negative rows with strong identity/slur/protected-target cues.

The previous prompt experiments suggested:

- The current strict prompt misses many gold-positive identity-coded attacks.
- Broad recall prompts recover FNs but increase FP risk.
- A contextual prompt was promising on two 20-FN/20-FP batches, but not stable
  enough to apply as the default without a larger controlled sample.

The LLM `pii_leftover` field is advisory only. It is not deliberate PII and it
does not rewrite output text. This ablation is about HSD classification/routing,
not PII masking.

## Local Model Inventory

Query the model list at the start of the run:

```bash
curl -sS http://100.120.207.64:1234/v1/models
```

The model list seen on 2026-06-16 included these likely small verifier
candidates:

- `qwen3.5-4b`
- `qwen/qwen3-4b`
- `qwen/qwen3-4b-2507`
- `shieldgemma-2-4b-it`
- `google/gemma-3n-e4b`
- `google/gemma-4-e4b`
- `nvidia/nemotron-3-nano-4b`
- `mistralai/ministral-3-3b`
- `microsoft/phi-4-mini-reasoning`
- `google/gemma-4-e2b`
- `qwen/qwen3-1.7b`

Recommended shortlist order:

1. `qwen/qwen3-4b-2507`
2. `qwen3.5-4b`
3. `qwen/qwen3-4b`
4. `shieldgemma-2-4b-it`
5. `google/gemma-3n-e4b`
6. `nvidia/nemotron-3-nano-4b`
7. `mistralai/ministral-3-3b`

Use `google/gemma-4-e2b` and `qwen/qwen3-1.7b` only as cost-floor probes if the
4B models are too slow. Treat `gemma-4-e4b-uncensored-hauhaucs-aggressive` as
exploratory only; do not select it for the final production route unless it is
clearly better and manually inspected, because calibration may be unstable.

Optional larger local reference models seen in LM Studio:

- `qwen/qwen3.5-9b`
- `google/gemma-4-12b`
- `google/gemma-4-12b-qat`
- `qwen/qwen3.6-27b`
- `openai/gpt-oss-20b`
- `gpt-oss-safeguard-20b`

Do not expand the default ablation to all larger models. The goal is not to find
a universal best model; it is to find a small, low-overhead router that improves
the current fast `openai/gpt-oss-20b` pipeline. Use one larger model only as a
calibration reference if the small-model results are unclear. If a 9B/12B model
is dramatically better, document the error patterns it fixes and try to distill
that behavior into the verifier/adjudication prompts before proposing it as a
runtime dependency.

Ignore embedding models.

## Uncensored / Aggressive Model Probe

There is currently one uncensored/aggressive local candidate:

- `gemma-4-e4b-uncensored-hauhaucs-aggressive`

Run it as a targeted probe, not as a default candidate. The hypothesis is that
less safety-tuned models may interact more directly with toxic language and
recover false negatives caused by model caution or refusal-like behavior.

Evaluate it specifically on:

- `FN60`, especially direct identity-coded insults that the main model marked
  `none`
- `FP60`, especially quoted/reported/counterspeech rows and vulgar non-identity
  profanity
- `TN20` controls, to check whether it over-labels offensive-but-non-HSD text

Selection rule:

- Useful as recall router if it flags many FNs while routing few TN controls.
- Not useful as final classifier if it increases FP risk on quotes,
  counterspeech, non-identity profanity, or political/institutional criticism.
- Do not allow it to directly override the main model in production unless it is
  manually inspected and beats the safer candidates on both precision and recall
  controls.

If the uncensored model is strong on recall but weak on precision, use it only
behind a high-precision gate: cue-bearing main-negative rows go to the
uncensored model, and only its `disagree`/`uncertain` rows are sent to the main
20B adjudicator.

## Current Main Prompt

The current runtime system prompt is defined in
`contextsafe_hsd/models/local_llm_hsd_review_runtime.py`:

```text
Classify cleaned text for a hate-speech dataset. Hate speech means the text itself endorses, advocates, commands, or asserts abuse, inferiority, exclusion, dehumanization, or violence against a protected identity group. Return hate=false for quotations, reports, moderation requests, condemnation, counterspeech, negation, hypotheticals, questions, or examples that mention hateful words without endorsing them. Offensive profanity without a protected target is not HSD. Return binary labels, allowed reason tags, exact residual PII substrings only, and no confidence or explanation.
```

Do not replace this prompt globally during the ablation. Test alternative prompts
in isolated scripts/artifacts only.

## Existing Analysis Files

If present, reuse these files:

- `data/outputs/train_split_full_pipeline_fixed_20260615_233312/llm_false_positives.csv`
- `data/outputs/train_split_full_pipeline_fixed_20260615_233312/llm_false_negatives.csv`
- `data/outputs/train_split_full_pipeline_fixed_20260615_233312/llm_classification_disagreements.csv`
- `data/outputs/train_split_full_pipeline_fixed_20260615_233312/llm_classification_disagreements_summary.json`
- `data/outputs/train_split_full_pipeline_fixed_20260615_233312/prompt_variant_contextual_2x20.json`

If the disagreement CSVs are missing, regenerate them from the full run artifact:

```bash
python - <<'PY'
import csv, json
from pathlib import Path

run = Path("data/outputs/train_split_full_pipeline_fixed_20260615_233312")
source_csv = Path("data/train/train_split.csv")
protected_csv = run / "train_split.protected.csv"
result_json = run / "protect_result.json"

result = json.loads(result_json.read_text())
reviews = {str(r["id"]): r for r in result["classification"]["row_reviews"]}

with source_csv.open(newline="", encoding="utf-8") as f:
    source_rows = {str(r["ID"]): r for r in csv.DictReader(f)}
with protected_csv.open(newline="", encoding="utf-8") as f:
    protected_rows = {str(r["ID"]): r for r in csv.DictReader(f)}

fieldnames = [
    "id", "gold_hs", "llm_hate", "error_type", "hsd_reasons",
    "review_needed", "parse_status", "accepted_pii_suggestion_count",
    "source_text", "cleaned_text",
]
rows, fp, fn = [], [], []
for row_id, src in source_rows.items():
    review = reviews[row_id]
    gold = str(src.get("hs", "")).strip()
    pred = "1" if review.get("hate") is True else "0"
    if gold not in {"0", "1"} or gold == pred:
        continue
    out = {
        "id": row_id,
        "gold_hs": gold,
        "llm_hate": pred,
        "error_type": "false_positive" if pred == "1" else "false_negative",
        "hsd_reasons": "|".join(review.get("hsd_reasons") or []),
        "review_needed": review.get("review_needed"),
        "parse_status": review.get("parse_status"),
        "accepted_pii_suggestion_count": review.get("accepted_pii_suggestion_count"),
        "source_text": src.get("text", ""),
        "cleaned_text": protected_rows.get(row_id, {}).get("text", ""),
    }
    rows.append(out)
    (fp if out["error_type"] == "false_positive" else fn).append(out)

for name, data in [
    ("llm_classification_disagreements.csv", rows),
    ("llm_false_positives.csv", fp),
    ("llm_false_negatives.csv", fn),
]:
    with (run / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
PY
```

## Sampling Plan

Use cleaned text for all LLM prompts. Do not include gold labels in prompts.

Build one fixed eval set and reuse it across all models:

- `FP60`: 60 false positives from `llm_false_positives.csv`
- `FN60`: 60 false negatives from `llm_false_negatives.csv`
- `TP20`: 20 true positives from the main run
- `TN20`: 20 true negatives from the main run

Total: 160 rows.

This is small enough to run repeatedly and large enough to expose obvious
precision/recall tradeoffs. With batch size `10`, this is 16 requests per model.

Selection rules:

- For `FP60`, stratify by `hsd_reasons` so the sample is not all one error
  pattern. Include common tags such as `identity_attack`,
  `identity_attack|dehumanization`, `inferiority_claim`, and `threat`.
- For `FN60`, include mostly `none` rows plus the few `quote_or_report` misses.
- For `TP20`, sample predicted-positive/gold-positive rows across different
  reason tags.
- For `TN20`, sample predicted-negative/gold-negative rows, including rows with
  offensive profanity but no protected target if available.
- Save the sampled IDs and rows to
  `data/outputs/mini_4b_verifier_ablation/eval_set_160.csv`.

Use this deterministic sampler unless there is a clear reason to hand-pick rows:

```bash
python - <<'PY'
import csv, json, random
from collections import defaultdict
from pathlib import Path

seed = 20260616
random.seed(seed)

source_csv = Path("data/train/train_split.csv")
run = Path("data/outputs/train_split_full_pipeline_fixed_20260615_233312")
protected_csv = run / "train_split.protected.csv"
result_json = run / "protect_result.json"
out_dir = Path("data/outputs/mini_4b_verifier_ablation")
out_dir.mkdir(parents=True, exist_ok=True)
out_csv = out_dir / "eval_set_160.csv"

result = json.loads(result_json.read_text())
reviews = {str(r["id"]): r for r in result["classification"]["row_reviews"]}

with source_csv.open(newline="", encoding="utf-8") as f:
    source_rows = {str(r["ID"]): r for r in csv.DictReader(f)}
with protected_csv.open(newline="", encoding="utf-8") as f:
    protected_rows = {str(r["ID"]): r for r in csv.DictReader(f)}

cases = []
for row_id, src in source_rows.items():
    review = reviews[row_id]
    gold = str(src.get("hs", "")).strip()
    pred = "1" if review.get("hate") is True else "0"
    if gold not in {"0", "1"}:
        continue
    if pred == "1" and gold == "1":
        case_type = "TP"
    elif pred == "0" and gold == "0":
        case_type = "TN"
    elif pred == "1" and gold == "0":
        case_type = "FP"
    else:
        case_type = "FN"
    cases.append(
        {
            "id": row_id,
            "case_type": case_type,
            "gold_hs": gold,
            "main_hate": pred,
            "main_hsd_reasons": "|".join(review.get("hsd_reasons") or []),
            "review_needed": review.get("review_needed"),
            "parse_status": review.get("parse_status"),
            "source_text": src.get("text", ""),
            "cleaned_text": protected_rows.get(row_id, {}).get("text", ""),
        }
    )

def stratified(rows, n):
    groups = defaultdict(list)
    for row in rows:
        groups[row["main_hsd_reasons"] or "none"].append(row)
    for group_rows in groups.values():
        random.shuffle(group_rows)
    keys = sorted(groups, key=lambda key: (-len(groups[key]), key))
    selected = []
    while keys and len(selected) < n:
        next_keys = []
        for key in keys:
            if groups[key] and len(selected) < n:
                selected.append(groups[key].pop())
            if groups[key]:
                next_keys.append(key)
        keys = next_keys
    return selected

targets = {"FP": 60, "FN": 60, "TP": 20, "TN": 20}
sample = []
for case_type, n in targets.items():
    pool = [row for row in cases if row["case_type"] == case_type]
    sample.extend(stratified(pool, n))

fieldnames = [
    "id", "case_type", "gold_hs", "main_hate", "main_hsd_reasons",
    "review_needed", "parse_status", "source_text", "cleaned_text",
]
with out_csv.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(sample)

print(out_csv)
print({key: sum(1 for row in sample if row["case_type"] == key) for key in targets})
PY
```

If runtime is tight, use this staged budget:

1. Smoke: 10 rows per candidate, mixed `FP5`/`FN5`.
2. Screen: 40 rows per candidate, `FP20`/`FN20`.
3. Shortlist: 160 rows only for the top 3 candidates.

## Candidate Verifier Prompt

Use this prompt for small-model verifier screening:

```text
You are a verifier for a hate-speech dataset label. You receive cleaned text and
the main model's binary label. Your job is not to be broad or creative. Decide
whether the main label is clearly supported, clearly wrong, or needs a stronger
model to adjudicate.

Hate speech is true when the author directly demeans, attacks, threatens,
excludes, or asserts inferiority about a person or group using protected
identity references or identity-coded slurs. Protected or identity-coded
categories include race, ethnicity, nationality, religion, gender, sex, sexual
orientation, trans identity, disability, and similar identity classes.

Return "agree" when the main label is clearly correct.
Return "disagree" when the main label is clearly wrong.
Return "uncertain" when context, quotation, counterspeech, sarcasm, negation, or
target ambiguity makes the decision hard.

Important false-positive guards:
- Vulgar insults with no protected identity cue are not hate speech.
- Sexual profanity alone is not hate speech.
- Political, institutional, or ideological criticism is not hate speech unless
  it uses protected identity abuse.
- Quoted, reported, moderated, debunked, or counterspeech examples are not hate
  speech unless the author endorses the abuse.

Important false-negative guards:
- Direct slur-as-insult or identity-coded insult can be hate speech even without
  an explicit policy demand.
- Attacking an individual can be hate speech when the attack relies on protected
  identity or identity-coded language.

Output only JSON:
{
  "id": "...",
  "decision": "agree" | "disagree" | "uncertain",
  "suggested_label": true | false | null,
  "reason": "protected_identity_attack" | "no_protected_target" | "quote_report_or_counterspeech" | "identity_cue_but_ambiguous" | "non_identity_profanity" | "other"
}
```

For batched calls, send an `items` array and require an `items` array in return.
Keep `temperature: 0`.

## Main-Model Adjudication Prompt

Use this only for rows routed by the small verifier. Do not send all rows back to
the big model.

```text
You are adjudicating a possible error in a hate-speech dataset label. A smaller
verifier disagreed with or was uncertain about the main model's previous label.

Decide the final binary label from the cleaned text only. Use the challenge
label policy:
- true when the author directly demeans, attacks, threatens, excludes, or asserts
  inferiority about a person or group using protected identity references or
  identity-coded slurs.
- false for vulgar insults without protected identity cues, sexual profanity
  alone, political/institutional criticism, quoted/reported/debunked language,
  moderation examples, counterspeech, negation, hypotheticals, and ambiguous
  cases without clear author endorsement.
- direct identity-coded slur-as-insult can be true even without an explicit
  policy demand.

Output only JSON:
{
  "id": "...",
  "hate": true | false,
  "reason": "protected_identity_attack" | "threat_or_exclusion" | "quote_report_or_counterspeech" | "no_protected_target" | "non_identity_profanity" | "ambiguous_false" | "other"
}
```

## Strategies To Compare

Evaluate these strategies offline on the fixed eval set:

### Strategy A: Small Model Direct Relabel

Small model reads cleaned text and outputs final `hate`.

Purpose: measure whether the small model is independently competent.

Expected risk: high. Do not choose this for production unless it is surprisingly
strong on both FP and FN cases.

### Strategy B: Positive Verifier Only

For rows where main model predicted `true`, small model checks whether the
positive label is clearly wrong.

Production-like action:

- `agree`: keep main positive
- `uncertain`: send to big adjudicator
- `disagree`: send to big adjudicator

Never let the small model directly flip a positive to negative in production.
For the ablation, compute both:

- direct flip score
- routed-to-big score

This estimates precision gain and overhead.

### Strategy C: Recall Trigger On Negative Rows

For rows where main model predicted `false`, only route rows that have strong
surface cues:

- protected identity term
- identity-coded slur/profanity cue
- detector target cue count above zero

Small model checks whether the negative label may be wrong.

Production-like action:

- `agree`: keep main negative
- `uncertain`: send to big adjudicator
- `disagree`: send to big adjudicator

This estimates recall gain and overhead.

### Strategy D: Combined Router

Use Strategy B for positives and Strategy C for cue-bearing negatives.

This is the only production candidate unless Strategy A is unexpectedly strong.

## Metrics

For each candidate model and strategy, report:

- parse success rate
- elapsed seconds
- requests made
- average seconds per row
- direct relabel accuracy on the eval set
- precision on the eval set
- recall on the eval set
- F1 on the eval set
- FP rescue rate:
  - among baseline FPs, percent flagged `disagree` or `uncertain`
- TP risk rate:
  - among baseline TPs, percent flagged `disagree`
- FN rescue rate:
  - among baseline FNs, percent flagged `disagree` or `uncertain`
- TN overhead/risk rate:
  - among baseline TNs, percent flagged `disagree` or `uncertain`
- estimated production overhead:
  - routed rows / evaluated rows

Suggested selection score:

```text
score =
  2.0 * FP_rescue_rate
+ 1.5 * FN_rescue_rate
- 2.5 * TP_disagree_rate
- 1.5 * TN_route_rate
- 1.0 * parse_failure_rate
- 0.2 * seconds_per_row
```

Do not select a model purely by this score. Inspect representative routed rows.

## Stop Conditions

Stop early for a candidate if any of these happen:

- parse success below `95%` on the 40-row screen
- it marks most offensive-but-non-identity rows as hate
- it fails to flag obvious baseline FPs in the first `FP20`
- it routes more than `60%` of control TN rows
- it is slower than expected enough to erase the overhead advantage

## Expected Decision

The most likely useful design is:

1. Keep `openai/gpt-oss-20b` as the main classifier.
2. Use a 4B model only as a router/verifier.
3. Send verifier `disagree` and `uncertain` rows back to the 20B adjudication
   prompt.
4. Do not allow the 4B model to directly override the 20B in production.

This adds overhead only on disputed rows and should improve precision more
safely than replacing the main prompt globally. A recall route should be tested
separately because precision verification alone will not recover FNs.

## Deliverables

Write results under:

`data/outputs/mini_4b_verifier_ablation/`

Required files:

- `models_seen.json`
- `eval_set_160.csv`
- `candidate_screen_results.json`
- `shortlist_results.json`
- `adjudication_results.json`
- `recommendation.md`

The final `recommendation.md` must answer:

- Which 4B model should be used, if any?
- Should the small model be direct relabeler, positive verifier, recall router,
  or combined router?
- What is the estimated overhead?
- What is the observed precision/recall tradeoff?
- Which error patterns remain unresolved?
- Should any prompt change be promoted to the actual runtime?

Do not commit generated data artifacts. Commit only code or planning-doc changes
if requested.
