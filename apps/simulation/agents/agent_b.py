"""M-09 — LLM Agent B.

Agent B is symmetric to Agent A: it operates under the same fog-of-war
and communication-lag constraints, uses the same tool set, and enforces
exactly one tool call per turn.

LangGraph node signature::

    def agent_b_node(state: LangGraphState) -> LangGraphState:
        ...

See ``agent_a.py`` for the full turn-execution narrative; only the
agent identity constant differs between the two files.
"""

from __future__ import annotations

import os
import time
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

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
from packages.shared.types import ToolName

from . import LangGraphState

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_AGENT_ID = "agent_b"
_OTHER_AGENT_ID = "agent_a"

_TOOLS = [move, observe, interact, communicate]

_TOOL_FN_MAP = {
    "move": move,
    "observe": observe,
    "interact": interact,
    "communicate": communicate,
}

_SYSTEM_PROMPT = (
    "You are agent_b, an autonomous agent navigating a dungeon grid.\n\n"
    "Objective: Cooperate with agent_a so that BOTH agents reach the exit. "
    "One agent must pick up the key and unlock the locked door before either "
    "agent can exit.\n\n"
    "Constraints:\n"
    "- Fog of war: you can only see adjacent cells (one step in any cardinal direction).\n"
    "- Communication lag: messages sent to agent_a arrive on the NEXT turn, not immediately.\n"
    "- You MUST choose exactly one tool per turn.\n\n"
    "Available tools:\n"
    "- move(direction): Move one cell north / south / east / west.\n"
    "- observe(): Observe all cells within your field of vision.\n"
    "- interact(): Pick up the key if on the key cell, or unlock the door "
    "if adjacent and holding the key.\n"
    "- communicate(recipient, message): Send a text message to agent_a "
    "(delivered next turn).\n"
)


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------


def agent_b_node(state: LangGraphState) -> LangGraphState:
    """LangGraph node that executes one turn for Agent B.

    Reads Agent B's belief state, prompts the LLM to select one tool
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
    belief_manager: AgentBeliefStateManager = state["belief_manager_b"]
    tracer = state["tracer"]

    # Step 1 — update belief from the latest perception (if provided).
    perception = state.get("perception_b")
    if perception is not None:
        belief_manager.update_from_perception(perception)

    model_name: str = os.environ.get("AGENT_LLM_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name).bind_tools(_TOOLS, tool_choice="required")

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

    return state
