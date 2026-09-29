from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

try:
    from langfuse import get_client, observe, propagate_attributes

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_span(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

    def get_client():
        return _DummyClient()

    @contextmanager
    def propagate_attributes(**kwargs: Any):
        yield


class _NoopObservation:
    def update(self, **kwargs: Any) -> None:
        return None


def get_langfuse_client():
    return get_client()


@contextmanager
def start_child_observation(client: Any, **kwargs: Any):
    """Mở child observation dưới observation hiện tại; no-op nếu client không hỗ trợ."""
    starter = getattr(client, "start_as_current_observation", None)
    if not callable(starter):
        yield _NoopObservation()
        return
    with starter(**kwargs) as observation:
        yield observation


def current_trace_id(client: Any) -> str | None:
    getter = getattr(client, "get_current_trace_id", None)
    try:
        return getter() if callable(getter) else None
    except Exception:  # tracing không được làm hỏng request
        return None


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )
