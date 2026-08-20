"""
Single intent-classification step for the Chat page, replacing two
independent keyword gates that could disagree with each other (e.g.
"What does TSH mean?" tripping a trend-question check meant for
personal-history questions).

Runs *after* utils/guardrails.py's deterministic safety check, which
stays keyword-based on purpose — emergency/dosage detection shouldn't
wait on an LLM round-trip. This router only replaces the softer
judgment calls: does this message need lab history, or the uploaded
document's content.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.llm import get_json_completion
from utils.lab_history import looks_like_lab_trend_question
from utils.knowledge_base import POPULATION_ELDERLY, POPULATION_GENERAL, POPULATION_MATERNAL, POPULATION_PEDIATRIC

_VALID_POPULATIONS = {POPULATION_GENERAL, POPULATION_MATERNAL, POPULATION_PEDIATRIC, POPULATION_ELDERLY}

_SCHEMA_INSTRUCTIONS = """You classify one chat message from a thyroid-health app into a JSON object with exactly these fields:

{
  "needs_lab_history": true or false,
  "needs_document_context": true or false,
  "population": "general" or "maternal" or "pediatric" or "elderly",
  "intent_label": a short string, e.g. "trend_question", "definitional", "diet_question", "document_question", "clinical_question", "general"
}

needs_lab_history: true ONLY if answering requires the patient's OWN past lab values over time (e.g. tracking whether a number is improving). False for questions that just define or explain a term, even if the term (like "TSH") appears in the message.

needs_document_context: true ONLY if a document was uploaded this session AND answering this specific message requires that document's content. If no document was uploaded, this must be false.

population: which guideline population this question is actually about — "maternal" for pregnancy-related questions, "pediatric" for questions about children/adolescents, "elderly" for questions about older patients, otherwise "general". Base this on the question's content, not on any assumption about who is asking.

Respond with ONLY the JSON object, no other text."""


@dataclass(frozen=True)
class RouteDecision:
    needs_lab_history: bool
    needs_document_context: bool
    population: str
    intent_label: str


def classify_intent(message: str, has_uploaded_document: bool) -> RouteDecision:
    """
    Fails safe: any error (network, bad JSON, missing fields) falls
    back to the old keyword heuristic rather than crashing chat or
    silently disabling trend-awareness. A broken router should degrade
    to "yesterday's crude behavior," never to "nothing works."
    """
    messages = [
        {"role": "system", "content": _SCHEMA_INSTRUCTIONS},
        {
            "role": "user",
            "content": (
                f"Document uploaded this session: {has_uploaded_document}\n"
                f"Message: {message}"
            ),
        },
    ]
    try:
        data = get_json_completion(messages)
        population = data.get("population", POPULATION_GENERAL)
        if population not in _VALID_POPULATIONS:
            population = POPULATION_GENERAL  # don't trust an off-schema value silently
        return RouteDecision(
            needs_lab_history=bool(data["needs_lab_history"]),
            needs_document_context=bool(data["needs_document_context"]) and has_uploaded_document,
            population=population,
            intent_label=str(data.get("intent_label", "unknown")),
        )
    except Exception:
        return RouteDecision(
            needs_lab_history=looks_like_lab_trend_question(message),
            needs_document_context=has_uploaded_document,
            population=POPULATION_GENERAL,
            intent_label="fallback_keyword_heuristic",
        )
