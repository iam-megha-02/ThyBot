from unittest.mock import patch

from langchain_core.documents import Document

from utils.knowledge_base import (
    POPULATION_ELDERLY,
    POPULATION_GENERAL,
    POPULATION_MATERNAL,
    POPULATION_PEDIATRIC,
    PopulationIndex,
    _combine_dedupe,
    _tokenize,
    list_source_pdfs,
    retrieve_with_population_filter,
    tag_population,
)


def test_maternal_document_tagged_correctly():
    assert tag_population("Maternal_Thyroid_Guidelines.pdf") == POPULATION_MATERNAL


def test_elderly_document_tagged_correctly():
    assert tag_population("Thyroid_Disease_Older_Patients.pdf") == POPULATION_ELDERLY


def test_pediatric_documents_tagged_correctly():
    assert tag_population("hyperthyroidism_children_adolescents_brochure.pdf") == POPULATION_PEDIATRIC
    assert tag_population("hypothyroidism-children-adolescents-brochure.pdf") == POPULATION_PEDIATRIC


def test_unlisted_document_defaults_to_general():
    assert tag_population("Goiter_brochure.pdf") == POPULATION_GENERAL
    assert tag_population("some_new_pdf_nobody_tagged.pdf") == POPULATION_GENERAL


def test_sample_lab_report_excluded_from_knowledge_base():
    sources = [p for p in list_source_pdfs("data")]
    assert not any("Thyroid-Report.pdf" in p for p in sources)


def test_real_data_directory_yields_the_expected_ten_clinical_pdfs():
    sources = list_source_pdfs("data")
    assert len(sources) == 10  # 11 PDFs bundled, minus the excluded sample report


def test_tokenize_lowercases_and_splits_on_word_boundaries():
    assert _tokenize("TSH levels: 4.5 mIU/L!") == ["tsh", "levels", "4", "5", "miu", "l"]


def _doc(text, population, source="test.pdf"):
    return Document(page_content=text, metadata={"population": population, "source": source})


def test_combine_dedupe_removes_exact_duplicates_across_lists():
    doc_a = _doc("shared content here", POPULATION_GENERAL)
    doc_b = _doc("different content", POPULATION_GENERAL)
    combined = _combine_dedupe([doc_a, doc_b], [doc_a])  # doc_a appears in both lists
    assert len(combined) == 2


def _population_index(texts_and_population):
    """Builds a real PopulationIndex (real BM25, fake FAISS) from
    (text, population) pairs — exercises the actual hybrid-candidate and
    dedupe logic, not just a stand-in."""
    documents = [_doc(text, population) for text, population in texts_and_population]

    class FakeFaiss:
        def similarity_search(self, query, k):
            return documents[:k]

    from rank_bm25 import BM25Okapi

    bm25 = BM25Okapi([_tokenize(d.page_content) for d in documents])
    return PopulationIndex(faiss=FakeFaiss(), bm25=bm25, documents=documents)


# Reranking (_rerank) uses a real cross-encoder model — mocked here as
# an identity pass-through so these tests stay fast and deterministic,
# same principle as mocking the LLM boundary elsewhere in this suite.
# The reranker itself is verified separately, live, not in this file.
@patch("utils.knowledge_base._rerank", side_effect=lambda query, candidates, top_k: candidates[:top_k])
def test_general_population_only_searches_the_general_index(_mock_rerank):
    indices = {
        POPULATION_GENERAL: _population_index([("general A", POPULATION_GENERAL), ("general B", POPULATION_GENERAL)]),
        POPULATION_MATERNAL: _population_index([("maternal A", POPULATION_MATERNAL)]),
    }
    results = retrieve_with_population_filter(indices, "query", population=POPULATION_GENERAL, k=4)
    assert all(r.metadata["population"] == POPULATION_GENERAL for r in results)
    assert len(results) == 2


@patch("utils.knowledge_base._rerank", side_effect=lambda query, candidates, top_k: candidates[:top_k])
def test_specific_population_never_competes_with_a_larger_general_index(_mock_rerank):
    # The actual bug this design fixes: a much larger general index
    # (many candidates) must never crowd out a smaller specific index's
    # results, since they're searched separately, not pooled first.
    indices = {
        POPULATION_GENERAL: _population_index([(f"general {i}", POPULATION_GENERAL) for i in range(50)]),
        POPULATION_MATERNAL: _population_index([("the only maternal chunk", POPULATION_MATERNAL)]),
    }
    results = retrieve_with_population_filter(indices, "query", population=POPULATION_MATERNAL, k=4)
    assert results[0].metadata["population"] == POPULATION_MATERNAL


@patch("utils.knowledge_base._rerank", side_effect=lambda query, candidates, top_k: candidates[:top_k])
def test_specific_population_tops_up_with_general_when_not_enough_specific_results(_mock_rerank):
    indices = {
        POPULATION_GENERAL: _population_index([("general A", POPULATION_GENERAL), ("general B", POPULATION_GENERAL)]),
        POPULATION_MATERNAL: _population_index([("the only maternal chunk", POPULATION_MATERNAL)]),
    }
    results = retrieve_with_population_filter(indices, "query", population=POPULATION_MATERNAL, k=3)
    assert len(results) == 3
    assert results[0].metadata["population"] == POPULATION_MATERNAL
    assert results[1].metadata["population"] == POPULATION_GENERAL
    assert results[2].metadata["population"] == POPULATION_GENERAL


@patch("utils.knowledge_base._rerank", side_effect=lambda query, candidates, top_k: candidates[:top_k])
def test_pediatric_chunks_never_leak_into_a_maternal_result(_mock_rerank):
    indices = {
        POPULATION_GENERAL: _population_index([("general info", POPULATION_GENERAL)]),
        POPULATION_MATERNAL: _population_index([("maternal info", POPULATION_MATERNAL)]),
        POPULATION_PEDIATRIC: _population_index([("pediatric info", POPULATION_PEDIATRIC)]),
    }
    results = retrieve_with_population_filter(indices, "query", population=POPULATION_MATERNAL, k=4)
    assert all(r.metadata["population"] != POPULATION_PEDIATRIC for r in results)


@patch("utils.knowledge_base._rerank", side_effect=lambda query, candidates, top_k: candidates[:top_k])
def test_missing_population_index_falls_back_to_general_only(_mock_rerank):
    # e.g. a population with zero source documents never got a
    # sub-index built at all — shouldn't KeyError, should just use general.
    indices = {POPULATION_GENERAL: _population_index([("general info", POPULATION_GENERAL)])}
    results = retrieve_with_population_filter(indices, "query", population=POPULATION_ELDERLY, k=2)
    assert len(results) == 1
    assert results[0].metadata["population"] == POPULATION_GENERAL


def test_bm25_candidates_actually_favor_lexical_term_overlap():
    # Real BM25, no mocking — a document that literally contains the
    # query term should score above ones that don't, even without dense
    # embedding similarity in play.
    #
    # Uses 3 documents, not 2: rank_bm25's BM25Okapi computes IDF as
    # log((N-n+0.5)/(n+0.5)), which is exactly zero whenever a term
    # appears in precisely half the corpus (discovered by an earlier,
    # accidental 2-document version of this test that hit exactly that
    # case and got a false failure — real corpora this small never
    # occur in the actual knowledge base, but the formula's zero-
    # crossing is a genuine BM25Okapi property worth knowing about).
    index = _population_index([
        ("this document discusses thyroid TSH levels specifically", POPULATION_GENERAL),
        ("this document is about something entirely unrelated", POPULATION_GENERAL),
        ("a third document, also unrelated to any lab values", POPULATION_GENERAL),
    ])
    scores = index.bm25.get_scores(_tokenize("TSH"))
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]
