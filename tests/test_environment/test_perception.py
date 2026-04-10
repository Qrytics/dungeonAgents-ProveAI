"""Unit tests for the PerceptionEngine (M-04).

All tests are fully deterministic and require no network or LLM access.
"""

from __future__ import annotations

import pytest

from apps.simulation.environment.grid import DungeonGrid
from apps.simulation.environment.perception import PerceptionEngine
from apps.simulation.schemas.state import AgentPerception, CellState, WorldState
from packages.shared.constants import FOG_RADIUS
from packages.shared.types import AgentID, RunID, TurnNumber


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGENT: AgentID = "agent_a"
_TURN: TurnNumber = TurnNumber(0)
_RUN: RunID = RunID("test-run")


def _make_world_state(rows: int = 8, cols: int = 8, seed: int = 0) -> WorldState:
    """Build a WorldState from a deterministic DungeonGrid."""
    grid = DungeonGrid(rows=rows, cols=cols, seed=seed)
    starts = grid.get_agent_start_positions()
    return grid.to_world_state(
        run_id=_RUN,
        turn=_TURN,
        agent_positions=dict(starts),
        key_held_by=None,
        door_unlocked=False,
    )


def _visible_count(perception: AgentPerception) -> int:
    return len(perception.visible_cells)


def _visible_positions(perception: AgentPerception) -> set[tuple[int, int]]:
    return {(c.row, c.col) for c in perception.visible_cells}


# ---------------------------------------------------------------------------
# Cell-count acceptance criteria (mask_world_state)
# ---------------------------------------------------------------------------


class TestVisibleCellCounts:
    """Acceptance criteria: correct visible cell counts for corner / edge / interior."""

    engine = PerceptionEngine()

    def test_interior_sees_nine_cells(self) -> None:
        """Agent at a strictly interior position sees exactly 9 cells (3×3 Moore window)."""
        ws = _make_world_state(rows=8, cols=8, seed=0)
        # (3, 3) is well inside the 8×8 grid — guaranteed interior
        perception = self.engine.mask_world_state(_AGENT, ws, position=(3, 3))
        assert _visible_count(perception) == 9

    def test_corner_sees_four_cells(self) -> None:
        """Agent at grid corner (0, 0) sees exactly 4 cells (clipped Moore window)."""
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(0, 0))
        assert _visible_count(perception) == 4

    def test_corner_top_right_sees_four_cells(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(0, 7))
        assert _visible_count(perception) == 4

    def test_corner_bottom_left_sees_four_cells(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(7, 0))
        assert _visible_count(perception) == 4

    def test_corner_bottom_right_sees_four_cells(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(7, 7))
        assert _visible_count(perception) == 4

    def test_top_edge_sees_six_cells(self) -> None:
        """Agent on the top edge (non-corner) sees exactly 6 cells."""
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(0, 3))
        assert _visible_count(perception) == 6

    def test_bottom_edge_sees_six_cells(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(7, 3))
        assert _visible_count(perception) == 6

    def test_left_edge_sees_six_cells(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(3, 0))
        assert _visible_count(perception) == 6

    def test_right_edge_sees_six_cells(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(3, 7))
        assert _visible_count(perception) == 6


# ---------------------------------------------------------------------------
# No information leakage outside FOG_RADIUS
# ---------------------------------------------------------------------------


class TestFogOfWar:
    """No cell outside FOG_RADIUS is ever included in visible_cells."""

    engine = PerceptionEngine()

    @pytest.mark.parametrize(
        "position",
        [(1, 1), (1, 6), (6, 1), (6, 6), (3, 3), (4, 4)],
    )
    def test_no_leakage_mask_world_state(self, position: tuple[int, int]) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=42)
        perception = self.engine.mask_world_state(_AGENT, ws, position=position)
        row, col = position
        for cell in perception.visible_cells:
            assert abs(cell.row - row) <= FOG_RADIUS, (
                f"cell ({cell.row},{cell.col}) is outside FOG_RADIUS={FOG_RADIUS} "
                f"from position {position}"
            )
            assert abs(cell.col - col) <= FOG_RADIUS, (
                f"cell ({cell.row},{cell.col}) is outside FOG_RADIUS={FOG_RADIUS} "
                f"from position {position}"
            )

    @pytest.mark.parametrize(
        "position",
        [(1, 1), (3, 3), (6, 6)],
    )
    def test_no_leakage_compute_viewport(self, position: tuple[int, int]) -> None:
        grid = DungeonGrid(rows=8, cols=8, seed=7)
        perception = self.engine.compute_viewport(
            agent_id=_AGENT,
            position=position,
            grid=grid,
            pending_messages=[],
            has_key=False,
            turn=_TURN,
        )
        row, col = position
        for cell in perception.visible_cells:
            assert abs(cell.row - row) <= FOG_RADIUS
            assert abs(cell.col - col) <= FOG_RADIUS


# ---------------------------------------------------------------------------
# Correct positions in viewport
# ---------------------------------------------------------------------------


class TestViewportPositions:
    """Visible cells contain exactly the expected (row, col) pairs."""

    engine = PerceptionEngine()

    def test_interior_viewport_exact_positions(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(3, 3))
        expected = {(r, c) for r in range(2, 5) for c in range(2, 5)}
        assert _visible_positions(perception) == expected

    def test_corner_viewport_exact_positions(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(0, 0))
        expected = {(0, 0), (0, 1), (1, 0), (1, 1)}
        assert _visible_positions(perception) == expected

    def test_edge_viewport_exact_positions(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(0, 3))
        expected = {(0, 2), (0, 3), (0, 4), (1, 2), (1, 3), (1, 4)}
        assert _visible_positions(perception) == expected


# ---------------------------------------------------------------------------
# is_visible_to annotation
# ---------------------------------------------------------------------------


class TestIsVisibleTo:
    """All returned cells must be annotated with the querying agent_id."""

    engine = PerceptionEngine()

    def test_all_cells_annotated_mask_world_state(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=1)
        for pos in [(3, 3), (0, 0), (0, 4)]:
            perception = self.engine.mask_world_state(_AGENT, ws, position=pos)
            for cell in perception.visible_cells:
                assert _AGENT in cell.is_visible_to, (
                    f"cell {(cell.row, cell.col)} missing agent_id in is_visible_to"
                )

    def test_all_cells_annotated_compute_viewport(self) -> None:
        grid = DungeonGrid(rows=8, cols=8, seed=1)
        perception = self.engine.compute_viewport(
            agent_id=_AGENT,
            position=(3, 3),
            grid=grid,
            pending_messages=[],
            has_key=False,
            turn=_TURN,
        )
        for cell in perception.visible_cells:
            assert _AGENT in cell.is_visible_to


# ---------------------------------------------------------------------------
# AgentPerception field correctness
# ---------------------------------------------------------------------------


class TestPerceptionFields:
    """Verify that all AgentPerception fields are populated correctly."""

    engine = PerceptionEngine()

    def test_compute_viewport_fields(self) -> None:
        grid = DungeonGrid(rows=8, cols=8, seed=3)
        messages = ["hello", "world"]
        perception = self.engine.compute_viewport(
            agent_id=_AGENT,
            position=(2, 2),
            grid=grid,
            pending_messages=messages,
            has_key=True,
            turn=TurnNumber(5),
        )
        assert perception.agent_id == _AGENT
        assert perception.turn == 5
        assert perception.position == (2, 2)
        assert perception.has_key is True
        assert perception.pending_messages == ("hello", "world")
        assert isinstance(perception.visible_cells, tuple)

    def test_mask_world_state_has_key_true(self) -> None:
        """has_key is True when world_state.key_held_by == agent_id."""
        ws = _make_world_state(rows=8, cols=8, seed=0)
        # Rebuild with agent_a holding the key
        grid = DungeonGrid(rows=8, cols=8, seed=0)
        starts = grid.get_agent_start_positions()
        ws_with_key = WorldState(
            run_id=_RUN,
            turn=_TURN,
            grid=ws.grid,
            agent_positions=dict(starts),
            key_held_by="agent_a",
            door_unlocked=False,
        )
        perception = self.engine.mask_world_state(_AGENT, ws_with_key, position=(3, 3))
        assert perception.has_key is True

    def test_mask_world_state_has_key_false(self) -> None:
        """has_key is False when key is held by another agent or no one."""
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(3, 3))
        assert perception.has_key is False

    def test_mask_world_state_pending_messages_empty(self) -> None:
        """mask_world_state always produces empty pending_messages."""
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(3, 3))
        assert perception.pending_messages == ()

    def test_compute_viewport_returns_agent_perception_instance(self) -> None:
        grid = DungeonGrid(rows=8, cols=8, seed=0)
        perception = self.engine.compute_viewport(
            agent_id=_AGENT,
            position=(1, 1),
            grid=grid,
            pending_messages=[],
            has_key=False,
            turn=_TURN,
        )
        assert isinstance(perception, AgentPerception)

    def test_mask_world_state_returns_agent_perception_instance(self) -> None:
        ws = _make_world_state(rows=8, cols=8, seed=0)
        perception = self.engine.mask_world_state(_AGENT, ws, position=(1, 1))
        assert isinstance(perception, AgentPerception)


# ---------------------------------------------------------------------------
# compute_viewport vs mask_world_state consistency
# ---------------------------------------------------------------------------


class TestConsistency:
    """compute_viewport and mask_world_state agree on cell count and positions."""

    engine = PerceptionEngine()

    @pytest.mark.parametrize(
        "position",
        [(1, 1), (3, 3), (0, 0), (0, 4), (4, 0), (7, 7)],
    )
    def test_consistent_visible_positions(self, position: tuple[int, int]) -> None:
        seed = 11
        grid = DungeonGrid(rows=8, cols=8, seed=seed)
        starts = grid.get_agent_start_positions()
        ws = grid.to_world_state(
            run_id=_RUN,
            turn=_TURN,
            agent_positions=dict(starts),
            key_held_by=None,
            door_unlocked=False,
        )

        p_viewport = self.engine.compute_viewport(
            agent_id=_AGENT,
            position=position,
            grid=grid,
            pending_messages=[],
            has_key=False,
            turn=_TURN,
        )
        p_mask = self.engine.mask_world_state(_AGENT, ws, position=position)

        assert _visible_positions(p_viewport) == _visible_positions(p_mask), (
            f"Position {position}: viewport and mask disagree on visible cells"
        )
