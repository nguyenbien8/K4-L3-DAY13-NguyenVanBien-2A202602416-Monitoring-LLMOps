from __future__ import annotations

from contextlib import contextmanager

import pytest

from app import agent as agent_module
from app.incidents import STATE


class RecordedObservation:
    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class ObservationClient:
    def __init__(self) -> None:
        self.observations: list[RecordedObservation] = []

    def get_prompt(self, name: str, **kwargs):
        raise TimeoutError("offline")

    def update_current_span(self, **kwargs) -> None:
        return None

    def get_current_trace_id(self) -> str:
        return "trace-abc"

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        observation = RecordedObservation(kwargs)
        self.observations.append(observation)
        yield observation


def _run(monkeypatch, message: str):
    client = ObservationClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)
    agent = agent_module.LabAgent()
    result = agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message=message,
        correlation_id="req-12345678",
    )
    return client, result


def test_run_creates_retrieval_and_generation_children(monkeypatch) -> None:
    client, result = _run(monkeypatch, "Refund policy? mail me at a.b@example.com")

    retrieval, generation = client.observations
    assert retrieval.kwargs["as_type"] == "retriever"
    assert retrieval.updates[-1]["output"] == {"doc_count": 1}

    assert generation.kwargs["as_type"] == "generation"
    assert generation.kwargs["model"] == "claude-sonnet-4-5"
    usage = generation.updates[-1]["usage_details"]
    assert usage["input_tokens"] == result.tokens_in
    assert usage["output_tokens"] == result.tokens_out
    assert generation.updates[-1]["cost_details"]["total"] == result.cost_usd
    assert result.trace_id == "trace-abc"

    raw = repr([o.kwargs for o in client.observations] + [o.updates for o in client.observations])
    assert "a.b@example.com" not in raw


def test_retrieval_failure_marks_span_as_error(monkeypatch) -> None:
    monkeypatch.setitem(STATE, "tool_fail", True)
    client = ObservationClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    with pytest.raises(RuntimeError):
        agent_module.LabAgent.run.__wrapped__(
            agent_module.LabAgent(),
            user_id="u",
            feature="qa",
            session_id="s",
            message="hello",
            correlation_id="req-12345678",
        )

    assert client.observations[0].updates[-1]["level"] == "ERROR"
