from pathlib import Path
from app.services.document_loader import load_all_documents
from app.services.chunking import recursive_chunk_all_documents
from app.services.dense_retrieval import DenseIndex
from app.services.sparse_retrieval import BM25Index
from app.services.hybrid_retrieval import reciprocal_rank_fusion
from app.schemas.retrieval import Chunk

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "clinical_documents"
POOL_SIZE = 10
RRF_K = 60

class RetrievalService:
    def __init__(self):
        documents = load_all_documents(DATA_DIR)
        self.chunks: list[Chunk] = recursive_chunk_all_documents(documents)
        self.dense_index = DenseIndex(self.chunks)
        self.sparse_index = BM25Index(self.chunks)

    def retrieve(self, query: str, top_k: int = 3) -> list[Chunk]:
        dense_results = self.dense_index.search(query, top_k=POOL_SIZE)
        sparse_results = self.sparse_index.search(query, top_k=POOL_SIZE)
        return reciprocal_rank_fusion(dense_results, sparse_results, k=RRF_K, top_k=top_k)

retrieval_service = RetrievalService()