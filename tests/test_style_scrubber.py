import csv

from contextsafe_hsd.metrics import row_metric
from contextsafe_hsd.pipeline import PrivatizerConfig, privatize_text
from contextsafe_hsd.style import scrub_style


def read_csv_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_style_scrubber_normalizes_author_style_and_preserves_hsd_cues():
    text = (
        "  REFUGEES dooo NOOOT belong here!!!! frfr #MyCatchphrase "
        "\U0001f602\U0001f602 -- sent from my iphone  "
    )

    result = scrub_style(text)

    assert result.text == (
        "refugees do not belong here! [STYLE] [TAG] [EMOJI] [SIGNATURE]"
    )
    assert result.metrics["style_scrub_changed"] is True
    assert result.metrics["style_counts_by_type"]["repeated_letters"] == 2
    assert "refugees" in result.text
    assert "do not belong" in result.text
    assert row_metric(text, result.text)["utility_cue_retention"] == 1.0
    assert row_metric(text, result.text)["target_cue_retention"] == 1.0


def test_style_scrubber_splits_cue_hashtags_instead_of_dropping_them():
    result = scrub_style("Women shouuuld be deported?!?! #DeportThem")

    assert result.text == "women should be deported?! deport them"
    assert "women" in result.text
    assert "should" in result.text
    assert "deported" in result.text
    assert row_metric("Women should be deported", result.text)[
        "utility_cue_retention"
    ] == 1.0


def test_style_scrubber_normalizes_language_style_and_preserves_hsd_cues():
    text = (
        "I'm utilising teh colour centre, subsequently, because Muslims "
        "shouldn't be deported?!?!"
    )

    result = scrub_style(text)

    assert result.text == (
        "I am using the color center, later, because muslims should not be "
        "deported?!"
    )
    assert result.metrics["style_counts_by_type"]["contraction"] == 2
    assert result.metrics["style_counts_by_type"]["american_english"] == 3
    assert result.metrics["style_counts_by_type"]["typo"] == 1
    assert result.metrics["style_counts_by_type"]["simple_language"] == 2
    assert "muslims" in result.text
    assert "should not be deported" in result.text
    assert row_metric(text, result.text)["target_cue_retention"] == 1.0
    assert row_metric(text, result.text)["utility_cue_retention"] == 1.0


def test_style_scrubber_can_skip_high_register_simplification_only():
    text = (
        "I'm utilising teh colour centre, subsequently, because Muslims "
        "shouldn't be deported?!?!"
    )

    result = scrub_style(text, simplify_language=False)

    assert result.text == (
        "I am utilizing the color center, subsequently, because muslims "
        "should not be deported?!"
    )
    assert result.metrics["style_counts_by_type"]["contraction"] == 2
    assert result.metrics["style_counts_by_type"]["american_english"] == 3
    assert result.metrics["style_counts_by_type"]["typo"] == 1
    assert "simple_language" not in result.metrics["style_counts_by_type"]
    assert row_metric(text, result.text)["target_cue_retention"] == 1.0
    assert row_metric(text, result.text)["utility_cue_retention"] == 1.0


def test_privatizer_style_scrub_preserves_privacy_placeholders():
    text = (
        "Call me Alex Vale. I HAAATE immigrants!!!! "
        "#SelfBrand \U0001f602\U0001f602"
    )

    result = privatize_text(text, PrivatizerConfig(mode="balanced", style_scrub=True))

    assert "[PERSON]" in result.text
    assert "[person]" not in result.text
    assert "hate" in result.text
    assert "immigrants" in result.text
    assert "[TAG]" in result.text
    assert result.metrics["style_scrub_enabled"] is True
    assert result.metrics["style_transform_count"] > 0
    assert any(
        transformation["source"] == "style_scrubber"
        for transformation in result.transformations
    )


def test_privatizer_can_disable_language_simplification():
    text = "I utilised additional assistance because Muslims should leave."

    result = privatize_text(
        text,
        PrivatizerConfig(
            mode="balanced",
            style_scrub=True,
            style_simplify_language=False,
        ),
    )

    assert "utilized" in result.text
    assert "more help" not in result.text
    assert "muslims should leave" in result.text


def test_privatizer_accepts_style_scrub_flag_for_csv_rows(tmp_path):
    source = tmp_path / "input.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "label"])
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "text": "@User HAAATES refugees!!!! #SelfTag",
                "label": "hate",
            }
        )

    rows = read_csv_rows(source)
    result = privatize_text(
        rows[0]["text"],
        PrivatizerConfig(mode="balanced", style_scrub=True),
    )

    assert result.text == "[USER] hates refugees! [TAG]"
    assert result.metrics["style_scrub_enabled"] is True
    assert result.metrics["style_transform_count"] > 0
