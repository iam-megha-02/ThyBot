"""
One-time (or re-run-on-demand) ingestion of the clinical PDFs in data/
into a persistent, population-tagged FAISS index on disk.

Not run automatically at app startup — embedding ~10 PDFs is slow.
Run manually whenever data/*.pdf changes:

    python scripts/build_knowledge_base.py
"""

from utils.knowledge_base import DEFAULT_INDEX_PATH, build_knowledge_base, list_source_pdfs

if __name__ == "__main__":
    sources = list_source_pdfs()
    print(f"Building knowledge base from {len(sources)} clinical PDFs...")
    for path in sources:
        print(f"  - {path}")

    counts = build_knowledge_base()
    print(f"\nIndexed to {DEFAULT_INDEX_PATH}:")
    for population, count in counts.items():
        print(f"  {population:10} {count} chunks")
