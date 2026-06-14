# Auto Pipeline Simplification Plan

Status: implemented on current branch and locally verified
Owner area: auto pipeline simplification, Council of Europe demo readiness
Last verified: 2026-06-14
Primary code: `privhsd/auto/`, `privhsd/cli.py`, `privhsd/submission.py`,
`privhsd/simple_pipeline.py`, `privhsd/detectors.py`, `privhsd/metrics.py`,
`privhsd/metadata_leakage.py`, `privhsd/span_providers/`,
`privhsd/models/hsd_advisory_runtime.py`

This file is the next-agent handoff for simplifying the system without throwing
away useful components. The product direction is:

> Keep `auto` as the single primary pipeline. Clean and refactor around it
> until the row transformation story is easy to explain.

Do not start by adding another model or another mode. Start by reducing the
user-facing surface and making the existing `auto` path easier to reason about,
test, and demonstrate.

## Target Public Story

The public explanation should fit into three stages:

```text
Input CSV
  -> Privacy Detection
  -> Meaning Protection
  -> Verification
  -> Exact cleaned CSV + manifest
```

Council/demo wording:

> The system removes personal and re-identifying details, uses local PII
> assistance only as a reviewer for missed spans, preserves the meaning needed
> for hate-speech review, and verifies the result with residual PII checks and
> HSD-signal checks.

This is the story to optimize for. Internal components may remain modular, but
they should be grouped under these three concepts in docs, manifests, and CLI
help.

## External Validation Pass

Reviewed against public guidance on 2026-06-14. The plan is meaningful and
defensible, with two important constraints: do not claim zero leakage, and do
not let privacy masking erase legally relevant hate-speech context.

Why the three-stage story fits:

- The Council of Europe's Framework Convention on AI requires lifecycle
  consistency with human rights, democracy, and rule of law, and lists privacy
  and personal-data protection, transparency and oversight, accountability,
  reliability, and iterative risk/impact assessment as core expectations:
  <https://www.coe.int/en/web/artificial-intelligence/the-framework-convention-on-artificial-intelligence>.
- The Council of Europe hate-speech recommendation frames hate-speech response
  as a calibrated human-rights task, not a one-size-fits-all classifier output:
  <https://www.coe.int/en/web/combating-hate-speech/recommendation-on-combating-hate-speech>.
- NIST's AI Risk Management Framework organizes trustworthy AI around risk
  management and evaluation, which maps well to a pipeline that explicitly
  separates detection, protection, and verification:
  <https://www.nist.gov/itl/ai-risk-management-framework> and
  <https://airc.nist.gov/airmf-resources/airmf/5-sec-core/>.
- NIST de-identification guidance describes de-identification as a privacy-risk
  reduction method that must balance data use/sharing against privacy
  protection; it also notes re-identification remains possible in some
  de-identified data:
  <https://csrc.nist.gov/Pubs/ir/8053/Final> and
  <https://csrc.nist.gov/News/2023/nist-publishes-sp-800-188>.
- ICO anonymisation guidance uses risk assessment concepts such as the
  "motivated intruder" test and distinguishes anonymisation from
  pseudonymisation when information enabling identification is retained:
  <https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/how-do-we-ensure-anonymisation-is-effective/>.

Implications for the next agent:

1. Keep the public design risk-based and auditable. Say "residual risk is
   reported and reduced", not "zero leakage".
2. Keep exact output and audit manifests separate from any classifier/demo
   analysis output.
3. Treat HSD preservation as a human-rights safeguard: protect target/action,
   negation, quotation, and counterspeech cues, but do not use that as an
   excuse to leave obvious personal identifiers.
4. Prefer grouped, inspectable stages over provider-specific knobs in public
   commands and docs.

## Correct Mental Model

Current `auto` is not:

```text
regex removes PII -> token model decides keep/hide -> target dictionary runs
-> classifier labels raw text -> write cleaned text
```

The intended simplified model is:

```text
1. Transparent privacy rules create a balanced baseline candidate.
2. Optional local PII helpers suggest additional spans on risky rows.
3. Span fusion rejects invalid spans and spans that would erase HSD cues.
4. Candidate texts are scored for privacy gain, cue retention, text retention,
   and optional HSD-advisory drift. Stricter residual-PII cleanup is tested as
   a candidate rung before final selection rather than hidden as an unscored
   rewrite.
5. The least destructive privacy-improving candidate is written back.
6. Residual privacy and metadata leakage checks are recorded.
```

Exact submission mode writes only cleaned text in the original schema.
Enriched analysis mode may append advisory HSD prediction columns, but that is
not the upload path.

## Name And Place Decision Rule

The next agent must document and implement this distinction consistently:

- High-confidence direct PII should be masked by default:
  emails, phones, URLs, handles, IPs, explicit IDs, obfuscated emails, and clear
  private self-disclosed names.
- Stricter masking should be gradual: first deterministic baseline, then
  strict residual cleanup for high-confidence direct PII and strongly
  contextual person/place/org residuals, then optional PII Assist/token-policy
  evidence. Do not use privacy-mode target generalization as the default
  strictness knob because it can obscure exact HSD wording.
- Ambiguous names and places should not be preserved silently. They should be:
  masked when private context is strong, or flagged when public/contextual
  ambiguity is high.
- HSD meaning cues should be preserved, but this does not mean names are kept
  just because masking is inconvenient. It means target groups, hostility,
  threat/action terms, negation/modality, quotation, counterspeech, and
  rationale cues are protected from destructive masking.
- If a name/place is itself part of the HSD evidence, prefer:
  1. typed placeholder plus preserved action/target cue where possible;
  2. row-level warning when a placeholder would destroy the only useful
     meaning;
  3. explicit review flag rather than silent leakage.

For example, `Kill Alex was posted` should become `Kill [PERSON] was posted`,
not `[PERSON] was posted`, because `Kill` is an HSD cue. A private lower-case
street or place in context should still be maskable.

## Current Systems Audit

| System | Current role | Simplification decision |
| --- | --- | --- |
| Deterministic regex/context detectors | Always-present baseline for direct and quasi identifiers. | Keep. Improve missed lowercase names/places and high-confidence residual cleanup. |
| Target/HSD cue lexicons | Protect target groups, threat/action, negation, modality, counterspeech, and utility cues. | Keep. Present as Meaning Protection, not as a separate user-facing mode. |
| Presidio | Optional PII span provider. | Merge into `PII Assist` concept. Keep internal provider status. |
| scrubadub | Optional PII span provider. | Merge into `PII Assist` concept. Keep internal provider status. |
| GLiNER | Optional explicit local/debug PII span provider with profiles. | Remove from default public `PII Assist`; keep debug provider code and profile knobs outside normal workflow. |
| Token-policy ensemble | Weakly supervised token-action model trained from local rules. | Demote from default public story. Keep as research/advisory until proven. Consider disabled-by-default for demo preset. |
| HSD advisory ensemble | Scores original/candidate text to detect HSD signal drift. | Keep as Verification. Use one fixed default ensemble or one fixed model for demo; hide model override flags. |
| `sanitize-classify` | Enriched local output with HSD columns. | Keep but rename/present as `analysis` preset, not main path. |
| Style scrubber | Reduces style leakage when style risk exists. | Keep as optional candidate inside auto; do not expose as a primary mode. |
| Residual PII metrics | Re-scan output for identifiers and warnings. | Keep and strengthen. Add high-confidence residual cleanup. |
| Metadata leakage scan | Checks metadata values leaking into text. | Keep as Verification. Integrate into audit preset when metadata columns are supplied. |
| `utility`, `balanced`, `privacy` modes | Historical/manual deterministic modes. | Keep internally and for tests, but remove from normal docs/CLI story. `auto` is primary. |
| Provider/model disable flags | Useful for debugging/config search. | Hide from public quickstart. Keep for developer/debug use. |
| Metric depth knobs | Useful for local audits. | Collapse to presets: exact uses fast, audit uses sampled/deep. |
| Local LLM / DPMLM / privacy-filter | Planned/research paths. | Keep out of default pipeline and Council explanation. |
| Author-risk evaluation | Future group/privacy risk layer when repeated author IDs exist. | Preserve as planned Verification extension; do not block current simplification. |

## Target User-Facing Interface

Add one public command or wrapper while preserving old commands for backward
compatibility:

```bash
python -m privhsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col id \
  --manifest OUTPUT.manifest.json
```

Default `protect` behavior:

- exact-format CSV output;
- internally calls `create_submission(..., mode="auto", replace_text=True)`;
- local-only model/provider behavior;
- fast metrics;
- manifest always written when a path is supplied;
- no appended HSD columns;
- no downloads during sensitive-data processing;
- provider/model details recorded under grouped audit sections.

Optional presets:

```bash
--preset exact     # default, exact schema
--preset analysis  # enriched local CSV with HSD advisory columns
--preset audit     # exact schema plus deeper sidecar reports
```

Keep `create-submission`, `sanitize-classify`, and `anonymize` available, but
make `protect` the documented path for humans.

## Manifest Shape To Aim For

The manifest should be readable without knowing every internal provider:

```json
{
  "pipeline": "auto",
  "preset": "exact",
  "stages": {
    "privacy_detection": {
      "baseline": "deterministic_balanced",
      "pii_assist": {
        "enabled": true,
        "components": {
          "presidio": "ready",
          "scrubadub": "ready"
        }
      }
    },
    "meaning_protection": {
      "protected_cue_policy": "target_action_negation_quote_counterspeech",
      "cue_loss_rejections": 0
    },
    "verification": {
      "residual_direct_identifier_count": 0,
      "residual_quasi_identifier_count": 0,
      "hsd_advisory_status": "ok_or_skipped",
      "metadata_leakage_status": "not_run_or_ok"
    }
  }
}
```

Keep raw `providers`, `models`, and `load_counts` for developer/debug
compatibility, but add this grouped summary so the row transformation is
explainable.

## Implementation Plan

### Phase 0: Branch And Agent Setup

Before editing:

```bash
git status -sb
python -m pytest tests/test_submission.py tests/test_auto_pipeline.py tests/test_simple_pipeline.py -q
```

Suggested subagent split if using parallel agents:

| Agent | Ownership | Task |
| --- | --- | --- |
| Agent A | `privhsd/cli.py`, `privhsd/submission.py`, tests for CLI/public API | Add `protect` preset wrapper and keep old commands stable. |
| Agent B | `privhsd/detectors.py`, `privhsd/metrics.py`, detector tests | Fix lowercase names/places and high-confidence residual cleanup. |
| Agent C | `privhsd/auto/`, `privhsd/simple_pipeline.py`, manifest tests | Add grouped stage summary and simplify provider/model presentation. |
| Agent D | docs/runbooks/reference/challenge docs | Rewrite docs around three-stage story and `protect`. |
| Agent E | author-risk planning docs only | Prepare author doxxing risk hook without changing default behavior. |

Keep write scopes disjoint. Do not let multiple agents edit the same code file
unless one is done and the other is explicitly integrating.

### Phase 1: Cleaning

Goal: remove public confusion without changing core behavior.

Tasks:

1. Add `protect` parser as the public default command.
2. Make `protect --preset exact` call the current exact `auto` path.
3. Make `protect --preset analysis` call `sanitize-classify`.
4. Hide developer knobs from `protect`:
   - no `--disable-provider`;
   - no `--disable-model`;
   - no `--gliner-profile`;
   - no `--metric-depth`;
   - no `--audit-level`.
5. Keep old commands intact for tests and research workflows.
6. Update help text to say:
   - no external API calls;
   - local model artifacts only by default;
   - exact output preserves schema.

Acceptance:

- `python -m privhsd.cli protect --help` is short and explainable.
- `protect` produces the same CSV shape as `create-submission --replace-text
  --mode auto`.
- Existing tests still pass.

### Phase 2: Detector And Residual Fixes

Goal: improve obvious misses without making the system overmask HSD cues.

Implement targeted fixes:

1. Lowercase street/location suffixes:
   - mask `james street`, `elm road`, `harbor lane` when they match address-like
     patterns;
   - keep action words and target terms protected.
2. Lowercase public/private place context:
   - mask `london library` when preceded by private context such as `at`,
     `near`, `from`, `works at`, `studies at`, `meet at`, `lives near`;
   - consider `[LOCATION] library` or full `[LOCATION]` consistently;
   - avoid masking generic `library` alone.
3. Lowercase person context:
   - mask `my name is james smith`;
   - improve `i met james smith`, `reported james smith`, `call james smith`
     only when context is person-like and not a target/action phrase.
4. Surname-only handling:
   - do not broadly mask every titlecase token;
   - mask surname-only only with strong private/person context or metadata
     leakage evidence;
   - otherwise flag for review.
5. High-confidence residual cleanup:
   - after candidate selection, re-run residual scan;
   - auto-mask high-confidence direct residuals: email, phone, URL, handle, IP,
     explicit ID, obfuscated email;
   - do not auto-mask ambiguous `PERSON`, `LOCATION`, `ORGANIZATION` residuals
     unless confidence/context is strong.

Required tests:

- `james street is near london library` masks address/place.
- `James Street is near London library` still masks.
- `My name is james smith` masks.
- `i met james smith at london library` masks person/place only if context rule
  is strong enough.
- `Muslims should leave` is unchanged in default exact path.
- `Kill Alex was posted` keeps `Kill` and masks only `Alex`.
- high-confidence residual email/phone/URL/handle is removed after candidate
  selection.

### Phase 3: Rewrite Auto Around Three Stages

Goal: keep internals, simplify the explanation.

Tasks:

1. Add a small summary builder in `privhsd/auto/`:
   - `privacy_detection`;
   - `meaning_protection`;
   - `verification`.
2. Populate stage summary from existing engine summary:
   - chosen candidate counts;
   - provider/model statuses;
   - residual identifier counts;
   - cue retention;
   - HSD advisory skipped/ok status.
3. Keep detailed provider/model status for debugging, but docs should lead with
   stage summary.
4. Add row-level audit explanation fields:
   - `chosen_candidate`;
   - `why_chosen`;
   - `privacy_gain`;
   - `meaning_protection_rejections`;
   - `residual_review_required`.

Acceptance:

- A non-engineer can read one manifest and explain why a row changed.
- Existing `providers`/`models` fields are preserved or compatibility tests are
  updated intentionally.

### Phase 4: Merge PII Assist

Goal: stop exposing Presidio/scrubadub/GLiNER as separate public decisions.

Tasks:

1. Add internal grouping in docs and manifest:
   - `pii_assist.components.presidio`;
   - `pii_assist.components.scrubadub`;
   - `pii_assist.components.gliner` only for explicit research/debug GLiNER
     runs.
2. Keep provider-specific errors and load counts for developer audit.
3. Pick one demo default:
   - deterministic baseline always;
   - Presidio/scrubadub when installed;
   - GLiNER excluded from the default path unless an explicit local/debug model
     is configured.
4. Do not ask the public user to choose GLiNER profiles.

Acceptance:

- User docs say "PII Assist", not "run these three providers".
- Debug docs still document individual providers.

### Phase 5: HSD Advisory Simplification

Goal: explain HSD checks as verification, not as the main output.

Tasks:

1. In exact mode, HSD advisory checks candidate drift only.
2. In analysis mode, it may append prediction columns.
3. Keep one default advisory configuration for demo.
4. If advisory model is unavailable:
   - exact mode still runs;
   - manifest says `hsd_advisory_status=skipped`;
   - analysis mode requires explicit `--require-hate-classification` if needed.

Acceptance:

- Public docs never imply the system is a production hate classifier.
- Exact output has no prediction columns.

### Phase 6: Author Doxxing Risk Hook

Do not implement full author-risk behavior until real repeated-author data is
available. Prepare a clean hook:

1. If an author/user column exists, manifest records:
   - repeated-author availability;
   - whether author-risk evaluation was run;
   - skipped reason if not run.
2. Keep current `evaluate-author-risk` as a sidecar verification command.
3. Do not mutate author metadata in exact submissions.
4. Future author-doxxing improvements should enter under Verification first,
   not as another public branch.

Acceptance:

- No fake author-risk claims on authorless data.
- When real data arrives, the place to plug in author-risk evaluation is clear.

### Phase 7: Documentation Rewrite

Rewrite docs in this order:

1. `readme.md`
2. `docs/runbooks/quickstart.md`
3. `docs/runbooks/official_submission.md`
4. `docs/reference/pipeline.md`
5. `docs/reference/cli.md`
6. `docs/reference/providers_and_models.md`
7. challenge/demo docs

All public docs should use the three-stage story:

```text
Privacy Detection -> Meaning Protection -> Verification
```

Move details about token-policy, GLiNER profile selection, DPMLM, local LLMs,
and public benchmark commands to planning/reference sections only.

## Testing Plan

Minimum fast checks:

```bash
python -m pytest tests/test_pipeline.py tests/test_metrics.py -q
python -m pytest tests/test_submission.py tests/test_auto_pipeline.py tests/test_simple_pipeline.py -q
python -m pytest tests/test_metadata_leakage.py tests/test_workbench_csv.py -q
```

Full local checks before handoff:

```bash
python -m pytest -q
python -m privhsd.cli protect --help
python -m privhsd.cli create-submission --help
python -m privhsd.cli sanitize-classify --help
```

Add a smoke fixture for the simplified demo story:

```csv
id,text,label
1,"my name is james smith, email james@example.test, Muslims should leave from london library",hate
2,"No one should attack black people near james street",not_hate
3,"I reported james smith because he said immigrants should be deported",not_hate
```

Expected behavior:

- direct identifiers masked;
- private lower-case person/place patterns handled;
- target/action/negation/reporting cues preserved;
- exact output keeps schema;
- manifest explains stage decisions.

## Council Demo Script

Use this after the simplification work:

> The pipeline has three checks. Privacy Detection finds personal and
> re-identifying information. Meaning Protection prevents the system from
> erasing the evidence needed to understand hate speech, such as target groups,
> threats, negation, quotation, and counterspeech. Verification scans the
> cleaned row for remaining privacy risk and checks that the HSD signal was not
> materially changed. The output is an exact CSV plus an audit manifest.

Avoid saying:

- "we run many providers";
- "the token policy decides what to hide";
- "the classifier decides whether a row is hate speech";
- "zero leakage";
- "state of the art PII removal by default".

Say instead:

- "local PII assistance";
- "checked candidate selection";
- "meaning-preserving privacy";
- "residual risk is reported, not hidden";
- "exact output, transparent audit".

## Done Criteria

The simplification is done when:

- `protect` is the documented default path.
- A single row transformation can be explained in less than one minute.
- Public docs use only three stage names.
- Token-policy and provider-specific knobs are not in quickstart/official
  runbooks.
- Lowercase person/place examples are covered by tests.
- High-confidence residual direct PII cleanup exists.
- Exact mode preserves CSV shape and does not append HSD columns.
- Analysis mode clearly appends HSD columns and is not upload-ready.
- Existing code paths remain available for research/debug workflows.

## Implementation Results 2026-06-14

Implemented in the current worktree:

- Added public `protect` command with `exact`, `analysis`, and `audit`
  presets. `exact` and `audit` call the current exact `auto` path with
  schema-preserving cleaned text. `analysis` calls the enriched
  sanitize/classify path and may append advisory HSD columns.
- Kept `create-submission`, `sanitize-classify`, and `anonymize` available for
  compatibility and research/debug workflows.
- Reworked exact and analysis manifests to lead with:
  `privacy_detection`, `meaning_protection`, and `verification`.
- Grouped Presidio and scrubadub under internal default `PII Assist` while
  preserving detailed provider/model status and load counts for debugging.
  A follow-up GLiNER ablation found no default-path benefit without an explicit
  local artifact, so GLiNER is no longer surfaced in default PII Assist and
  remains explicit research/debug-only.
- Added row-level audit fields for chosen candidate, why chosen, privacy gain,
  meaning-protection rejections, residual review requirement, and residual
  direct cleanup.
- Added manifest Verification hooks for HSD advisory skipped/ok status,
  metadata leakage not-run status, and author-risk column/repeated-author
  availability with skipped reason.
- Strengthened deterministic detection for lower-case/titlecase street, place,
  and person contexts required by the smoke examples while avoiding broad
  token masking.
- Added high-confidence direct residual cleanup for emails, phones, URLs,
  handles, IPs, explicit IDs, and obfuscated emails. Ambiguous
  PERSON/LOCATION/ORG residuals remain review signals unless strong context
  rules catch them.
- Updated public docs so the normal path is `protect` and the normal story is
  Privacy Detection -> Meaning Protection -> Verification. Token-policy,
  GLiNER profile selection, DPMLM, local LLM, and benchmark/debug options are
  kept out of quickstart and official submission docs.

Verification completed during implementation:

- `git diff --check` passed.
- `python -m privhsd.cli protect --help` passed.
- `python -m privhsd.cli create-submission --help` passed.
- `python -m privhsd.cli sanitize-classify --help` passed.
- `python -m pytest tests/test_pipeline.py tests/test_metrics.py tests/test_auto_pipeline.py tests/test_submission.py tests/test_simple_pipeline.py -q`
  passed with 61 tests.
- `python -m pytest tests/test_pipeline.py tests/test_metrics.py -q`
  passed with 38 tests.
- `python -m pytest tests/test_submission.py tests/test_auto_pipeline.py tests/test_simple_pipeline.py -q`
  passed with 23 tests.
- `python -m pytest tests/test_metadata_leakage.py tests/test_workbench_csv.py -q`
  passed with 6 tests and dependency deprecation warnings.
- `python -m pytest tests/test_synthetic_pii_stress.py -q` passed with 3
  tests.
- `python -m pytest -q` passed with 200 tests, 1 skipped test, and dependency
  deprecation warnings.
- A tiny `protect --preset exact` smoke preserved schema, masked
  `james street` / `london library`, preserved `Muslims should leave`, and
  wrote the three-stage manifest.

Follow-up implemented on 2026-06-14:

- Added a scored strict residual-PII candidate rung inside `auto`.
- Manifest `privacy_detection` now reports the privacy ladder and candidate
  counts by name, including `*_strict_pii` candidates.
- High-confidence direct PII cleanup is treated as a hard privacy rule:
  HSD advisory drift is recorded, but does not veto removal of emails, phones,
  URLs, handles, IPs, explicit IDs, or obfuscated emails.
- Ambiguous person/place/org residuals remain conservative: strict cleanup only
  masks them when deterministic context is strong; otherwise they remain
  review/reporting signals.

Remaining TODO:

- No implementation TODO is required for this simplification pass. Residual
  risk remains a reported Verification output, not a zero-leakage claim.
