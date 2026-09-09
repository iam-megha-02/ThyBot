import re
from rank_bm25 import BM25Okapi
from app.schemas.retrieval import Chunk


def tokenize(text: str) -> list[str]:
    """Simple, transparent tokenization: lowercase, strip punctuation,
    split on whitespace. Not linguistically sophisticated (no stemming,
    no stopword removal) — deliberately simple enough to fully explain
    if asked, and sufficient to demonstrate BM25's real behavior."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return text.split()


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        tokenized_corpus = [tokenize(chunk.text) for chunk in chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, top_k: int = 3) -> list[Chunk]:
        tokenized_query = tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [self.chunks[i] for i in top_indices]