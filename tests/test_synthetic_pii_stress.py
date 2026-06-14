import csv
import json
from pathlib import Path

from contextsafe_hsd.ablation import ABLATION_VARIANTS, run_ablation
from contextsafe_hsd.csv_pipeline import evaluate_csv, process_csv


FIXTURE = Path("tests/fixtures/synthetic_pii_stress.csv")
RESIDUAL_FIXTURE = Path("tests/fixtures/synthetic_pii_residual_metrics.csv")


def read_csv_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_synthetic_pii_fixture_masks_expected_fields_and_preserves_rows(tmp_path):
    output = tmp_path / "synthetic.privatized.csv"
    audit = tmp_path / "synthetic.audit.json"
    original_rows = read_csv_rows(FIXTURE)

    summary = process_csv(
        FIXTURE,
        output,
        text_col="text",
        id_col="id",
        audit_path=audit,
        mode="balanced",
    )

    rows = read_csv_rows(output)
    assert [row["id"] for row in rows] == [row["id"] for row in original_rows]
    assert [row["label"] for row in rows] == [row["label"] for row in original_rows]
    assert [row["source"] for row in rows] == [row["source"] for row in original_rows]
    assert [row["split"] for row in rows] == [row["split"] for row in original_rows]
    assert [row["case_type"] for row in rows] == [
        row["case_type"] for row in original_rows
    ]
    assert summary["metrics"]["row_count"] == len(original_rows)
    assert summary["metrics"]["direct_identifier_counts"]["after"] == 0

    by_id = {row["id"]: row["privatized_text"] for row in rows}
    expected_placeholders = {
        "S001": ["[PERSON]", "[USER]", "[EMAIL]", "[DATE]"],
        "S002": ["[PERSON]", "[PHONE]", "[URL]"],
        "S003": ["[LOCATION]", "[PERSON]", "[ID]", "[DATE]"],
        "S004": ["[ID]", "[ORG]", "[ALIAS]"],
        "S005": ["[ALIAS]", "[PERSON]", "[LOCATION]"],
        "S006": ["[ID]", "[PERSON]", "[AGE]", "[LOCATION]", "[ORG]"],
        "S007": ["[ID]", "[USER]", "[URL]"],
        "S008": ["[PERSON]", "[LOCATION]", "[AGE]", "[ORG]", "[ID]"],
    }
    for row_id, placeholders in expected_placeholders.items():
        for placeholder in placeholders:
            assert placeholder in by_id[row_id]

    absent_values = {
        "S001": ["Alex Vale", "@alex.v-77", "alex.vale+tip@example.test", "Jan 4, 2024"],
        "S002": ["Bri Stone", "+1 (202) 555-0188", "https://bri-stone.example.test/profile"],
        "S003": ["East Ridge", "Dana Kole", "192.0.2.44", "River City", "03/12/2025"],
        "S004": ["ID-STU-7781", "Northbridge University", "Night_Owl77"],
        "S005": ["CampusTruth", "Morgan Hale", "Lake Town"],
        "S006": ["ref-ZX5519", "Riley Hart", "aged 31", "Silver City", "Central Academy"],
        "S007": ["user-QA990", "@qa--team", "www.qa-example.test"],
        "S008": ["Mira Stone", "Harbor Point", "age 29", "West Park School", "case#ABC123"],
    }
    for row_id, values in absent_values.items():
        for value in values:
            assert value not in by_id[row_id]

    assert "refugees" in by_id["S001"]
    assert "women" in by_id["S002"]
    assert "immigrants" in by_id["S005"]
    assert "black people" in by_id["S007"]

    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    assert [row["row_id"] for row in audit_data["rows"]] == [
        row["id"] for row in original_rows
    ]
    transformed_types = summary["metrics"]["transformed_entity_counts"]
    assert transformed_types["ALIAS"] == 2
    assert transformed_types["EMAIL"] == 1
    assert transformed_types["PHONE"] == 1
    assert transformed_types["URL"] == 2
    assert transformed_types["IP_ADDRESS"] == 1
    assert transformed_types["ORGANIZATION"] >= 3


def test_synthetic_residual_fixture_reports_privacy_warnings():
    result = evaluate_csv(
        RESIDUAL_FIXTURE,
        text_col="text",
        privatized_col="privatized_text",
    )

    metrics = result["metrics"]
    assert metrics["row_count"] == 2
    assert metrics["residual_identifier_count"] >= 3
    assert metrics["residual_direct_identifier_count"] >= 2
    assert metrics["residual_quasi_identifier_count"] >= 1
    assert metrics["privacy_warning_counts"]["residual_identifier_detected"] == 2
    assert metrics["privacy_warning_counts"]["residual_direct_identifier_detected"] == 2
    assert metrics["rows_with_privacy_warnings"] == 2


def test_ablation_runs_on_synthetic_pii_fixture(tmp_path):
    report_path = tmp_path / "synthetic.ablation.json"
    output_dir = tmp_path / "variants"
    original_rows = read_csv_rows(FIXTURE)

    result = run_ablation(
        FIXTURE,
        text_col="text",
        id_col="id",
        output_path=report_path,
        output_dir=output_dir,
    )

    expected_variants = [variant.name for variant in ABLATION_VARIANTS]
    assert [variant["name"] for variant in result["variants"]] == expected_variants
    assert set(result["results"]) == set(expected_variants)

    identity_rows = read_csv_rows(output_dir / "synthetic_pii_stress.identity.csv")
    balanced_rows = read_csv_rows(output_dir / "synthetic_pii_stress.balanced.csv")
    target_rows = read_csv_rows(
        output_dir / "synthetic_pii_stress.balanced_with_targets.csv"
    )

    assert [row["id"] for row in balanced_rows] == [
        row["id"] for row in original_rows
    ]
    assert identity_rows[0]["privatized_text"] == original_rows[0]["text"]
    assert "[PERSON]" in balanced_rows[0]["privatized_text"]
    assert "refugees" in balanced_rows[0]["privatized_text"]
    assert "[TARGET_GROUP:nationality_or_origin]" in target_rows[0]["privatized_text"]
    assert "refugees" not in target_rows[0]["privatized_text"]
    assert result["results"]["balanced"]["metrics"]["direct_identifier_counts"][
        "after"
    ] == 0
