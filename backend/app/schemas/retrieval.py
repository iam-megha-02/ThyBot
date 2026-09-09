from pydantic import BaseModel


class Chunk(BaseModel):
    text: str
    source_file: str
    chunk_index: int