import logging

from fastapi import APIRouter
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.retrieval import retrieval_service
from app.services.llm_service import generate_grounded_answer
from app.services import guardrails
from app.services.guardrails import check_guardrails

router = APIRouter()
logger = logging.getLogger(__name__)

GENERATION_ERROR_RESPONSE = (
    "Something went wrong while generating an answer. Please try again in a moment."
)

GUARDRAIL_LABELS = {
    guardrails.EMERGENCY_RESPONSE: "emergency",
    guardrails.DOSAGE_REFUSAL_RESPONSE: "dosage_refusal",
    guardrails.OUT_OF_SCOPE_RESPONSE: "out_of_scope",
}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    guardrail_response = check_guardrails(request.question, dense_index=retrieval_service.dense_index)
    if guardrail_response is not None:
        return ChatResponse(answer=guardrail_response, sources=[], disclaimer="",
                             guardrail=GUARDRAIL_LABELS.get(guardrail_response))

    try:
        chunks = retrieval_service.retrieve(request.question, top_k=3)
        result = generate_grounded_answer(request.question, chunks)
    except Exception:
        logger.exception("Failed to generate an answer for a chat request.")
        return ChatResponse(answer=GENERATION_ERROR_RESPONSE, sources=[], disclaimer="")

    return ChatResponse(**result)