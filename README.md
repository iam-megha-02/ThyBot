# ThyBot — Thyroid Care Copilot

A personalized, memory-driven assistant for thyroid patients: it reads your lab reports over time, tells you when it's safe to take your medication relative to food and other drugs, and answers clinical questions grounded in guideline documents — routed to the guideline that actually matches your situation (pregnancy, pediatric, elderly, or general).

Built as a demonstration of production AI engineering practice: multi-level retrieval, an LLM-based router with a deterministic fallback, layered safety guardrails, hybrid search with reranking, and an evaluation harness that catches real regressions — not just a chatbot wrapper.

**This is patient decision-support and education, not diagnosis or treatment.** Every clinical answer carries a standing disclaimer, and anything resembling an emergency symptom or a dosage question is blocked before it ever reaches the model.

## Architecture

```
User message
     │
     ▼
Input guardrail (deterministic, no LLM call) ──blocked──▶ fixed safe response
     │ not blocked
     ▼
Router (single LLM classification call)
     │
     ├─ needs_lab_history?      ──▶ Postgres lab history ──▶ trend-grounded answer
     ├─ needs_document_context? ──▶ per-session uploaded-PDF RAG
     └─ otherwise                ──▶ persistent clinical knowledge base
                                       (population-routed: general/maternal/pediatric/elderly
                                        → hybrid BM25 + dense search → cross-encoder rerank)
                                       │ no relevant chunks found
                                       ▼
                                     web search fallback (confidence-gated, best-effort)
                                       │ still nothing
                                       ▼
                                     plain chat (ungrounded, last resort)
     │
     ▼
Output guardrail (disclaimer enforced in code) ──▶ shown to user, with citations
```

## Features

- **Chat** — grounded Q&A with citations, routed per-message to the right context source
- **Lab Reports** — upload a report, extract TSH/T3/T4 automatically, track trends over time
- **Medications** — deterministic levothyroxine timing-interaction lookup (calcium, iron, coffee, PPIs, etc.)
- **Patient Profile** — manual lab entry with rule-based thyroid-status classification
- **Meal Analysis** — thyroid-impact lookup for Indian dishes (goitrogen/iodine-source categories cited against real nutrition literature), plus a medication-timing cross-check using the dataset's own measured calcium/iron values

## Observability

Every chat message logs a structured trace (`data/traces.jsonl`) — one JSON line per step (guardrail check, router decision, retrieval, generation), sharing a `trace_id` so a full request can be reconstructed. Chosen over self-hosted Langfuse deliberately: current Langfuse needs 5 services (web, worker, Postgres, ClickHouse, Redis, S3-compatible storage), which is real infra weight this project's own design principle argues against building without the scale to justify it.

## Running it

### Docker Compose (recommended)

```bash
cp .env.example .env   # then add a real GROQ_API_KEY
docker compose up -d --build
```

Open http://localhost:8501. The clinical knowledge base (10 bundled guideline PDFs) is built into the image at build time, so there's no manual post-deploy step.

### Local dev (without Docker)

```bash
pip install -r requirements.txt
docker compose up -d postgres          # just the database
python -m scripts.build_knowledge_base  # one-time, ~1-2 min
streamlit run app.py
```

## Environment variables

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | LLM calls (chat, routing) — get one at [console.groq.com](https://console.groq.com) |
| `DATABASE_URL` | Postgres connection string for lab history |

See `.env.example`.

## Testing

```bash
pytest tests/           # 84 tests, fast, fully mocked — no network calls, no cost
python -m eval.run_eval  # slower, real Groq calls + real retrieval — run before a release, not every commit
```

CI (`.github/workflows/ci.yml`) runs `pytest tests/` on every push and PR.

## Project structure

```
app.py                      Streamlit UI, page routing, chat orchestration
models/llm.py                Groq client wrapper + JSON-mode classification helper
models/db_models.py           SQLAlchemy schema (Patient, LabResultRecord — append-only)
utils/
  router.py                    Intent classification (single LLM call, keyword-heuristic fallback)
  guardrails.py                 Input safety gate + output disclaimer enforcement
  knowledge_base.py              Population-routed hybrid search + reranking
  lab_extraction.py               Regex-based TSH/T3/T4 extraction from PDF text
  lab_history.py                   Postgres persistence + trend-question detection
  medication_timing.py              Deterministic drug/food interaction lookup
  web_search.py                      DuckDuckGo fallback, hard-timeout wrapped
  rag_utils.py                        Per-session upload RAG (separate from the persistent KB)
  observability.py                  Structured JSON trace logging, no new infra
eval/                          Golden-set regression harness
scripts/
  build_knowledge_base.py       Ingests data/*.pdf into the persistent index
  add_thyroid_impact.py          Tags the meal dataset (goitrogen/iodine categories + real calcium/iron cross-check)
tests/                        84 unit tests, all mocked/fast/free
```

## Known limitations

- **No real patient authentication** — every lab result belongs to a single shared "default" patient row. Fine for a local demo, not for anything multi-user.
- **Web search fallback is unreliable** — DuckDuckGo has no official free API; expect it to fail (rate-limited) more often than it succeeds. It fails fast and falls through to plain chat rather than hanging, but it is not a dependable retrieval source.
- **No CI-gated eval** — `eval/run_eval.py` catches real regressions but isn't wired into CI (it costs real tokens per run); `pytest tests/` is CI-gated via `.github/workflows/ci.yml`.
- **No per-dish iodine data** — checked against [IFCT 2017](https://github.com/nodef/ifct2017) (the free, open, authoritative Indian food composition database) before building this: it has no iodine column at all (iodine content varies too much by soil/water to reliably tabulate), and its 528 entries are raw ingredients, not the prepared dishes this app's dataset lists. Goitrogen/iodine-source status stays a cited category tag rather than a fabricated per-gram number.
