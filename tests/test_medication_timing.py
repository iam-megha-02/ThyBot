from utils.medication_timing import InteractionSeverity, check_medication_timing


def test_calcium_flagged_as_strict_separation():
    [result] = check_medication_timing(["calcium carbonate"])
    assert result.matched
    assert result.severity == InteractionSeverity.SEPARATE_STRICT
    assert result.min_hours_apart == 4.0


def test_coffee_flagged_as_caution_with_short_window():
    [result] = check_medication_timing(["coffee"])
    assert result.matched
    assert result.severity == InteractionSeverity.SEPARATE_CAUTION
    assert result.min_hours_apart == 0.5


def test_ppi_flagged_without_a_fixed_window():
    [result] = check_medication_timing(["omeprazole"])
    assert result.matched
    assert result.min_hours_apart is None
    assert "doctor" in result.guidance.lower()


def test_unknown_item_returns_no_known_interaction():
    [result] = check_medication_timing(["chamomile tea"])
    assert not result.matched
    assert result.severity == InteractionSeverity.NO_KNOWN_INTERACTION
    assert result.min_hours_apart is None


def test_alias_matches_as_substring_within_a_longer_phrase():
    [result] = check_medication_timing(["I take ferrous sulfate daily"])
    assert result.matched
    assert result.min_hours_apart == 4.0


def test_multiple_items_preserve_input_order():
    results = check_medication_timing(["coffee", "calcium", "chamomile tea"])
    assert [r.item for r in results] == ["coffee", "calcium", "chamomile tea"]
    assert [r.matched for r in results] == [True, True, False]
