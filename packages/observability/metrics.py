"""OTel metric-recording helpers for the observability package (M-13).

Each helper takes the OTel ``Meter`` obtained from
``opentelemetry.metrics.get_meter_provider().get_meter(...)`` and records
a single measurement with agent-scoped attributes.

Instruments are created lazily on first call and cached at module level so
that the OTel SDK can deduplicate them correctly across calls.
"""

from __future__ import annotations

from opentelemetry.metrics import Counter, Histogram, Meter

from packages.shared.types import AgentID, TurnNumber

# ---------------------------------------------------------------------------
# Lazy instrument cache.  Keys are (meter_id, instrument_name).
# ---------------------------------------------------------------------------
_histograms: dict[tuple[int, str], Histogram] = {}
_counters: dict[tuple[int, str], Counter] = {}


def _get_histogram(meter: Meter, name: str, description: str, unit: str) -> Histogram:
    key = (id(meter), name)
    if key not in _histograms:
        _histograms[key] = meter.create_histogram(
            name=name, description=description, unit=unit
        )
    return _histograms[key]


def _get_counter(meter: Meter, name: str, description: str, unit: str) -> Counter:
    key = (id(meter), name)
    if key not in _counters:
        _counters[key] = meter.create_counter(
            name=name, description=description, unit=unit
        )
    return _counters[key]


def record_divergence_score(
    meter: Meter,
    agent_id: AgentID,
    turn: TurnNumber,
    score: float,
) -> None:
    """Record the epistemic divergence score for a completed agent turn.

    Args:
        meter: An OTel :class:`~opentelemetry.metrics.Meter` instance.
        agent_id: Identifier of the agent whose turn was scored.
        turn: Turn number the score belongs to.
        score: Divergence score in the range ``[0.0, 1.0]``.
    """
    histogram = _get_histogram(
        meter,
        name="agent.divergence_score",
        description="Epistemic divergence score for an agent turn",
        unit="1",
    )
    histogram.record(score, attributes={"agent_id": agent_id, "turn": turn})


def record_token_usage(
    meter: Meter,
    agent_id: AgentID,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Record LLM token consumption for a single agent turn.

    Args:
        meter: An OTel :class:`~opentelemetry.metrics.Meter` instance.
        agent_id: Identifier of the agent that made the LLM call.
        prompt_tokens: Number of tokens in the prompt sent to the LLM.
        completion_tokens: Number of tokens in the LLM completion.
    """
    attrs = {"agent_id": agent_id}

    prompt_counter = _get_counter(
        meter,
        name="agent.prompt_tokens",
        description="Total prompt tokens used by an agent",
        unit="tokens",
    )
    prompt_counter.add(prompt_tokens, attributes=attrs)

    completion_counter = _get_counter(
        meter,
        name="agent.completion_tokens",
        description="Total completion tokens used by an agent",
        unit="tokens",
    )
    completion_counter.add(completion_tokens, attributes=attrs)


def record_turn_latency(
    meter: Meter,
    agent_id: AgentID,
    turn: TurnNumber,
    latency_ms: float,
) -> None:
    """Record the wall-clock latency of a complete agent turn.

    Args:
        meter: An OTel :class:`~opentelemetry.metrics.Meter` instance.
        agent_id: Identifier of the agent whose turn was measured.
        turn: Turn number the measurement belongs to.
        latency_ms: Elapsed time in milliseconds for the full turn.
    """
    histogram = _get_histogram(
        meter,
        name="agent.turn_latency_ms",
        description="Latency of an agent turn in milliseconds",
        unit="ms",
    )
    histogram.record(latency_ms, attributes={"agent_id": agent_id, "turn": turn})
