from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from packages.shared.types import AgentID, RunID, TerminationReason, ToolName, TurnNumber

from .state import WorldState


class IntentionEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: Literal["intention"]
    run_id: RunID
    turn: TurnNumber
    agent_id: AgentID
    tool_name: ToolName
    tool_args: dict[str, Any]
    llm_prompt_tokens: int
    llm_completion_tokens: int
    latency_ms: float
    raw_llm_output: str
    timestamp: datetime


class OutcomeEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: Literal["outcome"]
    run_id: RunID
    turn: TurnNumber
    agent_id: AgentID
    tool_name: ToolName
    success: bool
    result_description: str
    world_state_after: WorldState
    divergence_score: float | None  # populated post-hoc; None until computed
    timestamp: datetime


class MessageEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: Literal["message"]
    run_id: RunID
    turn_sent: TurnNumber
    turn_delivered: TurnNumber  # always turn_sent + COMM_LAG_TURNS
    sender: AgentID
    recipient: AgentID
    content: str
    timestamp: datetime


class TerminationEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: Literal["termination"]
    run_id: RunID
    final_turn: TurnNumber
    reason: TerminationReason
    winner: bool  # True if agents won
    timestamp: datetime


AnyEvent = Annotated[
    Union[IntentionEvent, OutcomeEvent, MessageEvent, TerminationEvent],
    Field(discriminator="event_type"),
]
