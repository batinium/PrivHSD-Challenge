import pytest

from contextsafe_hsd.detectors import target_group_spans
from contextsafe_hsd.pipeline import PrivatizerConfig, privatize_text


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


def test_lowercase_address_and_private_place_context_are_masked():
    text = "james street is near london library"
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == "[LOCATION] is near [LOCATION]"
    assert "james street" not in result.text
    assert "london library" not in result.text


def test_titlecase_address_and_mixedcase_place_context_are_masked():
    text = "James Street is near London library"
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == "[LOCATION] is near [LOCATION]"
    assert "James Street" not in result.text
    assert "London library" not in result.text


@pytest.mark.parametrize(
    "suffix",
    [
        "st.",
        "st",
        "ave.",
        "ave",
        "rd.",
        "rd",
        "blvd.",
        "blvd",
        "ln.",
        "ln",
        "dr.",
        "dr",
        "ct.",
        "ct",
        "sq.",
        "sq",
    ],
)
def test_lowercase_abbreviated_street_suffixes_are_masked(suffix):
    text = f"meet at oak {suffix} after school."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == "meet at [LOCATION] after school."


def test_lowercase_abbreviated_street_at_sentence_start_is_masked():
    text = "james st. is near london library."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == "[LOCATION] is near [LOCATION]."


def test_lowercase_abbreviated_street_after_direction_context_is_masked():
    text = "walk down elm st. today."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == "walk down [LOCATION] today."


def test_lowercase_street_suffix_avoids_common_non_address_phrase():
    text = "That is a good drive."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == text


@pytest.mark.parametrize("suffix", ["St.", "Rd.", "Ave.", "BLVD.", "LN", "DR"])
def test_mixedcase_abbreviated_street_suffixes_are_masked(suffix):
    text = f"Meet at Oak {suffix} after school."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == "Meet at [LOCATION] after school."


def test_lowercase_meeting_context_masks_person_and_place():
    text = "i met james smith at london library"
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == "i met [PERSON] at [LOCATION]"
    assert "james smith" not in result.text
    assert "london library" not in result.text


def test_lowercase_call_context_masks_two_word_name_only():
    text = "call james smith after the report"
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == "call [PERSON] after the report"
    assert "james smith" not in result.text


def test_lowercase_reporting_context_preserves_hsd_cues():
    text = (
        "reported james smith because he quoted Muslims should leave "
        "and I replied do not attack Muslims."
    )
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "james smith" not in result.text
    assert "[PERSON]" in result.text
    assert "Muslims should leave" in result.text
    assert "do not attack Muslims" in result.text


def test_hsd_statement_without_private_identifier_is_unchanged():
    text = "Muslims should leave"
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == text


def test_adjacent_social_handles_are_masked_individually():
    text = "@foo@bar said immigrants should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "@foo" not in result.text
    assert "@bar" not in result.text
    assert result.text.startswith("[USER][USER] said")
    assert "immigrants should leave" in result.text


def test_one_character_handle_and_obfuscated_url_are_masked():
    text = "RT @t posted hxxps://bad.example/path and Muslims should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "@t" not in result.text
    assert "hxxps://bad.example/path" not in result.text
    assert "[USER]" in result.text
    assert "[URL]" in result.text
    assert "Muslims should leave" in result.text


def test_deobfuscated_spaced_email_maps_back_to_original_span():
    text = "Email alex @ example dot test because Muslims should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "alex @ example dot test" not in result.text
    assert "[EMAIL]" in result.text
    assert "Muslims should leave" in result.text


def test_technical_identifiers_are_masked_without_losing_hsd_statement():
    text = (
        "Drop 2001:db8::8a2e:370:7334, bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kygt080, "
        "user#1234, linkedin.com/in/alex-v, 4111 1111 1111 1111, "
        "GB82 WEST 1234 5698 7654 32 because immigrants should leave."
    )
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "2001:db8::8a2e:370:7334" not in result.text
    assert "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kygt080" not in result.text
    assert "user#1234" not in result.text
    assert "linkedin.com/in/alex-v" not in result.text
    assert "4111 1111 1111 1111" not in result.text
    assert "GB82 WEST 1234 5698 7654 32" not in result.text
    assert "[CRYPTO_WALLET]" in result.text
    assert "[DISCORD_USER]" in result.text
    assert "[SOCIAL_LINK]" in result.text
    assert "[CREDIT_CARD]" in result.text
    assert "[IBAN]" in result.text
    assert "immigrants should leave" in result.text


def test_invalid_card_like_number_is_not_masked_by_luhn_detector():
    text = "Thread 4111 1111 1111 1112 says Muslims should leave."
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert "4111 1111 1111 1112" in result.text
    assert "Muslims should leave" in result.text


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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Riverside Jewish School should be attacked.",
            "Jewish [ORG] should be attacked.",
        ),
        (
            "Roma Cultural Center should be destroyed.",
            "Roma [ORG] should be destroyed.",
        ),
        (
            "Muslim Academy should be banned from the city.",
            "Muslim [ORG] should be banned from the city.",
        ),
        (
            "LGBTQ Youth Centre should be banned from the city.",
            "LGBTQ [ORG] should be banned from the city.",
        ),
        (
            "Disabled Students Centre should be destroyed.",
            "Disabled Students [ORG] should be destroyed.",
        ),
        (
            "The Roma Association should be banned.",
            "Roma [ORG] should be banned.",
        ),
        (
            "riverside jewish school should be attacked.",
            "jewish [ORG] should be attacked.",
        ),
        (
            "roma cultural club should be destroyed.",
            "roma [ORG] should be destroyed.",
        ),
        (
            "muslim charity should be shut down.",
            "muslim [ORG] should be shut down.",
        ),
        (
            "migrant aid office should be burned down.",
            "migrant [ORG] should be burned down.",
        ),
        (
            "black student union should be attacked.",
            "black [ORG] should be attacked.",
        ),
        (
            "islamic community house should be banned.",
            "islamic community [ORG] should be banned.",
        ),
        (
            "the muslim-owned cafe should be burned down.",
            "the muslim [ORG] should be burned down.",
        ),
        (
            "the queer-owned shop should be attacked.",
            "the queer [ORG] should be attacked.",
        ),
    ],
)
def test_balanced_preserves_target_cues_inside_attacked_organizations(text, expected):
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == expected
    assert result.transformations[0]["entity_type"] == "ORGANIZATION"
    assert result.transformations[0]["category"].startswith("target_org:")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Silver City Mosque should be destroyed and its members forced out.",
            "Mosque [ORG] should be destroyed and its members forced out.",
        ),
        (
            "Northbridge Synagogue should be attacked tonight.",
            "Synagogue [ORG] should be attacked tonight.",
        ),
        (
            "Old Town Church should be burned down.",
            "Church [ORG] should be burned down.",
        ),
        (
            "Riverside Hindu Temple should be banned.",
            "Hindu [ORG] should be banned.",
        ),
    ],
)
def test_balanced_preserves_implicit_religious_institution_targets(text, expected):
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == expected
    assert result.transformations[0]["entity_type"] == "ORGANIZATION"
    assert result.transformations[0]["category"] == "target_org:religion"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Do not attack Riverside Jewish School.",
            "Do not attack Jewish [ORG].",
        ),
        (
            "Riverside Jewish School should not be attacked.",
            "Jewish [ORG] should not be attacked.",
        ),
        (
            "A reporter documented the post saying 'Riverside Jewish School "
            "should be attacked'.",
            "A reporter documented the post saying 'Jewish [ORG] should be "
            "attacked'.",
        ),
        (
            "We condemn hate against Riverside Jewish School and support the "
            "students.",
            "We condemn hate against Jewish [ORG] and support the students.",
        ),
    ],
)
def test_target_org_preservation_keeps_context_stance(text, expected):
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == expected


@pytest.mark.parametrize(
    ("text", "expected", "preserved_target"),
    [
        (
            "I work at Riverside Jewish School and reported threats against "
            "Muslim students.",
            "I work at [ORG] and reported threats against Muslim students.",
            "Muslim students",
        ),
        (
            "Contact Lena at Riverside Jewish School about the meeting.",
            "Contact [PERSON] at [ORG] about the meeting.",
            None,
        ),
        (
            "i work at riverside jewish school and reported threats against "
            "Muslim students.",
            "i work at [ORG] and reported threats against Muslim students.",
            "Muslim students",
        ),
        (
            "contact lena at riverside jewish school about the meeting.",
            "contact [PERSON] at [ORG] about the meeting.",
            None,
        ),
        (
            "Riverside Jewish School failed disabled students and ignored "
            "complaints.",
            "[ORG] failed disabled students and ignored complaints.",
            "disabled students",
        ),
    ],
)
def test_target_org_privacy_contexts_still_mask_full_org(
    text,
    expected,
    preserved_target,
):
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == expected
    assert "Jewish" not in result.text
    if preserved_target:
        assert preserved_target in result.text


@pytest.mark.parametrize(
    "text",
    [
        "the public school should be closed.",
        "the black market should be shut down.",
        "the community centre should publish its report.",
    ],
)
def test_case_insensitive_target_org_detection_avoids_generic_lowercase_orgs(text):
    result = privatize_text(text, PrivatizerConfig(mode="balanced"))

    assert result.text == text


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


@pytest.mark.parametrize(
    ("text", "expected_text", "category"),
    [
        ("b l a c k s should leave.", "b l a c k s", "race_or_ethnicity"),
        ("b-l-a-c-k-s should leave.", "b-l-a-c-k-s", "race_or_ethnicity"),
        ("m.u.s.l.i.m.s should leave.", "m.u.s.l.i.m.s", "religion"),
        ("ref ugees should leave.", "ref ugees", "nationality_or_origin"),
        ("blakcs should leave.", "blakcs", "race_or_ethnicity"),
        ("mulsims should leave.", "mulsims", "religion"),
    ],
)
def test_target_split_and_transposed_variants_are_detected(text, expected_text, category):
    spans = target_group_spans(text)
    span_values = {(span.text, span.category, span.source) for span in spans}
    privacy_result = privatize_text(text, PrivatizerConfig(mode="privacy"))

    assert any(
        span_text == expected_text
        and span_category == category
        and span_source in {"target_spaced_variant", "target_variant"}
        for span_text, span_category, span_source in span_values
    )
    assert f"[TARGET_GROUP:{category}]" in privacy_result.text


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
