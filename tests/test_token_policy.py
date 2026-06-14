import csv
from collections import Counter

import torch

from contextsafe_hsd.cli import build_parser
from contextsafe_hsd.token_actions import (
    ACTION_GENERALIZE,
    ACTION_KEEP,
    ACTION_MASK,
    ACTION_PROTECT_HSD,
    ACTION_PROTECT_TARGET,
)
from contextsafe_hsd.token_policy import (
    ACTION_REVIEW,
    IGNORE_INDEX,
    TOKEN_POLICY_LABEL_TO_ID,
    ActionSpan,
    align_labels_to_offsets,
    apply_policy_to_text,
    build_class_weights,
    choose_ensemble_action,
    grouped_kfold_indices_with_report,
    label_feature_report,
    model_input_for_row,
    sample_row_indices_with_report,
    split_indices_with_report,
    token_examples_for_row,
)


def test_train_token_policy_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "train-token-policy",
            "--input",
            "input.csv",
            "--text-col",
            "text",
        ]
    )

    assert args.command == "train-token-policy"
    assert args.model_name == "FacebookAI/roberta-base"
    assert args.sample_strategy == "source_label_round_robin"
    assert args.split_strategy == "grouped_text"
    assert args.fold_count == 0
    assert args.fold_index is None
    assert args.class_weighting == "capped_inverse_sqrt"


def test_prepare_tweet_eval_unseen_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "prepare-tweet-eval-unseen",
            "--output",
            "external.csv",
            "--config",
            "hate",
        ]
    )

    assert args.command == "prepare-tweet-eval-unseen"
    assert args.output.name == "external.csv"
    assert args.configs == ["hate"]


def test_evaluate_token_policy_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "evaluate-token-policy",
            "--input",
            "input.csv",
            "--text-col",
            "text",
            "--model-dir",
            "model",
        ]
    )

    assert args.command == "evaluate-token-policy"
    assert args.model_dir.name == "model"
    assert args.sample_size == 0


def test_evaluate_token_policy_ensemble_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "evaluate-token-policy-ensemble",
            "--input",
            "input.csv",
            "--text-col",
            "text",
            "--model-dir",
            "roberta",
            "--model-dir",
            "hatebert",
            "--model-weight",
            "1.0",
            "--model-weight",
            "1.2",
        ]
    )

    assert args.command == "evaluate-token-policy-ensemble"
    assert [path.name for path in args.model_dirs] == ["roberta", "hatebert"]
    assert args.model_weights == [1.0, 1.2]
    assert args.ensemble_mode == "mean_prob"


def test_predict_token_policy_ensemble_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "predict-token-policy-ensemble",
            "--input",
            "input.csv",
            "--text-col",
            "text",
            "--model-dir",
            "roberta",
            "--model-dir",
            "hatebert",
        ]
    )

    assert args.command == "predict-token-policy-ensemble"
    assert [path.name for path in args.model_dirs] == ["roberta", "hatebert"]


def test_choose_ensemble_action_uses_weighted_mean_probabilities():
    keep = TOKEN_POLICY_LABEL_TO_ID[ACTION_KEEP]
    target = TOKEN_POLICY_LABEL_TO_ID[ACTION_PROTECT_TARGET]
    first = [0.0] * len(TOKEN_POLICY_LABEL_TO_ID)
    second = [0.0] * len(TOKEN_POLICY_LABEL_TO_ID)
    first[keep] = 0.7
    first[target] = 0.3
    second[keep] = 0.2
    second[target] = 0.8

    action, confidence, covered_count = choose_ensemble_action(
        [(first, True), (second, True)],
        model_weights=[1.0, 2.0],
        mode="mean_prob",
    )

    assert action == ACTION_PROTECT_TARGET
    assert confidence > 0.6
    assert covered_count == 2


def test_weak_policy_distinguishes_self_disclosure_from_target():
    row = {
        "id": "1",
        "text": "I am Muslim and I hate refugees.",
        "label": "hate",
        "source": "dynahate",
        "target": "religion;nationality_or_origin",
        "target_categories": "religion;nationality_or_origin",
        "rationale_spans": "",
    }

    labels = {
        example.token.lower(): example.action
        for example in token_examples_for_row(
            row,
            row_index=1,
            text_col="text",
            id_col="id",
            source_col="source",
            target_col="target",
            target_categories_col="target_categories",
            rationale_col="rationale_spans",
        )
    }

    assert labels["muslim"] == ACTION_REVIEW
    assert labels["hate"] == ACTION_PROTECT_HSD
    assert labels["refugees"] == ACTION_PROTECT_TARGET


def test_alignment_ignores_metadata_prefix_and_special_tokens():
    row = {
        "text": "Email Alex",
        "source": "dynahate",
        "label": "hate",
        "target": "none",
    }
    _, text_start = model_input_for_row(
        row,
        text_col="text",
        source_col="source",
        label_col="label",
        target_col="target",
        metadata_prefix=True,
    )
    labels = align_labels_to_offsets(
        [
            (0, 0),
            (1, max(1, text_start - 1)),
            (text_start, text_start + 5),
            (text_start + 6, text_start + 10),
        ],
        text_start=text_start,
        action_spans=[ActionSpan(0, 5, ACTION_MASK, "direct_identifier")],
    )

    assert labels[0] == IGNORE_INDEX
    assert labels[1] == IGNORE_INDEX
    assert labels[2] == TOKEN_POLICY_LABEL_TO_ID[ACTION_MASK]
    assert labels[3] == TOKEN_POLICY_LABEL_TO_ID[ACTION_KEEP]


def test_policy_application_does_not_mask_protected_targets():
    text = "Muslims should leave."

    candidate, audit = apply_policy_to_text(
        text,
        [{"start": 0, "end": 7, "action": ACTION_MASK, "confidence": 0.99}],
    )

    assert candidate == text
    assert audit["accepted"] is True
    assert audit["skipped_counts"]["protected_overlap"] == 1


def test_policy_application_still_masks_direct_identifiers():
    text = "Email alex@example.test because Muslims should leave."

    candidate, audit = apply_policy_to_text(text, [])

    assert "[EMAIL]" in candidate
    assert "Muslims" in candidate
    assert audit["accepted"] is True


def test_label_feature_report_writes_hashed_features_without_raw_text(tmp_path):
    source = tmp_path / "rows.csv"
    output = tmp_path / "features.json"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "text",
                "label",
                "source",
                "target",
                "target_categories",
                "rationale_spans",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "text": "Email alex@example.test because immigrants should leave!",
                "label": "hate",
                "source": "dynahate",
                "target": "nationality_or_origin",
                "target_categories": "nationality_or_origin",
                "rationale_spans": "",
            }
        )

    result = label_feature_report(
        source,
        text_col="text",
        id_col="id",
        source_col="source",
        label_col="label",
        target_col="target",
        target_categories_col="target_categories",
        rationale_col="rationale_spans",
        output_path=output,
        sample_size=0,
        top_features=10,
    )

    assert output.exists()
    assert result["top_features"]
    assert "feature_hash" in result["top_features"][0]
    assert "alex@example.test" not in output.read_text(encoding="utf-8")


def test_action_source_balanced_sampler_prioritizes_rare_actions():
    rows = [
        {
            "id": "1",
            "text": "Plain text only.",
            "source": "dynahate",
            "label": "not_hate",
            "target": "",
            "target_categories": "",
            "rationale_spans": "",
        },
        {
            "id": "2",
            "text": "I am Muslim and I hate refugees.",
            "source": "dynahate",
            "label": "hate",
            "target": "religion;nationality_or_origin",
            "target_categories": "religion;nationality_or_origin",
            "rationale_spans": "",
        },
        {
            "id": "3",
            "text": "Email alex@example.test now.",
            "source": "davidson",
            "label": "offensive",
            "target": "",
            "target_categories": "",
            "rationale_spans": "",
        },
        {
            "id": "4",
            "text": "I am from Boston.",
            "source": "measuring_hate_speech",
            "label": "ambiguous",
            "target": "",
            "target_categories": "",
            "rationale_spans": "",
        },
    ]

    indices, report = sample_row_indices_with_report(
        rows,
        sample_size=3,
        strategy="action_source_balanced",
        text_col="text",
        id_col="id",
        source_col="source",
        label_col="label",
        target_col="target",
        target_categories_col="target_categories",
        rationale_col="rationale_spans",
    )

    selected_ids = {rows[index]["id"] for index in indices}
    assert "2" in selected_ids
    assert "3" in selected_ids
    assert report["selected_action_row_counts"][ACTION_REVIEW] >= 1
    assert report["selected_action_row_counts"][ACTION_MASK] >= 1


def test_grouped_text_split_keeps_duplicates_on_one_side():
    rows = [
        {"text": "same text", "id": "1"},
        {"text": "same text", "id": "2"},
        {"text": "different text", "id": "3"},
        {"text": "another text", "id": "4"},
    ]

    train_indices, dev_indices, report = split_indices_with_report(
        rows,
        [0, 1, 2, 3],
        text_col="text",
        test_size=0.5,
        random_state=1,
        strategy="grouped_text",
    )

    assert train_indices
    assert dev_indices
    assert report["duplicate_group_overlap_count"] == 0
    duplicate_sides = {
        "train" if index in train_indices else "dev"
        for index in (0, 1)
    }
    assert len(duplicate_sides) == 1


def test_grouped_kfold_split_keeps_duplicates_on_one_side():
    rows = [
        {"text": "same text", "id": "1", "source": "a", "label": "x"},
        {"text": "same text", "id": "2", "source": "a", "label": "x"},
        {"text": "different text", "id": "3", "source": "b", "label": "y"},
        {"text": "another text", "id": "4", "source": "b", "label": "z"},
        {"text": "last text", "id": "5", "source": "c", "label": "z"},
    ]

    train_indices, dev_indices, report = grouped_kfold_indices_with_report(
        rows,
        [0, 1, 2, 3, 4],
        text_col="text",
        fold_count=3,
        fold_index=0,
        random_state=1,
        source_col="source",
        label_col="label",
    )

    assert train_indices
    assert dev_indices
    assert report["strategy"] == "grouped_text_kfold"
    assert report["fold_count"] == 3
    assert report["duplicate_group_overlap_count"] == 0
    duplicate_sides = {
        "train" if index in train_indices else "dev"
        for index in (0, 1)
    }
    assert len(duplicate_sides) == 1


def test_class_weights_boost_rare_actions_over_keep():
    weights = build_class_weights(
        torch,
        Counter(
            {
                ACTION_KEEP: 100,
                ACTION_MASK: 4,
                ACTION_GENERALIZE: 1,
            }
        ),
        mode="capped_inverse_sqrt",
        max_class_weight=6.0,
        device="cpu",
    )

    assert weights is not None
    assert weights[TOKEN_POLICY_LABEL_TO_ID[ACTION_KEEP]] == 1
    assert weights[TOKEN_POLICY_LABEL_TO_ID[ACTION_MASK]] > 1
    assert weights[TOKEN_POLICY_LABEL_TO_ID[ACTION_GENERALIZE]] == 6
