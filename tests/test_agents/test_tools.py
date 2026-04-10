"""Unit tests for agent tools (M-07) and belief state manager (M-08).

All tests use a stub orchestrator so that no LLM or real game state is
required — only the tool logic and the interaction validator are exercised.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.simulation.agents.state import AgentBeliefStateManager
from apps.simulation.agents.tools import (
    TOOL_CONTEXT_KEY,
    ToolContext,
    communicate,
    interact,
    move,
    observe,
)
from apps.simulation.environment.grid import DungeonGrid
from apps.simulation.environment.interaction import InteractionValidator
from apps.simulation.schemas.events import IntentionEvent, OutcomeEvent
from apps.simulation.schemas.state import AgentPerception, CellState, WorldState
from packages.shared.types import RunID, TurnNumber

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_RUN_ID: RunID = RunID("00000000-0000-0000-0000-000000000001")
_TURN: TurnNumber = TurnNumber(1)


def _make_grid(seed: int = 42) -> DungeonGrid:
    return DungeonGrid(rows=8, cols=8, seed=seed)


def _make_world_state(grid: DungeonGrid) -> WorldState:
    return grid.to_world_state(
        run_id=_RUN_ID,
        turn=_TURN,
        agent_positions=grid.get_agent_start_positions(),
        key_held_by=None,
        door_unlocked=False,
    )


def _find_cell(grid: DungeonGrid, cell_type: str) -> tuple[int, int]:
    """Return the first cell of *cell_type*, failing the test if absent."""
    for r in range(grid.rows):
        for c in range(grid.cols):
            if grid._grid[r][c] == cell_type:
                return (r, c)
    pytest.fail(f"No '{cell_type}' cell in grid.")
    raise AssertionError  # unreachable; satisfies type checker


def _floor_neighbor(grid: DungeonGrid, pos: tuple[int, int]) -> tuple[int, int] | None:
    """Return the first adjacent floor cell, or None."""
    r, c = pos
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < grid.rows and 0 <= nc < grid.cols:
            if grid._grid[nr][nc] == "floor":
                return (nr, nc)
    return None


# ---------------------------------------------------------------------------
# Stub orchestrator
# ---------------------------------------------------------------------------


class _StubOrchestrator:
    """Captures the last ``IntentionEvent`` and returns a preset ``OutcomeEvent``."""

    def __init__(
        self,
        result_description: str = "ok",
        success: bool = True,
    ) -> None:
        self.last_intention: IntentionEvent | None = None
        self._result_description = result_description
        self._success = success

    def apply_intention(
        self,
        intention: IntentionEvent,
        current_world_state: WorldState,
    ) -> OutcomeEvent:
        self.last_intention = intention
        return OutcomeEvent(
            event_type="outcome",
            run_id=intention.run_id,
            turn=intention.turn,
            agent_id=intention.agent_id,
            tool_name=intention.tool_name,
            success=self._success,
            result_description=self._result_description,
            world_state_after=current_world_state,
            divergence_score=None,
            timestamp=datetime.now(tz=timezone.utc),
        )


def _make_context(
    *,
    grid: DungeonGrid | None = None,
    agent_id: str = "agent_a",
    orchestrator: _StubOrchestrator | None = None,
    llm_prompt_tokens: int = 10,
    llm_completion_tokens: int = 5,
    latency_ms: float = 42.0,
    raw_llm_output: str = "test output",
) -> ToolContext:
    if grid is None:
        grid = _make_grid()
    if orchestrator is None:
        orchestrator = _StubOrchestrator()
    return ToolContext(
        agent_id=agent_id,  # type: ignore[arg-type]
        world_state=_make_world_state(grid),
        run_id=_RUN_ID,
        turn=_TURN,
        orchestrator=orchestrator,
        llm_prompt_tokens=llm_prompt_tokens,
        llm_completion_tokens=llm_completion_tokens,
        latency_ms=latency_ms,
        raw_llm_output=raw_llm_output,
    )


def _config(ctx: ToolContext) -> dict:
    return {"configurable": {TOOL_CONTEXT_KEY: ctx}}


# ---------------------------------------------------------------------------
# Tool tests: IntentionEvent construction & orchestrator delegation
# ---------------------------------------------------------------------------


class TestMoveTool:
    def test_move_emits_correct_intention(self) -> None:
        stub = _StubOrchestrator()
        ctx = _make_context(orchestrator=stub)
        move.invoke({"direction": "north"}, config=_config(ctx))

        assert stub.last_intention is not None
        assert stub.last_intention.event_type == "intention"
        assert stub.last_intention.tool_name == "move"
        assert stub.last_intention.tool_args == {"direction": "north"}
        assert stub.last_intention.agent_id == "agent_a"
        assert stub.last_intention.run_id == _RUN_ID
        assert stub.last_intention.turn == _TURN
        assert stub.last_intention.llm_prompt_tokens == 10
        assert stub.last_intention.llm_completion_tokens == 5
        assert stub.last_intention.latency_ms == 42.0

    def test_move_returns_orchestrator_result(self) -> None:
        stub = _StubOrchestrator(result_description="Moved to (2, 3).")
        ctx = _make_context(orchestrator=stub)
        result = move.invoke({"direction": "south"}, config=_config(ctx))
        assert result == "Moved to (2, 3)."

    def test_move_does_not_mutate_world_state(self) -> None:
        grid = _make_grid()
        stub = _StubOrchestrator()
        ctx = _make_context(grid=grid, orchestrator=stub)
        snapshot_before = ctx.world_state
        move.invoke({"direction": "east"}, config=_config(ctx))
        # WorldState is a frozen Pydantic model; invoking a tool must never
        # replace the reference stored in the context either.
        assert ctx.world_state is snapshot_before


class TestObserveTool:
    def test_observe_emits_correct_intention(self) -> None:
        stub = _StubOrchestrator()
        ctx = _make_context(orchestrator=stub)
        observe.invoke({}, config=_config(ctx))

        assert stub.last_intention is not None
        assert stub.last_intention.event_type == "intention"
        assert stub.last_intention.tool_name == "observe"
        assert stub.last_intention.tool_args == {}

    def test_observe_returns_orchestrator_result(self) -> None:
        stub = _StubOrchestrator(result_description="Visible: floor(3,3), wall(3,4)")
        ctx = _make_context(orchestrator=stub)
        result = observe.invoke({}, config=_config(ctx))
        assert result == "Visible: floor(3,3), wall(3,4)"


class TestInteractTool:
    def test_interact_emits_correct_intention(self) -> None:
        stub = _StubOrchestrator()
        ctx = _make_context(orchestrator=stub)
        interact.invoke({}, config=_config(ctx))

        assert stub.last_intention is not None
        assert stub.last_intention.tool_name == "interact"
        assert stub.last_intention.tool_args == {}

    def test_interact_returns_orchestrator_result(self) -> None:
        stub = _StubOrchestrator(result_description="Picked up the key.")
        ctx = _make_context(orchestrator=stub)
        result = interact.invoke({}, config=_config(ctx))
        assert result == "Picked up the key."


class TestCommunicateTool:
    def test_communicate_emits_correct_intention(self) -> None:
        stub = _StubOrchestrator()
        ctx = _make_context(orchestrator=stub)
        communicate.invoke(
            {"recipient": "agent_b", "message": "Hello!"},
            config=_config(ctx),
        )

        assert stub.last_intention is not None
        assert stub.last_intention.tool_name == "communicate"
        assert stub.last_intention.tool_args == {
            "recipient": "agent_b",
            "message": "Hello!",
        }

    def test_communicate_returns_orchestrator_result(self) -> None:
        stub = _StubOrchestrator(result_description="Message queued for agent_b.")
        ctx = _make_context(orchestrator=stub)
        result = communicate.invoke(
            {"recipient": "agent_b", "message": "Hello!"},
            config=_config(ctx),
        )
        assert result == "Message queued for agent_b."


# ---------------------------------------------------------------------------
# M-20 named test cases (validator-level, exercised without LLM)
# ---------------------------------------------------------------------------

_VAL = InteractionValidator()


class TestMoveIntoWallFails:
    def test_move_into_wall_fails(self) -> None:
        grid = _make_grid()
        grid._grid[1][1] = "floor"
        assert grid._grid[0][1] == "wall", "boundary must be a wall"

        valid, reason, new_pos = _VAL.validate_move(
            "agent_a", "north", (1, 1), grid, door_unlocked=False
        )
        assert valid is False
        assert new_pos is None
        assert "wall" in reason


class TestMoveIntoFloorSucceeds:
    def test_move_into_floor_succeeds(self) -> None:
        grid = _make_grid(seed=0)
        for r in range(1, 7):
            for c in range(1, 7):
                if grid._grid[r][c] != "floor":
                    continue
                for dr, dc, direction in [
                    (-1, 0, "north"),
                    (1, 0, "south"),
                    (0, 1, "east"),
                    (0, -1, "west"),
                ]:
                    nr, nc = r + dr, c + dc
                    if grid._grid[nr][nc] == "floor":
                        valid, reason, new_pos = _VAL.validate_move(
                            "agent_a", direction, (r, c), grid, door_unlocked=False
                        )
                        assert valid is True
                        assert new_pos == (nr, nc)
                        return
        pytest.skip("No two adjacent floor cells found in seed=0 grid.")


class TestPickUpKeySucceeds:
    def test_pick_up_key_succeeds(self) -> None:
        grid = _make_grid()
        key_pos = _find_cell(grid, "key")

        valid, reason, mutations = _VAL.validate_interact(
            "agent_a", key_pos, grid, key_held_by=None, door_unlocked=False
        )
        assert valid is True
        assert mutations == {"key_held_by": "agent_a"}


class TestUnlockDoorRequiresKey:
    def test_unlock_door_requires_key(self) -> None:
        grid = _make_grid()
        door_pos = _find_cell(grid, "locked_door")
        neighbor = _floor_neighbor(grid, door_pos)
        if neighbor is None:
            pytest.skip("No floor neighbor adjacent to locked_door in seed=42 grid.")

        # Without holding the key, unlocking must fail.
        valid, reason, mutations = _VAL.validate_interact(
            "agent_a", neighbor, grid, key_held_by=None, door_unlocked=False
        )
        assert valid is False
        assert mutations == {}


class TestCommunicateSelfFails:
    def test_communicate_self_fails(self) -> None:
        valid, reason = _VAL.validate_communicate("agent_a", "agent_a", "Hello!")
        assert valid is False
        assert "agent_a" in reason


# ---------------------------------------------------------------------------
# M-20 named test cases (belief state — AgentBeliefStateManager / M-08)
# ---------------------------------------------------------------------------


class TestBeliefUpdatesFromPerception:
    def test_belief_updates_from_perception(self) -> None:
        manager = AgentBeliefStateManager("agent_a")
        assert manager.get_current_belief().believed_grid == {}

        perception = AgentPerception(
            agent_id="agent_a",
            turn=TurnNumber(1),
            visible_cells=(
                CellState(row=3, col=3, cell_type="floor", is_visible_to=("agent_a",)),
                CellState(row=3, col=4, cell_type="wall", is_visible_to=("agent_a",)),
            ),
            position=(3, 3),
            has_key=False,
            pending_messages=(),
        )
        belief = manager.update_from_perception(perception)
        assert len(belief.believed_grid) == 2
        assert belief.believed_grid[(3, 3)] == "floor"
        assert belief.believed_grid[(3, 4)] == "wall"

        # Second perception at a new cell — belief map must grow monotonically.
        perception2 = AgentPerception(
            agent_id="agent_a",
            turn=TurnNumber(2),
            visible_cells=(
                CellState(row=3, col=3, cell_type="floor", is_visible_to=("agent_a",)),
                CellState(row=4, col=3, cell_type="floor", is_visible_to=("agent_a",)),
            ),
            position=(3, 3),
            has_key=False,
            pending_messages=(),
        )
        belief2 = manager.update_from_perception(perception2)
        # (3,3), (3,4) from first + (4,3) new from second
        assert len(belief2.believed_grid) == 3
        assert (4, 3) in belief2.believed_grid


class TestBeliefPreservesStalePositions:
    def test_belief_preserves_stale_positions(self) -> None:
        manager = AgentBeliefStateManager("agent_a")

        # Turn 1 — agent_b observed at (5, 5).
        perception1 = AgentPerception(
            agent_id="agent_a",
            turn=TurnNumber(1),
            visible_cells=(
                CellState(row=5, col=5, cell_type="agent", is_visible_to=("agent_a",)),
            ),
            position=(3, 3),
            has_key=False,
            pending_messages=(),
        )
        belief1 = manager.update_from_perception(perception1)
        assert belief1.known_agent_positions.get("agent_b") == (5, 5)

        # Turn 2 — agent_b no longer in viewport; stale position must be retained.
        perception2 = AgentPerception(
            agent_id="agent_a",
            turn=TurnNumber(2),
            visible_cells=(
                CellState(row=3, col=3, cell_type="floor", is_visible_to=("agent_a",)),
            ),
            position=(3, 3),
            has_key=False,
            pending_messages=(),
        )
        belief2 = manager.update_from_perception(perception2)
        assert belief2.known_agent_positions.get("agent_b") == (5, 5)
