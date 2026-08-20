from unittest.mock import patch

from utils.router import classify_intent
from utils.knowledge_base import POPULATION_GENERAL, POPULATION_MATERNAL


def test_successful_classification_is_used_directly():
    with patch("utils.router.get_json_completion") as mock_call:
        mock_call.return_value = {
            "needs_lab_history": True,
            "needs_document_context": False,
            "population": POPULATION_GENERAL,
            "intent_label": "trend_question",
        }
        decision = classify_intent("Is my TSH improving?", has_uploaded_document=False)

    assert decision.needs_lab_history is True
    assert decision.needs_document_context is False
    assert decision.intent_label == "trend_question"


def test_maternal_population_is_picked_up_correctly():
    with patch("utils.router.get_json_completion") as mock_call:
        mock_call.return_value = {
            "needs_lab_history": False,
            "needs_document_context": False,
            "population": POPULATION_MATERNAL,
            "intent_label": "clinical_question",
        }
        decision = classify_intent("What's a safe TSH level during pregnancy?", has_uploaded_document=False)

    assert decision.population == POPULATION_MATERNAL


def test_off_schema_population_value_is_clamped_to_general():
    # Defends against the model returning something outside the four
    # valid tags — silently trusting it would break the population
    # filter downstream rather than just defaulting sensibly.
    with patch("utils.router.get_json_completion") as mock_call:
        mock_call.return_value = {
            "needs_lab_history": False,
            "needs_document_context": False,
            "population": "adult",  # not one of the four valid tags
            "intent_label": "general",
        }
        decision = classify_intent("some question", has_uploaded_document=False)

    assert decision.population == POPULATION_GENERAL


def test_fallback_path_defaults_population_to_general():
    with patch("utils.router.get_json_completion", side_effect=RuntimeError("boom")):
        decision = classify_intent("some question", has_uploaded_document=False)

    assert decision.population == POPULATION_GENERAL


def test_definitional_question_correctly_does_not_need_history():
    # The exact case that broke the old keyword gate: "TSH" appears in
    # the message but this isn't a personal-trend question.
    with patch("utils.router.get_json_completion") as mock_call:
        mock_call.return_value = {
            "needs_lab_history": False,
            "needs_document_context": False,
            "intent_label": "definitional",
        }
        decision = classify_intent("What does TSH mean?", has_uploaded_document=False)

    assert decision.needs_lab_history is False
    assert decision.intent_label == "definitional"


def test_document_context_is_clamped_false_when_no_document_uploaded():
    # Defensive: even if the model hallucinates needs_document_context=True,
    # there's nothing to retrieve if no document was ever uploaded.
    with patch("utils.router.get_json_completion") as mock_call:
        mock_call.return_value = {
            "needs_lab_history": False,
            "needs_document_context": True,
            "intent_label": "document_question",
        }
        decision = classify_intent("What does this say?", has_uploaded_document=False)

    assert decision.needs_document_context is False


def test_network_failure_falls_back_to_keyword_heuristic():
    with patch("utils.router.get_json_completion", side_effect=ConnectionError("network down")):
        decision = classify_intent("Is my TSH improving?", has_uploaded_document=False)

    assert decision.needs_lab_history is True  # keyword heuristic still catches "tsh" + "improving"
    assert decision.intent_label == "fallback_keyword_heuristic"


def test_malformed_json_response_falls_back_gracefully():
    with patch("utils.router.get_json_completion", side_effect=ValueError("invalid json")):
        decision = classify_intent("What foods should I avoid?", has_uploaded_document=False)

    assert decision.needs_lab_history is False
    assert decision.intent_label == "fallback_keyword_heuristic"


def test_missing_keys_in_response_falls_back_gracefully():
    with patch("utils.router.get_json_completion") as mock_call:
        mock_call.return_value = {"intent_label": "incomplete"}  # missing required keys
        decision = classify_intent("Is my TSH improving?", has_uploaded_document=False)

    assert decision.intent_label == "fallback_keyword_heuristic"
    assert decision.needs_lab_history is True  # heuristic still catches it


def test_fallback_uses_uploaded_document_conservatively():
    # When we can't classify, treat "a document exists" as "probably needed" —
    # matches the old behavior rather than silently dropping RAG context.
    with patch("utils.router.get_json_completion", side_effect=RuntimeError("boom")):
        decision = classify_intent("some question", has_uploaded_document=True)

    assert decision.needs_document_context is True
