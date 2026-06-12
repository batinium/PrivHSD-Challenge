from privhsd.context import analyze_context


def tags(text):
    return set(analyze_context(text)["context_tags"])


def test_context_distinguishes_negation_from_endorsement():
    negated = tags("Do not attack Muslims.")
    endorsed = tags("Attack Muslims.")

    assert {"protected_target", "hostile_action", "negated_hate"} <= negated
    assert "counterspeech" in negated
    assert "negated_hate" not in endorsed
    assert "missing_context" in endorsed


def test_context_detects_counterspeech_and_quotation():
    result = tags('They reported "attack Muslims" while condemning hate.')

    assert "protected_target" in result
    assert "quoted_or_reported" in result
    assert "missing_context" not in result


def test_context_detects_offensive_only_without_protected_target():
    result = tags("That person is a stupid idiot.")

    assert "offensive_only_risk" in result
    assert "protected_target" not in result


def test_context_detects_protected_threat_exclusion_and_historical_group():
    result = tags("Holocaust survivors should leave.")

    assert {"protected_target", "historical_victim_group", "exclusion"} <= result
    assert "missing_context" in result


def test_context_detects_public_interest_criticism_without_target():
    result = tags("Government policy is corrupt and officials should resign.")

    assert "public_interest_or_institutional_criticism" in result
    assert "protected_target" not in result
