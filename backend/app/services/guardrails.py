import re

from app.services.semantic_guardrails import semantic_emergency_score, semantic_dosage_score

EMERGENCY_SIMILARITY_THRESHOLD = 0.5
DOSAGE_SIMILARITY_THRESHOLD = 0.40


EMERGENCY_KEYWORDS = [
    "chest pain", "difficulty breathing", "trouble breathing", "can't breathe",
    "cannot breathe", "unconscious", "unconsciousness", "severe bleeding",
    "seizure", "suicidal", "suicide", "want to die", "throat closing",
    "throat is closing",
]

DOSAGE_KEYWORDS = [
    "what dose", "what dosage", "how much levothyroxine", "how much thyroid medication",
    "increase my dose", "decrease my dose", "double my dose", "skip my dose",
    "should i take more", "should i take less", "change my dose", "reduce my dose",
    "how many mg", "how many micrograms", "adjust my dose", "stop taking my medication",
]

THYROID_SCOPE_KEYWORDS = [
    "thyroid", "tsh", "t3", "t4", "hypothyroid", "hyperthyroid", "hashimoto",
    "graves", "goiter", "goitre", "levothyroxine", "synthroid", "thyroiditis",
    "thyroidectomy", "iodine", "nodule", "underactive", "overactive",
]

EMERGENCY_RESPONSE = (
    "This sounds like it could be a medical emergency. Please call 112 (India's "
    "national emergency number) or go to the nearest emergency room immediately. "
    "If this involves thoughts of self-harm or suicide, you can also reach the "
    "KIRAN mental health helpline anytime at 1800-599-0019 (toll-free). "
    "This assistant cannot provide emergency medical care."
)

DOSAGE_REFUSAL_RESPONSE = (
    "I'm not able to provide guidance on medication dosages, including whether "
    "to change, increase, decrease, or skip a dose. Please contact your "
    "prescribing doctor or pharmacist for any dosage-related questions."
)

OUT_OF_SCOPE_RESPONSE = (
    "I'm designed to answer questions specifically about thyroid health. "
    "This question appears to be outside that scope. Please consult a general "
    "health resource or your doctor for this topic."
)


NEGATION_CUES = ["no ", "not ", "n't ", "without ", "denies ", "deny ", "denied "]
NEGATION_WINDOW = 15


def _is_negated(text_lower: str, match_start: int) -> bool:
    preceding = text_lower[max(0, match_start - NEGATION_WINDOW):match_start]
    return any(cue in preceding for cue in NEGATION_CUES)


def _contains_any(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    for keyword in keywords:
        start = text_lower.find(keyword)
        if start != -1 and not _is_negated(text_lower, start):
            return True
    return False


SCOPE_SIMILARITY_THRESHOLD = 0.35


def _scope_request(question: str) -> str:
    """Separate a simple condition introduction from a following request."""
    match = re.match(
        r"^\s*I (?:have|was diagnosed with|have been diagnosed with) "
        r"(?:hypothyroidism|hyperthyroidism|Hashimoto['’]s(?: disease)?|"
        r"Graves['’]?(?: disease)?)\s*[.!]\s*(\S[\s\S]*)$",
        question,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else question


def check_guardrails(question: str, dense_index=None) -> str | None:
    is_emergency = (
        _contains_any(question, EMERGENCY_KEYWORDS)
        or semantic_emergency_score(question) >= EMERGENCY_SIMILARITY_THRESHOLD
    )
    if is_emergency:
        return EMERGENCY_RESPONSE

    scope_request = _scope_request(question)
    has_thyroid_keyword = _contains_any(scope_request, THYROID_SCOPE_KEYWORDS)
    has_thyroid_scope = has_thyroid_keyword
    if not has_thyroid_scope and dense_index is not None:
        results = dense_index.search_with_scores(scope_request, top_k=1)
        top_score = results[0][1] if results else 0.0
        has_thyroid_scope = top_score >= SCOPE_SIMILARITY_THRESHOLD

    is_dosage = (
        _contains_any(question, DOSAGE_KEYWORDS)
        or semantic_dosage_score(question) >= DOSAGE_SIMILARITY_THRESHOLD
    )
    if is_dosage and has_thyroid_scope:
        return DOSAGE_REFUSAL_RESPONSE

    if not has_thyroid_scope:
        return OUT_OF_SCOPE_RESPONSE

    return None
