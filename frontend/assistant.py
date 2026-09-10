"""Runs guardrails, retrieval, and generation in-process — no separate backend service."""
import json
import logging
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

logger = logging.getLogger(__name__)

GENERATION_ERROR_RESPONSE = (
    "Something went wrong while generating an answer. Please try again in a moment."
)

# Lets frontend/tests/browser_review.py render the UI with a canned answer, skipping
# the real index build and the Groq call.
_MOCK_RESPONSE = os.environ.get("THYBOT_MOCK_RESPONSE")


def is_ready() -> bool:
    if _MOCK_RESPONSE:
        return True
    from app.core.config import settings
    return bool(settings.groq_api_key)


def ask_question(question: str) -> dict:
    if _MOCK_RESPONSE:
        return json.loads(_MOCK_RESPONSE)

    from app.services import guardrails
    from app.services.guardrails import check_guardrails
    from app.services.llm_service import generate_grounded_answer
    from app.services.retrieval import retrieval_service

    guardrail_labels = {
        guardrails.EMERGENCY_RESPONSE: "emergency",
        guardrails.DOSAGE_REFUSAL_RESPONSE: "dosage_refusal",
        guardrails.OUT_OF_SCOPE_RESPONSE: "out_of_scope",
    }

    guardrail_response = check_guardrails(question, dense_index=retrieval_service.dense_index)
    if guardrail_response is not None:
        return {"answer": guardrail_response, "sources": [], "disclaimer": "",
                "guardrail": guardrail_labels.get(guardrail_response)}

    try:
        chunks = retrieval_service.retrieve(question, top_k=3)
        result = generate_grounded_answer(question, chunks)
    except Exception:
        logger.exception("Failed to generate an answer for a chat request.")
        return {"answer": GENERATION_ERROR_RESPONSE, "sources": [], "disclaimer": "", "guardrail": None}

    return {**result, "guardrail": None}
