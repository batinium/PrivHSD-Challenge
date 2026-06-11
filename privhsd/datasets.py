"""Dataset preparation helpers."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request


COMMON_DATASET_FIELDNAMES = [
    "id",
    "text",
    "label",
    "source",
    "split",
    "target",
    "type",
    "platform",
    "source_id",
    "severity",
    "target_categories",
    "rationale_spans",
    "meta",
]

DEFAULT_DYNAHATE_URL = (
    "https://raw.githubusercontent.com/bvidgen/"
    "Dynamically-Generated-Hate-Speech-Dataset/main/"
    "Dynamically%20Generated%20Hate%20Dataset%20v0.2.3.csv"
)
DEFAULT_HATECHECK_URL = (
    "https://raw.githubusercontent.com/paul-rottger/hatecheck-data/main/all_cases.csv"
)
DEFAULT_HATEMOJI_CHECK_URL = (
    "https://raw.githubusercontent.com/HannahKirk/Hatemoji/main/HatemojiCheck/test.csv"
)
DEFAULT_HATEMOJI_BUILD_URLS = {
    "train": (
        "https://raw.githubusercontent.com/HannahKirk/Hatemoji/main/"
        "HatemojiBuild/train.csv"
    ),
    "validation": (
        "https://raw.githubusercontent.com/HannahKirk/Hatemoji/main/"
        "HatemojiBuild/validation.csv"
    ),
    "test": (
        "https://raw.githubusercontent.com/HannahKirk/Hatemoji/main/"
        "HatemojiBuild/test.csv"
    ),
}
DEFAULT_HATEXPLAIN_DATASET_URL = (
    "https://raw.githubusercontent.com/hate-alert/HateXplain/master/Data/dataset.json"
)
DEFAULT_HATEXPLAIN_SPLITS_URL = (
    "https://raw.githubusercontent.com/hate-alert/HateXplain/master/Data/"
    "post_id_divisions.json"
)
DEFAULT_TOXIC_SPANS_COMMENTS_URL = (
    "https://raw.githubusercontent.com/ipavlopoulos/toxic_spans/master/data/comments.csv"
)
DEFAULT_TOXIC_SPANS_ANNOTATIONS_URL = (
    "https://raw.githubusercontent.com/ipavlopoulos/toxic_spans/master/data/annotations.csv"
)
DEFAULT_TOXIC_SPANS_SPANS_URL = (
    "https://raw.githubusercontent.com/ipavlopoulos/toxic_spans/master/data/spans.csv"
)
DEFAULT_CONVABUSE_URL = (
    "https://raw.githubusercontent.com/amandacurry/convabuse/main/convabuse.csv"
)
DEFAULT_CONVABUSE_SPLIT_URLS = {
    "train": (
        "https://raw.githubusercontent.com/amandacurry/convabuse/main/2_splits/"
        "ConvAbuseEMNLPtrain.csv"
    ),
    "validation": (
        "https://raw.githubusercontent.com/amandacurry/convabuse/main/2_splits/"
        "ConvAbuseEMNLPvalid.csv"
    ),
    "test": (
        "https://raw.githubusercontent.com/amandacurry/convabuse/main/2_splits/"
        "ConvAbuseEMNLPtest.csv"
    ),
}
DEFAULT_DAVIDSON_URL = (
    "https://raw.githubusercontent.com/t-davidson/hate-speech-and-offensive-language/"
    "master/data/labeled_data.csv"
)
DEFAULT_MEASURING_HATE_SPEECH_DATASET = "ucberkeley-dlab/measuring-hate-speech"
DEFAULT_MEASURING_HATE_SPEECH_PARQUET_URL = (
    "https://huggingface.co/datasets/ucberkeley-dlab/measuring-hate-speech/"
    "resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet"
)
DEFAULT_MEASURING_HATE_SPEECH_PARQUET_ALIAS = (
    "hf://datasets/ucberkeley-dlab/measuring-hate-speech@~parquet/default/"
    "train/0000.parquet"
)
DEFAULT_RECOMMENDED_DATASETS = [
    "dynahate",
    "hatecheck",
    "hatemoji",
    "measuring_hate_speech",
    "hatexplain",
    "toxic_spans",
    "convabuse",
    "davidson",
]

MEASURING_SCORE_COLUMNS = [
    "sentiment",
    "respect",
    "insult",
    "humiliate",
    "status",
    "dehumanize",
    "violence",
    "genocide",
    "attack_defend",
    "hatespeech",
    "hate_speech_score",
]


def download_file(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        output.write_bytes(response.read())


def pick_column(fieldnames: list[str], *candidates: str) -> str:
    by_lower = {name.lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
        lowered = candidate.lower()
        if lowered in by_lower:
            return by_lower[lowered]
    raise ValueError(f"missing column; expected one of: {', '.join(candidates)}")


def optional_column(fieldnames: list[str], *candidates: str) -> str | None:
    by_lower = {name.lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
        lowered = candidate.lower()
        if lowered in by_lower:
            return by_lower[lowered]
    return None


def read_csv_rows(path: Path, *, delimiter: str = ",") -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: CSV header is required")
        return list(reader), list(reader.fieldnames)


def write_common_rows(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_DATASET_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in COMMON_DATASET_FIELDNAMES})
            count += 1
    return count


def compact_json(value: Any) -> str:
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compact_list(values: Iterable[Any]) -> str:
    cleaned = sorted({str(value).strip() for value in values if str(value).strip()})
    return ";".join(cleaned)


def format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6g}"


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "t"}


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_hate_label(label: Any) -> str:
    text = str(label).strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"1", "hate", "hateful", "hatespeech", "hate_speech", "abusive"}:
        return "hate"
    if text in {"0", "nothate", "not_hate", "non_hateful", "normal", "none", "neither"}:
        return "not_hate"
    if text in {"offensive", "offensive_language"}:
        return "offensive"
    if text in {"toxic", "all_toxic", "span_toxic"}:
        return "toxic"
    if text in {"not_abusive", "notabusive", "not_toxic"}:
        return "not_abusive"
    return text


def common_row(
    *,
    row_id: Any,
    text: Any,
    label: Any,
    source: str,
    split: Any = "",
    target: Any = "",
    type_: Any = "",
    platform: Any = "",
    source_id: Any = "",
    severity: Any = "",
    target_categories: Any = "",
    rationale_spans: Any = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, str]:
    source_id_text = str(source_id or row_id).strip()
    return {
        "id": str(row_id).strip(),
        "text": str(text or ""),
        "label": str(label or ""),
        "source": source,
        "split": str(split or ""),
        "target": str(target or ""),
        "type": str(type_ or ""),
        "platform": str(platform or ""),
        "source_id": source_id_text,
        "severity": str(severity or ""),
        "target_categories": str(target_categories or ""),
        "rationale_spans": str(rationale_spans or ""),
        "meta": compact_json(meta or {}),
    }


def normalize_dynahate(raw_path: Path, output_path: Path) -> int:
    rows, fields = read_csv_rows(raw_path)
    id_col = pick_column(fields, "acl.id")
    text_col = pick_column(fields, "Text", "text")
    label_col = pick_column(fields, "Label", "label")
    split_col = optional_column(fields, "Split", "split")
    target_col = optional_column(fields, "Target", "target")
    type_col = optional_column(fields, "Type", "type")

    output_rows = []
    for row in rows:
        output_rows.append(
            common_row(
                row_id=row.get(id_col, ""),
                text=row.get(text_col, ""),
                label=canonical_hate_label(row.get(label_col, "")),
                source="dynahate",
                split=row.get(split_col, "") if split_col else "",
                target=row.get(target_col, "") if target_col else "",
                type_=row.get(type_col, "") if type_col else "",
                platform="synthetic",
                meta={"source_label": row.get(label_col, "")},
            )
        )
    return write_common_rows(output_path, output_rows)


def prepare_dynahate(
    *,
    raw_path: Path,
    output_path: Path,
    download: bool = False,
    url: str = DEFAULT_DYNAHATE_URL,
) -> int:
    if download:
        download_file(url, raw_path)
    return normalize_dynahate(raw_path, output_path)


def normalize_hatecheck(raw_path: Path, output_path: Path) -> int:
    rows, fields = read_csv_rows(raw_path)
    id_col = pick_column(fields, "case_id")
    text_col = pick_column(fields, "test_case")
    label_col = pick_column(fields, "label_gold")
    target_col = optional_column(fields, "target_ident")
    type_col = optional_column(fields, "functionality")
    direction_col = optional_column(fields, "direction")
    focus_col = optional_column(fields, "focus_words")

    output_rows = []
    for row in rows:
        case_id = row.get(id_col, "")
        output_rows.append(
            common_row(
                row_id=case_id,
                text=row.get(text_col, ""),
                label=canonical_hate_label(row.get(label_col, "")),
                source="hatecheck",
                split="test",
                target=row.get(target_col, "") if target_col else "",
                type_=row.get(type_col, "") if type_col else "",
                platform="synthetic",
                target_categories=row.get(target_col, "") if target_col else "",
                meta={
                    "source_label": row.get(label_col, ""),
                    "direction": row.get(direction_col, "") if direction_col else "",
                    "focus_words": row.get(focus_col, "") if focus_col else "",
                },
            )
        )
    return write_common_rows(output_path, output_rows)


def prepare_hatecheck(
    *,
    raw_path: Path,
    output_path: Path,
    download: bool = False,
    url: str = DEFAULT_HATECHECK_URL,
) -> int:
    if download:
        download_file(url, raw_path)
    return normalize_hatecheck(raw_path, output_path)


def normalize_hatemoji(
    *,
    check_path: Path,
    build_paths: dict[str, Path],
    output_path: Path,
) -> int:
    output_rows = []

    check_rows, check_fields = read_csv_rows(check_path)
    check_id = pick_column(check_fields, "case_id")
    check_text = pick_column(check_fields, "text")
    check_label = pick_column(check_fields, "label_gold")
    check_target = optional_column(check_fields, "target")
    check_type = optional_column(check_fields, "functionality")
    for row in check_rows:
        output_rows.append(
            common_row(
                row_id=f"check:{row.get(check_id, '')}",
                text=row.get(check_text, ""),
                label=canonical_hate_label(row.get(check_label, "")),
                source="hatemoji_check",
                split="test",
                target=row.get(check_target, "") if check_target else "",
                type_=row.get(check_type, "") if check_type else "",
                platform="synthetic",
                target_categories=row.get(check_target, "") if check_target else "",
                source_id=row.get(check_id, ""),
                meta={
                    "source_label": row.get(check_label, ""),
                    "subset": "HatemojiCheck",
                    "set": row.get("set", ""),
                    "included_in_test_suite": row.get("included_in_test_suite", ""),
                    "unrealistic_flags": row.get("unrealistic_flags", ""),
                },
            )
        )

    for split, path in build_paths.items():
        build_rows, build_fields = read_csv_rows(path)
        build_id = pick_column(build_fields, "entry_id")
        build_text = pick_column(build_fields, "text")
        build_label = pick_column(build_fields, "label_gold")
        build_target = optional_column(build_fields, "target")
        build_type = optional_column(build_fields, "type")
        split_col = optional_column(build_fields, "split")
        for row in build_rows:
            output_rows.append(
                common_row(
                    row_id=f"build:{row.get(build_id, '')}",
                    text=row.get(build_text, ""),
                    label=canonical_hate_label(row.get(build_label, "")),
                    source="hatemoji_build",
                    split=row.get(split_col, "") if split_col else split,
                    target=row.get(build_target, "") if build_target else "",
                    type_=row.get(build_type, "") if build_type else "",
                    platform="synthetic",
                    source_id=row.get(build_id, ""),
                    target_categories=row.get(build_target, "") if build_target else "",
                    meta={
                        "source_label": row.get(build_label, ""),
                        "subset": "HatemojiBuild",
                        "set": row.get("set", ""),
                        "round_base": row.get("round.base", ""),
                        "round_set": row.get("round.set", ""),
                    },
                )
            )

    return write_common_rows(output_path, output_rows)


def prepare_hatemoji(
    *,
    check_path: Path,
    build_paths: dict[str, Path],
    output_path: Path,
    download: bool = False,
    check_url: str = DEFAULT_HATEMOJI_CHECK_URL,
    build_urls: dict[str, str] | None = None,
) -> int:
    if download:
        download_file(check_url, check_path)
        for split, url in (build_urls or DEFAULT_HATEMOJI_BUILD_URLS).items():
            download_file(url, build_paths[split])
    return normalize_hatemoji(
        check_path=check_path,
        build_paths=build_paths,
        output_path=output_path,
    )


def majority(values: Iterable[str]) -> str:
    counts = Counter(value for value in values if value)
    if not counts:
        return ""
    return counts.most_common(1)[0][0]


def token_ranges(indices: Iterable[int]) -> str:
    ordered = sorted(set(indices))
    if not ordered:
        return ""
    ranges: list[str] = []
    start = prev = ordered[0]
    for value in ordered[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = value
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ";".join(ranges)


def normalize_hatexplain(
    *,
    dataset_path: Path,
    splits_path: Path,
    output_path: Path,
) -> int:
    with dataset_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    with splits_path.open("r", encoding="utf-8") as handle:
        split_data = json.load(handle)
    split_by_id = {
        post_id: split for split, post_ids in split_data.items() for post_id in post_ids
    }

    output_rows = []
    for post_id, item in data.items():
        annotators = item.get("annotators", [])
        label = majority(canonical_hate_label(ann.get("label", "")) for ann in annotators)
        targets = []
        for ann in annotators:
            for target in ann.get("target", []):
                if str(target).strip().lower() != "none":
                    targets.append(target)
        tokens = [str(token) for token in item.get("post_tokens", [])]
        rationale_indices: set[int] = set()
        for rationale in item.get("rationales", []):
            for idx, flag in enumerate(rationale):
                if as_bool(flag):
                    rationale_indices.add(idx)
        output_rows.append(
            common_row(
                row_id=post_id,
                text=" ".join(tokens),
                label=label,
                source="hatexplain",
                split=split_by_id.get(post_id, ""),
                target=compact_list(targets),
                type_=label,
                platform="twitter_gab",
                target_categories=compact_list(targets),
                rationale_spans=token_ranges(rationale_indices),
                meta={
                    "annotator_count": len(annotators),
                    "rationale_token_count": len(rationale_indices),
                    "source_label_counts": dict(
                        Counter(
                            canonical_hate_label(ann.get("label", ""))
                            for ann in annotators
                        )
                    ),
                },
            )
        )
    return write_common_rows(output_path, output_rows)


def prepare_hatexplain(
    *,
    dataset_path: Path,
    splits_path: Path,
    output_path: Path,
    download: bool = False,
    dataset_url: str = DEFAULT_HATEXPLAIN_DATASET_URL,
    splits_url: str = DEFAULT_HATEXPLAIN_SPLITS_URL,
) -> int:
    if download:
        download_file(dataset_url, dataset_path)
        download_file(splits_url, splits_path)
    return normalize_hatexplain(
        dataset_path=dataset_path,
        splits_path=splits_path,
        output_path=output_path,
    )


def normalize_toxic_spans(
    *,
    comments_path: Path,
    annotations_path: Path,
    spans_path: Path,
    output_path: Path,
) -> int:
    comments, comment_fields = read_csv_rows(comments_path)
    comment_id_col = pick_column(comment_fields, "comment_id")
    text_col = pick_column(comment_fields, "comment_text")

    annotations, annotation_fields = read_csv_rows(annotations_path)
    annotation_col = pick_column(annotation_fields, "annotation")
    annotation_comment_col = pick_column(annotation_fields, "comment_id")
    all_toxic_col = optional_column(annotation_fields, "all toxic")
    not_toxic_col = optional_column(annotation_fields, "not toxic")
    annotation_to_comment = {
        row.get(annotation_col, ""): row.get(annotation_comment_col, "")
        for row in annotations
    }
    toxicity_votes: dict[str, Counter[str]] = defaultdict(Counter)
    for row in annotations:
        comment_id = row.get(annotation_comment_col, "")
        if all_toxic_col and as_bool(row.get(all_toxic_col, "")):
            toxicity_votes[comment_id]["all_toxic"] += 1
        elif not_toxic_col and as_bool(row.get(not_toxic_col, "")):
            toxicity_votes[comment_id]["not_toxic"] += 1
        else:
            toxicity_votes[comment_id]["span_toxic"] += 1

    span_rows, span_fields = read_csv_rows(spans_path)
    span_annotation_col = pick_column(span_fields, "annotation")
    span_type_col = optional_column(span_fields, "type")
    span_start_col = pick_column(span_fields, "start")
    span_end_col = pick_column(span_fields, "end")
    spans_by_comment: dict[str, list[str]] = defaultdict(list)
    span_types_by_comment: dict[str, set[str]] = defaultdict(set)
    for row in span_rows:
        comment_id = annotation_to_comment.get(row.get(span_annotation_col, ""), "")
        if not comment_id:
            continue
        spans_by_comment[comment_id].append(
            f"{row.get(span_start_col, '')}-{row.get(span_end_col, '')}"
        )
        if span_type_col and row.get(span_type_col, ""):
            span_types_by_comment[comment_id].add(row.get(span_type_col, ""))

    output_rows = []
    for row in comments:
        comment_id = row.get(comment_id_col, "")
        votes = toxicity_votes.get(comment_id, Counter())
        label = votes.most_common(1)[0][0] if votes else "toxic_span_available"
        output_rows.append(
            common_row(
                row_id=comment_id,
                text=row.get(text_col, ""),
                label=canonical_hate_label(label),
                source="toxic_spans",
                split="all",
                target="",
                type_=compact_list(span_types_by_comment.get(comment_id, [])),
                platform="civil_comments",
                rationale_spans=";".join(spans_by_comment.get(comment_id, [])),
                meta={"source_label_counts": dict(votes)},
            )
        )
    return write_common_rows(output_path, output_rows)


def prepare_toxic_spans(
    *,
    comments_path: Path,
    annotations_path: Path,
    spans_path: Path,
    output_path: Path,
    download: bool = False,
) -> int:
    if download:
        download_file(DEFAULT_TOXIC_SPANS_COMMENTS_URL, comments_path)
        download_file(DEFAULT_TOXIC_SPANS_ANNOTATIONS_URL, annotations_path)
        download_file(DEFAULT_TOXIC_SPANS_SPANS_URL, spans_path)
    return normalize_toxic_spans(
        comments_path=comments_path,
        annotations_path=annotations_path,
        spans_path=spans_path,
        output_path=output_path,
    )


def normalize_convabuse(raw_path: Path, output_path: Path) -> int:
    rows, fields = read_csv_rows(raw_path, delimiter=";")
    text_col = pick_column(fields, "Input.user")
    label_col = pick_column(fields, "is_abuse")
    id_col = optional_column(fields, "Input.conv_id", "AssignmentId")
    target_col = optional_column(fields, "target")
    category_cols = [
        column
        for column in [
            "ableism",
            "homoph",
            "intel",
            "racist",
            "sex_harassment",
            "sexism",
            "trans",
        ]
        if column in fields
    ]

    output_rows = []
    for index, row in enumerate(rows):
        categories = [column for column in category_cols if as_bool(row.get(column, ""))]
        label = "abuse" if as_bool(row.get(label_col, "")) else "not_abuse"
        output_rows.append(
            common_row(
                row_id=row.get(id_col, "") if id_col else str(index),
                text=row.get(text_col, ""),
                label=label,
                source="convabuse",
                split="all",
                target=row.get(target_col, "") if target_col else "",
                type_=compact_list(categories),
                platform="conversational_ai",
                target_categories=compact_list(categories),
                meta={
                    "source_label": row.get(label_col, ""),
                    "direction": row.get("direction", ""),
                },
            )
        )
    return write_common_rows(output_path, output_rows)


def convabuse_vote_label(votes: Counter[str]) -> str:
    abuse_votes = votes["-1"] + votes["-2"] + votes["-3"]
    not_abuse_votes = votes["1"]
    ambiguous_votes = votes["0"]
    if abuse_votes > max(not_abuse_votes, ambiguous_votes):
        return "abuse"
    if ambiguous_votes > max(abuse_votes, not_abuse_votes):
        return "ambiguous_abuse"
    return "not_abuse"


def normalize_convabuse_splits(
    *,
    split_paths: dict[str, Path],
    output_path: Path,
) -> int:
    output_rows = []
    abuse_suffixes = ["1", "0", "-1", "-2", "-3"]
    type_suffixes = [
        "ableist",
        "homophobic",
        "intellectual",
        "racist",
        "sexist",
        "sex_harassment",
        "transphobic",
    ]
    target_suffixes = ["target.generalised", "target.individual", "target.system"]
    directness_suffixes = ["explicit", "implicit"]

    for split, path in split_paths.items():
        rows, fields = read_csv_rows(path)
        id_col = pick_column(fields, "example_id")
        conv_col = optional_column(fields, "conv_id")
        text_col = pick_column(fields, "user")
        bot_col = optional_column(fields, "bot")
        for row in rows:
            votes: Counter[str] = Counter()
            types: set[str] = set()
            targets: set[str] = set()
            directness: set[str] = set()
            for column in fields:
                for suffix in abuse_suffixes:
                    if column.endswith(f"_is_abuse.{suffix}") and as_bool(row.get(column, "")):
                        votes[suffix] += 1
                for suffix in type_suffixes:
                    if column.endswith(f"_{suffix}") and as_bool(row.get(column, "")):
                        types.add(suffix)
                for suffix in target_suffixes:
                    if column.endswith(f"_{suffix}") and as_bool(row.get(column, "")):
                        targets.add(suffix.removeprefix("target."))
                for suffix in directness_suffixes:
                    if column.endswith(f"_{suffix}") and as_bool(row.get(column, "")):
                        directness.add(suffix)
            output_rows.append(
                common_row(
                    row_id=row.get(id_col, ""),
                    text=row.get(text_col, ""),
                    label=convabuse_vote_label(votes),
                    source="convabuse",
                    split=split,
                    target=compact_list(targets),
                    type_=compact_list(types),
                    platform="conversational_ai",
                    source_id=row.get(id_col, ""),
                    target_categories=compact_list([*types, *targets]),
                    meta={
                        "conv_id": row.get(conv_col, "") if conv_col else "",
                        "bot": row.get(bot_col, "") if bot_col else "",
                        "abuse_vote_counts": dict(votes),
                        "directness": compact_list(directness),
                    },
                )
            )
    return write_common_rows(output_path, output_rows)


def prepare_convabuse(
    *,
    raw_path: Path | None = None,
    split_paths: dict[str, Path] | None = None,
    output_path: Path,
    download: bool = False,
    url: str = DEFAULT_CONVABUSE_URL,
    split_urls: dict[str, str] | None = None,
) -> int:
    if split_paths is not None:
        if download:
            for split, split_url in (split_urls or DEFAULT_CONVABUSE_SPLIT_URLS).items():
                download_file(split_url, split_paths[split])
        return normalize_convabuse_splits(split_paths=split_paths, output_path=output_path)
    if raw_path is None:
        raise ValueError("raw_path or split_paths is required for ConvAbuse")
    if download:
        download_file(url, raw_path)
    return normalize_convabuse(raw_path, output_path)


def normalize_davidson(raw_path: Path, output_path: Path) -> int:
    rows, fields = read_csv_rows(raw_path)
    text_col = pick_column(fields, "tweet")
    class_col = pick_column(fields, "class")
    index_col = optional_column(fields, "", "index")
    label_map = {"0": "hate", "1": "offensive", "2": "not_hate"}

    output_rows = []
    for index, row in enumerate(rows):
        source_label = str(row.get(class_col, "")).strip()
        output_rows.append(
            common_row(
                row_id=row.get(index_col, "") if index_col else str(index),
                text=row.get(text_col, ""),
                label=label_map.get(source_label, source_label),
                source="davidson",
                split="all",
                target="",
                type_=label_map.get(source_label, source_label),
                platform="twitter",
                meta={
                    "source_label": source_label,
                    "hate_speech_votes": row.get("hate_speech", ""),
                    "offensive_language_votes": row.get("offensive_language", ""),
                    "neither_votes": row.get("neither", ""),
                },
            )
        )
    return write_common_rows(output_path, output_rows)


def prepare_davidson(
    *,
    raw_path: Path,
    output_path: Path,
    download: bool = False,
    url: str = DEFAULT_DAVIDSON_URL,
) -> int:
    if download:
        download_file(url, raw_path)
    return normalize_davidson(raw_path, output_path)


def measuring_hate_speech_rows(
    *,
    dataset: str = DEFAULT_MEASURING_HATE_SPEECH_DATASET,
    config: str = "default",
    split: str = "train",
    page_size: int = 100,
    max_rows: int | None = None,
    request_delay: float = 0.1,
    max_retries: int = 8,
) -> Iterable[dict[str, Any]]:
    base_url = "https://datasets-server.huggingface.co/rows"
    offset = 0
    seen = 0
    while True:
        length = page_size
        if max_rows is not None:
            remaining = max_rows - seen
            if remaining <= 0:
                return
            length = min(length, remaining)
        query = urllib.parse.urlencode(
            {
                "dataset": dataset,
                "config": config,
                "split": split,
                "offset": offset,
                "length": length,
            }
        )
        url = f"{base_url}?{query}"
        for attempt in range(max_retries + 1):
            try:
                with urllib.request.urlopen(url, timeout=120) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt >= max_retries:
                    raise
                retry_after = exc.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    sleep_seconds = float(retry_after)
                else:
                    sleep_seconds = min(30.0, 2.0 * (attempt + 1))
                time.sleep(sleep_seconds)
        row_items = payload.get("rows", [])
        if not row_items:
            return
        for item in row_items:
            yield item.get("row", {})
            seen += 1
        offset += len(row_items)
        total = payload.get("num_rows_total")
        if total is not None and offset >= int(total):
            return
        if request_delay > 0:
            time.sleep(request_delay)


def measuring_hate_speech_parquet_records(parquet_path: Path) -> Iterable[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
        raise ValueError(
            "pyarrow is required to read Measuring Hate Speech parquet files; "
            "install with `python -m pip install '.[data-prep]'`"
        ) from exc

    table = pq.read_table(parquet_path)
    for row in table.to_pylist():
        yield row


def normalize_measuring_hate_speech_records(
    records: Iterable[dict[str, Any]],
    output_path: Path,
) -> int:
    aggregates: dict[str, dict[str, Any]] = {}
    for row in records:
        comment_id = str(row.get("comment_id", "")).strip()
        text = str(row.get("text", ""))
        if not comment_id or not text:
            continue
        aggregate = aggregates.setdefault(
            comment_id,
            {
                "text": text,
                "platform": row.get("platform", ""),
                "count": 0,
                "scores": defaultdict(float),
                "score_counts": defaultdict(int),
                "targets": set(),
            },
        )
        aggregate["count"] += 1
        for column in MEASURING_SCORE_COLUMNS:
            value = as_float(row.get(column))
            if value is not None:
                aggregate["scores"][column] += value
                aggregate["score_counts"][column] += 1
        for column, value in row.items():
            if column.startswith("target_") and as_bool(value):
                aggregate["targets"].add(column.removeprefix("target_"))

    output_rows = []
    for comment_id, aggregate in aggregates.items():
        means = {
            column: aggregate["scores"][column] / aggregate["score_counts"][column]
            for column in MEASURING_SCORE_COLUMNS
            if aggregate["score_counts"][column]
        }
        hate_score = means.get("hate_speech_score")
        hatespeech = means.get("hatespeech")
        if hate_score is not None and hate_score > 0.5:
            label = "hate"
        elif hatespeech is not None and hatespeech >= 1.5:
            label = "hate"
        elif hatespeech is not None and hatespeech >= 0.5:
            label = "ambiguous"
        else:
            label = "not_hate"
        harm_scores = {
            column: round(means[column], 6)
            for column in MEASURING_SCORE_COLUMNS
            if column in means and column != "hate_speech_score"
        }
        output_rows.append(
            common_row(
                row_id=comment_id,
                text=aggregate["text"],
                label=label,
                source="measuring_hate_speech",
                split="train",
                target=compact_list(aggregate["targets"]),
                type_="severity_score",
                platform=str(aggregate["platform"]),
                severity=format_float(hate_score),
                target_categories=compact_list(aggregate["targets"]),
                meta={
                    "annotation_rows": aggregate["count"],
                    "harm_scores": harm_scores,
                    "label_policy": "hate_speech_score>0.5_or_mean_hatespeech>=1.5",
                },
            )
        )
    return write_common_rows(output_path, output_rows)


def normalize_measuring_hate_speech_csv(raw_path: Path, output_path: Path) -> int:
    rows, _fields = read_csv_rows(raw_path)
    return normalize_measuring_hate_speech_records(rows, output_path)


def export_measuring_hate_speech_csv_with_npx(output_path: Path) -> bool:
    if shutil.which("npx") is None:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path = str(output_path.resolve()).replace("'", "''")
    sql = f"COPY (SELECT * FROM data) TO '{sql_path}' (FORMAT CSV, HEADER, DELIMITER ',')"
    command = [
        "npx",
        "-y",
        "-p",
        "parquetlens",
        "-p",
        "@parquetlens/sql",
        "parquetlens",
        DEFAULT_MEASURING_HATE_SPEECH_PARQUET_ALIAS,
        "--sql",
        sql,
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return output_path.exists()


def prepare_measuring_hate_speech(
    *,
    output_path: Path,
    csv_path: Path | None = None,
    parquet_path: Path | None = None,
    dataset: str = DEFAULT_MEASURING_HATE_SPEECH_DATASET,
    config: str = "default",
    split: str = "train",
    page_size: int = 100,
    max_rows: int | None = None,
    request_delay: float = 0.1,
) -> int:
    if csv_path is not None and csv_path.exists() and max_rows is None:
        return normalize_measuring_hate_speech_csv(csv_path, output_path)
    if parquet_path is not None and parquet_path.exists() and max_rows is None:
        return normalize_measuring_hate_speech_records(
            measuring_hate_speech_parquet_records(parquet_path),
            output_path,
        )
    return normalize_measuring_hate_speech_records(
        measuring_hate_speech_rows(
            dataset=dataset,
            config=config,
            split=split,
            page_size=page_size,
            max_rows=max_rows,
            request_delay=request_delay,
        ),
        output_path,
    )


def merge_normalized_datasets(
    input_paths: Iterable[Path],
    output_path: Path,
    *,
    prefix_ids: bool = True,
) -> int:
    merged_rows = []
    seen_ids: Counter[str] = Counter()
    for path in input_paths:
        rows, fields = read_csv_rows(path)
        missing = [field for field in COMMON_DATASET_FIELDNAMES if field not in fields]
        if missing:
            raise ValueError(f"{path}: missing normalized field(s): {', '.join(missing)}")
        for row in rows:
            merged = {field: row.get(field, "") for field in COMMON_DATASET_FIELDNAMES}
            if prefix_ids:
                local_id = merged["id"]
                merged["source_id"] = merged.get("source_id") or local_id
                merged["id"] = f"{merged['source']}:{local_id}"
            seen_ids[merged["id"]] += 1
            if seen_ids[merged["id"]] > 1:
                merged["id"] = f"{merged['id']}:{seen_ids[merged['id']]}"
            merged_rows.append(merged)
    return write_common_rows(output_path, merged_rows)


def recommended_paths(output_dir: Path, raw_dir: Path) -> dict[str, Any]:
    return {
        "dynahate": {
            "raw": raw_dir / "dynahate_raw.csv",
            "output": output_dir / "dynahate.csv",
        },
        "hatecheck": {
            "raw": raw_dir / "hatecheck_all_cases.csv",
            "output": output_dir / "hatecheck.csv",
        },
        "hatemoji": {
            "check": raw_dir / "hatemoji_check_test.csv",
            "build": {
                "train": raw_dir / "hatemoji_build_train.csv",
                "validation": raw_dir / "hatemoji_build_validation.csv",
                "test": raw_dir / "hatemoji_build_test.csv",
            },
            "output": output_dir / "hatemoji.csv",
        },
        "measuring_hate_speech": {
            "raw_csv": raw_dir / "measuring_hate_speech_raw.csv",
            "raw": raw_dir / "measuring_hate_speech.parquet",
            "output": output_dir / "measuring_hate_speech.csv",
        },
        "hatexplain": {
            "dataset": raw_dir / "hatexplain_dataset.json",
            "splits": raw_dir / "hatexplain_post_id_divisions.json",
            "output": output_dir / "hatexplain.csv",
        },
        "toxic_spans": {
            "comments": raw_dir / "toxic_spans_comments.csv",
            "annotations": raw_dir / "toxic_spans_annotations.csv",
            "spans": raw_dir / "toxic_spans_spans.csv",
            "output": output_dir / "toxic_spans.csv",
        },
        "convabuse": {
            "raw": raw_dir / "convabuse.csv",
            "splits": {
                "train": raw_dir / "convabuse_train.csv",
                "validation": raw_dir / "convabuse_validation.csv",
                "test": raw_dir / "convabuse_test.csv",
            },
            "output": output_dir / "convabuse.csv",
        },
        "davidson": {
            "raw": raw_dir / "davidson_labeled_data.csv",
            "output": output_dir / "davidson.csv",
        },
    }


def prepare_recommended_datasets(
    *,
    output_dir: Path,
    raw_dir: Path,
    merged_output: Path,
    datasets: list[str] | None = None,
    download: bool = True,
    measuring_max_rows: int | None = None,
    measuring_page_size: int = 100,
    measuring_request_delay: float = 0.1,
) -> dict[str, Any]:
    selected = datasets or list(DEFAULT_RECOMMENDED_DATASETS)
    unknown = [dataset for dataset in selected if dataset not in DEFAULT_RECOMMENDED_DATASETS]
    if unknown:
        raise ValueError(f"unknown dataset(s): {', '.join(unknown)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    paths = recommended_paths(output_dir, raw_dir)

    results: dict[str, Any] = {
        "artifact_type": "recommended_public_dataset_bundle",
        "download": download,
        "datasets": {},
        "merged_output": str(merged_output),
    }
    normalized_paths: list[Path] = []

    for name in selected:
        info = paths[name]
        if name == "dynahate":
            count = prepare_dynahate(
                raw_path=info["raw"],
                output_path=info["output"],
                download=download,
            )
        elif name == "hatecheck":
            count = prepare_hatecheck(
                raw_path=info["raw"],
                output_path=info["output"],
                download=download,
            )
        elif name == "hatemoji":
            count = prepare_hatemoji(
                check_path=info["check"],
                build_paths=info["build"],
                output_path=info["output"],
                download=download,
            )
        elif name == "measuring_hate_speech":
            if (
                download
                and measuring_max_rows is None
                and not info["raw_csv"].exists()
                and export_measuring_hate_speech_csv_with_npx(info["raw_csv"])
            ):
                pass
            elif download and not info["raw_csv"].exists():
                download_file(DEFAULT_MEASURING_HATE_SPEECH_PARQUET_URL, info["raw"])
            count = prepare_measuring_hate_speech(
                output_path=info["output"],
                csv_path=info["raw_csv"],
                parquet_path=info["raw"],
                max_rows=measuring_max_rows,
                page_size=measuring_page_size,
                request_delay=measuring_request_delay,
            )
        elif name == "hatexplain":
            count = prepare_hatexplain(
                dataset_path=info["dataset"],
                splits_path=info["splits"],
                output_path=info["output"],
                download=download,
            )
        elif name == "toxic_spans":
            count = prepare_toxic_spans(
                comments_path=info["comments"],
                annotations_path=info["annotations"],
                spans_path=info["spans"],
                output_path=info["output"],
                download=download,
            )
        elif name == "convabuse":
            count = prepare_convabuse(
                split_paths=info["splits"],
                output_path=info["output"],
                download=download,
            )
        elif name == "davidson":
            count = prepare_davidson(
                raw_path=info["raw"],
                output_path=info["output"],
                download=download,
            )
        else:  # pragma: no cover - guarded above
            raise ValueError(name)
        normalized_paths.append(info["output"])
        results["datasets"][name] = {
            "output": str(info["output"]),
            "row_count": count,
        }

    merged_count = merge_normalized_datasets(normalized_paths, merged_output)
    results["merged_row_count"] = merged_count
    results["fieldnames"] = COMMON_DATASET_FIELDNAMES
    return results


def add_prepare_dynahate_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "prepare-dynahate",
        help="Download and normalize the public Dynahate dataset.",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("data/public_dev/raw/dynahate_raw.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/public_dev/dynahate.csv"),
    )
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--url", default=DEFAULT_DYNAHATE_URL)


def add_prepare_recommended_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "prepare-recommended-datasets",
        help="Download, normalize, and merge the recommended public dev datasets.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/public_dev"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/public_dev/raw"))
    parser.add_argument(
        "--merged-output",
        type=Path,
        default=Path("data/public_dev/recommended_merged.csv"),
    )
    parser.add_argument(
        "--dataset",
        dest="datasets",
        action="append",
        choices=DEFAULT_RECOMMENDED_DATASETS,
        help="Dataset to include. Repeatable. Defaults to all recommended datasets.",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Normalize existing raw files instead of downloading first.",
    )
    parser.add_argument(
        "--measuring-max-rows",
        type=int,
        help="Limit rows fetched from Measuring Hate Speech for smoke tests.",
    )
    parser.add_argument("--measuring-page-size", type=int, default=100)
    parser.add_argument("--measuring-request-delay", type=float, default=0.1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download and normalize Dynahate.")
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("data/public_dev/raw/dynahate_raw.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/public_dev/dynahate.csv"),
    )
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--url", default=DEFAULT_DYNAHATE_URL)
    args = parser.parse_args(argv)
    try:
        count = prepare_dynahate(
            raw_path=args.raw,
            output_path=args.output,
            download=args.download,
            url=args.url,
        )
        print(f"Wrote {count} normalized row(s) to {args.output}")
        return 0
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
