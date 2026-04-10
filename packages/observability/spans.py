"""Span context-managers for the observability package (M-13).

Each context manager creates an OTel span for a distinct phase of an
agent turn:

* ``perception_span``  — outermost parent span for the perception phase.
* ``reasoning_span``   — child span for prompt construction + LLM call.
* ``action_span``      — child span for tool execution and outcome application.

Callers may set additional attributes on the yielded ``Span`` object
after the context-manager starts, e.g.::

    with reasoning_span(tracer, "agent_a", turn=1, parent=perc_span) as span:
        span.set_attribute("llm.prompt_tokens", 120)
        span.set_attribute("llm.completion_tokens", 45)
        span.set_attribute("llm.model", "gpt-4o-mini")
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Span

from packages.shared.types import AgentID, ToolName, TurnNumber


@contextmanager
def perception_span(
    tracer: trace.Tracer,
    agent_id: AgentID,
    turn: TurnNumber,
) -> Iterator[Span]:
    """Parent span for the perception phase of a turn.

    Args:
        tracer: The OTel tracer obtained from :func:`init_tracer`.
        agent_id: Identifier of the agent whose turn is being traced.
        turn: Current turn number.

    Yields:
        The active OTel :class:`~opentelemetry.trace.Span`.  Callers may
        attach ``run_id``, ``divergence_score``, or other attributes on it.
    """
    start = time.monotonic()
    with tracer.start_as_current_span(
        "perception",
        attributes={
            "agent_id": agent_id,
            "turn": turn,
        },
    ) as span:
        try:
            yield span
        finally:
            latency_ms = (time.monotonic() - start) * 1000.0
            span.set_attribute("latency_ms", latency_ms)


@contextmanager
def reasoning_span(
    tracer: trace.Tracer,
    agent_id: AgentID,
    turn: TurnNumber,
    parent: Span,
) -> Iterator[Span]:
    """Child span for LLM reasoning (prompt construction + LLM call).

    The span is created as a child of *parent* by injecting the parent
    span into the OTel context.

    Expected attributes to set on the yielded span:
    ``llm.prompt_tokens``, ``llm.completion_tokens``, ``llm.model``.

    Args:
        tracer: The OTel tracer obtained from :func:`init_tracer`.
        agent_id: Identifier of the agent whose turn is being traced.
        turn: Current turn number.
        parent: The enclosing :func:`perception_span` span object.

    Yields:
        The active OTel :class:`~opentelemetry.trace.Span`.
    """
    start = time.monotonic()
    ctx = trace.set_span_in_context(parent, otel_context.get_current())
    with tracer.start_as_current_span(
        "reasoning",
        context=ctx,
        attributes={
            "agent_id": agent_id,
            "turn": turn,
        },
    ) as span:
        try:
            yield span
        finally:
            latency_ms = (time.monotonic() - start) * 1000.0
            span.set_attribute("latency_ms", latency_ms)


@contextmanager
def action_span(
    tracer: trace.Tracer,
    agent_id: AgentID,
    turn: TurnNumber,
    tool_name: ToolName,
    parent: Span,
) -> Iterator[Span]:
    """Child span for tool execution and outcome application.

    The span is created as a child of *parent*.  Callers should set
    ``tool.success`` and ``divergence_score`` on the yielded span after
    the tool invocation completes.

    Args:
        tracer: The OTel tracer obtained from :func:`init_tracer`.
        agent_id: Identifier of the agent whose turn is being traced.
        turn: Current turn number.
        tool_name: Name of the tool being invoked.
        parent: The enclosing :func:`perception_span` span object.

    Yields:
        The active OTel :class:`~opentelemetry.trace.Span`.
    """
    start = time.monotonic()
    ctx = trace.set_span_in_context(parent, otel_context.get_current())
    with tracer.start_as_current_span(
        "action",
        context=ctx,
        attributes={
            "agent_id": agent_id,
            "turn": turn,
            "tool.name": tool_name,
        },
    ) as span:
        try:
            yield span
        finally:
            latency_ms = (time.monotonic() - start) * 1000.0
            span.set_attribute("latency_ms", latency_ms)
