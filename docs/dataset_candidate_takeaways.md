# Dataset Candidate Takeaways

Date: 2026-06-11

Scope: English hate, abuse, toxicity, counter-hate, and related datasets listed
in the project discussion. This note is for planning only. Do not commit raw
datasets, hydrated tweets, official challenge examples, or generated examples.
Use ignored paths such as `data/public_dev/` and `data/outputs/`.

## Selection Criteria

This project is not primarily training a hate-speech classifier. Datasets are
useful only when they help evaluate or improve privacy-preserving
text-to-text transformation.

Prefer datasets that provide at least one of:

- text plus HSD/offensive/toxicity labels for utility benchmarking
- target-group, type, rationale, or toxic-span labels for cue preservation
- author, user, account, thread, or repeated-speaker structure for authorship
  risk evaluation
- compact adversarial or functional test cases for regression checks
- clear public access and license metadata

Avoid making a dataset central when it has:

- tweet-hydration requirements or high deletion risk
- unclear redistribution terms
- images or profile metadata that are outside this text-only baseline
- request-only access
- very large size without a concrete evaluation role

## Recommended Tiers

### Tier 1: Use First

| Dataset | Role | Why It Fits | Cautions |
| --- | --- | --- | --- |
| [Dynamically Generated Hate Speech](https://github.com/bvidgen/Dynamically-Generated-Hate-Speech-Dataset) | Primary public dev and utility benchmark. | Direct CSV files, English, synthetic/adversarial, target/type metadata, already supported by `prepare-dynahate`. | GitHub license metadata is not explicit; keep raw data out of git. |
| [Measuring Hate Speech](https://huggingface.co/datasets/ucberkeley-dlab/measuring-hate-speech) | Rich utility and target-preservation evaluation. | Hugging Face metadata shows `cc-by-4.0`; includes severity score, ordinal harm dimensions, target identities, and supportive/counterspeech region. | Not designed for authorship privacy; use as evaluation, not privacy ground truth. |
| [HateXplain](https://github.com/hate-alert/HateXplain) | Rationale and target cue preservation. | MIT metadata, target categories and rationales are useful for checking whether privatization preserves important HSD evidence. | Model/rationale tooling can be heavier than raw data use; keep integration optional. |
| [HateCheck](https://github.com/paul-rottger/hatecheck-data) | Compact functional regression tests. | CC-BY-4.0 metadata, direct CSV assets, targeted tests for protected groups and hate/non-hate contrast. | It is a test suite, not a natural training distribution. |
| [Hatemoji](https://github.com/HannahKirk/Hatemoji) | Emoji and adversarial cue regression. | CC-BY-4.0 metadata, split into HatemojiCheck and HatemojiBuild; useful for style-scrub and cue-retention checks. | Synthetic/adversarial, so do not overfit default behavior to it. |
| [Toxic Spans](https://github.com/ipavlopoulos/toxic_spans) | Toxic cue span preservation and over-masking checks. | CC0 metadata; span labels can help distinguish utility-bearing toxic cues from identifiers. | Toxicity is broader than hate speech. |
| [ConvAbuse](https://github.com/amandacurry/convabuse) | Conversation/context and nuanced abuse categories. | CC-BY-4.0 metadata, small direct CSV, includes target/directedness/type structure. | Conversational AI domain differs from social-media HSD. |

## Measuring Hate Speech Use Plan

Source: `https://huggingface.co/datasets/ucberkeley-dlab/measuring-hate-speech`

Verified via Hugging Face Dataset Viewer on 2026-06-11:

- public and non-gated
- license metadata: `cc-by-4.0`
- config: `default`
- split: `train`
- rows: 135,556
- columns: 143
- parquet: one shard, about 20 MB
- key columns: `comment_id`, `annotator_id`, `platform`, `text`,
  `hate_speech_score`, `hatespeech`, `sentiment`, `respect`, `insult`,
  `humiliate`, `status`, `dehumanize`, `violence`, `genocide`,
  `attack_defend`, and many `target_*` indicators

This is one of the best evaluation datasets in the list, but the Hugging Face
release is an expanded tabular form with annotator-level fields. Do not treat
all rows as independent social-media posts without checking duplicates. A
preparation command should group or deduplicate by `comment_id` and `text`, then
write a compact file such as:

```text
id,text,label,hate_speech_score,source,platform,target_categories,harm_scores
```

Suggested mapping:

- `id`: `comment_id`
- `text`: `text`
- `label`: thresholded utility label derived from `hate_speech_score` or
  `hatespeech`, recorded with the threshold in the manifest
- `hate_speech_score`: continuous utility target for drift analysis
- `target_categories`: compact list from aggregate `target_*` columns
- `harm_scores`: compact JSON object for insult, humiliation, dehumanization,
  violence, genocide, and attack/defend dimensions

Use it for:

- target-group cue retention by target category
- severity-score drift before versus after privatization
- utility benchmark robustness beyond Dynahate
- counterspeech/supportive-region preservation
- checking whether privacy modes over-generalize protected-class mentions

Do not use it for:

- author-risk evaluation, because it has annotator metadata rather than stable
  text-author labels
- default package dependencies
- committing raw rows or sample text
- training a new primary classifier before official data arrives

### Tier 2: Useful Later

| Dataset | Role | Why It Fits | Cautions |
| --- | --- | --- | --- |
| [Davidson Hate Speech and Offensive Language](https://github.com/t-davidson/hate-speech-and-offensive-language) | Noisy short-form social-media utility benchmark. | MIT metadata, common baseline with hate/offensive/neither labels. | Older Twitter data and known offensive-vs-hate label limitations. |
| OLID / OffensEval and [AbuseEval](https://github.com/tommasoc80/AbuseEval) | Offensive/abusive explicitness checks. | Useful for explicit versus implicit abuse behavior. | Data access can involve task/CodaLab packaging; not first-line. |
| [Large-Scale Hate Speech Detection with Cross-Domain Transfer](https://github.com/avaapm/hatespeech) | Cross-domain social-media utility benchmark. | Large English/Turkish resource with target domains. | GitHub license metadata not explicit; includes multimodal framing but this project is text-first. |
| [Counterhate Replies](https://github.com/albanyan/counterhate_reply) | Counterspeech and reply relationship preservation. | Helps evaluate whether privatization keeps agreement, attack-author, support-hate, and additional-counterhate signals. | Small and Twitter-thread based; license metadata not explicit. |
| [Hateful Tweets and Replies](https://github.com/albanyan/hateful-tweets-replies) | Reply-level hate/counterhate relationship preservation. | Useful for preserving counterhate versus additional-hate distinctions. | Same Twitter/access caveats. |
| [Slur Corpus](https://github.com/networkdynamics/slur-corpus) | Slur-use disambiguation. | MIT metadata; useful for preserving or testing context-sensitive slur function. | Reddit-specific and label taxonomy differs from challenge labels. |
| [ETHOS](https://github.com/intelligence-csd-auth-gr/Ethos-Hate-Speech-Dataset) | Small target-category smoke test. | Includes binary and multi-label hate dimensions. | GPL-3.0 metadata; avoid mixing code/data assumptions into package defaults. |
| [CAD](https://zenodo.org/record/4881008) | Contextual abuse and counterspeech taxonomy. | Strong fit for nuanced context, identity/person-directed categories, and counterspeech. | Zenodo package and schema need separate inspection before use. |
| [CONAN](https://github.com/marcoguerini/CONAN) | Counter-narrative/counterspeech behavior. | Useful for checking that the pipeline does not erase counterhate utility. | Semi-synthetic and topic-specific. |
| [Jigsaw/Civil Comments](https://www.tensorflow.org/datasets/catalog/civil_comments) | Large toxicity and identity-bias benchmark. | Good for optional model-backed utility and unintended-bias evaluation. | Very large; toxicity is not identical to hate speech. |
| [Wiki Detox](https://github.com/ewulczyn/wiki-detox) | Personal attack/toxicity scale benchmark. | Large and accessible for toxicity/personal attack utility checks. | Wikipedia talk-page domain differs from social-media HSD. |

### Tier 3: Defer Or Mine For Ideas

| Dataset | Reason |
| --- | --- |
| [Online-Abusive-Attacks OAA](https://github.com/RaneemAlharthi/Online-Abusive-Attacks-OAA-Dataset) | Potentially valuable for account/profile/metadata privacy thinking, but too large and sensitive for the current text-only hackathon path. |
| [HatefulUsersTwitter](https://github.com/manoelhortaribeiro/HatefulUsersTwitter) | User-level structure is relevant to authorship risk, but Twitter account data and access constraints make it a later privacy experiment. |
| [Gab/Reddit intervention dataset](https://github.com/jing-qian/A-Benchmark-Dataset-for-Learning-to-Intervene-in-Online-Hate-Speech) | Conversation context is useful, but not needed before the core exact-format pipeline and official dataset. |
| MultiOFF and other multimodal meme datasets | Defer because the current pipeline is text-only. Text fields may be useful later, but image/meme signal is outside scope. |
| ALONE and request-only harassment datasets | Defer because access requires direct requests or special handling. |
| Domain-specific datasets such as chess adversarial, software-review toxicity, gaming harassment, and political-opponent hate | Use as robustness examples only if official scores expose matching weaknesses. |
| Non-English datasets | Defer unless the official challenge includes those languages. Current implementation and cue lexicons are English-first. |

## What To Build From These

### 1. Dataset Registry

Add a small local registry only for prepared datasets we actually use. The
registry should describe column names and roles, not download everything.

Suggested fields:

- dataset id
- source URL
- license or access note
- text column
- label column
- optional id column
- optional author/user/thread columns
- optional target/type/rationale/span columns
- preparation command
- intended role: utility, cue-regression, author-risk, robustness

### 2. Prepare Scripts By Need, Not By List Size

Only add prepare scripts when a dataset has a concrete experiment.

Recommended order:

1. Keep `prepare-dynahate` as the primary public dev path.
2. Add `prepare-hatecheck` for compact functional cue regression.
3. Add `prepare-hatemoji` for emoji/style regression.
4. Add `prepare-measuring-hate-speech` if Hugging Face `datasets` is allowed as
   an optional data-prep dependency. The command should deduplicate or
   aggregate by `comment_id`.
5. Add `prepare-hatexplain` only if rationale/target checks need direct data.

### 3. Cue Regression Suite

Use compact datasets to create aggregate regression reports, not committed raw
examples.

Candidate checks:

- target-group retention from HateCheck and Measuring Hate Speech
- emoji cue handling from Hatemoji
- rationale/toxic-span retention from HateXplain and Toxic Spans
- counterhate/counterspeech preservation from Counterhate, CAD, and CONAN

Outputs should be aggregate JSON/CSV under `data/outputs/`.

### 4. Author-Risk Search

The best public author-risk dataset is not obvious from this list. Most
tweet-level HSD datasets are designed around labels, not repeated authors.

When searching later, prioritize datasets with:

- repeated author IDs or pseudonymous user IDs
- enough posts per author for train/test splits
- text plus HSD/toxicity labels
- license/access compatible with local evaluation

Until then, official challenge `author` columns and synthetic author-risk
fixtures are the better path.

## Current Recommendation

Do not broaden the project by downloading many datasets. The highest-leverage
path is:

1. Keep Dynahate as the public dev set.
2. Add HateCheck and Hatemoji as compact cue/style regression datasets.
3. Add Measuring Hate Speech for richer target and severity evaluation.
4. Add HateXplain or Toxic Spans if rationale/span preservation becomes a
   known weakness.
5. Use Twitter-heavy and large context datasets only after official score
   feedback shows a concrete gap.

## Prepared Bundle Status

Implemented command:

```bash
python -m privhsd.cli prepare-recommended-datasets \
  --output-dir data/public_dev \
  --raw-dir data/public_dev/raw \
  --merged-output data/public_dev/recommended_merged.csv
```

Current generated row counts:

| Dataset | Normalized rows |
| --- | ---: |
| Dynahate | 41,144 |
| HateCheck | 3,901 |
| Hatemoji | 9,842 |
| Measuring Hate Speech | 39,565 |
| HateXplain | 20,148 |
| Toxic Spans | 16,100 |
| ConvAbuse | 4,185 |
| Davidson | 24,783 |
| Merged | 159,668 |

The merged file has no missing `text` values and no duplicate merged `id`
values after source-prefixing.
