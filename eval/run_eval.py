"""
Runs the golden set against the REAL live stack — real persisted FAISS
index, real Groq calls through utils.router.classify_intent. Not part
of the default `pytest tests/` run: it costs real tokens and hits the
network, so it's a deliberate, occasional check (before a release,
after touching prompts/retrieval/embeddings), not a per-commit gate.

    python -m eval.run_eval

Exits non-zero if anything regresses, so it's usable as a CI step
later even though nothing wires it into CI today.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()

from eval.golden_set import GOLDEN_SET
from utils.knowledge_base import load_knowledge_base, retrieve_with_population_filter, POPULATION_GENERAL
from utils.router import classify_intent


def _check_retrieval(index, case) -> tuple:
    if case.expected_source_contains is None:
        return None  # not checked for this case
    population = case.expected_population or POPULATION_GENERAL
    results = retrieve_with_population_filter(index, case.question, population)
    sources = [r.metadata.get("source", "") for r in results]
    passed = any(case.expected_source_contains in s for s in sources)
    return passed, sources


def _check_routing(case) -> tuple:
    checks_requested = any(
        v is not None
        for v in (case.expected_population, case.expected_needs_lab_history, case.expected_needs_document_context)
    )
    if not checks_requested:
        return None

    decision = classify_intent(case.question, case.has_uploaded_document)
    failures = []
    if case.expected_population is not None and decision.population != case.expected_population:
        failures.append(f"population: expected {case.expected_population!r}, got {decision.population!r}")
    if case.expected_needs_lab_history is not None and decision.needs_lab_history != case.expected_needs_lab_history:
        failures.append(
            f"needs_lab_history: expected {case.expected_needs_lab_history!r}, got {decision.needs_lab_history!r}"
        )
    if (
        case.expected_needs_document_context is not None
        and decision.needs_document_context != case.expected_needs_document_context
    ):
        failures.append(
            f"needs_document_context: expected {case.expected_needs_document_context!r}, "
            f"got {decision.needs_document_context!r}"
        )
    return (len(failures) == 0, failures)


def main() -> int:
    print(f"Loading persisted clinical knowledge base...")
    index = load_knowledge_base()

    retrieval_results = []
    routing_results = []

    for case in GOLDEN_SET:
        print(f"\n--- {case.question!r} ---")

        retrieval_outcome = _check_retrieval(index, case)
        if retrieval_outcome is not None:
            passed, sources = retrieval_outcome
            retrieval_results.append(passed)
            status = "PASS" if passed else "FAIL"
            print(f"  [retrieval {status}] expected source containing {case.expected_source_contains!r}")
            print(f"                 got sources: {sources}")

        routing_outcome = _check_routing(case)
        if routing_outcome is not None:
            passed, failures = routing_outcome
            routing_results.append(passed)
            status = "PASS" if passed else "FAIL"
            print(f"  [routing   {status}]" + ("" if passed else f" {failures}"))

    retrieval_hits = sum(retrieval_results)
    routing_hits = sum(routing_results)

    print("\n" + "=" * 60)
    print(f"Retrieval hit rate: {retrieval_hits}/{len(retrieval_results)}")
    print(f"Routing accuracy:   {routing_hits}/{len(routing_results)}")
    print("=" * 60)

    all_passed = retrieval_hits == len(retrieval_results) and routing_hits == len(routing_results)
    if not all_passed:
        print("\nREGRESSION DETECTED — see FAIL lines above.")
        return 1

    print("\nAll golden-set cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
