from collections import Counter
import csv
import importlib.util
from pathlib import Path
import random


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate_lm_studio_challenge_corpus.py"
)
SPEC = importlib.util.spec_from_file_location("generate_lm_studio_challenge_corpus", SCRIPT_PATH)
generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(generator)


def test_balance_counts_canonicalize_adjacent_training_labels(tmp_path):
    path = tmp_path / "training.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "label", "text"])
        writer.writeheader()
        for index, label in enumerate(
            [
                "not_hate",
                "not_hate",
                "not_hate",
                "not_abuse",
                "hate",
                "hate",
                "hate",
                "toxic",
                "abuse",
                "offensive",
                "ambiguous",
            ]
        ):
            writer.writerow({"id": str(index), "label": label, "text": "x"})

    counts = generator.read_balance_counts(
        path,
        label_col="label",
        label_mode="canonical",
    )

    assert counts["not_hate"] == 4
    assert counts["hate"] == 3
    assert counts["offensive"] == 3
    assert counts["ambiguous"] == 1


def test_balance_plan_targets_only_deficit_labels():
    plan, schedule = generator.build_balance_plan(
        Counter({"not_hate": 10, "hate": 8, "offensive": 4, "ambiguous": 1}),
        target_count=9,
        balance_to_count=None,
        min_deficit=1,
    )

    schedule_counts = Counter(schedule)
    assert plan["balance_target_count_per_label"] == 10
    assert plan["active_deficits"] == {"ambiguous": 9, "hate": 2, "offensive": 6}
    assert "not_hate" not in schedule_counts
    assert schedule_counts["ambiguous"] > schedule_counts["offensive"]
    assert schedule_counts["offensive"] > schedule_counts["hate"]
    assert sum(schedule_counts.values()) == 9


def test_validate_offsets_ignores_empty_sentinel_spans():
    valid, errors = generator.validate_offsets(
        "Alex posted from Boston.",
        [{"text": "none"}, {"text": ""}, {"text": "Boston"}],
    )

    assert errors == []
    assert [item["text"] for item in valid] == ["Boston"]


def test_requested_hate_label_keeps_protected_target_category():
    rng = random.Random(7)
    scenario = generator.choose_scenario(
        0,
        rng,
        target_labels=["hate"],
        label_cycle_size=1,
        label_index=len(generator.TARGET_CATEGORIES) - 1,
    )

    assert scenario["label_hint"] == "hate"
    assert scenario["requested_label"] == "hate"
    assert scenario["target_category"] != "none"
