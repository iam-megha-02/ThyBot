<p align="center">
  <img src="frontend/assets/logo.png" alt="ThyBot logo" width="120">
</p>

<h1 align="center">ThyBot</h1>

ThyBot answers questions about thyroid health using real medical documents, it doesn't just make things up. If you ask something outside that scope, something that sounds like a medical emergency, or something like "what dose should I take," it won't try to answer. It'll point you somewhere safer instead.

## How it works

Think of it as three steps:

1. **Find relevant text (retrieval)** - Nine thyroid-related PDFs are split into small chunks and searched two ways: a "meaning-based" search (dense embeddings + FAISS) and a "keyword-based" search (BM25). Their results get merged using a ranking trick called reciprocal rank fusion, so the best chunks from either method rise to the top.
2. **Safety checks (guardrails)** - Before any question reaches the AI model, it's checked for:
   - **Emergency language** (chest pain, can't breathe, thoughts of self-harm) → tells you to get real help immediately, no AI answer.
   - **Personal dosage questions** ("should I increase my dose?") → refused, redirected to a doctor.
   - **Anything unrelated to the thyroid** → refused, politely.
   
   These checks use keyword matching plus a semantic similarity check (comparing what your question *means* to a set of example phrases), so a reworded version of the same request still gets caught.
3. **Answer generation** - If a question passes the checks, the retrieved text chunks and your question go to an LLM (via Groq), which writes an answer grounded only in that text, plus a list of sources.

Curious how well this actually works? See [backend/eval/README.md](backend/eval/README.md) for how it's tested, and [backend/eval/results/BASELINE.md](backend/eval/results/BASELINE.md) for the results.

## Tech stack

- **UI**: [Streamlit](https://streamlit.io/)
- **PDF parsing**: [pypdf](https://pypdf.readthedocs.io/)
- **Meaning-based search**: [sentence-transformers](https://www.sbert.net/) for embeddings + [FAISS](https://github.com/facebookresearch/faiss) for the vector index
- **Keyword-based search**: [rank_bm25](https://github.com/dorianbrown/rank_bm25)
- **LLM**: [Groq](https://groq.com/) (fast inference, currently `qwen/qwen3.8-27b` for answers)
- **Config**: [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) + python-dotenv, reading a `.env` file
- **Answer-quality evaluation**: [Ragas](https://docs.ragas.io/) (only needed if you run the eval suite, not the app itself)

## Project layout

```
backend/
  app/
    services/        the actual logic: retrieval, chunking, guardrails, calling the LLM
    schemas/          one shared data shape (a "Chunk")
    core/config.py    reads settings/secrets from .env in the project root
  eval/               test questions + the script that runs evaluations (see its own README)
frontend/
  app.py              the Streamlit app - what you see and click
  assistant.py        glue code: guardrails -> retrieval -> generation, in the same process
data/
  clinical_documents/   the 9 source PDFs everything is grounded in
```

## Setup

You'll need Python 3.11+ and a free [Groq](https://console.groq.com/) API key.

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

Then create a `.env` file in the project root with your key:

```
GROQ_API_KEY=your-key-here
```

## Running it

One command, from the project root:

```powershell
.\venv\Scripts\streamlit run frontend/app.py
```

The first run takes a bit longer, it's reading all the PDFs and building the search indexes. After that, it keeps everything in memory, so it's fast.

## Evaluation

There's a full test suite under `backend/eval/` - 100 questions, written and reviewed by hand, covering normal questions, reworded questions, dosage requests, emergencies, off-topic questions, and tricky edge cases. It checks whether retrieval finds the right document, whether guardrails route things correctly, and how good the generated answers are (using Ragas). Details and commands are in [backend/eval/README.md](backend/eval/README.md).

## Disclaimer

This is a learning project built on public clinical documents, not a real medical tool. It's not a substitute for talking to an actual doctor, the guardrails exist specifically to make sure it never tries to be one.
