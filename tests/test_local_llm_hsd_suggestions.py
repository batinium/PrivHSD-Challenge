from contextsafe_hsd.models.local_llm_hsd_review_runtime import validate_pii_suggestions


def statuses(records):
    return [record.validator_status for record in records]


def test_suggestion_validator_accepts_exact_substring_for_review():
    records = validate_pii_suggestions(
        "Reach Alex after masking the email.",
        ["Alex"],
        model_id="fake-model",
    )

    assert statuses(records) == ["accepted_for_review"]
    assert records[0].start == 6
    assert records[0].end == 10
    assert records[0].text_hash


def test_suggestion_validator_rejects_placeholder_and_non_substring():
    records = validate_pii_suggestions(
        "Reach [EMAIL] after masking the address.",
        ["[EMAIL]", "missing@example.test"],
        model_id="fake-model",
    )

    assert statuses(records) == [
        "rejected_placeholder",
        "rejected_not_substring",
    ]


def test_suggestion_validator_rejects_protected_targets_and_hsd_cues():
    records = validate_pii_suggestions(
        "Muslims should leave town.",
        ["Muslims", "should leave"],
        model_id="fake-model",
    )

    assert statuses(records) == [
        "rejected_protected_or_hsd_cue",
        "rejected_protected_or_hsd_cue",
    ]


def test_suggestion_validator_rejects_external_hsd_cues(monkeypatch):
    monkeypatch.setattr(
        "contextsafe_hsd.models.local_llm_hsd_review_runtime.contains_external_profanity",
        lambda value: value == "external-cue",
    )

    records = validate_pii_suggestions(
        "The protected text still contains external-cue.",
        ["external-cue"],
        model_id="fake-model",
    )

    assert statuses(records) == ["rejected_protected_or_hsd_cue"]


def test_suggestion_validator_deduplicates_per_row():
    records = validate_pii_suggestions(
        "Reach Alex. Alex is visible.",
        ["Alex", "Alex"],
        model_id="fake-model",
    )

    assert statuses(records) == ["accepted_for_review", "rejected_duplicate"]


def test_suggestion_validator_rejects_full_sentence_spans():
    records = validate_pii_suggestions(
        "Reach Alex near the station tomorrow. Muslims should leave.",
        ["Reach Alex near the station tomorrow."],
        model_id="fake-model",
    )

    assert statuses(records) == ["rejected_too_broad"]
