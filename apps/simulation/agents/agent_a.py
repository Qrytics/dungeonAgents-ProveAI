"""M-09 — LLM Agent A.

Agent A is one of two LangGraph agent nodes in the dungeon simulation.
It selects exactly one tool call per turn based solely on its internal
belief state (fog-of-war; no ground truth is visible to the LLM).

LangGraph node signature::

    def agent_a_node(state: LangGraphState) -> LangGraphState:
        ...

Each turn the node:

1. Updates the belief state from the latest ``AgentPerception`` (if any).
2. Builds a system + user prompt that contains only the belief context.
3. Calls the LLM with all four tools bound and ``tool_choice="required"``
   so that exactly one tool call is always produced.
4. Executes the selected tool (which routes through the orchestrator to
   emit an ``IntentionEvent`` and receive an ``OutcomeEvent``).
5. Records an OTel span tree: perception → reasoning → action.
"""

from __future__ import annotations

import os
import time
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

from apps.simulation.agents.llm_factory import build_llm
from apps.simulation.agents.state import AgentBeliefStateManager
from apps.simulation.agents.tools import (
    TOOL_CONTEXT_KEY,
    ToolContext,
    communicate,
    interact,
    move,
    observe,
)
from packages.observability.spans import action_span, perception_span, reasoning_span
from packages.shared.types import Direction, ToolName

from . import LangGraphState

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_AGENT_ID = "agent_a"
_OTHER_AGENT_ID = "agent_b"

_TOOLS = [move, observe, interact, communicate]

_TOOL_FN_MAP = {
    "move": move,
    "observe": observe,
    "interact": interact,
    "communicate": communicate,
}


def _fallback_move_direction(belief_manager: AgentBeliefStateManager, turn: int) -> Direction:
    """Pick a deterministic move direction from known adjacent walkable cells.

    This prevents deadlocks when the model repeatedly selects `observe`.
    """
    belief = belief_manager.get_current_belief()
    row, col = belief.believed_position

    # Prefer objective cells first when known nearby.
    candidates: list[tuple[Direction, tuple[int, int]]] = [
        ("north", (row - 1, col)),
        ("east", (row, col + 1)),
        ("south", (row + 1, col)),
        ("west", (row, col - 1)),
    ]
    for direction, pos in candidates:
        ctype = belief.believed_grid.get(pos)
        if ctype in ("key", "exit"):
            return direction
    for direction, pos in candidates:
        ctype = belief.believed_grid.get(pos)
        if ctype == "floor":
            return direction

    # If everything is unknown, rotate deterministically by turn.
    cycle: list[Direction] = ["north", "east", "south", "west"]
    return cycle[turn % len(cycle)]


def _should_force_interact(belief_manager: AgentBeliefStateManager) -> bool:
    """Return True when interaction should be forced from local belief state."""
    belief = belief_manager.get_current_belief()
    row, col = belief.believed_position
    here = belief.believed_grid.get((row, col))

    # Standing on key and not carrying it yet.
    if here == "key" and not belief.has_key:
        return True

    # Carrying key and adjacent to locked door.
    if belief.has_key:
        for pos in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if belief.believed_grid.get(pos) == "locked_door":
                return True

    return False

_SYSTEM_PROMPT = (
    "You are agent_a, an autonomous agent navigating a dungeon grid.\n\n"
    "Objective: Cooperate with agent_b so that BOTH agents reach the exit. "
    "One agent must pick up the key and unlock the locked door before either "
    "agent can exit.\n\n"
    "Constraints:\n"
    "- Fog of war: you can only see adjacent cells (one step in any cardinal direction).\n"
    "- Communication lag: messages sent to agent_b arrive on the NEXT turn, not immediately.\n"
    "- You MUST choose exactly one tool per turn.\n\n"
    "Available tools:\n"
    "- move(direction): Move one cell north / south / east / west.\n"
    "- observe(): Observe all cells within your field of vision.\n"
    "- interact(): Pick up the key if on the key cell, or unlock the door "
    "if adjacent and holding the key.\n"
    "- communicate(recipient, message): Send a text message to agent_b "
    "(delivered next turn).\n\n"
    "Decision rules — MUST follow:\n"
    "1. Use observe ONLY on your very first turn OR after a move/interact. NEVER call observe twice in a row.\n"
    "2. After observing, you MUST call move() or interact() next turn — use the cell info you just got.\n"
    "3. If KEY(!) appears in your recent observe result or explored map, move toward it immediately.\n"
    "4. If you are standing on the key cell, call interact() to pick it up.\n"
    "5. If you hold the key and LOCKED_DOOR is adjacent, call interact() to unlock it.\n"
    "6. Once the door is unlocked, move toward EXIT(!).\n"
    "7. When no objective is visible, move in any floor direction — DO NOT stay still.\n"
    "8. If a move fails (wall), try a different direction immediately.\n"
)


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------


def agent_a_node(state: LangGraphState) -> LangGraphState:
    """LangGraph node that executes one turn for Agent A.

    Reads Agent A's belief state, prompts the LLM to select one tool
    call, executes the tool through the orchestrator, and records a
    nested OTel span tree (perception → reasoning → action).

    Args:
        state: The current ``LangGraphState`` shared across all graph nodes.

    Returns:
        The same ``LangGraphState`` (belief state is mutated in-place via
        ``AgentBeliefStateManager``; no new fields are added).
    """
    run_id = state["run_id"]
    turn = state["turn"]
    world_state = state["world_state"]
    orchestrator = state["orchestrator"]
    belief_manager: AgentBeliefStateManager = state["belief_manager_a"]
    tracer = state["tracer"]

    # Step 1 — update belief from the latest perception (if provided).
    perception = state.get("perception_a")
    if perception is not None:
        belief_manager.update_from_perception(perception)

    model_name: str = os.environ.get("AGENT_LLM_MODEL", "gpt-4o-mini")
    llm = build_llm(model_name).bind_tools(_TOOLS, tool_choice="any")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    raw_output: str = ""
    tool_name: str = "observe"
    tool_args: dict = {}

    # Outer span — perception phase (also serves as the parent span).
    with perception_span(tracer, _AGENT_ID, turn) as perc_span:
        perc_span.set_attribute("run_id", run_id)

        # Step 2 — build prompts from belief state only (never ground truth).
        belief_context = belief_manager.to_llm_prompt_context()
        user_content = f"Turn: {turn}\n\n{belief_context}"
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        # Step 3 — call LLM inside the reasoning child span.
        t0 = time.monotonic()
        with reasoning_span(tracer, _AGENT_ID, turn, perc_span) as reas_span:
            response = llm.invoke(messages)
            latency_ms = (time.monotonic() - t0) * 1000.0

            usage = response.usage_metadata or {}
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)
            raw_output = response.content if isinstance(response.content, str) else ""

            reas_span.set_attribute("llm.prompt_tokens", prompt_tokens)
            reas_span.set_attribute("llm.completion_tokens", completion_tokens)
            reas_span.set_attribute("llm.model", model_name)
            reas_span.set_attribute("latency_ms", latency_ms)

        # Enforce exactly one tool call per turn; fall back to observe if needed.
        if response.tool_calls:
            tool_call = response.tool_calls[0]
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})

        # Deterministic safety policy to prevent no-op loops.
        if _should_force_interact(belief_manager):
            tool_name = "interact"
            tool_args = {}
        elif tool_name in ("observe", "communicate") and (
            belief_manager.last_action_tool_name() == tool_name
        ):
            tool_name = "move"
            tool_args = {"direction": _fallback_move_direction(belief_manager, int(turn))}

        # Build the tool context carrying token-count and latency metadata.
        tool_context = ToolContext(
            agent_id=_AGENT_ID,
            world_state=world_state,
            run_id=run_id,
            turn=turn,
            orchestrator=orchestrator,
            llm_prompt_tokens=prompt_tokens,
            llm_completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            raw_llm_output=raw_output,
            message_queue=state.get("message_queue"),
        )
        config = {"configurable": {TOOL_CONTEXT_KEY: tool_context}}
        tool_fn = _TOOL_FN_MAP.get(tool_name, observe)

        # Step 4 — execute the tool inside the action child span.
        with action_span(
            tracer,
            _AGENT_ID,
            turn,
            cast(ToolName, tool_name),
            perc_span,
        ) as act_span:
            result = tool_fn.invoke(tool_args, config=config)
            act_span.set_attribute("tool.result", result)

            belief_manager.record_action(int(turn), tool_name, str(result))

    return state
