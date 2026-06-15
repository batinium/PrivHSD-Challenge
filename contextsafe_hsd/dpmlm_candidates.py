"""Optional protected-token DPMLM candidate generation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import importlib
from pathlib import Path
import random
import re
import time
from typing import Any

from .csv_pipeline import read_csv, write_csv, write_json
from .cue_checks import DEFAULT_RETENTION_THRESHOLD, row_cue_report
from .dpmlm_spike import DPMLM_WARNING, protected_cue_manifest
from .row_ids import report_row_id
from .rerank import validate_rewrite_candidate
from .style import PLACEHOLDER_PATTERN


DEFAULT_MODEL = "FacebookAI/roberta-base"
DEFAULT_SAMPLE_SIZE = 25
DEFAULT_EPSILON = 50.0
DEFAULT_BATCH_SIZE = 8
DEFAULT_MAX_REWRITE_TOKENS = 4
DEFAULT_MIN_ELIGIBLE_SCORE = 5
DEFAULT_MIN_CHARACTER_RETENTION = 0.65
DEFAULT_MAX_LENGTH_DRIFT = 0.45
DPMLM_CANDIDATE_WARNING = (
    "DPMLM outputs are optional rewrite candidates only. They must be reranked "
    "and audited before any submission; protected-token validation rejects rows "
    "that lose target/action/negation/utility cues."
)

PUNCTUATION_PATTERN = re.compile(r"^\W+$", re.UNICODE)
WORDISH_PATTERN = re.compile(r"^[A-Za-z][A-Za-z'-]*$")
REPEATED_LETTER_PATTERN = re.compile(r"([A-Za-z])\1{2,}")
HASHTAG_TOKEN_PATTERN = re.compile(r"^#[A-Za-z0-9_]{2,}$")
SPECIAL_TOKEN_PATTERN = re.compile(r"^(?:<[^>]+>|\[[A-Z_]+]|\[UNK]|</?s>)$")

STOPWORDS = frozenset(
    {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
    }
)


class DpmlmCandidateError(ValueError):
    pass


@dataclass(frozen=True)
class RewriteResult:
    text: str
    token_count: int
    eligible_count: int
    requested_rewrite_count: int
    changed_token_count: int
    skipped_prediction_count: int


def rounded(value: float) -> float:
    return round(float(value), 4)


def load_dpmlm_model(model_name: str) -> Any:
    try:
        module = importlib.import_module("dpmlm")
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise DpmlmCandidateError(
            "dpmlm is not installed; install the optional extra with "
            "python -m pip install '.[dpmlm]'"
        ) from exc
    try:
        return module.DPMLM(MODEL=model_name)
    except Exception as exc:  # pragma: no cover - environment dependent
        raise DpmlmCandidateError(
            f"failed to initialize DPMLM model {model_name!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def tokenize_text(text: str) -> list[str]:
    try:
        nltk = importlib.import_module("nltk")
        return [str(token) for token in nltk.word_tokenize(text)]
    except LookupError as exc:  # pragma: no cover - local resource dependent
        raise DpmlmCandidateError(
            "NLTK tokenizer resources are missing; run "
            "python -m nltk.downloader punkt punkt_tab"
        ) from exc
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise DpmlmCandidateError(
            "nltk is not installed; install the optional dpmlm dependencies"
        ) from exc


def seed_everything(seed: int) -> None:
    random.seed(seed)
    try:
        numpy = importlib.import_module("numpy")
        numpy.random.seed(seed)
    except Exception:  # pragma: no cover - optional dependency behavior
        pass
    try:
        torch = importlib.import_module("torch")
        torch.manual_seed(seed)
    except Exception:  # pragma: no cover - optional dependency behavior
        pass


def stable_row_seed(base_seed: int, row_index: int, text: str) -> int:
    digest = hashlib.sha256(f"{base_seed}:{row_index}:{text}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def normalize_token(token: str) -> str:
    return token.strip().strip("`\"'.,!?;:(){}<>").lower()


def repeated_letter_variants(token: str) -> set[str]:
    normalized = normalize_token(token)
    if not normalized:
        return set()
    collapsed_to_one = REPEATED_LETTER_PATTERN.sub(r"\1", normalized)
    collapsed_to_two = REPEATED_LETTER_PATTERN.sub(r"\1\1", normalized)
    return {collapsed_to_one, collapsed_to_two}


def protected_tokens() -> set[str]:
    manifest = protected_cue_manifest()
    tokens = {normalize_token(token) for token in manifest["protected_tokens"]}
    tokens |= {normalize_token(token) for token in STOPWORDS}
    return {token for token in tokens if token}


def is_placeholder_token(token: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.fullmatch(token))


def is_protected_token(token: str, protected: set[str]) -> bool:
    normalized = normalize_token(token)
    if not normalized:
        return True
    if normalized in protected:
        return True
    if repeated_letter_variants(token) & protected:
        return True
    if REPEATED_LETTER_PATTERN.search(token):
        return True
    if is_placeholder_token(token):
        return True
    if PUNCTUATION_PATTERN.fullmatch(token):
        return True
    if len(normalized) > 1 and token[:1].isupper():
        return True
    if token.startswith("@"):
        return True
    if token.startswith("http://") or token.startswith("https://"):
        return True
    return False


def eligible_score(token: str, index: int, protected: set[str]) -> int:
    if is_protected_token(token, protected):
        return -1
    normalized = normalize_token(token)
    if len(normalized) <= 3 and not REPEATED_LETTER_PATTERN.search(token):
        return -1
    if SPECIAL_TOKEN_PATTERN.fullmatch(token):
        return -1
    if not (WORDISH_PATTERN.fullmatch(token) or HASHTAG_TOKEN_PATTERN.fullmatch(token)):
        return -1

    score = 1
    if REPEATED_LETTER_PATTERN.search(token) or HASHTAG_TOKEN_PATTERN.fullmatch(token):
        score += 8
    if token[:1].isupper() and index > 0:
        score += 5
    if len(normalized) >= 9:
        score += 3
    elif len(normalized) >= 6:
        score += 2
    return score


def eligible_indices(
    tokens: list[str],
    *,
    protected: set[str],
    max_rewrite_tokens: int,
    min_score: int,
    seed: int,
) -> list[int]:
    if max_rewrite_tokens <= 0:
        return []
    scored = [
        (eligible_score(token, index, protected), index)
        for index, token in enumerate(tokens)
    ]
    scored = [(score, index) for score, index in scored if score >= min_score]
    rng = random.Random(seed)
    scored.sort(key=lambda item: (-item[0], rng.random(), item[1]))
    return [index for _score, index in scored[:max_rewrite_tokens]]


def sanitize_prediction(original: str, prediction: str, protected: set[str]) -> str | None:
    cleaned = prediction.strip()
    if not cleaned:
        return None
    if " " in cleaned or "\t" in cleaned or "\n" in cleaned:
        return None
    if SPECIAL_TOKEN_PATTERN.fullmatch(cleaned):
        return None
    normalized = normalize_token(cleaned)
    if not normalized:
        return None
    if normalized == normalize_token(original):
        return None
    if normalized in protected:
        return None
    if not WORDISH_PATTERN.fullmatch(cleaned):
        return None
    if original.isupper():
        return cleaned.upper()
    if original[:1].isupper():
        return cleaned[:1].upper() + cleaned[1:]
    return cleaned


def detokenize(model: Any, tokens: list[str]) -> str:
    detokenizer = getattr(model, "detokenizer", None)
    if detokenizer and hasattr(detokenizer, "detokenize"):
        return str(detokenizer.detokenize(tokens))
    return " ".join(tokens)


def rewrite_text_with_dpmlm(
    model: Any,
    text: str,
    *,
    epsilon: float,
    batch_size: int,
    max_rewrite_tokens: int,
    min_eligible_score: int,
    seed: int,
    concat: bool = True,
) -> RewriteResult:
    tokens = tokenize_text(text)
    protected = protected_tokens()
    indices = eligible_indices(
        tokens,
        protected=protected,
        max_rewrite_tokens=max_rewrite_tokens,
        min_score=min_eligible_score,
        seed=seed,
    )
    if not indices:
        return RewriteResult(
            text=text,
            token_count=len(tokens),
            eligible_count=0,
            requested_rewrite_count=0,
            changed_token_count=0,
            skipped_prediction_count=0,
        )

    seed_everything(seed)
    predictions = model.privatize_batch(
        tokens,
        indices,
        [epsilon for _index in indices],
        CONCAT=concat,
        batch_size=batch_size,
    )
    rewritten_tokens = list(tokens)
    changed = 0
    skipped = 0
    for index in indices:
        original = tokens[index]
        prediction = str(predictions.get(f"{original}_{index}", "") or "")
        replacement = sanitize_prediction(original, prediction, protected)
        if replacement is None:
            skipped += 1
            continue
        rewritten_tokens[index] = replacement
        changed += 1

    return RewriteResult(
        text=detokenize(model, rewritten_tokens),
        token_count=len(tokens),
        eligible_count=len(indices),
        requested_rewrite_count=len(indices),
        changed_token_count=changed,
        skipped_prediction_count=skipped,
    )


def validate_candidate(
    original: str,
    candidate: str,
    *,
    row_index: int,
    row_id: str,
    min_target_retention: float,
    min_utility_retention: float,
    min_character_retention: float,
    max_length_drift: float,
    cue_retention_threshold: float,
) -> tuple[bool, dict[str, Any]]:
    accepted, checks = validate_rewrite_candidate(
        original,
        candidate,
        min_target_retention=min_target_retention,
        min_utility_retention=min_utility_retention,
        min_character_retention=min_character_retention,
        max_length_drift=max_length_drift,
        reject_unchanged=True,
    )
    cue_report = row_cue_report(
        row_index=row_index,
        row_id=row_id,
        original=original,
        privatized=candidate,
        threshold=cue_retention_threshold,
    )
    reasons = list(checks["reasons"])
    if cue_report["loss_groups"]:
        reasons.append("conservative_hsd_cue_loss")

    checks = {
        **checks,
        "accepted": accepted and not cue_report["loss_groups"],
        "reasons": reasons,
        "cue_loss_groups": cue_report["loss_groups"],
        "cue_retention_threshold": cue_retention_threshold,
    }
    return checks["accepted"], checks


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_col: str,
    id_col: str | None,
) -> None:
    missing = [column for column in (text_col, id_col) if column]
    missing = [column for column in missing if column not in fieldnames]
    if missing:
        raise DpmlmCandidateError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )


def run_dpmlm_candidates(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    candidate_col: str = "dpmlm_candidate",
    report_path: Path | None = None,
    model_name: str = DEFAULT_MODEL,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    epsilon: float = DEFAULT_EPSILON,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_rewrite_tokens: int = DEFAULT_MAX_REWRITE_TOKENS,
    min_eligible_score: int = DEFAULT_MIN_ELIGIBLE_SCORE,
    random_seed: int = 0,
    min_target_retention: float = 1.0,
    min_utility_retention: float = 1.0,
    min_character_retention: float = DEFAULT_MIN_CHARACTER_RETENTION,
    max_length_drift: float = DEFAULT_MAX_LENGTH_DRIFT,
    cue_retention_threshold: float = DEFAULT_RETENTION_THRESHOLD,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(input_path, fieldnames, text_col=text_col, id_col=id_col)
    if sample_size < 0:
        raise DpmlmCandidateError("--sample-size must be non-negative")
    if epsilon <= 0:
        raise DpmlmCandidateError("--epsilon must be positive")
    if batch_size <= 0:
        raise DpmlmCandidateError("--batch-size must be positive")
    if max_rewrite_tokens < 0:
        raise DpmlmCandidateError("--max-rewrite-tokens must be non-negative")
    if min_eligible_score < 0:
        raise DpmlmCandidateError("--min-eligible-score must be non-negative")
    if not 0 <= min_target_retention <= 1:
        raise DpmlmCandidateError("--min-target-retention must be between 0 and 1")
    if not 0 <= min_utility_retention <= 1:
        raise DpmlmCandidateError("--min-utility-retention must be between 0 and 1")
    if not 0 <= min_character_retention <= 1:
        raise DpmlmCandidateError("--min-character-retention must be between 0 and 1")
    if max_length_drift < 0:
        raise DpmlmCandidateError("--max-length-drift must be non-negative")
    if not 0 <= cue_retention_threshold <= 1:
        raise DpmlmCandidateError("--cue-retention-threshold must be between 0 and 1")

    output_fieldnames = list(fieldnames)
    if candidate_col not in output_fieldnames:
        output_fieldnames.append(candidate_col)

    limit = len(rows) if sample_size <= 0 else min(sample_size, len(rows))
    start = time.perf_counter()
    model = load_dpmlm_model(model_name) if limit else None
    output_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    accepted_count = 0
    first_error: str | None = None
    status_counter: Counter[str] = Counter()
    reject_reasons: Counter[str] = Counter()

    for row_index, row in enumerate(rows, start=1):
        output_row = dict(row)
        candidate = ""
        row_status = "not_requested"
        checks: dict[str, Any] | None = None
        rewrite_summary: dict[str, int] | None = None
        detail = None
        if row_index <= limit:
            row_id = report_row_id(row, row_index=row_index, id_col=id_col)
            original = str(row.get(text_col, "") or "")
            row_seed = stable_row_seed(random_seed, row_index, original)
            try:
                result = rewrite_text_with_dpmlm(
                    model,
                    original,
                    epsilon=epsilon,
                    batch_size=batch_size,
                    max_rewrite_tokens=max_rewrite_tokens,
                    min_eligible_score=min_eligible_score,
                    seed=row_seed,
                )
                rewrite_summary = {
                    "token_count": result.token_count,
                    "eligible_count": result.eligible_count,
                    "requested_rewrite_count": result.requested_rewrite_count,
                    "changed_token_count": result.changed_token_count,
                    "skipped_prediction_count": result.skipped_prediction_count,
                }
                accepted, checks = validate_candidate(
                    original,
                    result.text,
                    row_index=row_index,
                    row_id=row_id,
                    min_target_retention=min_target_retention,
                    min_utility_retention=min_utility_retention,
                    min_character_retention=min_character_retention,
                    max_length_drift=max_length_drift,
                    cue_retention_threshold=cue_retention_threshold,
                )
                if result.changed_token_count == 0:
                    accepted = False
                    checks["accepted"] = False
                    if "no_token_change" not in checks["reasons"]:
                        checks["reasons"].append("no_token_change")
                if accepted:
                    candidate = result.text
                    row_status = "accepted"
                    accepted_count += 1
                else:
                    row_status = "rejected_by_checks"
                    reject_reasons.update(checks["reasons"])
            except DpmlmCandidateError as exc:
                row_status = "failed"
                detail = str(exc)
                first_error = first_error or detail
            except Exception as exc:  # pragma: no cover - backend dependent
                row_status = "failed"
                detail = f"{type(exc).__name__}: {exc}"
                first_error = first_error or detail
            status_counter[row_status] += 1
            audit_rows.append(
                {
                    "row_index": row_index,
                    "row_id": row_id,
                    "status": row_status,
                    "rewrite": rewrite_summary,
                    "checks": checks,
                    "detail": detail,
                }
            )
        output_row[candidate_col] = candidate
        output_rows.append(output_row)

    write_csv(output_path, output_rows, output_fieldnames)
    status = "ok" if accepted_count else "skipped"
    report = {
        "input": str(input_path),
        "output": str(output_path),
        "report": str(report_path) if report_path else None,
        "generator_type": "dpmlm_protected_candidate",
        "status": status,
        "skip_reason": "no_accepted_candidates" if status == "skipped" else None,
        "detail": first_error if status == "skipped" else None,
        "first_error": first_error,
        "warning": DPMLM_CANDIDATE_WARNING,
        "dpmlm_warning": DPMLM_WARNING,
        "model": model_name,
        "privacy_parameters": {
            "epsilon": epsilon,
            "random_seed": random_seed,
        },
        "generation_policy": {
            "protected_token_count": len(protected_tokens()),
            "protected_sources": [
                "target_terms",
                "utility_cues",
                "action_terms",
                "negation_modality_terms",
                "stopwords",
                "capitalized_tokens",
                "repeated_letter_tokens",
                "placeholders",
                "punctuation",
            ],
            "selection": "highest_risk_non_protected_tokens_first",
            "batch_size": batch_size,
            "max_rewrite_tokens": max_rewrite_tokens,
            "min_eligible_score": min_eligible_score,
        },
        "validation_policy": {
            "min_target_retention": min_target_retention,
            "min_utility_retention": min_utility_retention,
            "min_character_retention": min_character_retention,
            "max_length_drift": max_length_drift,
            "cue_retention_threshold": cue_retention_threshold,
            "rejects_new_identifier_signal": True,
            "rejects_style_risk_increase": True,
            "min_changed_tokens": 1,
        },
        "columns": {
            "text_col": text_col,
            "id_col": id_col,
            "candidate_col": candidate_col,
        },
        "sample": {
            "requested_sample_size": sample_size,
            "sample_size": limit,
            "source_row_count": len(rows),
            "strategy": "first_n_rows",
        },
        "accepted_count": accepted_count,
        "status_counts": dict(sorted(status_counter.items())),
        "reject_reasons": dict(sorted(reject_reasons.items())),
        "runtime_seconds": rounded(time.perf_counter() - start),
        "rows": audit_rows,
        "next_step": (
            "Run rerank-candidates with --candidate-col "
            f"{candidate_col}; do not submit raw DPMLM candidates directly."
        ),
    }
    if report_path:
        write_json(report_path, report)
    return report
