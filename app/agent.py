from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id, summarize_text
from .prompt_management import resolve_prompt
from .tracing import (
    current_trace_id,
    get_langfuse_client,
    observe,
    propagate_attributes,
    start_child_observation,
    tracing_enabled,
)


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    ttft_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float
    trace_id: str | None = None


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    @observe(name="lab-agent-run", as_type="agent", capture_input=False, capture_output=False)
    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str,
    ) -> AgentResult:
        langfuse_client = get_langfuse_client()
        with propagate_attributes(
            user_id=hash_user_id(user_id),
            session_id=session_id,
            tags=["lab", feature, self.model],
            trace_name="day13-agent-request",
            environment=os.getenv("APP_ENV", "dev"),
            metadata={
                "feature": feature,
                "model": self.model,
                "correlation_id": correlation_id,
            },
        ):
            started = time.perf_counter()
            trace_id = current_trace_id(langfuse_client)
            with start_child_observation(
                langfuse_client,
                name="retrieval",
                as_type="retriever",
                input={"query_preview": summarize_text(message)},
            ) as retrieval_obs:
                retrieval_started = time.perf_counter()
                try:
                    docs = retrieve(message)
                except Exception as exc:
                    retrieval_obs.update(
                        level="ERROR",
                        status_message=type(exc).__name__,
                        metadata={"tool_success": False, "error_type": type(exc).__name__},
                    )
                    raise
                retrieval_obs.update(
                    output={"doc_count": len(docs)},
                    metadata={
                        "tool_success": True,
                        "retrieval_ms": int((time.perf_counter() - retrieval_started) * 1000),
                    },
                )
            prompt = resolve_prompt(
                langfuse_client,
                feature=feature,
                docs=docs,
                message=message,
                enabled=tracing_enabled(),
            )
            langfuse_client.update_current_span(
                metadata={
                    "doc_count": len(docs),
                    "query_preview": summarize_text(message),
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                    "prompt_fetch_error": prompt.fetch_error or "",
                },
                version=prompt.version,
            )
            # Generation chỉ nhận preview đã scrub, không capture raw prompt/output có thể chứa PII.
            with propagate_attributes(prompt=prompt.managed_prompt), start_child_observation(
                langfuse_client,
                name="llm-generate",
                as_type="generation",
                model=self.model,
                prompt=prompt.managed_prompt,
                input={"prompt_preview": summarize_text(prompt.text, max_len=160)},
                metadata={
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                },
            ) as generation_obs:
                generation_started = datetime.now(timezone.utc)
                response = self.llm.generate(prompt.text)
                cost_usd = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)
                generation_obs.update(
                    output={"answer_preview": summarize_text(response.text)},
                    completion_start_time=generation_started + timedelta(milliseconds=response.ttft_ms),
                    usage_details={
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                    },
                    cost_details={
                        "input": self._estimate_cost(response.usage.input_tokens, 0),
                        "output": self._estimate_cost(0, response.usage.output_tokens),
                        "total": cost_usd,
                    },
                    metadata={"ttft_ms": response.ttft_ms},
                )
            quality_score = self._heuristic_quality(message, response.text, docs)
            latency_ms = int((time.perf_counter() - started) * 1000)

        metrics.record_request(
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
            trace_id=trace_id,
        )

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost = (tokens_in / 1_000_000) * 3
        output_cost = (tokens_out / 1_000_000) * 15
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
