"""LangGraph agent package for the dungeon simulation.

Exports ``LangGraphState``, the shared TypedDict that flows through every
node in the dungeon graph (agent nodes, tool nodes, game-loop nodes).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from langfuse import Langfuse
from opentelemetry import trace

from apps.simulation.agents.tools import OrchestratorProtocol
from apps.simulation.schemas.state import AgentPerception, WorldState
from packages.shared.types import RunID, TurnNumber

if TYPE_CHECKING:
    from apps.simulation.agents.state import AgentBeliefStateManager


class LangGraphState(TypedDict):
    """Shared state flowing through every node in the dungeon LangGraph.

    Fields
    ------
    run_id:
        Unique identifier for the current simulation run.
    turn:
        Current turn number (0-indexed).
    world_state:
        Ground-truth world state at the start of this turn.  Agent nodes
        must *not* expose this to the LLM; it is used only by tools to
        build ``IntentionEvent`` metadata and by the orchestrator.
    orchestrator:
        Object that validates and applies agent intentions.
    belief_manager_a:
        Running belief model for Agent A.
    belief_manager_b:
        Running belief model for Agent B.
    perception_a:
        Latest ``AgentPerception`` snapshot for Agent A, or ``None`` if no
        new perception is available this turn.  Consumed by the agent node
        to update its belief state.
    perception_b:
        Latest ``AgentPerception`` snapshot for Agent B (same semantics).
    tracer:
        OpenTelemetry ``Tracer`` instance for the current run.
    langfuse_client:
        Langfuse client for the current run.
    """

    run_id: RunID
    turn: TurnNumber
    world_state: WorldState
    orchestrator: OrchestratorProtocol
    belief_manager_a: AgentBeliefStateManager
    belief_manager_b: AgentBeliefStateManager
    perception_a: AgentPerception | None
    perception_b: AgentPerception | None
    tracer: trace.Tracer
    langfuse_client: Langfuse


__all__ = ["LangGraphState"]
