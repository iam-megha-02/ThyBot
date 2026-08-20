"""
Lightweight structured tracing — no new infrastructure.

Chose this over self-hosted Langfuse deliberately: current Langfuse
needs 5 services (web, worker, Postgres, ClickHouse, Redis, S3-
compatible storage), which is real infra weight for a project whose
own design principle (see the architecture blueprint's "what NOT to
build" section) is not reaching for infrastructure the actual scale
doesn't justify — doubly true given real resource constraints on the
deploy target. One JSON line per event, appended to a local file,
captures most of the same debugging value: what happened, in what
order, how long each step took.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path("data") / "traces.jsonl"


def _write(event: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


def new_trace_id() -> str:
    """One trace_id per user message — every span below shares it, so a
    single request's full journey can be reconstructed by filtering."""
    return uuid.uuid4().hex[:12]


@contextmanager
def span(trace_id: str, name: str, **metadata):
    """
    Wraps one step (router call, retrieval, generation, guardrail
    check) and logs its duration and outcome. Exceptions are logged
    and re-raised — this must never swallow an error just because it's
    also being observed.

    Yields a mutable dict the caller can fill in with result-derived
    metadata (e.g. the population the router picked), since that's
    only known *after* the wrapped call completes, unlike the
    **metadata kwargs which are only ever known going in.
    """
    start = time.monotonic()
    context: dict = {}
    try:
        yield context
    except Exception as exc:
        _write({
            "trace_id": trace_id,
            "span": name,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "duration_ms": round((time.monotonic() - start) * 1000, 1),
            **metadata,
            **context,
        })
        raise
    else:
        _write({
            "trace_id": trace_id,
            "span": name,
            "status": "ok",
            "duration_ms": round((time.monotonic() - start) * 1000, 1),
            **metadata,
            **context,
        })
