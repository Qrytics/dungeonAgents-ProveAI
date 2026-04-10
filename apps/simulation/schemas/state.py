from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from packages.shared.types import AgentID, CellType, Position, RunID, TurnNumber


class CellState(BaseModel):
    model_config = ConfigDict(frozen=True)

    row: int
    col: int
    cell_type: CellType
    is_visible_to: tuple[AgentID, ...]  # which agents currently see this cell


class WorldState(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: RunID
    turn: TurnNumber
    grid: tuple[tuple[CellState, ...], ...]  # full 8×8 (or larger) grid; ground truth
    agent_positions: dict[AgentID, Position]
    key_held_by: AgentID | None
    door_unlocked: bool


class AgentPerception(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_id: AgentID
    turn: TurnNumber
    visible_cells: tuple[CellState, ...]  # only cells within FOG_RADIUS
    position: Position
    has_key: bool
    pending_messages: tuple[str, ...]  # messages delivered this turn (sent N-1)


class AgentBeliefState(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_id: AgentID
    turn: TurnNumber
    believed_position: Position
    # Serialized as list-of-pairs [[row, col], cell_type] for JSON round-trip safety.
    believed_grid: dict[Position, CellType]  # agent's internal world map
    has_key: bool
    known_agent_positions: dict[AgentID, Position]  # may be stale

    @field_validator("believed_grid", mode="before")
    @classmethod
    def _parse_believed_grid(cls, v: Any) -> Any:
        # Accept list-of-pairs produced by serialization: [[[row, col], cell_type], ...]
        if isinstance(v, list):
            return {(int(k[0]), int(k[1])): ct for k, ct in v}
        return v

    @field_serializer("believed_grid")
    def _serialize_believed_grid(
        self, v: dict[Position, CellType]
    ) -> list[tuple[Position, CellType]]:
        return list(v.items())
