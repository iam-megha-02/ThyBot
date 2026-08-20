"""
Persistent, population-aware clinical knowledge base built from the
PDFs bundled in data/.

Unlike utils/rag_utils.py's per-session RAG (built fresh, in memory,
from whatever a user uploads this session), this index is built once
offline via scripts/build_knowledge_base.py and loaded from disk at
runtime — the persistent index the original repo shipped a stub for
(data/faiss_index.pkl) but never actually wired up.

One FAISS index PER population tag, not one shared index filtered
after search: an earlier shared-index design let the two largest
documents (Maternal_Thyroid_Guidelines.pdf: 169 chunks,
Depression_Guidelines.pdf: 131 chunks — 58% of the whole corpus)
dominate the top-k candidate pool and crowd out the much smaller
pediatric/elderly documents (18-21 chunks each) entirely, even though
the population *label* was being detected correctly. Caught by the
eval harness (eval/run_eval.py), not by manual spot-checks, which had
only probed the two largest — and therefore "safe" — populations.
"""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from functools import lru_cache

from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from utils.rag_utils import get_embedding_model

POPULATION_GENERAL = "general"
POPULATION_MATERNAL = "maternal"
POPULATION_PEDIATRIC = "pediatric"
POPULATION_ELDERLY = "elderly"
POPULATIONS = (POPULATION_GENERAL, POPULATION_MATERNAL, POPULATION_PEDIATRIC, POPULATION_ELDERLY)

# Filename -> population tag. Deliberately explicit and human-curated —
# these filenames already say who each document is for; guessing
# population from PDF content when the answer is already in the name
# would be needless complexity.
_POPULATION_BY_FILENAME = {
    "Maternal_Thyroid_Guidelines.pdf": POPULATION_MATERNAL,
    "Thyroid_Disease_Older_Patients.pdf": POPULATION_ELDERLY,
    "hyperthyroidism_children_adolescents_brochure.pdf": POPULATION_PEDIATRIC,
    "hypothyroidism-children-adolescents-brochure.pdf": POPULATION_PEDIATRIC,
}

# Not clinical guidance — a sample patient lab report bundled for the
# lab-extraction feature, excluded from the knowledge base entirely.
_EXCLUDED_FILENAMES = {"Thyroid-Report.pdf"}

DEFAULT_INDEX_PATH = os.path.join("data", "clinical_index")


def tag_population(filename: str) -> str:
    return _POPULATION_BY_FILENAME.get(filename, POPULATION_GENERAL)


def list_source_pdfs(data_dir: str = "data") -> list:
    paths = sorted(glob.glob(os.path.join(data_dir, "*.pdf")))
    return [p for p in paths if os.path.basename(p) not in _EXCLUDED_FILENAMES]


def build_knowledge_base(data_dir: str = "data", index_path: str = DEFAULT_INDEX_PATH) -> dict:
    """
    Chunk + tag every clinical PDF in data_dir, then build one FAISS
    index per population tag (saved as a subdirectory each) so a small
    population-specific document is never competing against a much
    larger unrelated one for a spot in the results. Not called
    automatically at app startup — run via
    scripts/build_knowledge_base.py. Returns chunk counts per population.
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks_by_population = {p: [] for p in POPULATIONS}

    for path in list_source_pdfs(data_dir):
        filename = os.path.basename(path)
        population = tag_population(filename)
        pages = PyPDFLoader(path).load()
        chunks = splitter.split_documents(pages)
        for chunk in chunks:
            chunk.metadata["source"] = filename
            chunk.metadata["population"] = population
        chunks_by_population[population].extend(chunks)

    embedding_model = get_embedding_model()
    counts = {}
    for population, chunks in chunks_by_population.items():
        counts[population] = len(chunks)
        if chunks:
            sub_index = FAISS.from_documents(chunks, embedding_model)
            sub_index.save_local(os.path.join(index_path, population))

    if sum(counts.values()) == 0:
        raise RuntimeError(f"No clinical PDFs found in {data_dir!r} to build a knowledge base from.")
    return counts


@dataclass
class PopulationIndex:
    """One population's retrieval surface: dense (FAISS) + lexical
    (BM25) over the same chunk set. BM25 is rebuilt from the FAISS
    docstore at load time rather than persisted separately — building
    a BM25 index over ~500 chunks is milliseconds, so there's nothing
    worth saving to disk."""

    faiss: FAISS
    bm25: BM25Okapi
    documents: list


def _tokenize(text: str) -> list:
    return re.findall(r"\w+", text.lower())


def load_knowledge_base(index_path: str = DEFAULT_INDEX_PATH) -> dict:
    """Returns {population: PopulationIndex} for every population with a built sub-index."""
    embedding_model = get_embedding_model()
    indices = {}
    for population in POPULATIONS:
        sub_path = os.path.join(index_path, population)
        if not os.path.isdir(sub_path):
            continue
        faiss_index = FAISS.load_local(sub_path, embedding_model, allow_dangerous_deserialization=True)
        documents = list(faiss_index.docstore._dict.values())
        bm25 = BM25Okapi([_tokenize(d.page_content) for d in documents])
        indices[population] = PopulationIndex(faiss=faiss_index, bm25=bm25, documents=documents)
    return indices


@lru_cache(maxsize=1)
def _get_reranker() -> CrossEncoder:
    """Loaded on first use, same lazy pattern as the embedding model —
    a cross-encoder is a second, separate small model, no reason to
    pay its load cost for pages that never retrieve anything."""
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def _rerank(query: str, candidates: list, top_k: int) -> list:
    """
    Cross-encoder reranking: unlike the bi-encoder FAISS search (query
    and document embedded separately, then compared — fast but less
    precise), a cross-encoder scores each (query, document) pair
    together, which is far more accurate but too slow to run over an
    entire corpus. Used here only on the small candidate pool the fast
    stage below already narrowed down.
    """
    if not candidates:
        return []
    reranker = _get_reranker()
    pairs = [[query, c.page_content] for c in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
    return [doc for doc, _score in ranked[:top_k]]


def _combine_dedupe(*candidate_lists) -> list:
    seen = set()
    combined = []
    for candidates in candidate_lists:
        for doc in candidates:
            key = (doc.metadata.get("source"), doc.page_content[:100])
            if key not in seen:
                seen.add(key)
                combined.append(doc)
    return combined


def _hybrid_candidates(pop_index: PopulationIndex, query: str, fetch_k: int) -> list:
    """Dense + lexical candidates for one population, combined and deduped."""
    dense = pop_index.faiss.similarity_search(query, k=fetch_k)

    bm25_scores = pop_index.bm25.get_scores(_tokenize(query))
    ranked_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)
    lexical = [pop_index.documents[i] for i in ranked_indices[:fetch_k] if bm25_scores[i] > 0]

    return _combine_dedupe(dense, lexical)


def retrieve_with_population_filter(indices: dict, query: str, population: str, k: int = 4, fetch_k: int = 10) -> list:
    """
    Hybrid retrieval (dense + BM25) per population sub-index, reranked
    with a cross-encoder for final precision. Searches the population-
    specific sub-index first — guaranteed not to be crowded out by a
    larger, unrelated document, since each sub-index only contains its
    own population's chunks — then tops up with general-index results
    if there aren't enough specific matches.
    """
    results = []
    if population != POPULATION_GENERAL and population in indices:
        candidates = _hybrid_candidates(indices[population], query, fetch_k)
        results = _rerank(query, candidates, k)

    if len(results) < k and POPULATION_GENERAL in indices:
        remaining = k - len(results)
        general_candidates = _hybrid_candidates(indices[POPULATION_GENERAL], query, fetch_k)
        results.extend(_rerank(query, general_candidates, remaining))

    return results[:k]
