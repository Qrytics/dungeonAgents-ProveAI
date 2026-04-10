"""Observability package (M-13).

Public API::

    from packages.observability import (
        init_tracer,
        perception_span,
        reasoning_span,
        action_span,
        record_divergence_score,
        record_token_usage,
        record_turn_latency,
    )
"""

from packages.observability.metrics import (
    record_divergence_score,
    record_token_usage,
    record_turn_latency,
)
from packages.observability.spans import action_span, perception_span, reasoning_span
from packages.observability.tracer import init_tracer

__all__ = [
    "init_tracer",
    "perception_span",
    "reasoning_span",
    "action_span",
    "record_divergence_score",
    "record_token_usage",
    "record_turn_latency",
]
