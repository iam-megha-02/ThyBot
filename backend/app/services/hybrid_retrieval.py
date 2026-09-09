from app.schemas.retrieval import Chunk


def chunk_key(chunk: Chunk) -> tuple:
    return (chunk.source_file, chunk.chunk_index)


def reciprocal_rank_fusion(
    dense_results: list[Chunk],
    sparse_results: list[Chunk],
    k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
    top_k: int = 3,
) -> list[Chunk]:
    scores: dict[tuple, float] = {}
    chunk_lookup: dict[tuple, Chunk] = {}

    for rank, chunk in enumerate(dense_results):
        key = chunk_key(chunk)
        scores[key] = scores.get(key, 0.0) + dense_weight * (1 / (k + rank))
        chunk_lookup[key] = chunk

    for rank, chunk in enumerate(sparse_results):
        key = chunk_key(chunk)
        scores[key] = scores.get(key, 0.0) + sparse_weight * (1 / (k + rank))
        chunk_lookup[key] = chunk

    ranked_keys = sorted(scores.keys(), key=lambda key: scores[key], reverse=True)
    return [chunk_lookup[key] for key in ranked_keys[:top_k]]