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

