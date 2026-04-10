"""Unit tests for the DungeonGrid (M-03).

These tests are fully deterministic (fixed seeds) and require no network access
or LLM API keys.
"""

import json

import pytest

from apps.simulation.environment.grid import DungeonGrid
from packages.shared.constants import GRID_MIN_SIZE
from packages.shared.types import CellType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def count_cell_type(grid: DungeonGrid, cell_type: CellType) -> int:
    count = 0
    for r in range(grid._rows):
        for c in range(grid._cols):
            if grid._grid[r][c] == cell_type:
                count += 1
    return count


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_grid_minimum_size() -> None:
    """A grid of minimum size (GRID_MIN_SIZE × GRID_MIN_SIZE) is created without errors."""
    g = DungeonGrid(rows=GRID_MIN_SIZE, cols=GRID_MIN_SIZE, seed=0)
    assert g._rows == GRID_MIN_SIZE
    assert g._cols == GRID_MIN_SIZE


def test_grid_rejects_too_small() -> None:
    """Grids smaller than GRID_MIN_SIZE raise ValueError."""
    with pytest.raises(ValueError):
        DungeonGrid(rows=GRID_MIN_SIZE - 1, cols=GRID_MIN_SIZE, seed=0)
    with pytest.raises(ValueError):
        DungeonGrid(rows=GRID_MIN_SIZE, cols=GRID_MIN_SIZE - 1, seed=0)


def test_required_elements() -> None:
    """Grid must contain exactly one key, one locked_door, one exit."""
    for seed in range(10):
        g = DungeonGrid(seed=seed)
        assert count_cell_type(g, "key") == 1, f"seed={seed}: expected 1 key"
        assert count_cell_type(g, "locked_door") == 1, f"seed={seed}: expected 1 locked_door"
        assert count_cell_type(g, "exit") == 1, f"seed={seed}: expected 1 exit"


def test_no_agent_overlap() -> None:
    """Agent start positions must be on floor tiles and differ from each other."""
    for seed in range(10):
        g = DungeonGrid(seed=seed)
        starts = g.get_agent_start_positions()
        a_pos = starts["agent_a"]
        b_pos = starts["agent_b"]

        assert g.is_passable(a_pos), f"seed={seed}: agent_a at non-passable {a_pos}"
        assert g.is_passable(b_pos), f"seed={seed}: agent_b at non-passable {b_pos}"
        assert a_pos != b_pos, f"seed={seed}: agents share start position {a_pos}"


def test_seed_reproducibility() -> None:
    """Same seed always produces the same layout."""
    for seed in (0, 42, 99):
        g1 = DungeonGrid(seed=seed)
        g2 = DungeonGrid(seed=seed)
        assert g1.serialize() == g2.serialize(), f"seed={seed}: grids differ"


def test_passable_cells() -> None:
    """Walls and locked_doors return False from is_passable(); floor/key/exit return True."""
    g = DungeonGrid(seed=7)
    for r in range(g._rows):
        for c in range(g._cols):
            pos = (r, c)
            ct: CellType = g._grid[r][c]
            if ct in ("wall", "locked_door"):
                assert not g.is_passable(pos), f"{ct} at {pos} should not be passable"
            else:
                assert g.is_passable(pos), f"{ct} at {pos} should be passable"


def test_outer_boundary_walls() -> None:
    """All cells on the outer boundary must be walls."""
    g = DungeonGrid(seed=3)
    rows, cols = g._rows, g._cols
    for r in range(rows):
        assert g._grid[r][0] == "wall", f"left boundary at row {r} is not wall"
        assert g._grid[r][cols - 1] == "wall", f"right boundary at row {r} is not wall"
    for c in range(cols):
        assert g._grid[0][c] == "wall", f"top boundary at col {c} is not wall"
        assert g._grid[rows - 1][c] == "wall", f"bottom boundary at col {c} is not wall"


def test_to_world_state_valid_schema() -> None:
    """to_world_state() produces a valid WorldState schema."""
    from apps.simulation.schemas.state import WorldState
    from packages.shared.types import RunID, TurnNumber

    g = DungeonGrid(seed=1)
    starts = g.get_agent_start_positions()
    ws = g.to_world_state(
        run_id=RunID("run-test"),
        turn=TurnNumber(0),
        agent_positions=dict(starts),
        key_held_by=None,
        door_unlocked=False,
    )
    assert isinstance(ws, WorldState)
    assert ws.run_id == "run-test"
    assert ws.turn == 0
    # Grid dimensions must match
    assert len(ws.grid) == g._rows
    assert all(len(row) == g._cols for row in ws.grid)


def test_serialize_round_trip() -> None:
    """serialize() produces valid JSON with expected top-level keys."""
    g = DungeonGrid(seed=5)
    data = json.loads(g.serialize())
    for key in ("rows", "cols", "seed", "grid", "key_pos", "door_pos", "exit_pos", "agent_starts"):
        assert key in data, f"missing key '{key}' in serialized output"
    assert data["rows"] == g._rows
    assert data["cols"] == g._cols


def test_set_cell_mutates_grid() -> None:
    """set_cell() changes the cell type at the given position."""
    g = DungeonGrid(seed=2)
    # Find a floor cell to mutate
    for r in range(1, g._rows - 1):
        for c in range(1, g._cols - 1):
            if g._grid[r][c] == "floor":
                pos = (r, c)
                g.set_cell(pos, "wall")
                assert g._grid[r][c] == "wall"
                return
    pytest.fail("No floor cell found to mutate")


def test_get_cell_out_of_bounds() -> None:
    """get_cell() raises IndexError for out-of-bounds positions."""
    g = DungeonGrid(seed=0)
    with pytest.raises(IndexError):
        g.get_cell((-1, 0))
    with pytest.raises(IndexError):
        g.get_cell((g._rows, 0))
    with pytest.raises(IndexError):
        g.get_cell((0, g._cols))
