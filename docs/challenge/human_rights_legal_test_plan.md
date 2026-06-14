# Human Rights Legal Test Plan

Date: 2026-06-11

Status: active
Owner area: legal and governance stress tests
Last verified: 2026-06-14

This note captures the legal and governance constraints that should guide the
PrivHSD proof of concept. The challenge system is a privacy-preserving text
transformation tool for hate-speech datasets, not a court, a takedown engine,
or a production moderation classifier.

## Core Legal Position

The system must satisfy two constraints at the same time:

1. Avoid over-restriction of speech.
2. Preserve enough evidence that hate speech against vulnerable or historically
   targeted groups can still be detected.

Under the ECtHR Article 10 approach, offensive, shocking, disturbing, vulgar, or
insulting language is not automatically hate speech. Hate-speech analysis is
case-specific and depends on the interaction between content, speaker, target,
audience, social context, intent, likely harm, and proportionality.

The same words can be lawful counterspeech, reclaimed identity language,
political criticism, satire, evidence-gathering, harassment, or hate speech
depending on who says them, who is targeted, and why. A text-only CSV often lacks
that context, so the system must avoid presenting a row-level legal conclusion
as certain when the necessary context is absent.

## Article 10 Over-Restriction Tests

The proof of concept should be able to explain that it does not suppress speech
merely because a row contains:

- profanity or vulgar style;
- insult without protected-group targeting;
- criticism of public officials, public institutions, police, or governments;
- political expression or public-interest reporting;
- satire, parody, artistic expression, or provocative campaigning;
- counterspeech, anti-discrimination speech, quotation, or documentation of
  abuse.

Technical implication:

- Default transformations must preserve meaning and avoid turning lawful
  criticism into hate or turning hate into vague non-actionable text.
- Any classifier-style score in demos must be framed as a utility proxy or
  review signal, not as a legal finding.
- When speaker/recipient/social context is missing, the audit should say so
  instead of implying full legal certainty.

## Victim Protection And Positive Obligations

Articles 8, 13, and 14 create the opposite failure mode: under-detection can
also be legally serious when authorities or deployers disregard hatred directed
at vulnerable groups. The risk is highest when there are direct or indirect
calls to violence, threats, dehumanisation, exclusion, segregation, or repeated
vilification of protected groups.

The system must therefore preserve, by default:

- target-group terms;
- historical-victim and vulnerable-group references;
- slurs and abuse cues when they are needed for downstream HSD utility;
- hostile action phrases, including exclusion, removal, violence, and
  dehumanisation;
- negation and modality, because "do not attack group X" and "attack group X"
  have opposite meanings;
- counterspeech markers, so victim-protective speech is not converted into a
  false hate signal.

Technical implication:

- Target generalisation must not be the default submission path.
- The cue checker must keep target/action/negation/modality retention close to
  1.0, especially for vulnerable groups.
- Rows involving protected groups plus hostile action should be treated as
  high-priority utility-preservation cases, not as convenient places to mask
  more aggressively.

## Delfi Notice-And-Takedown Relevance

Delfi AS v. Estonia matters because the ECtHR accepted platform responsibility
for clearly unlawful third-party comments in a specific context: a professional
commercial news portal, highly harmful user comments, insufficient prevention or
rapid removal, and a proportionate sanction.

For this project, the correct lesson is not "remove broadly". It is:

- identify clearly unlawful, high-risk comments for prompt human review;
- preserve evidence needed to understand threats and protected-group targeting;
- distinguish professional platform duties from ordinary users, forums, or
  private blogs;
- keep the response proportionate and reviewable;
- document whether a case is notice-based, proactively detected, or uncertain.

## Google LLC v. Russia Proportionality Relevance

Google LLC and Others v. Russia is the warning case for overbroad moderation
pressure. The ECtHR found an Article 10 violation where removal demands and
massive fines targeted broad user-generated content including political
expression, public-interest reporting, opposition support, and LGBTQ-rights
content without a concrete harm analysis.

For this project, the tool must not resemble an official-narrative enforcement
mechanism. A legally safer design must:

- require concrete reasons tied to target, hostility, threat, or discrimination;
- avoid broad labels such as "extremist" without row-level evidence;
- avoid treating disagreement with official policy as harm;
- avoid disproportionate consequences from a noisy score;
- keep human review, appeal, and audit paths visible.

## Framework Convention And HUDERIA Mapping

The Council of Europe Framework Convention on AI (CETS No. 225) and HUDERIA
push the project toward documented lifecycle governance. For the proof of
concept, the practical mapping is:

| Requirement | PoC response |
| --- | --- |
| Transparency | Deterministic default rules, typed placeholders, exact-submission manifests, hashes, validation reports, optional local row-level audit JSON, and explicit utility/privacy metrics. |
| Accountability | The tool produces transformations and evidence; the deploying organisation remains responsible for moderation, takedown, appeal, and remedy decisions. |
| Human oversight | The system stops at anonymisation plus risk/utility evidence. Human reviewers step in for high-risk hate cues, large semantic drift, missing context, or any operational sanction. |
| Risk assessment | Evaluate both false positives against lawful expression and false negatives against vulnerable groups. |
| Stakeholder sensitivity | Treat affected groups, counterspeech, and historical victim groups as first-class risk categories, not as generic tokens. |
| Proportionality | Prefer the least meaning-changing transformation that reduces author-identifying signal while preserving HSD utility. |
| Remedy | Preserve enough audit detail for review without exposing raw sensitive text unnecessarily. |

## Legal Stress-Test Set

When the official CSV arrives, supplement local scoring with a small private
probe set that checks these patterns:

- same insult used as in-group reclaimed speech versus out-group abuse;
- quote/documentation of hate versus endorsement of hate;
- counterspeech containing slurs but rejecting hatred;
- public official or police criticism without protected-group targeting;
- vulnerable-group targeting with exclusion or violence;
- Holocaust, Roma, Jewish, Muslim, migrant, LGBTI, disability, and other
  historically targeted group examples;
- direct threat versus hyperbole or political rhetoric;
- satire or anti-discrimination campaign text using stereotypes to criticise
  discrimination;
- missing speaker/recipient context.

Expected result:

- The privatized text should retain the cues needed to distinguish these cases.
- The audit should identify what was changed and what legally relevant context
  is absent.
- The pitch should describe the output as evidence for human review, not as an
  automated legal decision.

## Non-Negotiable Demo Claims

Use these statements in the pitch and documentation:

- PrivHSD is not a takedown system.
- PrivHSD does not equate offensiveness with hate speech.
- PrivHSD preserves vulnerable-group target evidence because erasing it can
  create under-detection and victim-protection failures.
- PrivHSD exposes reasons, limitations, and uncertainty through audit artifacts.
- Humans remain responsible for moderation consequences and legal balancing.

## Official Sources

- [ECtHR Key Theme: Article 10 - Hate speech](https://ks.echr.coe.int/documents/d/echr-ks/hate-speech)
- [ECtHR Key Theme: Articles 8, 13 and 14 - Protection against hate speech](https://ks.echr.coe.int/documents/d/echr-ks/protection-against-hate-speech)
- [ECtHR press release: Google LLC and Others v. Russia, 8 July 2025](https://hudoc.echr.coe.int/app/conversion/pdf/?filename=Judgment+Google+LLC+and+Others+v.+Russia+-+Judgments+and+fines+against+Google+breached+its+free-expression+rights+.pdf&id=003-8278525-11655461&library=ECHR)
- [Council of Europe Framework Convention on Artificial Intelligence](https://www.coe.int/en/web/artificial-intelligence/the-framework-convention-on-artificial-intelligence)
- [Council of Europe HUDERIA overview](https://www.coe.int/en/web/artificial-intelligence/huderia-risk-and-impact-assessment-of-ai-systems)
