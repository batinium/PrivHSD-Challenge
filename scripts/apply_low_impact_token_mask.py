"""Mask low-HSD-impact author/style tokens after deterministic PII cleanup."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
import time
from typing import Any, Iterable

from contextsafe_hsd.models.dpmlm_rewrite_runtime import (
    REPEATED_LETTER_PATTERN,
    STYLE_MARKER_PATTERN,
    normalize_token,
    protected_tokens,
)
from contextsafe_hsd.models.hf_hsd_classifier_runtime import (
    DEFAULT_HF_HSD_BATCH_SIZE,
    DEFAULT_HF_HSD_MAX_LENGTH,
    DEFAULT_HF_HSD_MODEL_PATH,
    DEFAULT_HF_HSD_THRESHOLD,
    HfHsdClassifierRuntime,
)
from contextsafe_hsd.submission import validation_report


TOKEN_PATTERN = re.compile(
    r"\[[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?\]"
    r"|https?://\S+"
    r"|@[A-Za-z0-9._-]+"
    r"|#[A-Za-z0-9_]{2,}"
    r"|[A-Za-z][A-Za-z'-]*"
    r"|\d+(?:[./-]\d+)*"
)
PLACEHOLDER_PATTERN = re.compile(r"^\[[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?\]$")
WORD_BOUNDARY_TEMPLATE = r"(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"
NEVER_MASK_TERMS = frozenset(
    {
        "abuse",
        "abusive",
        "antisemitic",
        "asian",
        "asians",
        "attack",
        "attacked",
        "attacking",
        "autism",
        "autistic",
        "bisexual",
        "black",
        "blacks",
        "biden",
        "catholic",
        "catholics",
        "christian",
        "christians",
        "clinton",
        "communism",
        "communist",
        "communists",
        "conservative",
        "conservatives",
        "cuck",
        "cucks",
        "dumbass",
        "dumbasses",
        "dead",
        "death",
        "democrat",
        "democrats",
        "deport",
        "deported",
        "deporting",
        "die",
        "disabled",
        "disability",
        "dying",
        "extremist",
        "extremists",
        "fascism",
        "fascist",
        "fascists",
        "fat",
        "gay",
        "genocide",
        "hate",
        "hated",
        "hateful",
        "hating",
        "homophobic",
        "incel",
        "incels",
        "immigrant",
        "immigrants",
        "islam",
        "islamic",
        "islamophobic",
        "jihad",
        "jihadist",
        "jihadists",
        "jew",
        "jewish",
        "jews",
        "kill",
        "killed",
        "killing",
        "leftist",
        "leftists",
        "lesbian",
        "liberal",
        "liberals",
        "lynch",
        "maga",
        "man",
        "marxism",
        "marxist",
        "marxists",
        "men",
        "mexican",
        "mexicans",
        "murder",
        "murdered",
        "murdering",
        "moron",
        "morons",
        "muslim",
        "muslims",
        "nazi",
        "nazis",
        "obama",
        "obese",
        "queer",
        "racism",
        "racist",
        "racists",
        "rape",
        "raped",
        "raping",
        "rapist",
        "rapists",
        "refugee",
        "refugees",
        "republican",
        "republicans",
        "sexism",
        "sexist",
        "sexual",
        "shoot",
        "shooting",
        "sjw",
        "sjws",
        "socialism",
        "socialist",
        "socialists",
        "terror",
        "terrorism",
        "terrorist",
        "threat",
        "threaten",
        "threatened",
        "trans",
        "transgender",
        "trump",
        "violence",
        "violent",
        "white",
        "whites",
        "woman",
        "women",
    }
)
NEVER_MASK_PREFIXES = (
    "bitch",
    "asshole",
    "cunt",
    "fag",
    "fuck",
    "motherfuck",
    "nigg",
    "puss",
    "retard",
    "shit",
    "slut",
    "whore",
)


@dataclass(frozen=True)
class ImportanceToken:
    token: str
    normalized: str
    abs_delta: float


@dataclass(frozen=True)
class TokenDistribution:
    total_count: int
    author_count: int
    author_concentration: float
    document_frequency: int


@dataclass(frozen=True)
class AuthorTfidfSignal:
    tfidf_score: float
    tfidf_rank: int
    author_count: int


@dataclass(frozen=True)
class MaskDecision:
    token: str
    normalized: str
    abs_delta: float
    reason: str
    replacements: int
    tfidf_score: float | None = None
    tfidf_rank: int | None = None
    author_count: int | None = None


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def iter_normalized_tokens(text: str) -> Iterable[str]:
    for match in TOKEN_PATTERN.finditer(text):
        normalized = normalize_token(match.group(0))
        if normalized:
            yield normalized


def load_importance(path: Path) -> dict[str, list[ImportanceToken]]:
    by_row: dict[str, list[ImportanceToken]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            normalized = normalize_token(str(row.get("token") or ""))
            if not normalized:
                continue
            try:
                abs_delta = float(row.get("abs_delta_hate_score") or 0.0)
            except ValueError:
                continue
            by_row[str(row.get("row_id") or "").strip()].append(
                ImportanceToken(
                    token=str(row.get("token") or ""),
                    normalized=normalized,
                    abs_delta=abs_delta,
                )
            )
    return dict(by_row)


def build_distribution(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    id_col: str,
    author_col: str | None,
) -> dict[tuple[str, str], TokenDistribution]:
    total_counts: Counter[str] = Counter()
    document_counts: Counter[str] = Counter()
    author_counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        author = str(row.get(author_col or "", "") or "").strip()
        row_tokens = list(iter_normalized_tokens(str(row.get(text_col, "") or "")))
        total_counts.update(row_tokens)
        document_counts.update(set(row_tokens))
        if author:
            author_counts.update((author, token) for token in row_tokens)
    distributions: dict[tuple[str, str], TokenDistribution] = {}
    for (author, token), author_count in author_counts.items():
        total_count = total_counts[token]
        distributions[(author, token)] = TokenDistribution(
            total_count=total_count,
            author_count=author_count,
            author_concentration=author_count / max(1, total_count),
            document_frequency=document_counts[token],
        )
    return distributions


def build_author_tfidf_signals(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    author_col: str | None,
    protected: frozenset[str],
    min_token_length: int,
) -> dict[tuple[str, str], AuthorTfidfSignal]:
    from sklearn.feature_extraction.text import TfidfVectorizer

    author_docs: dict[str, list[str]] = defaultdict(list)
    author_counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        author = str(row.get(author_col or "", "") or "").strip()
        if not author:
            continue
        text = str(row.get(text_col, "") or "")
        author_docs[author].append(text)
        author_counts.update((author, token) for token in iter_normalized_tokens(text))
    if not author_docs:
        return {}

    def analyzer(text: str) -> list[str]:
        tokens: list[str] = []
        for match in TOKEN_PATTERN.finditer(text):
            original = match.group(0)
            normalized = normalize_token(original)
            if len(normalized) < min_token_length:
                continue
            if PLACEHOLDER_PATTERN.fullmatch(original):
                continue
            if normalized in protected or is_never_mask_token(normalized):
                continue
            tokens.append(normalized)
        return tokens

    authors = sorted(author_docs)
    documents = ["\n".join(author_docs[author]) for author in authors]
    vectorizer = TfidfVectorizer(
        analyzer=analyzer,
        lowercase=False,
        norm="l2",
        smooth_idf=True,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(documents)
    terms = vectorizer.get_feature_names_out()

    signals: dict[tuple[str, str], AuthorTfidfSignal] = {}
    for author_index, author in enumerate(authors):
        row = matrix.getrow(author_index)
        ranked = sorted(zip(row.indices, row.data), key=lambda item: -float(item[1]))
        for rank, (term_index, score) in enumerate(ranked, start=1):
            token = str(terms[term_index])
            signals[(author, token)] = AuthorTfidfSignal(
                tfidf_score=float(score),
                tfidf_rank=rank,
                author_count=author_counts[(author, token)],
            )
    return signals


def token_reason(
    *,
    original_token: str,
    normalized: str,
    distribution: TokenDistribution | None,
    min_token_length: int,
    min_author_count: int,
    min_author_concentration: float,
    rare_document_frequency: int,
) -> str | None:
    if PLACEHOLDER_PATTERN.fullmatch(original_token):
        return None
    if STYLE_MARKER_PATTERN.fullmatch(original_token):
        return "style_marker"
    if REPEATED_LETTER_PATTERN.search(original_token):
        return "repeated_letters"
    if original_token[:1].isupper():
        return None
    if len(normalized) < min_token_length:
        return None
    if distribution is None:
        return None
    if (
        distribution.author_count >= min_author_count
        and distribution.author_concentration >= min_author_concentration
    ):
        return "author_concentrated"
    if distribution.document_frequency <= rare_document_frequency and len(normalized) >= (
        min_token_length + 2
    ):
        return "rare_long_token"
    return None


def tfidf_token_reason(
    *,
    original_token: str,
    normalized: str,
    signal: AuthorTfidfSignal | None,
    min_token_length: int,
    min_author_count: int,
    min_tfidf_score: float,
    max_tfidf_rank: int,
) -> str | None:
    if PLACEHOLDER_PATTERN.fullmatch(original_token):
        return None
    if STYLE_MARKER_PATTERN.fullmatch(original_token):
        return "style_marker"
    if REPEATED_LETTER_PATTERN.search(original_token):
        return "repeated_letters"
    if len(normalized) < min_token_length:
        return None
    if signal is None:
        return None
    if signal.author_count < min_author_count:
        return None
    if signal.tfidf_score < min_tfidf_score:
        return None
    if signal.tfidf_rank > max_tfidf_rank:
        return None
    return "author_tfidf"


def is_never_mask_token(normalized: str) -> bool:
    return normalized in NEVER_MASK_TERMS or any(
        normalized.startswith(prefix) for prefix in NEVER_MASK_PREFIXES
    )


def replace_token_once(text: str, token: str, replacement: str) -> tuple[str, bool]:
    pattern = re.compile(
        WORD_BOUNDARY_TEMPLATE.format(re.escape(token)),
        flags=re.IGNORECASE,
    )
    updated, count = pattern.subn(replacement, text, count=1)
    return updated, bool(count)


def candidate_text_for_row(
    *,
    row_id: str,
    author: str,
    text: str,
    importance_rows: dict[str, list[ImportanceToken]],
    distributions: dict[tuple[str, str], TokenDistribution],
    author_tfidf_signals: dict[tuple[str, str], AuthorTfidfSignal],
    author_signal_mode: str,
    low_impact_threshold: float,
    protect_threshold: float,
    max_masks_per_row: int,
    min_token_length: int,
    min_author_count: int,
    min_author_concentration: float,
    rare_document_frequency: int,
    min_tfidf_score: float,
    max_tfidf_rank: int,
    replacement: str,
    protected: frozenset[str],
) -> tuple[str, list[MaskDecision]]:
    candidates: list[
        tuple[int, float, float, int, ImportanceToken, str, AuthorTfidfSignal | None]
    ] = []
    seen: set[str] = set()
    for item in importance_rows.get(row_id, []):
        if item.normalized in seen:
            continue
        seen.add(item.normalized)
        if item.abs_delta > low_impact_threshold:
            continue
        if item.abs_delta >= protect_threshold:
            continue
        if item.normalized in protected:
            continue
        if is_never_mask_token(item.normalized):
            continue
        signal = author_tfidf_signals.get((author, item.normalized))
        if author_signal_mode == "tfidf":
            reason = tfidf_token_reason(
                original_token=item.token,
                normalized=item.normalized,
                signal=signal,
                min_token_length=min_token_length,
                min_author_count=min_author_count,
                min_tfidf_score=min_tfidf_score,
                max_tfidf_rank=max_tfidf_rank,
            )
        else:
            distribution = distributions.get((author, item.normalized))
            reason = token_reason(
                original_token=item.token,
                normalized=item.normalized,
                distribution=distribution,
                min_token_length=min_token_length,
                min_author_count=min_author_count,
                min_author_concentration=min_author_concentration,
                rare_document_frequency=rare_document_frequency,
            )
        if reason is None:
            continue
        risk_rank = {
            "repeated_letters": 4,
            "style_marker": 3,
            "author_tfidf": 2,
            "author_concentrated": 2,
            "rare_long_token": 1,
        }[reason]
        tfidf_score = signal.tfidf_score if signal else 0.0
        candidates.append(
            (risk_rank, tfidf_score, item.abs_delta, len(item.normalized), item, reason, signal)
        )

    candidates.sort(
        key=lambda value: (-value[0], -value[1], value[2], -value[3], value[4].normalized)
    )
    masked_text = text
    decisions: list[MaskDecision] = []
    replacements = 0
    for _risk_rank, _tfidf_score, _delta, _length, item, reason, signal in candidates:
        if replacements >= max_masks_per_row:
            break
        updated, changed = replace_token_once(masked_text, item.token, replacement)
        if not changed and item.token != item.normalized:
            updated, changed = replace_token_once(masked_text, item.normalized, replacement)
        if not changed:
            continue
        masked_text = updated
        replacements += 1
        decisions.append(
            MaskDecision(
                token=item.token,
                normalized=item.normalized,
                abs_delta=item.abs_delta,
                reason=reason,
                replacements=1,
                tfidf_score=round(signal.tfidf_score, 6) if signal else None,
                tfidf_rank=signal.tfidf_rank if signal else None,
                author_count=signal.author_count if signal else None,
            )
        )
    return masked_text, decisions


def classifier_rows(rows: list[dict[str, str]], *, text_col: str, id_col: str) -> list[dict[str, str]]:
    return [
        {
            "id": str(row.get(id_col, "") or ""),
            "text": str(row.get(text_col, "") or ""),
        }
        for row in rows
    ]


def classification_metrics(labels: list[str], gold: list[str]) -> dict[str, Any]:
    tp = sum(pred == "1" and expected == "1" for pred, expected in zip(labels, gold, strict=True))
    fp = sum(pred == "1" and expected == "0" for pred, expected in zip(labels, gold, strict=True))
    fn = sum(pred == "0" and expected == "1" for pred, expected in zip(labels, gold, strict=True))
    tn = sum(pred == "0" and expected == "0" for pred, expected in zip(labels, gold, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "accuracy": round((tp + tn) / len(labels), 6) if labels else 0.0,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    raw_rows, raw_fieldnames = read_csv(args.raw_input)
    cleaned_rows, cleaned_fieldnames = read_csv(args.cleaned_input)
    if [row[args.id_col] for row in raw_rows] != [row[args.id_col] for row in cleaned_rows]:
        raise ValueError("raw and cleaned CSV row IDs do not match")
    importance_rows = load_importance(args.importance_csv)
    protected = protected_tokens()
    distributions = build_distribution(
        raw_rows,
        text_col=args.text_col,
        id_col=args.id_col,
        author_col=args.author_col,
    )
    author_tfidf_signals = build_author_tfidf_signals(
        raw_rows,
        text_col=args.text_col,
        author_col=args.author_col,
        protected=protected,
        min_token_length=args.min_token_length,
    )

    candidate_rows = [dict(row) for row in cleaned_rows]
    row_decisions: list[dict[str, Any]] = []
    proposed_count = 0
    for raw_row, candidate_row in zip(raw_rows, candidate_rows, strict=True):
        row_id = str(raw_row.get(args.id_col, "") or "")
        author = str(raw_row.get(args.author_col or "", "") or "").strip()
        current_text = str(candidate_row.get(args.text_col, "") or "")
        candidate_text, decisions = candidate_text_for_row(
            row_id=row_id,
            author=author,
            text=current_text,
            importance_rows=importance_rows,
            distributions=distributions,
            author_tfidf_signals=author_tfidf_signals,
            author_signal_mode=args.author_signal_mode,
            low_impact_threshold=args.low_impact_threshold,
            protect_threshold=args.protect_threshold,
            max_masks_per_row=args.max_masks_per_row,
            min_token_length=args.min_token_length,
            min_author_count=args.min_author_count,
            min_author_concentration=args.min_author_concentration,
            rare_document_frequency=args.rare_document_frequency,
            min_tfidf_score=args.min_tfidf_score,
            max_tfidf_rank=args.max_tfidf_rank,
            replacement=args.replacement,
            protected=protected,
        )
        if decisions:
            candidate_row[args.text_col] = candidate_text
            proposed_count += 1
        row_decisions.append(
            {
                "row_id": row_id,
                "author": author,
                "proposed": bool(decisions),
                "accepted": False,
                "reverted_reason": None,
                "decisions": [decision.__dict__ for decision in decisions],
            }
        )

    classifier = HfHsdClassifierRuntime(
        model_path=args.model_path,
        threshold=args.threshold,
        device=args.device,
        max_length=args.max_length,
    )
    baseline_result = classifier.classify_texts(
        classifier_rows(cleaned_rows, text_col=args.text_col, id_col=args.id_col),
        batch_size=args.batch_size,
    )
    candidate_result = classifier.classify_texts(
        classifier_rows(candidate_rows, text_col=args.text_col, id_col=args.id_col),
        batch_size=args.batch_size,
    )
    output_rows = [dict(row) for row in candidate_rows]
    accepted_count = 0
    reverted_count = 0
    for index, (baseline, candidate) in enumerate(
        zip(baseline_result.rows, candidate_result.rows, strict=True)
    ):
        decision = row_decisions[index]
        if not decision["proposed"]:
            continue
        score_delta = abs(candidate.score - baseline.score)
        if baseline.label != candidate.label:
            output_rows[index][args.text_col] = cleaned_rows[index][args.text_col]
            decision["reverted_reason"] = "classifier_label_flip"
            reverted_count += 1
            continue
        if score_delta > args.max_score_delta:
            output_rows[index][args.text_col] = cleaned_rows[index][args.text_col]
            decision["reverted_reason"] = "classifier_score_drift"
            reverted_count += 1
            continue
        decision["accepted"] = True
        decision["baseline_hsd_score"] = round(baseline.score, 6)
        decision["candidate_hsd_score"] = round(candidate.score, 6)
        decision["score_delta"] = round(score_delta, 6)
        accepted_count += 1

    final_result = classifier.classify_texts(
        classifier_rows(output_rows, text_col=args.text_col, id_col=args.id_col),
        batch_size=args.batch_size,
    )
    write_csv(args.output, output_rows, cleaned_fieldnames)
    validation = validation_report(
        args.raw_input,
        args.output,
        text_cols=[args.text_col],
        id_col=args.id_col,
    )
    gold = [str(row.get(args.label_col, "") or "") for row in raw_rows]
    final_labels = [row.label for row in final_result.rows]
    baseline_labels = [row.label for row in baseline_result.rows]
    candidate_labels = [row.label for row in candidate_result.rows]
    summary = {
        "artifact_type": (
            "author_tfidf_token_mask"
            if args.author_signal_mode == "tfidf"
            else "low_impact_token_mask"
        ),
        "raw_input": str(args.raw_input),
        "cleaned_input": str(args.cleaned_input),
        "output": str(args.output),
        "importance_csv": str(args.importance_csv),
        "row_count": len(output_rows),
        "proposed_rows": proposed_count,
        "accepted_rows": accepted_count,
        "reverted_rows": reverted_count,
        "changed_text_cells": sum(
            str(out.get(args.text_col, "") or "") != str(clean.get(args.text_col, "") or "")
            for out, clean in zip(output_rows, cleaned_rows, strict=True)
        ),
        "config": {
            "low_impact_threshold": args.low_impact_threshold,
            "protect_threshold": args.protect_threshold,
            "max_masks_per_row": args.max_masks_per_row,
            "max_score_delta": args.max_score_delta,
            "replacement": args.replacement,
            "author_signal_mode": args.author_signal_mode,
            "min_token_length": args.min_token_length,
            "min_author_count": args.min_author_count,
            "min_author_concentration": args.min_author_concentration,
            "rare_document_frequency": args.rare_document_frequency,
            "min_tfidf_score": args.min_tfidf_score,
            "max_tfidf_rank": args.max_tfidf_rank,
            "classifier_model_path": args.model_path,
            "classifier_threshold": args.threshold,
        },
        "classifier": {
            "baseline_vs_gold": classification_metrics(baseline_labels, gold),
            "candidate_pre_guard_vs_gold": classification_metrics(candidate_labels, gold),
            "final_vs_gold": classification_metrics(final_labels, gold),
            "baseline_to_final_label_flips": sum(
                before != after for before, after in zip(baseline_labels, final_labels, strict=True)
            ),
        },
        "validation": validation,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "rows": row_decisions,
    }
    if args.audit:
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply deterministic low-HSD-impact token masking on top of a "
            "deterministically cleaned CSV, guarded by the local HSD classifier."
        )
    )
    parser.add_argument("--raw-input", type=Path, required=True)
    parser.add_argument("--cleaned-input", type=Path, required=True)
    parser.add_argument("--importance-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--text-col", default="text")
    parser.add_argument("--id-col", default="ID")
    parser.add_argument("--author-col", default="author")
    parser.add_argument("--label-col", default="hs")
    parser.add_argument("--low-impact-threshold", type=float, default=0.003)
    parser.add_argument("--protect-threshold", type=float, default=0.03)
    parser.add_argument("--max-masks-per-row", type=int, default=2)
    parser.add_argument("--max-score-delta", type=float, default=0.1)
    parser.add_argument("--replacement", default="[STYLE]")
    parser.add_argument("--author-signal-mode", choices=["count", "tfidf"], default="count")
    parser.add_argument("--min-token-length", type=int, default=7)
    parser.add_argument("--min-author-count", type=int, default=2)
    parser.add_argument("--min-author-concentration", type=float, default=0.75)
    parser.add_argument("--rare-document-frequency", type=int, default=1)
    parser.add_argument("--min-tfidf-score", type=float, default=0.06)
    parser.add_argument("--max-tfidf-rank", type=int, default=25)
    parser.add_argument("--model-path", default=DEFAULT_HF_HSD_MODEL_PATH)
    parser.add_argument("--threshold", type=float, default=DEFAULT_HF_HSD_THRESHOLD)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--max-length", type=int, default=DEFAULT_HF_HSD_MAX_LENGTH)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_HF_HSD_BATCH_SIZE)
    return parser


def main() -> int:
    summary = run(build_parser().parse_args())
    printable = {key: value for key, value in summary.items() if key != "rows"}
    print(json.dumps(printable, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
