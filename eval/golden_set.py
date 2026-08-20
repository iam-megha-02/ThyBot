"""
Hand-curated eval cases for the RAG + router pipeline.

Every "expected" value here was actually observed against the real
live stack during development (real Groq calls, real persisted FAISS
index) — not guessed from filenames or invented as a plausible-sounding
answer. Where a case checks retrieval, `expected_source_contains` is a
substring of a filename that was actually confirmed to come back for
that exact question. Where a case checks routing, the expected fields
are what utils.router.classify_intent actually returned when run live.

This is a starting scaffold (~11 cases), not a finished eval program —
each case checks the one thing it was actually verified for, not
everything at once, since not every question was checked against
both retrieval and routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EvalCase:
    question: str
    grounding: str  # what real, observed fact this case is based on
    has_uploaded_document: bool = False
    expected_source_contains: Optional[str] = None       # None = don't check retrieval
    expected_population: Optional[str] = None             # None = don't check routing population
    expected_needs_lab_history: Optional[bool] = None      # None = don't check
    expected_needs_document_context: Optional[bool] = None  # None = don't check


GOLDEN_SET = (
    # --- Retrieval: does the right document come back for each population? ---
    EvalCase(
        question="When is TSH considered too high for someone who feels no symptoms?",
        grounding=(
            "Live-verified: retrieved from Depression_Guidelines.pdf, answer "
            "correctly stated '>10 mIU/L... asymptomatic... 4-10 mIU/L treated "
            "only if symptomatic'."
        ),
        expected_source_contains="Depression_Guidelines",
    ),
    EvalCase(
        question="What TSH level is considered safe during pregnancy?",
        grounding=(
            "Live-verified: retrieved from Maternal_Thyroid_Guidelines.pdf, "
            "answer correctly gave trimester-specific thresholds (<=2.5 "
            "mIU/L first trimester) that the general document doesn't have."
        ),
        expected_source_contains="Maternal_Thyroid_Guidelines",
        expected_population="maternal",
    ),
    EvalCase(
        question="hypothyroidism symptoms in children",
        grounding=(
            "Live-verified: retrieved from hypothyroidism-children-adolescents-"
            "brochure.pdf, chunk content covered delayed pubertal development "
            "and goiter as physical exam findings."
        ),
        expected_source_contains="hypothyroidism-children-adolescents",
        expected_population="pediatric",
    ),
    EvalCase(
        question="thyroid treatment considerations for older patients",
        grounding=(
            "Live-verified: retrieved from Thyroid_Disease_Older_Patients.pdf, "
            "chunk content stated hypothyroidism is more common in older than "
            "younger adults."
        ),
        expected_source_contains="Thyroid_Disease_Older_Patients",
        expected_population="elderly",
    ),

    # --- Routing: does classify_intent decide correctly on real questions? ---
    EvalCase(
        question="Is my TSH improving?",
        grounding="Live-verified router output: needs_lab_history=True, population=general.",
        expected_needs_lab_history=True,
        expected_population="general",
    ),
    EvalCase(
        question="What does TSH mean?",
        grounding=(
            "The exact case that broke the old keyword-gate design — 'tsh' as "
            "a substring used to wrongly trigger the trend-question path. "
            "Live-verified router output: needs_lab_history=False, population=general."
        ),
        expected_needs_lab_history=False,
        expected_population="general",
    ),
    EvalCase(
        question="What foods should I avoid with hypothyroidism?",
        grounding="Live-verified router output: needs_lab_history=False, population=general.",
        expected_needs_lab_history=False,
        expected_population="general",
    ),
    EvalCase(
        question="Can you summarize what this document says about goiters?",
        grounding="Live-verified router output: needs_document_context=True (with a document uploaded).",
        has_uploaded_document=True,
        expected_needs_document_context=True,
    ),
    EvalCase(
        question="What TSH level is considered safe during pregnancy?",
        grounding="Live-verified router output: population=maternal.",
        expected_population="maternal",
    ),
    EvalCase(
        question="What are signs of hypothyroidism in adolescents?",
        grounding="Live-verified router output: population=pediatric.",
        expected_population="pediatric",
    ),
    EvalCase(
        question="Is hypothyroidism more common in older adults?",
        grounding="Live-verified router output: population=elderly.",
        expected_population="elderly",
    ),
)
