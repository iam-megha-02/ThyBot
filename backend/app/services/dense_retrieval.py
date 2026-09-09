import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from app.schemas.retrieval import Chunk


class DenseIndex:
    def __init__(self, chunks: list[Chunk], model_name: str = "all-MiniLM-L6-v2"):
        self.chunks = chunks
        self.model = SentenceTransformer(model_name)

        embeddings = self.model.encode([c.text for c in chunks], convert_to_numpy=True)
        embeddings = embeddings.astype("float32")
        faiss.normalize_L2(embeddings)

        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings)

    def search(self, query: str, top_k: int = 10) -> list[Chunk]:
        query_embedding = self.model.encode([query], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(query_embedding)

        _, indices = self.index.search(query_embedding, top_k)
        return [self.chunks[i] for i in indices[0]]

    def search_with_scores(self, query: str, top_k: int = 1) -> list[tuple[Chunk, float]]:
        query_embedding = self.model.encode([query], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(query_embedding)
        scores, indices = self.index.search(query_embedding, top_k)
        return [(self.chunks[i], float(scores[0][j])) for j, i in enumerate(indices[0])]