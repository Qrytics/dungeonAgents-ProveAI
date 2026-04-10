"""M-04 — Environment: Perception & Fog-of-War Engine."""

from __future__ import annotations

from apps.simulation.environment.grid import DungeonGrid
from apps.simulation.schemas.state import AgentPerception, CellState, WorldState
from packages.shared.constants import FOG_RADIUS
from packages.shared.types import AgentID, Position, TurnNumber


class PerceptionEngine:
    """Fog-of-war engine for the dungeon simulation.

    Each agent sees only cells within ``FOG_RADIUS`` of their current position
    (Moore neighborhood: self + up to 8 adjacent cells).  Visibility is clipped
    at grid boundaries so corner/edge agents see fewer cells.  No cell outside
    the viewport is ever included in the returned ``AgentPerception``.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_viewport(
        self,
        agent_id: AgentID,
        position: Position,
        grid: DungeonGrid,
        pending_messages: list[str],
        has_key: bool,
        turn: TurnNumber,
    ) -> AgentPerception:
        """Compute the agent's perception from the live ``DungeonGrid``.

        Parameters
        ----------
        agent_id:
            The agent whose perception is being computed.
        position:
            The agent's current ``(row, col)`` position.
        grid:
            The authoritative dungeon grid (read-only access used here).
        pending_messages:
            Messages delivered to the agent this turn (sent on turn - 1).
        has_key:
            Whether the agent is currently holding the key.
        turn:
            Current turn number.

        Returns
        -------
        AgentPerception
            Immutable perception snapshot containing only cells within
            ``FOG_RADIUS`` of *position*.
        """
        visible_cells = self._cells_from_grid(agent_id, position, grid)
        return AgentPerception(
            agent_id=agent_id,
            turn=turn,
            visible_cells=tuple(visible_cells),
            position=position,
            has_key=has_key,
            pending_messages=tuple(pending_messages),
        )

    def mask_world_state(
        self,
        agent_id: AgentID,
        world_state: WorldState,
        position: Position,
    ) -> AgentPerception:
        """Derive perception from a full ``WorldState``; used for testing.

        Parameters
        ----------
        agent_id:
            The agent whose perception is being computed.
        world_state:
            The complete world state (ground truth).  Only cells within
            ``FOG_RADIUS`` of *position* are included in the result.
        position:
            The agent's current ``(row, col)`` position.  Callers may pass a
            position that differs from ``world_state.agent_positions[agent_id]``
            to test boundary/edge scenarios without constructing a live grid.

        Returns
        -------
        AgentPerception
            Immutable perception snapshot.  ``pending_messages`` is always
            empty because ``WorldState`` carries no message queue.
        """
        visible_cells = self._cells_from_world_state(agent_id, position, world_state)
        has_key = world_state.key_held_by == agent_id
        return AgentPerception(
            agent_id=agent_id,
            turn=world_state.turn,
            visible_cells=tuple(visible_cells),
            position=position,
            has_key=has_key,
            pending_messages=(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _moore_neighborhood(
        position: Position,
        rows: int,
        cols: int,
    ) -> list[Position]:
        """Return all ``(row, col)`` pairs within ``FOG_RADIUS`` of *position*.

        Applies Moore neighborhood logic (includes diagonals) and clips
        results to the grid boundaries.
        """
        row, col = position
        neighbors: list[Position] = []
        for dr in range(-FOG_RADIUS, FOG_RADIUS + 1):
            for dc in range(-FOG_RADIUS, FOG_RADIUS + 1):
                nr, nc = row + dr, col + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    neighbors.append((nr, nc))
        return neighbors

    def _cells_from_grid(
        self,
        agent_id: AgentID,
        position: Position,
        grid: DungeonGrid,
    ) -> list[CellState]:
        """Gather ``CellState`` objects from a live ``DungeonGrid``."""
        visible: list[CellState] = []
        for pos in self._moore_neighborhood(position, grid.rows, grid.cols):
            raw = grid.get_cell(pos)
            # Annotate visibility — the raw cell's is_visible_to is always ()
            visible.append(
                CellState(
                    row=raw.row,
                    col=raw.col,
                    cell_type=raw.cell_type,
                    is_visible_to=(agent_id,),
                )
            )
        return visible

    def _cells_from_world_state(
        self,
        agent_id: AgentID,
        position: Position,
        world_state: WorldState,
    ) -> list[CellState]:
        """Gather ``CellState`` objects from a ``WorldState`` grid snapshot."""
        rows = len(world_state.grid)
        cols = len(world_state.grid[0]) if rows > 0 else 0
        visible: list[CellState] = []
        for nr, nc in self._moore_neighborhood(position, rows, cols):
            raw = world_state.grid[nr][nc]
            visible.append(
                CellState(
                    row=raw.row,
                    col=raw.col,
                    cell_type=raw.cell_type,
                    is_visible_to=(agent_id,),
                )
            )
        return visible
