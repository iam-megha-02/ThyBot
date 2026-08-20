import pytest

from utils.guardrails import DISCLAIMER, check_input_safety, ensure_disclaimer


@pytest.mark.parametrize("message", [
    "I have chest pain and can't breathe",
    "I feel suicidal right now",
    "she is unconscious and having a seizure",
])
def test_emergency_phrases_are_blocked(message):
    result = check_input_safety(message)
    assert result.blocked
    assert result.reason == "emergency"
    assert "emergency" in result.response.lower()


@pytest.mark.parametrize("message", [
    "how much levothyroxine should I take",
    "what dose of synthroid is right for me",
    "should I double my dose today",
])
def test_dosage_requests_are_blocked(message):
    result = check_input_safety(message)
    assert result.blocked
    assert result.reason == "dosage"
    assert "doctor" in result.response.lower() or "pharmacist" in result.response.lower()


@pytest.mark.parametrize("message", [
    "what does TSH mean",
    "is coffee bad for my thyroid medication",
    "what foods should I avoid with hypothyroidism",
    "why did my chest x-ray get mentioned in this report",  # "chest" present, not an emergency phrase
])
def test_benign_questions_are_not_blocked(message):
    result = check_input_safety(message)
    assert not result.blocked
    assert result.response == ""


def test_emergency_takes_priority_when_both_could_match():
    result = check_input_safety("I have chest pain, what dose of aspirin should I take")
    assert result.reason == "emergency"


def test_ensure_disclaimer_appends_when_missing():
    reply = "Your TSH looks stable."
    result = ensure_disclaimer(reply)
    assert reply in result
    assert DISCLAIMER in result


def test_ensure_disclaimer_does_not_duplicate_when_already_present():
    reply = "Your TSH looks stable. Please consult your doctor about any changes."
    result = ensure_disclaimer(reply)
    assert result.count("consult") == 1
    assert DISCLAIMER not in result
