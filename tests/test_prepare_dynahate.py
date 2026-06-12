import csv
import json

from privhsd.datasets import (
    COMMON_DATASET_FIELDNAMES,
    canonical_tweet_eval_label,
    merge_normalized_datasets,
    normalize_convabuse,
    normalize_dynahate,
    normalize_hatecheck,
    normalize_hatemoji,
    normalize_hatexplain,
    normalize_measuring_hate_speech_records,
    normalize_toxic_spans,
)


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fieldnames, rows, delimiter=","):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def test_canonical_tweet_eval_label_maps_non_hate_to_not_hate():
    assert canonical_tweet_eval_label("hate", "non-hate") == "not_hate"
    assert canonical_tweet_eval_label("offensive", "non-offensive") == "not_hate"
    assert canonical_tweet_eval_label("offensive", "offensive") == "offensive"


def test_normalize_dynahate_shape(tmp_path):
    raw = tmp_path / "raw.csv"
    out = tmp_path / "normalized.csv"
    write_csv(
        raw,
        ["acl.id", "Text", "Label", "Split", "Target", "Type"],
        [
            {
                "acl.id": "abc",
                "Text": "sample text",
                "Label": "nothate",
                "Split": "train",
                "Target": "none",
                "Type": "none",
            }
        ],
    )

    count = normalize_dynahate(raw, out)

    assert count == 1
    rows = read_rows(out)
    assert rows[0]["id"] == "abc"
    assert rows[0]["text"] == "sample text"
    assert rows[0]["label"] == "not_hate"
    assert rows[0]["source"] == "dynahate"
    assert rows[0]["split"] == "train"
    assert rows[0]["target"] == "none"
    assert rows[0]["type"] == "none"
    assert rows[0]["platform"] == "synthetic"
    assert list(rows[0]) == COMMON_DATASET_FIELDNAMES


def test_normalize_dynahate_lowercase_shape(tmp_path):
    raw = tmp_path / "raw.csv"
    out = tmp_path / "normalized.csv"
    write_csv(
        raw,
        ["", "acl.id", "text", "label", "split", "target", "type"],
        [
            {
                "": "1",
                "acl.id": "acl1",
                "text": "sample text",
                "label": "hate",
                "split": "test",
                "target": "none",
                "type": "none",
            }
        ],
    )

    count = normalize_dynahate(raw, out)

    assert count == 1
    rows = read_rows(out)
    assert rows[0]["id"] == "acl1"
    assert rows[0]["text"] == "sample text"
    assert rows[0]["label"] == "hate"
    assert rows[0]["split"] == "test"


def test_normalize_hatecheck(tmp_path):
    raw = tmp_path / "hatecheck.csv"
    out = tmp_path / "normalized.csv"
    write_csv(
        raw,
        ["case_id", "test_case", "label_gold", "target_ident", "functionality"],
        [
            {
                "case_id": "hc1",
                "test_case": "sample text",
                "label_gold": "non-hateful",
                "target_ident": "target group",
                "functionality": "contrast",
            }
        ],
    )

    assert normalize_hatecheck(raw, out) == 1
    row = read_rows(out)[0]
    assert row["source"] == "hatecheck"
    assert row["label"] == "not_hate"
    assert row["target"] == "target group"
    assert row["type"] == "contrast"


def test_normalize_hatemoji_combines_check_and_build(tmp_path):
    check = tmp_path / "check.csv"
    train = tmp_path / "train.csv"
    out = tmp_path / "hatemoji.csv"
    write_csv(
        check,
        ["case_id", "text", "target", "functionality", "set", "label_gold"],
        [
            {
                "case_id": "case1",
                "text": "sample text",
                "target": "target",
                "functionality": "emoji",
                "set": "check",
                "label_gold": "hateful",
            }
        ],
    )
    write_csv(
        train,
        ["entry_id", "text", "type", "target", "split", "label_gold"],
        [
            {
                "entry_id": "entry1",
                "text": "sample text two",
                "type": "emoji",
                "target": "target",
                "split": "train",
                "label_gold": "non-hateful",
            }
        ],
    )

    assert normalize_hatemoji(check_path=check, build_paths={"train": train}, output_path=out) == 2
    rows = read_rows(out)
    assert [row["source"] for row in rows] == ["hatemoji_check", "hatemoji_build"]
    assert [row["label"] for row in rows] == ["hate", "not_hate"]


def test_normalize_hatexplain_majority_and_rationales(tmp_path):
    dataset = tmp_path / "dataset.json"
    splits = tmp_path / "splits.json"
    out = tmp_path / "hatexplain.csv"
    dataset.write_text(
        json.dumps(
            {
                "post1": {
                    "annotators": [
                        {"label": "normal", "target": ["None"]},
                        {"label": "hatespeech", "target": ["group"]},
                        {"label": "hatespeech", "target": ["group"]},
                    ],
                    "rationales": [[0, 1, 1, 0], [0, 0, 1, 1]],
                    "post_tokens": ["sample", "text", "with", "cue"],
                }
            }
        ),
        encoding="utf-8",
    )
    splits.write_text(json.dumps({"train": ["post1"]}), encoding="utf-8")

    assert normalize_hatexplain(dataset_path=dataset, splits_path=splits, output_path=out) == 1
    row = read_rows(out)[0]
    assert row["label"] == "hate"
    assert row["split"] == "train"
    assert row["target"] == "group"
    assert row["rationale_spans"] == "1-3"


def test_normalize_toxic_spans(tmp_path):
    comments = tmp_path / "comments.csv"
    annotations = tmp_path / "annotations.csv"
    spans = tmp_path / "spans.csv"
    out = tmp_path / "toxic_spans.csv"
    write_csv(comments, ["comment_id", "comment_text"], [{"comment_id": "c1", "comment_text": "sample text"}])
    write_csv(
        annotations,
        ["annotation", "comment_id", "worker", "country", "all toxic", "not toxic"],
        [
            {
                "annotation": "a1",
                "comment_id": "c1",
                "worker": "w1",
                "country": "US",
                "all toxic": "True",
                "not toxic": "False",
            }
        ],
    )
    write_csv(spans, ["annotation", "type", "start", "end"], [{"annotation": "a1", "type": "Insult", "start": "1", "end": "3"}])

    assert normalize_toxic_spans(comments_path=comments, annotations_path=annotations, spans_path=spans, output_path=out) == 1
    row = read_rows(out)[0]
    assert row["label"] == "toxic"
    assert row["type"] == "Insult"
    assert row["rationale_spans"] == "1-3"


def test_normalize_convabuse(tmp_path):
    raw = tmp_path / "convabuse.csv"
    out = tmp_path / "convabuse_normalized.csv"
    write_csv(
        raw,
        ["Input.conv_id", "Input.user", "is_abuse", "target", "sexism", "racist", "direction"],
        [
            {
                "Input.conv_id": "conv1",
                "Input.user": "sample text",
                "is_abuse": "1",
                "target": "person",
                "sexism": "1",
                "racist": "0",
                "direction": "explicit",
            }
        ],
        delimiter=";",
    )

    assert normalize_convabuse(raw, out) == 1
    row = read_rows(out)[0]
    assert row["label"] == "abuse"
    assert row["target_categories"] == "sexism"


def test_normalize_convabuse_splits(tmp_path):
    from privhsd.datasets import normalize_convabuse_splits

    train = tmp_path / "train.csv"
    out = tmp_path / "convabuse_splits.csv"
    write_csv(
        train,
        [
            "example_id",
            "conv_id",
            "user",
            "bot",
            "Annotator1_is_abuse.1",
            "Annotator1_is_abuse.-1",
            "Annotator1_sexist",
            "Annotator1_target.individual",
            "Annotator1_explicit",
        ],
        [
            {
                "example_id": "ex1",
                "conv_id": "conv1",
                "user": "sample text",
                "bot": "bot",
                "Annotator1_is_abuse.1": "0",
                "Annotator1_is_abuse.-1": "1",
                "Annotator1_sexist": "1",
                "Annotator1_target.individual": "1",
                "Annotator1_explicit": "1",
            }
        ],
    )

    assert normalize_convabuse_splits(split_paths={"train": train}, output_path=out) == 1
    row = read_rows(out)[0]
    assert row["label"] == "abuse"
    assert row["split"] == "train"
    assert row["target"] == "individual"
    assert row["type"] == "sexist"


def test_normalize_measuring_hate_speech_records_aggregates_by_comment(tmp_path):
    out = tmp_path / "measuring.csv"
    records = [
        {
            "comment_id": 1,
            "text": "sample text",
            "platform": 0,
            "hate_speech_score": 1.0,
            "hatespeech": 2.0,
            "insult": 1.0,
            "target_race": True,
        },
        {
            "comment_id": 1,
            "text": "sample text",
            "platform": 0,
            "hate_speech_score": 0.0,
            "hatespeech": 1.0,
            "insult": 2.0,
            "target_religion_muslim": True,
        },
    ]

    assert normalize_measuring_hate_speech_records(records, out) == 1
    row = read_rows(out)[0]
    assert row["id"] == "1"
    assert row["label"] == "hate"
    assert row["severity"] == "0.5"
    assert row["target_categories"] == "race;religion_muslim"
    assert json.loads(row["meta"])["annotation_rows"] == 2


def test_merge_normalized_datasets_prefixes_ids(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    merged = tmp_path / "merged.csv"
    write_csv(
        first,
        COMMON_DATASET_FIELDNAMES,
        [
            {
                "id": "1",
                "text": "a",
                "label": "hate",
                "source": "first",
                "split": "",
                "target": "",
                "type": "",
                "platform": "",
                "source_id": "",
                "severity": "",
                "target_categories": "",
                "rationale_spans": "",
                "meta": "",
            }
        ],
    )
    write_csv(
        second,
        COMMON_DATASET_FIELDNAMES,
        [
            {
                "id": "1",
                "text": "b",
                "label": "not_hate",
                "source": "second",
                "split": "",
                "target": "",
                "type": "",
                "platform": "",
                "source_id": "",
                "severity": "",
                "target_categories": "",
                "rationale_spans": "",
                "meta": "",
            }
        ],
    )

    assert merge_normalized_datasets([first, second], merged) == 2
    rows = read_rows(merged)
    assert [row["id"] for row in rows] == ["first:1", "second:1"]
    assert [row["source_id"] for row in rows] == ["1", "1"]
