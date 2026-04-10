"""Unit tests for apps/legibility/analysis/divergence.py (M-14)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from apps.legibility.analysis.divergence import (
    compute_divergence_score,
    compute_divergence_timeseries,
    find_divergence_spikes,
)
from apps.simulation.schemas import AgentBeliefState, CellState, WorldState
from packages.shared.types import RunID, TurnNumber


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_world(grid_cells: list[CellState], turn: int = 1) -> WorldState:
    """Build a minimal WorldState from a flat list of CellState objects."""
    max_row = max(c.row for c in grid_cells) + 1
    max_col = max(c.col for c in grid_cells) + 1
    grid_map: dict[tuple[int, int], CellState] = {(c.row, c.col): c for c in grid_cells}
    grid_2d = tuple(
        tuple(
            grid_map.get((r, col), CellState(row=r, col=col, cell_type="wall", is_visible_to=()))
            for col in range(max_col)
        )
        for r in range(max_row)
    )
    return WorldState(
        run_id=RunID("test-run"),
        turn=TurnNumber(turn),
        grid=grid_2d,
        agent_positions={"agent_a": (0, 0)},
        key_held_by=None,
        door_unlocked=False,
    )


def _make_belief(
    believed_grid: dict[tuple[int, int], str],
    agent_id: str = "agent_a",
    turn: int = 1,
) -> AgentBeliefState:
    return AgentBeliefState(
        agent_id=agent_id,  # type: ignore[arg-type]
        turn=TurnNumber(turn),
        believed_position=(0, 0),
        believed_grid=believed_grid,  # type: ignore[arg-type]
        has_key=False,
        known_agent_positions={},
    )


# ---------------------------------------------------------------------------
# compute_divergence_score
# ---------------------------------------------------------------------------

class TestComputeDivergenceScore:
    def test_empty_belief_returns_zero(self):
        world = _make_world(
            [CellState(row=0, col=0, cell_type="floor", is_visible_to=())]
        )
        belief = _make_belief({})
        assert compute_divergence_score(belief, world) == 0.0

    def test_perfect_knowledge_returns_zero(self):
        cells = [
            CellState(row=0, col=0, cell_type="floor", is_visible_to=()),
            CellState(row=0, col=1, cell_type="wall", is_visible_to=()),
        ]
        world = _make_world(cells)
        belief = _make_belief({(0, 0): "floor", (0, 1): "wall"})
        assert compute_divergence_score(belief, world) == 0.0

    def test_all_wrong_returns_one(self):
        cells = [
            CellState(row=0, col=0, cell_type="floor", is_visible_to=()),
            CellState(row=0, col=1, cell_type="floor", is_visible_to=()),
        ]
        world = _make_world(cells)
        belief = _make_belief({(0, 0): "wall", (0, 1): "wall"})
        assert compute_divergence_score(belief, world) == 1.0

    def test_half_wrong_returns_half(self):
        cells = [
            CellState(row=0, col=0, cell_type="floor", is_visible_to=()),
            CellState(row=0, col=1, cell_type="wall", is_visible_to=()),
        ]
        world = _make_world(cells)
        belief = _make_belief({(0, 0): "floor", (0, 1): "floor"})
        assert compute_divergence_score(belief, world) == pytest.approx(0.5)

    def test_score_range_0_to_1(self):
        cells = [CellState(row=r, col=c, cell_type="floor", is_visible_to=()) for r in range(3) for c in range(3)]
        world = _make_world(cells)
        # Mix: 5 correct, 4 wrong out of 9
        believed = {(r, c): ("wall" if (r + c) % 2 == 0 else "floor") for r in range(3) for c in range(3)}
        belief = _make_belief(believed)
        score = compute_divergence_score(belief, world)
        assert 0.0 <= score <= 1.0

    def test_unknown_position_in_belief_treated_as_mismatch(self):
        """Cells believed but not in ground truth count as mismatches."""
        cells = [CellState(row=0, col=0, cell_type="floor", is_visible_to=())]
        world = _make_world(cells)
        # Believe a position (5, 5) that does not appear in the tiny world
        belief = _make_belief({(0, 0): "floor", (5, 5): "exit"})
        # (5,5) not in ground truth → treated as mismatch; (0,0) correct
        score = compute_divergence_score(belief, world)
        assert score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# compute_divergence_timeseries
# ---------------------------------------------------------------------------

def _outcome_event_line(
    agent_id: str,
    turn: int,
    world: WorldState,
) -> str:
    """Serialize a minimal OutcomeEvent to a JSONL line."""
    return json.dumps({
        "event_type": "outcome",
        "run_id": "test-run",
        "turn": turn,
        "agent_id": agent_id,
        "tool_name": "move",
        "success": True,
        "result_description": "ok",
        "world_state_after": json.loads(world.model_dump_json()),
        "divergence_score": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


class TestComputeDivergenceTimeseries:
    def _write_log(self, tmp_path: Path, lines: list[str]) -> Path:
        log_file = tmp_path / "test.jsonl"
        log_file.write_text("\n".join(lines) + "\n")
        return log_file

    def test_empty_log_returns_empty_dict(self, tmp_path: Path):
        path = self._write_log(tmp_path, [])
        result = compute_divergence_timeseries(path)
        assert result == {}

    def test_single_agent_single_turn_perfect_knowledge(self, tmp_path: Path):
        cell = CellState(row=0, col=0, cell_type="floor", is_visible_to=("agent_a",))
        world = _make_world([cell])
        path = self._write_log(tmp_path, [_outcome_event_line("agent_a", 1, world)])
        result = compute_divergence_timeseries(path)
        assert "agent_a" in result
        assert len(result["agent_a"]) == 1
        turn, score = result["agent_a"][0]
        assert turn == 1
        assert score == 0.0

    def test_two_agents_independent_timeseries(self, tmp_path: Path):
        cell_a = CellState(row=0, col=0, cell_type="floor", is_visible_to=("agent_a",))
        cell_b = CellState(row=0, col=1, cell_type="wall", is_visible_to=("agent_b",))
        world = _make_world([cell_a, cell_b])
        path = self._write_log(tmp_path, [
            _outcome_event_line("agent_a", 1, world),
            _outcome_event_line("agent_b", 1, world),
        ])
        result = compute_divergence_timeseries(path)
        assert "agent_a" in result
        assert "agent_b" in result

    def test_non_outcome_events_are_skipped(self, tmp_path: Path):
        intention_line = json.dumps({
            "event_type": "intention",
            "run_id": "test-run",
            "turn": 1,
            "agent_id": "agent_a",
            "tool_name": "move",
            "tool_args": {},
            "llm_prompt_tokens": 10,
            "llm_completion_tokens": 5,
            "latency_ms": 100.0,
            "raw_llm_output": "move north",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        path = self._write_log(tmp_path, [intention_line])
        result = compute_divergence_timeseries(path)
        assert result == {}

    def test_timeseries_grows_over_turns(self, tmp_path: Path):
        cell = CellState(row=0, col=0, cell_type="floor", is_visible_to=("agent_a",))
        world1 = _make_world([cell], turn=1)
        world2 = _make_world([cell], turn=2)
        path = self._write_log(tmp_path, [
            _outcome_event_line("agent_a", 1, world1),
            _outcome_event_line("agent_a", 2, world2),
        ])
        result = compute_divergence_timeseries(path)
        assert len(result["agent_a"]) == 2
        turns = [t for t, _ in result["agent_a"]]
        assert turns == [1, 2]



# ---------------------------------------------------------------------------
# find_divergence_spikes
# ---------------------------------------------------------------------------

class TestFindDivergenceSpikes:
    def test_no_spikes_below_threshold(self):
        ts = {"agent_a": [(TurnNumber(1), 0.1), (TurnNumber(2), 0.2)]}
        result = find_divergence_spikes(ts, threshold=0.3)
        assert result == {"agent_a": []}

    def test_spike_exactly_at_threshold_not_included(self):
        ts = {"agent_a": [(TurnNumber(1), 0.3)]}
        result = find_divergence_spikes(ts, threshold=0.3)
        assert result == {"agent_a": []}

    def test_spike_above_threshold_included(self):
        ts = {"agent_a": [(TurnNumber(1), 0.31), (TurnNumber(2), 0.1)]}
        result = find_divergence_spikes(ts, threshold=0.3)
        assert result == {"agent_a": [TurnNumber(1)]}

    def test_multiple_agents(self):
        ts = {
            "agent_a": [(TurnNumber(1), 0.5), (TurnNumber(2), 0.1)],
            "agent_b": [(TurnNumber(1), 0.1), (TurnNumber(2), 0.9)],
        }
        result = find_divergence_spikes(ts, threshold=0.3)
        assert result["agent_a"] == [TurnNumber(1)]
        assert result["agent_b"] == [TurnNumber(2)]

    def test_empty_timeseries(self):
        result = find_divergence_spikes({}, threshold=0.3)
        assert result == {}

    def test_default_threshold_is_0_3(self):
        ts = {"agent_a": [(TurnNumber(1), 0.4)]}
        assert find_divergence_spikes(ts) == {"agent_a": [TurnNumber(1)]}
