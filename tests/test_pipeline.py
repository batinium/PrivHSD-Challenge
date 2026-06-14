from privhsd.detectors import target_group_spans
from privhsd.pipeline import PrivatizerConfig, privatize_text


def sensitive_word_from_codes(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


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


def test_contact_context_masks_person_and_obfuscated_email():
    text = "Reach Lina at lina [at] example dot test or Telegram alias night_owl77."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "Lina" not in result.text
    assert "lina [at] example dot test" not in result.text
    assert "[PERSON]" in result.text
    assert "[EMAIL]" in result.text
    assert "[ALIAS]" in result.text
    assert "Telegram" in result.text


def test_bare_at_dot_words_do_not_create_email_without_contact_context():
    text = "We met at example dot cafe and Muslims should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "[EMAIL]" not in result.text
    assert "example dot cafe" in result.text
    assert "Muslims should leave" in result.text


def test_reported_person_context_masks_name_without_flattening_counterspeech():
    text = (
        "I reported Omar Vale because he quoted Muslims should leave "
        "and I replied do not attack Muslims."
    )
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "Omar Vale" not in result.text
    assert "[PERSON]" in result.text
    assert "Muslims should leave" in result.text
    assert "do not attack Muslims" in result.text


def test_sentence_start_abuse_words_are_not_context_person_names():
    abuse = sensitive_word_from_codes(98, 105, 116, 99, 104)
    text = f"{abuse.capitalize()} said her shoes are ugly."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert abuse.capitalize() in result.text
    assert "ugly" in result.text
    assert "[PERSON]" not in result.text


def test_pronoun_call_context_is_not_context_person_name():
    abuse = sensitive_word_from_codes(98, 105, 116, 99, 104)
    text = f"She called me a {abuse}."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == text


def test_call_me_context_does_not_mask_hostility_cue_as_name():
    text = "They call me ugly and I do not care."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == text


def test_context_person_still_masks_real_name_before_speech_verb():
    text = "Dana Cole said immigrants should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "Dana Cole" not in result.text
    assert "[PERSON] said immigrants should leave" in result.text


def test_short_name_threat_context_preserves_action_cue():
    text = "Kill Alex was posted by a throwaway account near Paris."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text.startswith("Kill [PERSON] was posted")
    assert "Alex" not in result.text
    assert "[LOCATION]" in result.text


def test_adjacent_social_handles_are_masked_individually():
    text = "@foo@bar said immigrants should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "@foo" not in result.text
    assert "@bar" not in result.text
    assert result.text.startswith("[USER][USER] said")
    assert "immigrants should leave" in result.text


def test_context_person_masks_unicode_and_lowercase_self_identification():
    text = "My name is ayşe and Muslims should leave Lagos."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "ayşe" not in result.text
    assert "[PERSON]" in result.text
    assert "Muslims should leave" in result.text
    assert "[LOCATION]" in result.text


def test_balanced_preserves_historical_victim_group_terms():
    text = "Alex Vale wrote that Holocaust survivors should be attacked."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "Alex Vale" not in result.text
    assert "[PERSON]" in result.text
    assert "Holocaust survivors" in result.text
    assert "attacked" in result.text


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


def test_action_context_city_is_masked_as_location():
    text = "Muslims should leave Boston on Jan 12, 2025."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "Boston" not in result.text
    assert "[LOCATION]" in result.text
    assert "[DATE]" in result.text
    assert "Muslims should leave" in result.text


def test_street_suffix_is_masked_as_location():
    text = "Jefferson Street was mentioned by Alex Vale."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "Jefferson Street" not in result.text
    assert "[LOCATION]" in result.text


def test_external_profanity_lexicon_marks_abusive_target_cue():
    term = sensitive_word_from_codes(110, 105, 103, 103, 101, 114, 115)
    text = f"{term.capitalize()} should leave."
    spans = target_group_spans(text)
    privacy_result = privatize_text(text, PrivatizerConfig(mode="privacy"))
    balanced_result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert any(
        span.category == "slur_or_profanity"
        and span.source == "external_profanity_lexicon"
        for span in spans
    )
    assert "[TARGET_GROUP:slur_or_profanity]" in privacy_result.text
    assert f"{term.capitalize()} should leave" in balanced_result.text


def test_african_target_and_hashtag_target_are_detected():
    text = (
        "They say Africans are resourceful near Lagos. "
        "#StarvingAfricans #HandoutHogs"
    )
    spans = target_group_spans(text)
    span_values = {(span.text, span.category, span.source) for span in spans}
    privacy_result = privatize_text(text, PrivatizerConfig(mode="privacy"))

    assert ("Africans", "race_or_ethnicity", "target_dictionary") in span_values
    assert ("#StarvingAfricans", "race_or_ethnicity", "target_hashtag") in span_values
    assert "[TARGET_GROUP:race_or_ethnicity]" in privacy_result.text
    assert "[LOCATION]" in privacy_result.text


def test_target_typos_and_obfuscations_are_detected_near_hostile_context():
    obfuscated_abuse = "".join(["n", "1", "g", "g", "e", "r", "s"])
    text = f"Africanz should leave and {obfuscated_abuse} should leave."
    spans = target_group_spans(text)
    span_values = {(span.text, span.category, span.source) for span in spans}
    privacy_result = privatize_text(text, PrivatizerConfig(mode="privacy"))

    assert ("Africanz", "race_or_ethnicity", "target_variant") in span_values
    assert (
        obfuscated_abuse,
        "slur_or_profanity",
        "external_profanity_lexicon",
    ) in span_values
    assert "[TARGET_GROUP:race_or_ethnicity]" in privacy_result.text
    assert "[TARGET_GROUP:slur_or_profanity]" in privacy_result.text


def test_spaced_target_obfuscation_is_detected_near_spaced_hostile_context():
    text = "bla cks are sh i t and should leave."
    spans = target_group_spans(text)
    span_values = {(span.text, span.category, span.source) for span in spans}
    privacy_result = privatize_text(text, PrivatizerConfig(mode="privacy"))
    balanced_result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert ("bla cks", "race_or_ethnicity", "target_spaced_variant") in span_values
    assert "[TARGET_GROUP:race_or_ethnicity]" in privacy_result.text
    assert "bla cks are sh i t and should leave" in balanced_result.text


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


def test_privacy_mode_generalizes_contextual_gender_terms_for_violence():
    text = "Women should be killed."
    result = privatize_text(text, PrivatizerConfig(mode="privacy"))

    assert "Women" not in result.text
    assert "[TARGET_GROUP:gender]" in result.text
