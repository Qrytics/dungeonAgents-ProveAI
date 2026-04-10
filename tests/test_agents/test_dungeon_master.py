"""Unit tests for DungeonMasterAgent (M-10).

All tests stub out the LLM and Langfuse client so no external services are
needed.  The orchestrator is also stubbed — the DM must never mutate game
state directly.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.simulation.agents.dungeon_master import DM_STALENESS, DungeonMasterAgent
from apps.simulation.environment.grid import DungeonGrid
from apps.simulation.schemas.state import WorldState
from langchain_openai import ChatOpenAI
from packages.shared.types import RunID, TurnNumber

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_RUN_ID: RunID = RunID("00000000-0000-0000-0000-000000000010")


def _make_world_state(
    grid: DungeonGrid | None = None,
    turn: int = 0,
) -> WorldState:
    if grid is None:
        grid = DungeonGrid(rows=8, cols=8, seed=42)
    return grid.to_world_state(
        run_id=_RUN_ID,
        turn=TurnNumber(turn),
        agent_positions=grid.get_agent_start_positions(),
        key_held_by=None,
        door_unlocked=False,
    )


def _make_dm(
    llm_response: str = "The dungeon hums with tension.",
    prompt_tokens: int = 50,
    completion_tokens: int = 20,
) -> tuple[DungeonMasterAgent, MagicMock, MagicMock, MagicMock]:
    """Return (agent, stub_orchestrator, stub_langfuse_client, mock_llm)."""
    stub_orchestrator = MagicMock()

    stub_langfuse = MagicMock()
    stub_trace = MagicMock()
    stub_langfuse.trace.return_value = stub_trace

    mock_llm = MagicMock(spec=ChatOpenAI)
    fake_response = MagicMock()
    fake_response.content = llm_response
    fake_response.usage_metadata = {
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
    }
    mock_llm.invoke.return_value = fake_response
    mock_llm.model_name = "gpt-4o-mini"

    agent = DungeonMasterAgent(
        orchestrator=stub_orchestrator,
        run_id=_RUN_ID,
        langfuse_client=stub_langfuse,
        llm_model="gpt-4o-mini",
        llm=mock_llm,
    )
    return agent, stub_orchestrator, stub_langfuse, mock_llm


# ---------------------------------------------------------------------------
# Tests: DM_STALENESS constant
# ---------------------------------------------------------------------------


class TestDMStalenessConstant:
    def test_staleness_is_two(self) -> None:
        assert DM_STALENESS == 2


# ---------------------------------------------------------------------------
# Tests: act() return value
# ---------------------------------------------------------------------------


class TestActReturnsAnnotation:
    def test_act_returns_llm_content(self) -> None:
        agent, _, _, _ = _make_dm(llm_response="Shadows dance across the crumbling walls.")
        stale_state = _make_world_state(turn=0)
        result = agent.act(stale_state, TurnNumber(2))
        assert result == "Shadows dance across the crumbling walls."

    def test_act_returns_none_on_llm_error(self) -> None:
        agent, _, stub_langfuse, mock_llm = _make_dm()
        mock_llm.invoke.side_effect = RuntimeError("API error")
        stale_state = _make_world_state(turn=0)
        result = agent.act(stale_state, TurnNumber(2))
        assert result is None
        # Langfuse must not be called when the LLM fails.
        stub_langfuse.trace.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: stale state is used, not current state
# ---------------------------------------------------------------------------


class TestStaleStateIsUsed:
    def test_prompt_contains_stale_turn_annotation(self) -> None:
        """The DM prompt must explicitly say 'as it was 2 turns ago'."""
        agent, _, _, _ = _make_dm()
        stale_state = _make_world_state(turn=3)
        current_turn = TurnNumber(5)

        prompt = agent._build_prompt(stale_state, current_turn)  # type: ignore[attr-defined]

        assert "2 turns ago" in prompt
        assert f"turn {3}" in prompt   # stale turn number
        assert f"current turn is {5}" in prompt

    def test_prompt_includes_full_grid(self) -> None:
        """The DM prompt must include all standard grid symbols."""
        agent, _, _, _ = _make_dm()
        stale_state = _make_world_state(turn=0)
        prompt = agent._build_prompt(stale_state, TurnNumber(2))  # type: ignore[attr-defined]

        # Grid legend line must be present.
        assert "# wall" in prompt
        assert ". floor" in prompt
        assert "K key" in prompt


# ---------------------------------------------------------------------------
# Tests: full grid rendering (no fog)
# ---------------------------------------------------------------------------


class TestRenderGrid:
    def test_grid_rows_match_world_state(self) -> None:
        grid = DungeonGrid(rows=8, cols=8, seed=7)
        state = _make_world_state(grid=grid, turn=0)
        rendered = DungeonMasterAgent._render_grid(state)  # type: ignore[attr-defined]
        lines = rendered.split("\n")
        assert len(lines) == 8

    def test_grid_cols_match_world_state(self) -> None:
        grid = DungeonGrid(rows=8, cols=8, seed=7)
        state = _make_world_state(grid=grid, turn=0)
        rendered = DungeonMasterAgent._render_grid(state)  # type: ignore[attr-defined]
        for line in rendered.split("\n"):
            assert len(line) == 8

    def test_outer_boundary_is_walls(self) -> None:
        grid = DungeonGrid(rows=8, cols=8, seed=0)
        state = _make_world_state(grid=grid, turn=0)
        rendered = DungeonMasterAgent._render_grid(state)  # type: ignore[attr-defined]
        lines = rendered.split("\n")
        # Top and bottom rows are all walls.
        assert all(ch == "#" for ch in lines[0])
        assert all(ch == "#" for ch in lines[-1])
        # Left and right columns are all walls.
        for line in lines:
            assert line[0] == "#"
            assert line[-1] == "#"


# ---------------------------------------------------------------------------
# Tests: Langfuse logging
# ---------------------------------------------------------------------------


class TestLangfuseLogging:
    def test_langfuse_trace_is_created_on_success(self) -> None:
        agent, _, stub_langfuse, _ = _make_dm()
        stale_state = _make_world_state(turn=1)
        agent.act(stale_state, TurnNumber(3))
        stub_langfuse.trace.assert_called_once()

    def test_langfuse_generation_is_created_on_success(self) -> None:
        agent, _, stub_langfuse, _ = _make_dm()
        stub_trace = stub_langfuse.trace.return_value
        stale_state = _make_world_state(turn=1)
        agent.act(stale_state, TurnNumber(3))
        stub_trace.generation.assert_called_once()

    def test_langfuse_trace_metadata_includes_run_id(self) -> None:
        agent, _, stub_langfuse, _ = _make_dm()
        stale_state = _make_world_state(turn=0)
        agent.act(stale_state, TurnNumber(2))

        call_kwargs: dict[str, Any] = stub_langfuse.trace.call_args.kwargs
        assert call_kwargs.get("session_id") == _RUN_ID
        meta = call_kwargs.get("metadata", {})
        assert meta.get("run_id") == _RUN_ID

    def test_langfuse_trace_metadata_includes_turn_numbers(self) -> None:
        agent, _, stub_langfuse, _ = _make_dm()
        stale_state = _make_world_state(turn=4)
        agent.act(stale_state, TurnNumber(6))

        call_kwargs: dict[str, Any] = stub_langfuse.trace.call_args.kwargs
        meta = call_kwargs.get("metadata", {})
        assert meta.get("current_turn") == 6
        assert meta.get("stale_turn") == 4
        assert meta.get("staleness_turns") == DM_STALENESS

    def test_langfuse_generation_includes_annotation(self) -> None:
        annotation_text = "The adventurers creep through the gloom."
        agent, _, stub_langfuse, _ = _make_dm(llm_response=annotation_text)
        stub_trace = stub_langfuse.trace.return_value
        stale_state = _make_world_state(turn=0)
        agent.act(stale_state, TurnNumber(2))

        gen_kwargs: dict[str, Any] = stub_trace.generation.call_args.kwargs
        assert gen_kwargs.get("output") == annotation_text


# ---------------------------------------------------------------------------
# Tests: orchestrator is NOT called
# ---------------------------------------------------------------------------


class TestOrchestratorNotCalled:
    def test_orchestrator_apply_intention_not_called(self) -> None:
        """DM must not write to game state via apply_intention."""
        agent, stub_orchestrator, _, _ = _make_dm()
        stale_state = _make_world_state(turn=0)
        agent.act(stale_state, TurnNumber(2))
        stub_orchestrator.apply_intention.assert_not_called()
