from __future__ import annotations

from apps.simulation.schemas.state import AgentBeliefState, AgentPerception
from packages.shared.types import AgentID, CellType, Position, TurnNumber

_CELL_SYMBOLS: dict[CellType, str] = {
    "floor": ".",
    "wall": "#",
    "key": "K",
    "locked_door": "D",
    "exit": "E",
    "agent": "@",
}

_PLAYABLE_AGENTS: tuple[AgentID, AgentID] = ("agent_a", "agent_b")


class AgentBeliefStateManager:
    """Manages an agent's internal world model (the belief side of epistemic divergence)."""

    def __init__(self, agent_id: AgentID) -> None:
        self._agent_id = agent_id
        self._believed_grid: dict[Position, CellType] = {}
        self._believed_position: Position = (0, 0)
        self._has_key: bool = False
        self._known_agent_positions: dict[AgentID, Position] = {}
        # Tracks the turn each other agent's position was last observed (for staleness notes).
        self._agent_position_turns: dict[AgentID, TurnNumber] = {}
        self._current_turn: TurnNumber = TurnNumber(0)
        self._pending_messages: tuple[str, ...] = ()
        self._current_belief: AgentBeliefState | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_from_perception(self, perception: AgentPerception) -> AgentBeliefState:
        """Merge newly perceived cells into the running belief map and return a snapshot."""
        self._current_turn = perception.turn
        self._believed_position = perception.position
        self._has_key = perception.has_key
        self._pending_messages = perception.pending_messages

        for cell in perception.visible_cells:
            pos: Position = (cell.row, cell.col)
            # Additive merge — previously seen cells are never forgotten; visible cells
            # override with the latest observed type (handles key removal, etc.).
            self._believed_grid[pos] = cell.cell_type

            # Infer the other playable agent's position from visible "agent" cells.
            if cell.cell_type == "agent" and pos != perception.position:
                other = self._other_agent_id()
                if other is not None:
                    self._known_agent_positions[other] = pos
                    self._agent_position_turns[other] = perception.turn

        self._current_belief = AgentBeliefState(
            agent_id=self._agent_id,
            turn=self._current_turn,
            believed_position=self._believed_position,
            believed_grid=dict(self._believed_grid),
            has_key=self._has_key,
            known_agent_positions=dict(self._known_agent_positions),
        )
        return self._current_belief

    def get_current_belief(self) -> AgentBeliefState:
        """Return the latest frozen AgentBeliefState snapshot."""
        if self._current_belief is None:
            self._current_belief = AgentBeliefState(
                agent_id=self._agent_id,
                turn=TurnNumber(0),
                believed_position=self._believed_position,
                believed_grid=dict(self._believed_grid),
                has_key=self._has_key,
                known_agent_positions=dict(self._known_agent_positions),
            )
        return self._current_belief

    def to_llm_prompt_context(self) -> str:
        """Format the belief state as a deterministic human-readable string for LLM injection.

        Includes: current position, explored map layout, known agent positions (with
        staleness annotation), key status, and pending messages.
        """
        belief = self.get_current_belief()

        lines: list[str] = [
            f"=== Agent {self._agent_id} Belief State (Turn {belief.turn}) ===",
            f"Current Position: row={belief.believed_position[0]}, col={belief.believed_position[1]}",
            f"Carrying Key: {'Yes' if belief.has_key else 'No'}",
        ]

        # Known agent positions — sorted by agent_id for determinism.
        if belief.known_agent_positions:
            lines.append("Known Agent Positions (may be stale):")
            for agent_id in sorted(belief.known_agent_positions):
                pos = belief.known_agent_positions[agent_id]
                turn_seen = self._agent_position_turns.get(agent_id)
                staleness = (
                    f" (last seen turn {turn_seen})"
                    if turn_seen is not None
                    else " (turn unknown)"
                )
                lines.append(f"  {agent_id}: row={pos[0]}, col={pos[1]}{staleness}")
        else:
            lines.append("Known Agent Positions: None observed yet")

        # Explored map — rendered as a compact ASCII grid.
        if belief.believed_grid:
            all_positions = list(belief.believed_grid.keys())
            rows = sorted({p[0] for p in all_positions})
            cols = sorted({p[1] for p in all_positions})
            lines.append(
                "Explored Map (# wall, . floor, K key, D locked door, E exit, @ agent):"
            )
            for row in rows:
                row_str = "  "
                for col in cols:
                    cell_type = belief.believed_grid.get((row, col))
                    row_str += _CELL_SYMBOLS.get(cell_type, " ") if cell_type is not None else " "
                lines.append(row_str)
        else:
            lines.append("Explored Map: No cells observed yet")

        # Pending messages delivered this turn.
        if self._pending_messages:
            lines.append("Pending Messages:")
            for msg in self._pending_messages:
                lines.append(f"  - {msg}")
        else:
            lines.append("Pending Messages: None")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _other_agent_id(self) -> AgentID | None:
        """Return the ID of the other playable agent, or None for non-playable agents."""
        for agent_id in _PLAYABLE_AGENTS:
            if agent_id != self._agent_id:
                return agent_id
        return None
