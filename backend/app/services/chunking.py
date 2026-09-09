import re
from app.schemas.retrieval import Chunk


def chunk_text(text: str, source_file: str, chunk_size: int = 800, overlap: int = 100) -> list[Chunk]:
    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = start + chunk_size
        chunk_text_piece = text[start:end].strip()

        if chunk_text_piece:
            chunks.append(Chunk(
                text=chunk_text_piece,
                source_file=source_file,
                chunk_index=chunk_index,
            ))
            chunk_index += 1

        start += chunk_size - overlap

    return chunks


def chunk_all_documents(documents: dict[str, str]) -> list[Chunk]:
    all_chunks = []
    for filename, text in documents.items():
        all_chunks.extend(chunk_text(text, source_file=filename))
    return all_chunks


def split_into_sentences(text: str) -> list[str]:
    """
    Naive sentence splitter: breaks on '.', '!', '?' followed by whitespace.
    Not perfect (e.g., 'Dr. Smith' would incorrectly split), but genuinely
    good enough for this corpus — the final fallback when a piece has no
    paragraph or line breaks to split on at all.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _split_on_separator(text: str, separator: str) -> list[str]:
    if not separator:
        return [text]
    return [piece for piece in text.split(separator) if piece.strip()]


def recursive_chunk_text(text: str, source_file: str, target_size: int = 800, overlap_sentences: int = 1) -> list[Chunk]:
    """
    Tries paragraph breaks first, then single newlines, then sentences —
    only falling back to a finer-grained split when a piece is still too
    large after trying the coarser one.
    """
    separators = ["\n\n", "\n"]

    def split_recursively(piece: str, remaining_separators: list[str]) -> list[str]:
        if len(piece) <= target_size:
            return [piece]
        if not remaining_separators:
            return split_into_sentences(piece)

        separator = remaining_separators[0]
        sub_pieces = _split_on_separator(piece, separator)

        if len(sub_pieces) == 1:
            return split_recursively(piece, remaining_separators[1:])

        result = []
        for sub_piece in sub_pieces:
            result.extend(split_recursively(sub_piece, remaining_separators[1:]))
        return result

    raw_pieces = split_recursively(text, separators)

    chunks = []
    current_pieces: list[str] = []
    current_length = 0
    chunk_index = 0

    for piece in raw_pieces:
        piece = piece.strip()
        if not piece:
            continue
        if current_length + len(piece) > target_size and current_pieces:
            chunk_body = " ".join(current_pieces)
            chunks.append(Chunk(text=chunk_body, source_file=source_file, chunk_index=chunk_index))
            chunk_index += 1
            current_pieces = current_pieces[-overlap_sentences:] if overlap_sentences else []
            current_length = sum(len(p) for p in current_pieces)

        current_pieces.append(piece)
        current_length += len(piece)

    if current_pieces:
        chunk_body = " ".join(current_pieces)
        chunks.append(Chunk(text=chunk_body, source_file=source_file, chunk_index=chunk_index))

    return chunks


def recursive_chunk_all_documents(documents: dict[str, str]) -> list[Chunk]:
    all_chunks = []
    for filename, text in documents.items():
        all_chunks.extend(recursive_chunk_text(text, source_file=filename))
    return all_chunks