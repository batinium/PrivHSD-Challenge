"""Local DP-MLM-style masked language model rewrite candidate runtime."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
import re
from difflib import SequenceMatcher
import time
from typing import Any, Iterable

from contextsafe_hsd.cue_checks import cue_terms
from contextsafe_hsd.style import (
    ACTION_TERMS,
    NEGATION_MODALITY_TERMS,
    PLACEHOLDER_PATTERN,
    REPEATED_LETTER_PATTERN,
    STYLE_MARKER_PATTERN,
)


DEFAULT_DPMLM_MODEL_PATH = "FacebookAI/roberta-base"
DEFAULT_DPMLM_EPSILON = 100.0
DEFAULT_DPMLM_MAX_REWRITE_TOKENS = 2
DEFAULT_DPMLM_MIN_ELIGIBLE_SCORE = 4
DEFAULT_DPMLM_TOP_K = 96
DEFAULT_DPMLM_MAX_LENGTH = 256
DEFAULT_DPMLM_CLIP_MIN = -10.0
DEFAULT_DPMLM_CLIP_MAX = 10.0

WORD_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z'-]*")
TOKEN_PATTERN = re.compile(
    r"\[[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?\]"
    r"|https?://\S+"
    r"|@[A-Za-z0-9._-]+"
    r"|#[A-Za-z0-9_]{2,}"
    r"|[A-Za-z][A-Za-z'-]*"
    r"|\d+(?:[./-]\d+)*"
    r"|[^\w\s]",
)
PUNCTUATION_PATTERN = re.compile(r"^\W+$", re.UNICODE)
SPECIAL_TOKEN_PATTERN = re.compile(r"^(?:<[^>]+>|\[[A-Z_]+]|\[UNK]|</?s>)$")
HASHTAG_PATTERN = re.compile(r"^#[A-Za-z0-9_]{2,}$")
MIN_REPLACEMENT_SIMILARITY = 0.75
MIN_REPLACEMENT_LENGTH_RATIO = 0.75
BYTE_LEVEL_WORD_START_MARKERS = ("Ġ", "▁")

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


class DpmlmRewriteError(ValueError):
    pass


@dataclass(frozen=True)
class TokenSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class DpmlmRewriteResult:
    text: str
    token_count: int
    eligible_count: int
    protected_token_count: int
    extra_protected_token_count: int
    requested_rewrite_count: int
    changed_token_count: int
    skipped_prediction_count: int
    elapsed_seconds: float
    rewritten_tokens: tuple[dict[str, Any], ...]

    def metadata(self) -> dict[str, Any]:
        return {
            "token_count": self.token_count,
            "eligible_count": self.eligible_count,
            "protected_token_count": self.protected_token_count,
            "extra_protected_token_count": self.extra_protected_token_count,
            "requested_rewrite_count": self.requested_rewrite_count,
            "changed_token_count": self.changed_token_count,
            "skipped_prediction_count": self.skipped_prediction_count,
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "rewritten_tokens": list(self.rewritten_tokens),
        }


def stable_row_seed(base_seed: int, row_index: int, text: str) -> int:
    digest = hashlib.sha256(f"{base_seed}:{row_index}:{text}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def normalize_token(token: str) -> str:
    return token.strip().strip("`\"'.,!?;:(){}<>").lower()


def protected_tokens() -> frozenset[str]:
    protected: set[str] = set(STOPWORDS)
    for terms in cue_terms().values():
        for term in terms:
            protected.update(
                normalize_token(match.group(0))
                for match in WORD_TOKEN_PATTERN.finditer(term)
            )
    protected.update(term.lower() for term in ACTION_TERMS)
    protected.update(term.lower() for term in NEGATION_MODALITY_TERMS)
    return frozenset(token for token in protected if token)


def repeated_letter_variants(token: str) -> set[str]:
    normalized = normalize_token(token)
    if not normalized:
        return set()
    return {
        REPEATED_LETTER_PATTERN.sub(r"\1", normalized),
        REPEATED_LETTER_PATTERN.sub(r"\1\1", normalized),
    }


def replacement_similarity(original: str, replacement: str) -> float:
    original_normalized = normalize_token(original)
    replacement_normalized = normalize_token(replacement)
    if not original_normalized or not replacement_normalized:
        return 0.0
    original_variants = repeated_letter_variants(original) | {original_normalized}
    replacement_variants = repeated_letter_variants(replacement) | {replacement_normalized}
    return max(
        SequenceMatcher(None, left, right).ratio()
        for left in original_variants
        for right in replacement_variants
    )


def replacement_length_ratio(original: str, replacement: str) -> float:
    original_normalized = normalize_token(original)
    replacement_normalized = normalize_token(replacement)
    if not original_normalized or not replacement_normalized:
        return 0.0
    return min(len(original_normalized), len(replacement_normalized)) / max(
        len(original_normalized),
        len(replacement_normalized),
    )


def same_word_family(original: str, replacement: str) -> bool:
    original_normalized = normalize_token(original)
    replacement_normalized = normalize_token(replacement)
    if not original_normalized or not replacement_normalized:
        return False
    return original_normalized[0] == replacement_normalized[0]


def tokenizer_uses_word_start_markers(tokenizer: Any) -> bool:
    unknown_id = getattr(tokenizer, "unk_token_id", None)
    for marker in BYTE_LEVEL_WORD_START_MARKERS:
        token_id = tokenizer.convert_tokens_to_ids(f"{marker}the")
        if token_id is not None and token_id != unknown_id:
            return True
    return False


def token_spans(text: str) -> list[TokenSpan]:
    return [
        TokenSpan(match.start(), match.end(), match.group(0))
        for match in TOKEN_PATTERN.finditer(text)
    ]


def is_placeholder_token(token: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.fullmatch(token))


def is_protected_token(token: str, protected: frozenset[str]) -> bool:
    normalized = normalize_token(token)
    if not normalized:
        return True
    if normalized in protected:
        return True
    if repeated_letter_variants(token) & protected:
        return True
    if is_placeholder_token(token):
        return True
    if PUNCTUATION_PATTERN.fullmatch(token):
        return True
    if token[:1].isupper():
        return True
    if token.startswith(("@", "http://", "https://", "#")):
        return True
    return False


def eligible_score(token: str, protected: frozenset[str]) -> int:
    if is_protected_token(token, protected):
        return -1
    normalized = normalize_token(token)
    if len(normalized) <= 3 and not REPEATED_LETTER_PATTERN.search(token):
        return -1
    if SPECIAL_TOKEN_PATTERN.fullmatch(token):
        return -1
    if HASHTAG_PATTERN.fullmatch(token):
        return -1
    if not WORD_TOKEN_PATTERN.fullmatch(token):
        return -1

    score = 0
    if STYLE_MARKER_PATTERN.fullmatch(token):
        score += 8
    if REPEATED_LETTER_PATTERN.search(token):
        score += 8
    return score


def eligible_indices(
    tokens: list[TokenSpan],
    *,
    protected: frozenset[str],
    max_rewrite_tokens: int,
    min_score: int,
    seed: int,
) -> list[int]:
    if max_rewrite_tokens <= 0:
        return []
    scored = [
        (eligible_score(token.text, protected), index)
        for index, token in enumerate(tokens)
    ]
    scored = [(score, index) for score, index in scored if score >= min_score]
    rng = random.Random(seed)
    scored.sort(key=lambda item: (-item[0], rng.random(), item[1]))
    return [index for _score, index in scored[:max_rewrite_tokens]]


def rebuild_text(text: str, tokens: list[TokenSpan], replacements: dict[int, str]) -> str:
    parts: list[str] = []
    cursor = 0
    for index, token in enumerate(tokens):
        parts.append(text[cursor : token.start])
        parts.append(replacements.get(index, token.text))
        cursor = token.end
    parts.append(text[cursor:])
    return "".join(parts)


def match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def sanitize_prediction(
    *,
    tokenizer: Any,
    token_id: int,
    original: str,
    protected: frozenset[str],
) -> str | None:
    raw_token = str(tokenizer.convert_ids_to_tokens(int(token_id)))
    if raw_token.startswith("##"):
        return None
    if tokenizer_uses_word_start_markers(tokenizer) and not raw_token.startswith(
        BYTE_LEVEL_WORD_START_MARKERS
    ):
        return None
    decoded = str(tokenizer.decode([int(token_id)], clean_up_tokenization_spaces=True))
    cleaned = decoded.strip()
    if not cleaned:
        return None
    if any(character.isspace() for character in cleaned):
        return None
    if SPECIAL_TOKEN_PATTERN.fullmatch(cleaned):
        return None
    normalized = normalize_token(cleaned)
    if not normalized or normalized == normalize_token(original):
        return None
    if normalized in protected:
        return None
    if repeated_letter_variants(cleaned) & protected:
        return None
    if not WORD_TOKEN_PATTERN.fullmatch(cleaned):
        return None
    if not same_word_family(original, cleaned):
        return None
    if (
        not REPEATED_LETTER_PATTERN.search(original)
        and replacement_length_ratio(original, cleaned) < MIN_REPLACEMENT_LENGTH_RATIO
    ):
        return None
    if replacement_similarity(original, cleaned) < MIN_REPLACEMENT_SIMILARITY:
        return None
    return match_case(original, cleaned)


class DpmlmRewriteRuntime:
    """Generate conservative DP-MLM-style rewrite candidates with local MLM logits."""

    def __init__(
        self,
        *,
        model_path: str = DEFAULT_DPMLM_MODEL_PATH,
        device: str = "auto",
        epsilon: float = DEFAULT_DPMLM_EPSILON,
        top_k: int = DEFAULT_DPMLM_TOP_K,
        max_length: int = DEFAULT_DPMLM_MAX_LENGTH,
        clip_min: float = DEFAULT_DPMLM_CLIP_MIN,
        clip_max: float = DEFAULT_DPMLM_CLIP_MAX,
    ) -> None:
        if epsilon <= 0:
            raise ValueError("dpmlm_epsilon must be positive")
        if top_k < 1:
            raise ValueError("dpmlm_top_k must be positive")
        if max_length < 1:
            raise ValueError("dpmlm_max_length must be positive")
        if clip_max <= clip_min:
            raise ValueError("dpmlm_clip_max must be greater than dpmlm_clip_min")

        import torch
        from transformers import AutoModelForMaskedLM, AutoTokenizer

        requested_device = device.strip().lower()
        if requested_device == "auto":
            selected_device = "cuda" if torch.cuda.is_available() else "cpu"
        elif requested_device in {"cpu", "cuda"}:
            selected_device = requested_device
        else:
            raise ValueError("dpmlm_device must be auto, cpu, or cuda")

        self.model_path = model_path
        self.device = selected_device
        self.epsilon = float(epsilon)
        self.top_k = int(top_k)
        self.max_length = int(max_length)
        self.clip_min = float(clip_min)
        self.clip_max = float(clip_max)
        self.temperature = max(
            1e-6,
            2.0 * (self.clip_max - self.clip_min) / self.epsilon,
        )
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForMaskedLM.from_pretrained(model_path)
        if self._tokenizer.mask_token_id is None:
            raise DpmlmRewriteError(f"model {model_path!r} does not define a mask token")
        self._model.eval()
        self._model.to(self.device)
        self.model_id = str(getattr(self._model.config, "_name_or_path", model_path))
        self._protected = protected_tokens()

    def status_metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_path": self.model_path,
            "device": self.device,
            "epsilon": round(self.epsilon, 6),
            "top_k": self.top_k,
            "max_length": self.max_length,
            "clip_min": self.clip_min,
            "clip_max": self.clip_max,
            "temperature": round(self.temperature, 6),
            "approved_use": "experimental rewrite candidate only; scored before selection",
        }

    def _masked_context(
        self,
        text: str,
        tokens: list[TokenSpan],
        token_index: int,
        replacements: dict[int, str],
    ) -> str:
        masked_replacements = dict(replacements)
        masked_replacements[token_index] = str(self._tokenizer.mask_token)
        masked_text = rebuild_text(text, tokens, masked_replacements)
        sep = self._tokenizer.sep_token or "</s>"
        return f"{text} {sep} {masked_text}"

    def _sample_replacement(
        self,
        *,
        context: str,
        original: str,
        protected: frozenset[str],
        seed: int,
    ) -> str | None:
        torch = self._torch
        encoded = self._tokenizer(
            context,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_length,
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        mask_positions = (encoded["input_ids"] == self._tokenizer.mask_token_id).nonzero(
            as_tuple=False
        )
        if mask_positions.numel() == 0:
            return None
        mask_index = int(mask_positions[-1, 1].item())
        with torch.no_grad():
            logits = self._model(**encoded).logits[0, mask_index, :]
        logits = torch.clamp(logits.float(), self.clip_min, self.clip_max)
        scaled = logits / self.temperature
        candidate_count = min(int(self.top_k), int(scaled.shape[-1]))
        top_values, top_indices = torch.topk(scaled, k=candidate_count)
        valid_values = []
        valid_indices = []
        for value, token_id in zip(top_values, top_indices):
            replacement = sanitize_prediction(
                tokenizer=self._tokenizer,
                token_id=int(token_id.item()),
                original=original,
                protected=protected,
            )
            if replacement is None:
                continue
            valid_values.append(value)
            valid_indices.append((int(token_id.item()), replacement))
        if not valid_indices:
            return None
        valid_tensor = torch.stack(valid_values)
        probs = torch.softmax(valid_tensor, dim=0)
        generator = torch.Generator(device=probs.device)
        generator.manual_seed(seed)
        choice = int(torch.multinomial(probs, num_samples=1, generator=generator).item())
        return valid_indices[choice][1]

    def rewrite(
        self,
        text: str,
        *,
        seed: int,
        max_rewrite_tokens: int = DEFAULT_DPMLM_MAX_REWRITE_TOKENS,
        min_eligible_score: int = DEFAULT_DPMLM_MIN_ELIGIBLE_SCORE,
        extra_protected_tokens: Iterable[str] | None = None,
    ) -> DpmlmRewriteResult:
        if max_rewrite_tokens < 0:
            raise ValueError("dpmlm_max_rewrite_tokens must be non-negative")
        if min_eligible_score < 0:
            raise ValueError("dpmlm_min_eligible_score must be non-negative")
        started = time.perf_counter()
        extra_protected = frozenset(
            normalized
            for token in (extra_protected_tokens or ())
            if (normalized := normalize_token(str(token)))
        )
        protected = self._protected | extra_protected
        tokens = token_spans(text)
        indices = eligible_indices(
            tokens,
            protected=protected,
            max_rewrite_tokens=max_rewrite_tokens,
            min_score=min_eligible_score,
            seed=seed,
        )
        replacements: dict[int, str] = {}
        rewritten: list[dict[str, Any]] = []
        skipped = 0
        for offset, index in enumerate(indices):
            original = tokens[index].text
            context = self._masked_context(text, tokens, index, replacements)
            replacement = self._sample_replacement(
                context=context,
                original=original,
                protected=protected,
                seed=seed + offset + 1,
            )
            if replacement is None:
                skipped += 1
                continue
            replacements[index] = replacement
            rewritten.append(
                {
                    "token_index": index,
                    "original_token_length": len(original),
                    "replacement_token_length": len(replacement),
                    "eligible_score": eligible_score(original, protected),
                }
            )
        result_text = rebuild_text(text, tokens, replacements)
        return DpmlmRewriteResult(
            text=result_text,
            token_count=len(tokens),
            eligible_count=len(indices),
            protected_token_count=len(protected),
            extra_protected_token_count=len(extra_protected),
            requested_rewrite_count=len(indices),
            changed_token_count=len(replacements),
            skipped_prediction_count=skipped,
            elapsed_seconds=time.perf_counter() - started,
            rewritten_tokens=tuple(rewritten),
        )


__all__ = [
    "DEFAULT_DPMLM_CLIP_MAX",
    "DEFAULT_DPMLM_CLIP_MIN",
    "DEFAULT_DPMLM_EPSILON",
    "DEFAULT_DPMLM_MAX_LENGTH",
    "DEFAULT_DPMLM_MAX_REWRITE_TOKENS",
    "DEFAULT_DPMLM_MIN_ELIGIBLE_SCORE",
    "DEFAULT_DPMLM_MODEL_PATH",
    "DEFAULT_DPMLM_TOP_K",
    "DpmlmRewriteError",
    "DpmlmRewriteResult",
    "DpmlmRewriteRuntime",
    "stable_row_seed",
]
