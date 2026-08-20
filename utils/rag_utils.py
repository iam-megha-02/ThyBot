from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
import tempfile
from functools import lru_cache

@lru_cache(maxsize=1)
def get_embedding_model():
    """Loaded on first actual use, not at import time — pages that
    don't touch RAG (Lab Reports, Medications) shouldn't pay the cost
    of loading a sentence-transformers model just by importing this
    module. Shared with utils/knowledge_base.py so both the per-session
    upload index and the persistent clinical index use the same model."""
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

def _load_pdf_pages(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
    return PyPDFLoader(tmp_path).load()

def load_and_split_pdf(uploaded_file):
    pages = _load_pdf_pages(uploaded_file)
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(pages)
    return chunks

def load_pdf_text(uploaded_file):
    """Raw text, unchunked — for structured extraction (lab values) rather than RAG."""
    pages = _load_pdf_pages(uploaded_file)
    return "\n".join(page.page_content for page in pages)

def embed_chunks(chunks):
    return FAISS.from_documents(chunks, _get_embedding_model())

def retrieve_relevant_chunks(query, faiss_index, k=4):
    return faiss_index.similarity_search(query, k=k)
