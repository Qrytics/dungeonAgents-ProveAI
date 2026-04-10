"""M-07 — Agent Tools.

Defines the four LangGraph tool functions that agents can call each turn.
These are the *only* interface agents have with the world.

Context injection
-----------------
All tools receive the current ``ToolContext`` through LangGraph's
``RunnableConfig`` mechanism so that no global state is required and the
tools remain fully deterministic and testable.

Usage::

    from langchain_core.runnables import RunnableConfig
    from apps.simulation.agents.tools import TOOL_CONTEXT_KEY, ToolContext, move

    ctx = ToolContext(
        agent_id="agent_a",
        world_state=current_world_state,
        run_id=run_id,
        turn=turn_number,
        orchestrator=my_orchestrator,
    )
    config: RunnableConfig = {"configurable": {TOOL_CONTEXT_KEY: ctx}}
    result = move.invoke({"direction": "north"}, config=config)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.simulation.schemas.events import IntentionEvent, OutcomeEvent
from apps.simulation.schemas.state import WorldState
from packages.shared.types import AgentID, Direction, RunID, TurnNumber

# Key used in ``RunnableConfig["configurable"]`` to inject the tool context.
TOOL_CONTEXT_KEY: str = "tool_context"


# ---------------------------------------------------------------------------
# Orchestrator protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class OrchestratorProtocol(Protocol):
    """Structural interface that the orchestrator (M-06) must satisfy.

    Defined here so that M-07 can be tested without a concrete orchestrator
    implementation and without creating a circular dependency.
    """

    def apply_intention(
        self,
        intention: IntentionEvent,
        current_world_state: WorldState,
    ) -> OutcomeEvent:
        """Validate *intention*, apply mutations, and return the outcome."""
        ...


# ---------------------------------------------------------------------------
# Tool context
# ---------------------------------------------------------------------------


@dataclass
class ToolContext:
    """All state that agent tools need, injected via ``RunnableConfig``.

    Construct one instance per agent turn and pass it via::

        config = {"configurable": {TOOL_CONTEXT_KEY: ctx}}

    Fields
    ------
    agent_id:
        Identity of the agent that is currently executing.
    world_state:
        The authoritative world state at the start of this turn.  Tools read
        it to build ``IntentionEvent`` metadata; they never mutate it directly.
    run_id:
        Unique identifier for the current simulation run.
    turn:
        Current turn number (0-indexed).
    orchestrator:
        Object that validates and applies intentions.  Must implement
        ``OrchestratorProtocol``.
    llm_prompt_tokens:
        Number of prompt tokens consumed by the LLM call that produced this
        tool invocation.
    llm_completion_tokens:
        Number of completion tokens consumed by the same LLM call.
    latency_ms:
        Wall-clock latency of the LLM call in milliseconds.
    raw_llm_output:
        The raw text returned by the LLM (for observability / replay).
    """

    agent_id: AgentID
    world_state: WorldState
    run_id: RunID
    turn: TurnNumber
    orchestrator: OrchestratorProtocol
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    latency_ms: float = 0.0
    raw_llm_output: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_context(config: RunnableConfig) -> ToolContext:
    """Extract and validate ``ToolContext`` from ``RunnableConfig``."""
    configurable = config.get("configurable") or {}
    ctx = configurable.get(TOOL_CONTEXT_KEY)
    if ctx is None:
        raise RuntimeError(
            f"ToolContext not found in config['configurable']['{TOOL_CONTEXT_KEY}']. "
            "Ensure the agent populates it before invoking tools."
        )
    if not isinstance(ctx, ToolContext):
        raise TypeError(
            f"Expected a ToolContext in config['configurable']['{TOOL_CONTEXT_KEY}'], "
            f"got {type(ctx).__name__}."
        )
    return ctx


def _make_intention(
    ctx: ToolContext,
    tool_name: str,
    tool_args: dict[str, Any],
) -> IntentionEvent:
    """Build a frozen ``IntentionEvent`` from the current ``ToolContext``."""
    return IntentionEvent(
        event_type="intention",
        run_id=ctx.run_id,
        turn=ctx.turn,
        agent_id=ctx.agent_id,
        tool_name=tool_name,  # type: ignore[arg-type]
        tool_args=tool_args,
        llm_prompt_tokens=ctx.llm_prompt_tokens,
        llm_completion_tokens=ctx.llm_completion_tokens,
        latency_ms=ctx.latency_ms,
        raw_llm_output=ctx.raw_llm_output,
        timestamp=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------


@tool
def move(direction: Direction, config: RunnableConfig) -> str:
    """Move the agent one cell in the specified direction.

    Returns a description of the result (success or reason for failure).
    """
    ctx = _get_context(config)
    intention = _make_intention(ctx, "move", {"direction": direction})
    outcome = ctx.orchestrator.apply_intention(intention, ctx.world_state)
    return outcome.result_description


@tool
def observe(config: RunnableConfig) -> str:
    """Observe all cells within your field of vision (adjacent cells only).

    Returns a formatted description of visible cells, including cell types and positions.
    """
    ctx = _get_context(config)
    intention = _make_intention(ctx, "observe", {})
    outcome = ctx.orchestrator.apply_intention(intention, ctx.world_state)
    return outcome.result_description


@tool
def interact(config: RunnableConfig) -> str:
    """Interact with the current cell or adjacent items.

    Picks up the key if on the key cell. Unlocks the door if adjacent and holding the key.
    Returns result description.
    """
    ctx = _get_context(config)
    intention = _make_intention(ctx, "interact", {})
    outcome = ctx.orchestrator.apply_intention(intention, ctx.world_state)
    return outcome.result_description


@tool
def communicate(recipient: AgentID, message: str, config: RunnableConfig) -> str:
    """Send a message to the other agent. Message will be delivered on the NEXT turn (communication lag).

    Returns confirmation of message queued.
    """
    ctx = _get_context(config)
    intention = _make_intention(
        ctx, "communicate", {"recipient": recipient, "message": message}
    )
    outcome = ctx.orchestrator.apply_intention(intention, ctx.world_state)
    return outcome.result_description
