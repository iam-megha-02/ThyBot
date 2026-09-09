from pathlib import Path
from pypdf import PdfReader


def load_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            full_text += page_text + "\n"
    return full_text


def load_all_documents(directory: Path) -> dict[str, str]:
    documents = {}
    for pdf_path in sorted(directory.glob("*.pdf")):
        documents[pdf_path.name] = load_pdf_text(pdf_path)
    return documents