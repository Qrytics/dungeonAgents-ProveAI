from __future__ import annotations

import json
import random
from typing import Any

from apps.simulation.schemas.state import CellState, WorldState
from packages.shared.constants import GRID_MIN_SIZE
from packages.shared.types import AgentID, CellType, Position, RunID, TurnNumber

# Minimum Manhattan distance between agent start positions
_AGENT_MIN_DISTANCE: int = 3
# Probability that any interior cell starts as a wall
_INTERIOR_WALL_DENSITY: float = 0.20


class DungeonGrid:
    """Authoritative physical state of the dungeon.

    The grid is initialized once per run and mutated exclusively through
    ``set_cell``.  All coordinates use (row, col) order.
    """

    def __init__(
        self,
        rows: int = 8,
        cols: int = 8,
        seed: int | None = None,
    ) -> None:
        if rows < GRID_MIN_SIZE:
            raise ValueError(f"rows must be >= {GRID_MIN_SIZE}, got {rows}")
        if cols < GRID_MIN_SIZE:
            raise ValueError(f"cols must be >= {GRID_MIN_SIZE}, got {cols}")

        self._rows = rows
        self._cols = cols
        self._seed = seed
        self._rng = random.Random(seed)

        # Internal grid: list-of-lists indexed by [row][col]
        self._grid: list[list[CellType]] = []

        # Special positions — set during generation
        self._key_pos: Position | None = None
        self._door_pos: Position | None = None
        self._exit_pos: Position | None = None
        self._agent_starts: dict[AgentID, Position] = {}

        self._generate()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_cell(self, pos: Position) -> CellState:
        row, col = pos
        self._validate_pos(pos)
        return CellState(row=row, col=col, cell_type=self._grid[row][col], is_visible_to=())

    def set_cell(self, pos: Position, cell_type: CellType) -> None:
        self._validate_pos(pos)
        row, col = pos
        self._grid[row][col] = cell_type

    def is_passable(self, pos: Position) -> bool:
        """Return True for floor, key, exit; False for wall or locked_door."""
        self._validate_pos(pos)
        row, col = pos
        return self._grid[row][col] in ("floor", "key", "exit")

    def get_agent_start_positions(self) -> dict[AgentID, Position]:
        return dict(self._agent_starts)

    def to_world_state(
        self,
        run_id: RunID,
        turn: TurnNumber,
        agent_positions: dict[AgentID, Position],
        key_held_by: AgentID | None,
        door_unlocked: bool,
    ) -> WorldState:
        grid_rows: list[tuple[CellState, ...]] = []
        for r in range(self._rows):
            row_cells: list[CellState] = []
            for c in range(self._cols):
                row_cells.append(
                    CellState(row=r, col=c, cell_type=self._grid[r][c], is_visible_to=())
                )
            grid_rows.append(tuple(row_cells))

        return WorldState(
            run_id=run_id,
            turn=turn,
            grid=tuple(grid_rows),
            agent_positions=agent_positions,
            key_held_by=key_held_by,
            door_unlocked=door_unlocked,
        )

    def serialize(self) -> str:
        """Return the full grid as a JSON string."""
        payload: dict[str, Any] = {
            "rows": self._rows,
            "cols": self._cols,
            "seed": self._seed,
            "grid": self._grid,
            "key_pos": list(self._key_pos) if self._key_pos else None,
            "door_pos": list(self._door_pos) if self._door_pos else None,
            "exit_pos": list(self._exit_pos) if self._exit_pos else None,
            "agent_starts": {
                agent_id: list(pos)
                for agent_id, pos in self._agent_starts.items()
            },
        }
        return json.dumps(payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_pos(self, pos: Position) -> None:
        row, col = pos
        if not (0 <= row < self._rows and 0 <= col < self._cols):
            raise IndexError(
                f"Position {pos} is out of bounds for {self._rows}×{self._cols} grid"
            )

    def _generate(self) -> None:
        """Build the grid according to the spec rules."""
        rows, cols = self._rows, self._cols

        # Step 1 — fill with floor, then wall the outer boundary
        self._grid = [["floor"] * cols for _ in range(rows)]
        for r in range(rows):
            for c in range(cols):
                if r == 0 or r == rows - 1 or c == 0 or c == cols - 1:
                    self._grid[r][c] = "wall"

        # Step 2 — randomise interior walls (~20% density)
        interior_cells: list[Position] = []
        for r in range(1, rows - 1):
            for c in range(1, cols - 1):
                interior_cells.append((r, c))

        for pos in interior_cells:
            if self._rng.random() < _INTERIOR_WALL_DENSITY:
                r, c = pos
                self._grid[r][c] = "wall"

        # Step 3 — collect passable interior cells for placement
        floor_cells = self._floor_interior_cells()

        if len(floor_cells) < 4:
            # Extremely rare; clear all interior walls and retry placement
            for r in range(1, rows - 1):
                for c in range(1, cols - 1):
                    self._grid[r][c] = "floor"
            floor_cells = self._floor_interior_cells()

        # Step 4 — place key and exit (must be on floor tiles)
        key_pos = self._rng.choice(floor_cells)
        self._grid[key_pos[0]][key_pos[1]] = "key"
        self._key_pos = key_pos

        remaining = [p for p in floor_cells if p != key_pos]
        exit_pos = self._rng.choice(remaining)
        self._grid[exit_pos[0]][exit_pos[1]] = "exit"
        self._exit_pos = exit_pos

        # Step 5 — place locked_door adjacent to at least one wall
        remaining = [p for p in remaining if p != exit_pos]
        door_candidates = [p for p in remaining if self._has_wall_neighbor(p)]
        if not door_candidates:
            # Fall back: use any remaining interior floor cell
            door_candidates = remaining

        door_pos = self._rng.choice(door_candidates)
        self._grid[door_pos[0]][door_pos[1]] = "locked_door"
        self._door_pos = door_pos

        # Step 6 — choose agent start positions
        #  • must be on floor tiles (not key/exit/locked_door)
        #  • at least AGENT_MIN_DISTANCE apart (Manhattan)
        start_candidates = self._floor_interior_cells()

        a_pos, b_pos = self._pick_two_distant(start_candidates, _AGENT_MIN_DISTANCE)
        self._agent_starts = {"agent_a": a_pos, "agent_b": b_pos}

    def _floor_interior_cells(self) -> list[Position]:
        """Return all interior cells currently typed as 'floor'."""
        cells: list[Position] = []
        for r in range(1, self._rows - 1):
            for c in range(1, self._cols - 1):
                if self._grid[r][c] == "floor":
                    cells.append((r, c))
        return cells

    def _has_wall_neighbor(self, pos: Position) -> bool:
        row, col = pos
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = row + dr, col + dc
            if 0 <= nr < self._rows and 0 <= nc < self._cols:
                if self._grid[nr][nc] == "wall":
                    return True
        return False

    @staticmethod
    def _manhattan(a: Position, b: Position) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _pick_two_distant(
        self,
        candidates: list[Position],
        min_dist: int,
    ) -> tuple[Position, Position]:
        """Pick two positions at least *min_dist* Manhattan distance apart."""
        # Shuffle then find the first valid pair
        shuffled = list(candidates)
        self._rng.shuffle(shuffled)
        for i, a in enumerate(shuffled):
            for b in shuffled[i + 1 :]:
                if self._manhattan(a, b) >= min_dist:
                    return a, b
        # Fallback: return the two most distant positions
        best_a, best_b, best_d = shuffled[0], shuffled[1], 0
        for i, a in enumerate(shuffled):
            for b in shuffled[i + 1 :]:
                d = self._manhattan(a, b)
                if d > best_d:
                    best_a, best_b, best_d = a, b, d
        return best_a, best_b
