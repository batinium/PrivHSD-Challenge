from privhsd.pipeline import PrivatizerConfig, privatize_text


def test_privatizes_direct_identifiers_and_preserves_target_terms_by_default():
    text = (
        "@mara from Berlin emailed mara@example.test and said immigrants "
        "should be deported."
    )
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "@mara" not in result.text
    assert "mara@example.test" not in result.text
    assert "[USER]" in result.text
    assert "[EMAIL]" in result.text
    assert "immigrants" in result.text
    assert "deported" in result.text


def test_privacy_mode_can_generalize_target_groups():
    text = "Muslims should be excluded, said Alex Vale."
    result = privatize_text(text, PrivatizerConfig(mode="privacy"))

    assert "[TARGET_GROUP:religion]" in result.text
    assert "Muslims" not in result.text
    assert "[PERSON]" in result.text


def test_utility_mode_keeps_context_detectors_but_not_target_generalization():
    text = "My name is Alex Vale and I think refugees do not belong here."
    result = privatize_text(text, PrivatizerConfig(mode="utility"))

    assert "Alex Vale" not in result.text
    assert "[PERSON]" in result.text
    assert "refugees" in result.text


def test_context_person_masks_single_token_self_identification():
    text = "My name is Amy and Muslims should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "Amy" not in result.text
    assert "[PERSON]" in result.text
    assert "Muslims should leave" in result.text


def test_context_location_does_not_mask_target_terms():
    text = "I live in Muslim neighborhoods and they should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "[LOCATION]" not in result.text
    assert "Muslim neighborhoods" in result.text


def test_context_location_still_masks_non_target_places():
    text = "I live in London and Muslims should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "London" not in result.text
    assert "[LOCATION]" in result.text
    assert "Muslims should leave" in result.text


def test_privacy_mode_preserves_broad_gender_terms_without_hostile_context():
    text = "The women from River City organized a public meeting."
    result = privatize_text(text, PrivatizerConfig(mode="privacy"))

    assert "women" in result.text
    assert "[TARGET_GROUP:gender]" not in result.text
    assert "[LOCATION]" in result.text


def test_privacy_mode_generalizes_broad_gender_terms_in_hostile_context():
    text = "Women do not belong in the public meeting."
    result = privatize_text(text, PrivatizerConfig(mode="privacy"))

    assert "Women" not in result.text
    assert "[TARGET_GROUP:gender]" in result.text
