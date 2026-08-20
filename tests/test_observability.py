import json

import pytest

from utils.observability import new_trace_id, span


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setattr("utils.observability.LOG_PATH", path)
    return path


def _read_events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_new_trace_id_is_a_short_hex_string():
    trace_id = new_trace_id()
    assert len(trace_id) == 12
    int(trace_id, 16)  # doesn't raise -> valid hex


def test_new_trace_id_is_unique_per_call():
    assert new_trace_id() != new_trace_id()


def test_span_logs_duration_and_ok_status(log_path):
    trace_id = new_trace_id()
    with span(trace_id, "router", population="general"):
        pass

    events = _read_events(log_path)
    assert len(events) == 1
    assert events[0]["trace_id"] == trace_id
    assert events[0]["span"] == "router"
    assert events[0]["status"] == "ok"
    assert events[0]["population"] == "general"
    assert events[0]["duration_ms"] >= 0
    assert "timestamp" in events[0]


def test_span_logs_error_and_still_reraises(log_path):
    trace_id = new_trace_id()

    with pytest.raises(ValueError, match="boom"):
        with span(trace_id, "retrieval"):
            raise ValueError("boom")

    events = _read_events(log_path)
    assert events[0]["status"] == "error"
    assert "boom" in events[0]["error"]


def test_span_context_dict_captures_result_derived_metadata(log_path):
    # e.g. the router's chosen population is only known after the call
    # completes, not before — this must land in the log line too.
    trace_id = new_trace_id()
    with span(trace_id, "router") as ctx:
        ctx["population"] = "maternal"
        ctx["intent_label"] = "clinical_question"

    events = _read_events(log_path)
    assert events[0]["population"] == "maternal"
    assert events[0]["intent_label"] == "clinical_question"


def test_multiple_spans_share_one_trace_id(log_path):
    trace_id = new_trace_id()
    with span(trace_id, "router"):
        pass
    with span(trace_id, "retrieval"):
        pass

    events = _read_events(log_path)
    assert len(events) == 2
    assert events[0]["trace_id"] == events[1]["trace_id"] == trace_id
    assert [e["span"] for e in events] == ["router", "retrieval"]
