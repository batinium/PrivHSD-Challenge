import pytest

from contextsafe_hsd.metrics import (
    aggregate_metrics,
    cleanup_high_confidence_residuals,
    row_metric,
    row_metric_fast,
)


def test_row_metric_reports_placeholder_density_residuals_and_quasi_flags():
    original = (
        "My name is Alex Vale from Berlin on Jan 4, 2024. "
        "Email alex@example.test and call +1 202 555 0188."
    )
    privatized = (
        "My name is [PERSON] from [LOCATION] on [DATE]. "
        "Email [EMAIL] and call [PHONE]."
    )

    metrics = row_metric(original, privatized)

    assert metrics["placeholder_count"] == 5
    assert metrics["placeholder_counts_by_type"] == {
        "DATE": 1,
        "EMAIL": 1,
        "LOCATION": 1,
        "PERSON": 1,
        "PHONE": 1,
    }
    assert metrics["placeholder_density"] > 0
    assert metrics["mask_density"] > 0
    assert metrics["residual_identifier_count"] == 0
    assert metrics["direct_identifier_count_before"] >= 2
    assert metrics["direct_identifier_count_after"] == 0
    assert metrics["quasi_identifier_count_before"] >= 2
    assert metrics["quasi_identifier_count_after"] == 0
    assert metrics["quasi_identifier_flags"]["before"]["DATE"] is True
    assert metrics["quasi_identifier_flags"]["before"]["LOCATION"] is True
    assert metrics["quasi_identifier_flags"]["after"]["DATE"] is False
    assert metrics["quasi_identifier_flags"]["after"]["LOCATION"] is False


def test_row_metric_target_cue_retention_counts_category_placeholders():
    original = "Muslims and refugees should leave."
    privatized = (
        "[TARGET_GROUP:religion] and "
        "[TARGET_GROUP:nationality_or_origin] should leave."
    )

    metrics = row_metric(original, privatized)

    assert metrics["target_cue_count_before"] == 2
    assert metrics["target_cue_count_after"] == 2
    assert metrics["target_cue_retention"] == 1.0
    assert metrics["target_term_count_before"] == 2
    assert metrics["target_term_count_after"] == 0
    assert metrics["target_term_retention"] == 0.0
    assert metrics["target_categories_before"] == [
        "nationality_or_origin",
        "religion",
    ]
    assert metrics["target_categories_after"] == [
        "nationality_or_origin",
        "religion",
    ]
    assert metrics["target_category_retention"] == 1.0
    assert "target_cue_loss" not in metrics["overmasking_warnings"]


def test_row_metric_warns_for_residual_identifiers_and_overmasking():
    original = "Email alex@example.test and meet in Berlin."
    privatized = (
        "Email alex@example.test [PERSON] [LOCATION] [DATE] [PHONE] [USER]."
    )

    metrics = row_metric(original, privatized)

    assert metrics["residual_identifier_count"] >= 1
    assert "residual_identifier_detected" in metrics["privacy_warnings"]
    assert "residual_direct_identifier_detected" in metrics["privacy_warnings"]
    assert "high_placeholder_density" in metrics["overmasking_warnings"]
    assert "low_character_utility_retention" in metrics["overmasking_warnings"]
    assert "residual_identifier_detected" in metrics["warnings"]


def test_high_confidence_residual_cleanup_masks_direct_identifiers_only():
    privatized = (
        "Email alex@example.test call +1 202 555 0100 visit "
        "https://example.test/post @alex 192.0.2.44 case#ABC123 "
        "alex [at] example dot test hxxps://bad.example/path @t "
        "near london library and Alex."
    )

    cleanup = cleanup_high_confidence_residuals(privatized)
    metrics = row_metric("original text", privatized)
    aggregate = aggregate_metrics([metrics])

    assert cleanup["changed"] is True
    assert cleanup["cleanup_count"] == 9
    assert cleanup["counts_by_entity_type"] == {
        "EMAIL": 2,
        "IDENTIFIER": 1,
        "IP_ADDRESS": 1,
        "PHONE": 1,
        "URL": 2,
        "USER": 2,
    }
    assert "alex@example.test" not in cleanup["text"]
    assert "+1 202 555 0100" not in cleanup["text"]
    assert "https://example.test/post" not in cleanup["text"]
    assert "@alex" not in cleanup["text"]
    assert "192.0.2.44" not in cleanup["text"]
    assert "case#ABC123" not in cleanup["text"]
    assert "alex [at] example dot test" not in cleanup["text"]
    assert "hxxps://bad.example/path" not in cleanup["text"]
    assert "@t" not in cleanup["text"]
    assert "london library" in cleanup["text"]
    assert "Alex" in cleanup["text"]
    assert metrics["residual_high_confidence_direct_identifier_count"] == 9
    assert aggregate["residual_high_confidence_direct_identifier_count"] == 9


def test_aggregate_metrics_rolls_up_new_fields():
    rows = [
        row_metric(
            "@alex emailed alex@example.test about Muslims.",
            "[USER] emailed [EMAIL] about Muslims.",
        ),
        row_metric(
            "My name is Alex Vale from Berlin.",
            "My name is Alex Vale from Berlin.",
        ),
    ]

    metrics = aggregate_metrics(rows)

    assert metrics["row_count"] == 2
    assert metrics["placeholder_count_total"] == 2
    assert metrics["placeholder_counts_by_type"] == {"EMAIL": 1, "USER": 1}
    assert metrics["residual_identifier_count"] >= 2
    assert metrics["direct_identifier_counts"]["before"] >= 3
    assert metrics["quasi_identifier_counts"]["before"] >= 1
    assert metrics["target_cue_counts"]["before"] == 1
    assert metrics["target_cue_counts"]["after"] == 1
    assert metrics["target_cue_retention_mean"] == 1.0
    assert metrics["privacy_warning_counts"]["residual_identifier_detected"] == 1
    assert metrics["rows_with_warnings"] == 1


def test_fast_metric_avoids_deep_target_scan(monkeypatch):
    def fail_deep_scan(_text):
        raise AssertionError("deep target scan should not run")

    monkeypatch.setattr("contextsafe_hsd.metrics.target_term_spans", fail_deep_scan)

    metrics = row_metric_fast("Muslims should leave.", "Muslims should leave.")

    assert metrics["metric_depth"] == "fast"
    assert metrics["target_cue_count_before"] == 1
    with pytest.raises(AssertionError, match="deep target scan"):
        row_metric("Muslims should leave.", "Muslims should leave.")
