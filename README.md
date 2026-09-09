# ThyBot

A thyroid health Q&A assistant. It answers questions using only what's actually written in a set of clinical PDFs (guidelines and patient brochures).It doesn't make things up, and it refuses to give personal medical advice like dosage changes.

FastAPI backend and Streamlit chat frontend.

## How it works

1. **Retrieval** - nine clinical PDFs are chunked and indexed two ways: dense (sentence-transformer embeddings + FAISS) and sparse (BM25). Results from both are combined with reciprocal rank fusion.
2. **Guardrails** - before anything reaches the LLM, the question is checked for:
   - **Emergency** language (chest pain, trouble breathing, suicidal ideation, etc.) → redirected to emergency services, not answered.
   - **Personal dosage** requests ("should I increase my dose?") → refused, redirected to a doctor.
   - **Out-of-scope** questions (nothing to do with the thyroid) → refused.
   
   These use keyword matching plus a semantic similarity check against reference phrases, so paraphrased versions still get caught.
3. **Generation** - if a question passes the guardrails, the retrieved chunks and the question go to an LLM (via Groq) to produce a grounded answer with sources.

See [backend/eval/README.md](backend/eval/README.md) for how all of this is tested, and [backend/eval/results/BASELINE.md](backend/eval/results/BASELINE.md) for the latest results.

## Project layout

```
backend/
  app/
    api/            FastAPI routes (/chat, /health)
    services/       retrieval, chunking, guardrails, LLM calls
    schemas/        request/response models
    core/config.py  settings (reads backend/.env)
  eval/             question sets + evaluation runner (see its own README)
frontend/
  app.py            Streamlit chat UI
  api_client.py     talks to the backend
data/
  clinical_documents/   the source PDFs
```

## Setup

Requires Python 3.11+ and a [Groq](https://console.groq.com/) API key.

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

Create `backend/.env`:

```
GROQ_API_KEY=your-key-here
```

## Running it

Start the backend from `backend/` (loads the PDFs and builds the indexes on startup, so the first run takes a bit):

```powershell
cd backend
..\venv\Scripts\uvicorn app.main:app --reload
```

Start the frontend in a separate terminal from `frontend/`:

```powershell
cd frontend
..\venv\Scripts\streamlit run app.py
```

The frontend talks to `http://127.0.0.1:8000` by default — set `THYBOT_BACKEND_URL` if the backend is elsewhere.

## Evaluation

There's a full evaluation harness under `backend/eval/` with 100 hand-reviewed questions covering answerable questions, paraphrases, dosage requests, emergencies, out-of-scope questions, and boundary cases. It checks retrieval accuracy, guardrail routing, and answer quality (via Ragas). Details and commands are in [backend/eval/README.md](backend/eval/README.md).

## Disclaimer

This is an educational tool built on public clinical documents. It is not a substitute for professional medical advice, and it will not act as one — that's the point of the guardrails.
