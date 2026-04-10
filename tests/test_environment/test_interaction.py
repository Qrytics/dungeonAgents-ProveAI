"""Unit tests for InteractionValidator (M-05).

All tests use fixed seeds for determinism and require no network or LLM access.
"""
from __future__ import annotations

import pytest

from apps.simulation.environment.grid import DungeonGrid
from apps.simulation.environment.interaction import InteractionValidator

# Maps (delta_row, delta_col) → direction name
_DELTA_TO_DIRECTION: dict[tuple[int, int], str] = {
    (-1, 0): "north",
    (1, 0): "south",
    (0, 1): "east",
    (0, -1): "west",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tiny_grid() -> DungeonGrid:
    """Return a minimal 8×8 grid with a fixed seed."""
    return DungeonGrid(rows=8, cols=8, seed=42)


def _find_cell(grid: DungeonGrid, cell_type: str) -> tuple[int, int]:
    """Return the position of the first cell with *cell_type*."""
    for r in range(grid._rows):
        for c in range(grid._cols):
            if grid._grid[r][c] == cell_type:
                return (r, c)
    pytest.fail(f"No cell of type '{cell_type}' found in grid.")


def _floor_neighbor(grid: DungeonGrid, pos: tuple[int, int]) -> tuple[int, int] | None:
    """Return an adjacent floor cell of *pos*, or None."""
    row, col = pos
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = row + dr, col + dc
        if 0 <= nr < grid._rows and 0 <= nc < grid._cols:
            if grid._grid[nr][nc] == "floor":
                return (nr, nc)
    return None


# ---------------------------------------------------------------------------
# validate_move
# ---------------------------------------------------------------------------


class TestValidateMove:
    val = InteractionValidator()

    def test_move_into_wall_is_invalid(self) -> None:
        grid = _make_tiny_grid()
        # The boundary row=0 is all walls; place agent at (1,1) and move north into (0,1).
        # Force (1,1) to floor so we have a known starting position.
        grid._grid[1][1] = "floor"
        # (0,1) is a boundary wall — guaranteed by grid construction.
        assert grid._grid[0][1] == "wall"
        valid, reason, new_pos = self.val.validate_move("agent_a", "north", (1, 1), grid, False)
        assert valid is False
        assert new_pos is None
        assert "wall" in reason

    def test_move_into_floor_is_valid(self) -> None:
        grid = DungeonGrid(rows=8, cols=8, seed=0)
        # Place agent on a known interior floor cell and try moving
        for r in range(1, 7):
            for c in range(1, 7):
                if grid._grid[r][c] == "floor":
                    for dr, dc, direction in ((-1, 0, "north"), (1, 0, "south"), (0, 1, "east"), (0, -1, "west")):
                        nr, nc = r + dr, c + dc
                        if grid._grid[nr][nc] == "floor":
                            valid, reason, new_pos = self.val.validate_move(
                                "agent_a", direction, (r, c), grid, False
                            )
                            assert valid is True
                            assert new_pos == (nr, nc)
                            return

    def test_move_into_locked_door_without_unlock_is_invalid(self) -> None:
        grid = _make_tiny_grid()
        door_pos = _find_cell(grid, "locked_door")
        neighbor = _floor_neighbor(grid, door_pos)
        if neighbor is None:
            pytest.skip("No floor neighbor adjacent to locked_door in seed=42 grid.")
        row, col = door_pos
        nr, nc = neighbor
        direction = _DELTA_TO_DIRECTION[(row - nr, col - nc)]
        valid, reason, new_pos = self.val.validate_move("agent_a", direction, neighbor, grid, door_unlocked=False)
        assert valid is False
        assert new_pos is None
        assert "locked" in reason.lower()

    def test_move_into_unlocked_door_is_valid(self) -> None:
        grid = _make_tiny_grid()
        door_pos = _find_cell(grid, "locked_door")
        neighbor = _floor_neighbor(grid, door_pos)
        if neighbor is None:
            pytest.skip("No floor neighbor adjacent to locked_door in seed=42 grid.")
        row, col = door_pos
        nr, nc = neighbor
        direction = _DELTA_TO_DIRECTION[(row - nr, col - nc)]
        valid, reason, new_pos = self.val.validate_move("agent_a", direction, neighbor, grid, door_unlocked=True)
        assert valid is True
        assert new_pos == door_pos

    def test_move_into_key_cell_is_valid(self) -> None:
        grid = _make_tiny_grid()
        key_pos = _find_cell(grid, "key")
        neighbor = _floor_neighbor(grid, key_pos)
        if neighbor is None:
            pytest.skip("No floor neighbor adjacent to key in seed=42 grid.")
        row, col = key_pos
        nr, nc = neighbor
        direction = _DELTA_TO_DIRECTION[(row - nr, col - nc)]
        valid, reason, new_pos = self.val.validate_move("agent_a", direction, neighbor, grid, False)
        assert valid is True
        assert new_pos == key_pos

    def test_move_into_exit_cell_is_valid(self) -> None:
        grid = _make_tiny_grid()
        exit_pos = _find_cell(grid, "exit")
        neighbor = _floor_neighbor(grid, exit_pos)
        if neighbor is None:
            pytest.skip("No floor neighbor adjacent to exit in seed=42 grid.")
        row, col = exit_pos
        nr, nc = neighbor
        direction = _DELTA_TO_DIRECTION[(row - nr, col - nc)]
        valid, reason, new_pos = self.val.validate_move("agent_a", direction, neighbor, grid, False)
        assert valid is True
        assert new_pos == exit_pos

    def test_move_out_of_bounds_is_invalid(self) -> None:
        grid = _make_tiny_grid()
        # Outer boundary cells are walls, but we can test via placing agent at (0,0)
        # The boundary walls make direct OOB hard; instead manipulate grid internals.
        # Override a boundary wall to floor temporarily to expose OOB logic.
        grid._grid[0][0] = "floor"
        valid, reason, new_pos = self.val.validate_move("agent_a", "north", (0, 0), grid, False)
        assert valid is False
        assert new_pos is None
        grid._grid[0][0] = "wall"  # restore


# ---------------------------------------------------------------------------
# validate_interact
# ---------------------------------------------------------------------------


class TestValidateInteract:
    val = InteractionValidator()

    def test_pickup_key_when_on_key_cell_and_no_holder(self) -> None:
        grid = _make_tiny_grid()
        key_pos = _find_cell(grid, "key")
        valid, reason, mutations = self.val.validate_interact(
            "agent_a", key_pos, grid, key_held_by=None, door_unlocked=False
        )
        assert valid is True
        assert mutations == {"key_held_by": "agent_a"}

    def test_pickup_key_fails_if_already_held(self) -> None:
        grid = _make_tiny_grid()
        key_pos = _find_cell(grid, "key")
        valid, reason, mutations = self.val.validate_interact(
            "agent_a", key_pos, grid, key_held_by="agent_b", door_unlocked=False
        )
        assert valid is False
        assert mutations == {}
        assert "agent_b" in reason

    def test_unlock_door_when_adjacent_and_holding_key(self) -> None:
        grid = _make_tiny_grid()
        door_pos = _find_cell(grid, "locked_door")
        neighbor = _floor_neighbor(grid, door_pos)
        if neighbor is None:
            pytest.skip("No floor neighbor adjacent to locked_door in seed=42 grid.")
        valid, reason, mutations = self.val.validate_interact(
            "agent_a", neighbor, grid, key_held_by="agent_a", door_unlocked=False
        )
        assert valid is True
        assert mutations == {"door_unlocked": True}

    def test_unlock_door_fails_if_not_holding_key(self) -> None:
        grid = _make_tiny_grid()
        door_pos = _find_cell(grid, "locked_door")
        neighbor = _floor_neighbor(grid, door_pos)
        if neighbor is None:
            pytest.skip("No floor neighbor adjacent to locked_door in seed=42 grid.")
        valid, reason, mutations = self.val.validate_interact(
            "agent_a", neighbor, grid, key_held_by=None, door_unlocked=False
        )
        assert valid is False
        assert mutations == {}

    def test_unlock_door_fails_if_already_unlocked(self) -> None:
        grid = _make_tiny_grid()
        door_pos = _find_cell(grid, "locked_door")
        neighbor = _floor_neighbor(grid, door_pos)
        if neighbor is None:
            pytest.skip("No floor neighbor adjacent to locked_door in seed=42 grid.")
        valid, reason, mutations = self.val.validate_interact(
            "agent_a", neighbor, grid, key_held_by="agent_a", door_unlocked=True
        )
        assert valid is False
        assert mutations == {}

    def test_unlock_door_requires_adjacency_not_standing_on_door(self) -> None:
        """Standing directly ON the door cell should NOT trigger unlock."""
        grid = _make_tiny_grid()
        door_pos = _find_cell(grid, "locked_door")
        # Temporarily make the door cell appear as floor so validate_interact
        # can reason about it (agent is "on" it, not adjacent).
        grid._grid[door_pos[0]][door_pos[1]] = "floor"
        valid, reason, mutations = self.val.validate_interact(
            "agent_a", door_pos, grid, key_held_by="agent_a", door_unlocked=False
        )
        # No adjacent locked_door → nothing to interact with
        assert valid is False
        assert mutations == {}
        grid._grid[door_pos[0]][door_pos[1]] = "locked_door"  # restore

    def test_nothing_to_interact_on_plain_floor(self) -> None:
        grid = _make_tiny_grid()
        # Find a floor cell that is not adjacent to a locked_door
        door_pos = _find_cell(grid, "locked_door")
        for r in range(1, 7):
            for c in range(1, 7):
                if grid._grid[r][c] != "floor":
                    continue
                pos = (r, c)
                if pos == door_pos:
                    continue
                # Check not adjacent to door
                adjacent = any(
                    (r + dr, c + dc) == door_pos
                    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                )
                if not adjacent:
                    valid, reason, mutations = self.val.validate_interact(
                        "agent_a", pos, grid, key_held_by=None, door_unlocked=False
                    )
                    assert valid is False
                    assert mutations == {}
                    return
        pytest.skip("Could not find a non-adjacent floor cell.")


# ---------------------------------------------------------------------------
# validate_observe
# ---------------------------------------------------------------------------


class TestValidateObserve:
    val = InteractionValidator()

    def test_observe_always_valid(self) -> None:
        grid = _make_tiny_grid()
        for pos in [(1, 1), (3, 3), (6, 6)]:
            valid, reason = self.val.validate_observe("agent_a", pos, grid)
            assert valid is True

    def test_observe_includes_agent_in_reason(self) -> None:
        grid = _make_tiny_grid()
        valid, reason = self.val.validate_observe("agent_b", (2, 2), grid)
        assert valid is True
        assert "agent_b" in reason


# ---------------------------------------------------------------------------
# validate_communicate
# ---------------------------------------------------------------------------


class TestValidateCommunicate:
    val = InteractionValidator()

    def test_valid_message(self) -> None:
        valid, reason = self.val.validate_communicate("agent_a", "agent_b", "Hello!")
        assert valid is True

    def test_self_message_is_invalid(self) -> None:
        valid, reason = self.val.validate_communicate("agent_a", "agent_a", "Hello!")
        assert valid is False
        assert "agent_a" in reason

    def test_empty_content_is_invalid(self) -> None:
        valid, reason = self.val.validate_communicate("agent_a", "agent_b", "")
        assert valid is False

    def test_whitespace_only_content_is_invalid(self) -> None:
        valid, reason = self.val.validate_communicate("agent_a", "agent_b", "   ")
        assert valid is False
