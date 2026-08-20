"""
Input/output safety gates for LLM-facing pages.

Deliberately outside the model's control: a system-prompt instruction
like "don't give dosage advice" is a request the model can ignore,
misjudge, or be talked past. A guardrail is a deterministic check code
enforces regardless of what the model decides to do.
"""

from __future__ import annotations

from dataclasses import dataclass

# Unambiguous phrases only — the cost of a false positive here is
# blocking a legitimate question, so the list stays narrow rather than
# broad. This is the MVP keyword version, not the red-team-tested
# production one from the architecture blueprint's eval section.
_EMERGENCY_PHRASES = (
    "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
    "suicidal", "want to die", "kill myself", "severe bleeding",
    "unconscious", "seizure", "can't swallow", "cannot swallow",
    "throat closing", "heart attack", "stroke symptoms",
)

_DOSAGE_PATTERNS = (
    "how much levothyroxine", "how much synthroid", "how many mg",
    "how many mcg", "what dose", "what dosage", "is it safe to take",
    "should i increase my dose", "should i decrease my dose",
    "how much should i take", "double my dose", "skip my dose",
)

EMERGENCY_RESPONSE = (
    "This sounds like it could be a medical emergency. Please contact "
    "emergency services or go to the nearest emergency room right away — "
    "I'm not able to help with this here."
)

DOSAGE_RESPONSE = (
    "I can't advise on medication doses — that has to come from your "
    "doctor or pharmacist, since it depends on your specific labs and "
    "history. I can help explain what your lab values mean or how "
    "timing with food/other medications works, if that's useful instead."
)

DISCLAIMER = (
    "This is general educational information, not medical advice or a "
    "diagnosis. Please discuss your specific situation with a doctor."
)

_DISCLAIMER_MARKERS = ("not medical advice", "consult a doctor", "consult your doctor", "discuss with your doctor", "discuss with a doctor")


@dataclass(frozen=True)
class GuardrailResult:
    blocked: bool
    reason: str  # "emergency" | "dosage" | "" (not blocked)
    response: str  # the fixed safe reply if blocked, else ""


def check_input_safety(message: str) -> GuardrailResult:
    """
    Runs before any branching in chat_page(). Emergency check takes
    priority over dosage — a message can plausibly match both, and
    the emergency response is the one that actually matters if so.
    """
    lowered = message.lower()

    if any(phrase in lowered for phrase in _EMERGENCY_PHRASES):
        return GuardrailResult(blocked=True, reason="emergency", response=EMERGENCY_RESPONSE)

    if any(phrase in lowered for phrase in _DOSAGE_PATTERNS):
        return GuardrailResult(blocked=True, reason="dosage", response=DOSAGE_RESPONSE)

    return GuardrailResult(blocked=False, reason="", response="")


def ensure_disclaimer(reply: str) -> str:
    """
    Appends a standing disclaimer to an LLM-generated reply unless it
    already looks like it has one — enforced in code so it doesn't
    depend on the model remembering to include it.
    """
    lowered = reply.lower()
    if any(marker in lowered for marker in _DISCLAIMER_MARKERS):
        return reply
    return f"{reply}\n\n*{DISCLAIMER}*"
