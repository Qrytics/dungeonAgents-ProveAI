"""M-11 — Game Loop.

Implements the turn-based execution engine that drives the dungeon simulation.
Each turn follows a strict ordering: message delivery, perception, Agent A,
Agent B, Dungeon Master narration, termination check.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from apps.simulation.agents import LangGraphState
from apps.simulation.agents.agent_a import agent_a_node
from apps.simulation.agents.agent_b import agent_b_node
from apps.simulation.agents.dungeon_master import DM_STALENESS, DungeonMasterAgent
from apps.simulation.agents.state import AgentBeliefStateManager
from apps.simulation.environment.grid import DungeonGrid
from apps.simulation.environment.orchestrator import EnvironmentOrchestrator
from apps.simulation.environment.perception import PerceptionEngine
from apps.simulation.game_loop.message_queue import MessageQueue
from apps.simulation.schemas.events import TerminationEvent
from apps.simulation.schemas.state import WorldState
from packages.observability.tracer import init_tracer
from packages.shared.constants import RUNS_DIR
from packages.shared.types import RunID, TurnNumber

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class GameConfig:
    """Configuration for a single dungeon simulation run.

    Fields
    ------
    run_id:
        Unique identifier for the run; used for event log filenames and
        Langfuse / OTel session tagging.
    grid_rows:
        Number of rows in the dungeon grid (must be >= ``GRID_MIN_SIZE``).
    grid_cols:
        Number of columns in the dungeon grid (must be >= ``GRID_MIN_SIZE``).
    seed:
        Optional RNG seed for deterministic grid generation.
    llm_model:
        OpenAI model name passed to all LLM-powered components.
    event_log_dir:
        Directory where the ``.jsonl`` event log is written.
    """

    run_id: RunID
    grid_rows: int = 8
    grid_cols: int = 8
    seed: int | None = None
    llm_model: str = "gpt-4o-mini"
    event_log_dir: Path = field(default_factory=lambda: RUNS_DIR)
    verbose: bool = False


# ---------------------------------------------------------------------------
# Game loop
# ---------------------------------------------------------------------------


class GameLoop:
    """Turn-based execution engine for the dungeon simulation.

    Initializes all simulation components from a :class:`GameConfig` and
    drives the game to completion via :meth:`run`.  The loop enforces strict
    turn ordering, communication lag, and termination conditions.

    Parameters
    ----------
    config:
        Configuration describing this simulation run.
    """

    def __init__(self, config: GameConfig) -> None:
        self._config = config

        # Core environment components.
        self._grid = DungeonGrid(
            rows=config.grid_rows,
            cols=config.grid_cols,
            seed=config.seed,
        )
        event_log_path = config.event_log_dir / f"{config.run_id}.jsonl"
        self._orchestrator = EnvironmentOrchestrator(self._grid, event_log_path)
        self._message_queue = MessageQueue()
        self._perception_engine = PerceptionEngine()

        # Per-agent belief state managers.
        self._belief_a = AgentBeliefStateManager("agent_a")
        self._belief_b = AgentBeliefStateManager("agent_b")

        # Observability.
        tracer, langfuse_client = init_tracer(config.run_id)
        self._tracer = tracer
        self._langfuse = langfuse_client

        # Dungeon Master agent.
        self._dm = DungeonMasterAgent(
            orchestrator=self._orchestrator,
            run_id=config.run_id,
            langfuse_client=langfuse_client,
            llm_model=config.llm_model,
        )

        # Ordered history of world states — used to supply the DM with stale state.
        self._world_state_history: list[WorldState] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> TerminationEvent:
        """Execute the simulation until a terminal condition is reached.

        Turn execution order each iteration:

        1. Deliver pending messages to each agent via ``MessageQueue.deliver()``.
        2. Compute perception (including delivered messages) for both agents.
        3. Agent A takes its turn → ``IntentionEvent`` → Orchestrator → ``OutcomeEvent``.
        4. Update world state from orchestrator after Agent A's action.
        5. Agent B takes its turn → ``IntentionEvent`` → Orchestrator → ``OutcomeEvent``.
        6. Update world state from orchestrator after Agent B's action.
        7. DM Agent acts on stale state (``turn - DM_STALENESS``).
        8. Check termination via the orchestrator.
        9. Increment turn counter.

        Returns
        -------
        TerminationEvent
            The terminal event describing why the game ended (``"win"``,
            ``"turn_limit"``, or ``"stuck"``).  Always returned; never raises.
        """
        run_id = self._config.run_id
        turn = TurnNumber(0)

        # Build the initial world state from the grid's agent start positions.
        world_state = self._orchestrator.get_current_world_state(run_id, turn)

        state: LangGraphState = {
            "run_id": run_id,
            "turn": turn,
            "world_state": world_state,
            "orchestrator": self._orchestrator,
            "belief_manager_a": self._belief_a,
            "belief_manager_b": self._belief_b,
            "perception_a": None,
            "perception_b": None,
            "message_queue": self._message_queue,
            "tracer": self._tracer,
            "langfuse_client": self._langfuse,
        }

        while True:
            turn = state["turn"]
            world_state = state["world_state"]

            # ----------------------------------------------------------
            # Step 1 — Deliver pending messages for this turn.
            # ----------------------------------------------------------
            msgs_a = self._message_queue.deliver(turn, "agent_a")
            msgs_b = self._message_queue.deliver(turn, "agent_b")

            # ----------------------------------------------------------
            # Step 2 — Compute perception (includes delivered messages).
            # ----------------------------------------------------------
            pos_a = world_state.agent_positions["agent_a"]
            pos_b = world_state.agent_positions["agent_b"]
            has_key_a = world_state.key_held_by == "agent_a"
            has_key_b = world_state.key_held_by == "agent_b"

            perception_a = self._perception_engine.compute_viewport(
                "agent_a", pos_a, self._grid, msgs_a, has_key_a, turn
            )
            perception_b = self._perception_engine.compute_viewport(
                "agent_b", pos_b, self._grid, msgs_b, has_key_b, turn
            )
            state["perception_a"] = perception_a
            state["perception_b"] = perception_b

            # ----------------------------------------------------------
            # Steps 3–4 — Agent A takes its turn.
            # ----------------------------------------------------------
            state = agent_a_node(state)
            world_state = self._orchestrator.get_current_world_state(run_id, turn)
            state["world_state"] = world_state

            # ----------------------------------------------------------
            # Steps 5–6 — Agent B takes its turn.
            # ----------------------------------------------------------
            state = agent_b_node(state)
            world_state = self._orchestrator.get_current_world_state(run_id, turn)
            state["world_state"] = world_state

            # Record snapshot for DM staleness window.
            self._world_state_history.append(world_state)

            # ----------------------------------------------------------
            # Step 7 — DM narrates the stale state.
            # ----------------------------------------------------------
            stale_idx = len(self._world_state_history) - 1 - DM_STALENESS
            dm_annotation: str | None = None
            if stale_idx >= 0:
                stale_state = self._world_state_history[stale_idx]
                try:
                    dm_annotation = self._dm.act(stale_state, turn)
                except Exception:  # noqa: BLE001 — DM errors must not stop the loop
                    logger.exception(
                        "DungeonMasterAgent raised unexpectedly on turn %d; continuing.",
                        int(turn),
                    )

            # ----------------------------------------------------------
            # Verbose console output.
            # ----------------------------------------------------------
            if self._config.verbose:
                pos_a = world_state.agent_positions.get("agent_a", "?")
                pos_b = world_state.agent_positions.get("agent_b", "?")
                key_status = (
                    f"held by {world_state.key_held_by}"
                    if world_state.key_held_by
                    else "floor"
                )
                door_status = "unlocked" if world_state.door_unlocked else "locked"
                print(
                    f"\n── Turn {int(turn)} "
                    + "─" * 40
                    + f"\n  Agent A: {pos_a}  Agent B: {pos_b}"
                    f"  |  Key: {key_status}  |  Door: {door_status}"
                )
                if dm_annotation:
                    print(f"  DM: {dm_annotation}")

            # ----------------------------------------------------------
            # Step 8 — Check termination conditions.
            # ----------------------------------------------------------
            termination = self._orchestrator.check_termination(world_state, turn)
            if termination is not None:
                self._orchestrator.log_termination(termination)
                return termination

            # ----------------------------------------------------------
            # Step 9 — Advance to the next turn.
            # ----------------------------------------------------------
            next_turn = TurnNumber(int(turn) + 1)
            state["turn"] = next_turn
            state["world_state"] = self._orchestrator.get_current_world_state(
                run_id, next_turn
            )
