# Final Pitch Outline

Date: 2026-06-12

Use this as the five-minute Dragon's Den story. The goal is to show a working
system, a rights-aware privacy/utility tradeoff, and a plausible public-impact
deployment path.

## One-Sentence Claim

ContextSafe-HSD lets researchers, NGOs, and public-interest teams share
hate-speech datasets more safely by reducing author-identifying signals while
preserving the evidence needed to detect and review hate.

## Five-Minute Flow

1. Problem: hate-speech datasets are sensitive twice. They can expose the
   author or victim, and careless anonymization can erase the very context that
   proves abuse, counterspeech, quotation, or protected-group targeting.
2. System: a local CSV-to-CSV privatization pipeline with exact-format
   validation, typed placeholders, manifests, hashes, cue checks, slice
   regression, and human-review queues.
3. Evidence: show the current `balanced` result and transformer token-policy
   ensemble results without raw text.
4. Rights framing: this is not a takedown engine. It preserves target/action
   and negation cues so vulnerable-group abuse is not hidden and lawful
   expression is not flattened into "hate" by a noisy model.
5. Demo: run a small synthetic example through the CLI or web workbench, then
   show the audit, risk gauges, and export manifest.

## Evidence To Show

| Evidence | Number | Why it matters |
| --- | ---: | --- |
| Merged public rows processed | 159,668 | Practical scale beyond toy data. |
| Identifier detections reduced | 40,304 -> 5 | Concrete privacy pressure. |
| Target cue retention | 0.9999 | Does not erase who was targeted. |
| Utility cue retention | 0.9999 | Does not erase hostile/action evidence. |
| Rationale/span preservation | 47,729/47,740 | Uses dataset evidence spans where available. |
| RoBERTa token-policy dev macro F1 | 0.9061 | Transformer fine-tuning is implemented. |
| RoBERTa grouped K-fold macro F1 | 0.8977 +/- 0.0152 | Anti-overfit evidence. |
| External ensemble macro F1 | 0.8837 | RoBERTa plus HateBERT generalizes to unseen TweetEval data. |
| External ensemble `PROTECT_TARGET` F1 | 0.8143 | Target-protection training is measurable. |

## Demo Script

```bash
python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/SUBMISSION.balanced.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode balanced \
  --manifest data/outputs/SUBMISSION.balanced.manifest.json

python -m privhsd.cli validate-submission \
  --source INPUT.csv \
  --submission data/outputs/SUBMISSION.balanced.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/SUBMISSION.balanced.validation.json
```

Show:

- exact row and column preservation;
- before/after only on synthetic or consented demo text;
- typed placeholders;
- cue-retention report;
- source/label slice warnings;
- manifest with command, commit, and hashes.

## Website Wow Factor

Build a local "Privacy Review Workbench" for civilians, NGOs, journalists, and
researchers:

- paste text or upload a CSV;
- run privatization locally or on an NGO server;
- highlight changed spans with labels such as `MASK_IDENTIFIER` and
  `PROTECT_TARGET`;
- show risk gauges for identifiers, author style, and HSD cue drift;
- route uncertain rows into a human-review queue;
- export anonymized CSV, manifest, and audit report;
- provide a policy-safe mode that stores no raw text in server logs.

This is more compelling than a leaderboard-only story because policymakers can
see how the tool would be used responsibly: protect people, preserve evidence,
and keep humans in charge.

## Judge Questions

**Is this just PII redaction?**

No. It also handles quasi-identifiers, author-style pressure, cue retention,
source-aware regression, author-risk evaluation when labels exist, and
transformer token-action policy evidence.

**Why preserve target words?**

Because erasing target identity can hide hate against vulnerable groups and can
also distort counterspeech or reporting. The system preserves targets by
default and reports cue retention.

**Did you fine-tune a transformer?**

Yes. RoBERTa and HateBERT token-policy models were fine-tuned on weak
token-action labels, evaluated with grouped K-folds, and tested on external
TweetEval data. They are advisory so that deterministic audit and validation
still control final output.

**What are the limitations?**

Official scores may differ from local proxies. True author-risk reduction
requires repeated author IDs. Weak token labels are not human privacy labels.
The website demo must avoid storing raw sensitive text. LLM and DPMLM rewrites
are candidate-only until they beat deterministic outputs under audit.

## Close

ContextSafe-HSD is a rights-aware data protection layer: it makes sensitive HSD
datasets safer to share, keeps evidence usable, and produces transparent
artifacts that a human reviewer, NGO, or policymaker can inspect.
