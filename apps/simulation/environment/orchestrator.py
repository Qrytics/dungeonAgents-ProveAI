"""M-06 — Environment: Orchestrator (Dungeon Master Logic).

The :class:`EnvironmentOrchestrator` is the single authoritative
decision-maker for applying agent intentions to world state.  It receives
:class:`~apps.simulation.schemas.events.IntentionEvent`s, validates them via
:class:`~apps.simulation.environment.interaction.InteractionValidator`, applies
mutations to the :class:`~apps.simulation.environment.grid.DungeonGrid`, and
emits :class:`~apps.simulation.schemas.events.OutcomeEvent`s to the event log.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import TypeAdapter

from apps.simulation.environment.grid import DungeonGrid
from apps.simulation.environment.interaction import InteractionValidator
from apps.simulation.schemas.events import (
    AnyEvent,
    IntentionEvent,
    MessageEvent,
    OutcomeEvent,
    TerminationEvent,
)
from apps.simulation.schemas.state import WorldState
from packages.shared.constants import TURN_LIMIT
from packages.shared.types import AgentID, Direction, Position, TurnNumber

# Number of consecutive no-move turns before "stuck" termination is declared.
_STUCK_TURN_THRESHOLD: int = 3

# Singleton type adapter for deserialising AnyEvent from JSON.
_EVENT_ADAPTER: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)


class EnvironmentOrchestrator:
    """Single authoritative decision-maker for applying agent intentions.

    Validates every :class:`~apps.simulation.schemas.events.IntentionEvent`
    through :class:`~apps.simulation.environment.interaction.InteractionValidator`,
    mutates the :class:`~apps.simulation.environment.grid.DungeonGrid` on
    success, writes both the intention and the resulting
    :class:`~apps.simulation.schemas.events.OutcomeEvent` to an append-only
    ``.jsonl`` event log, and exposes game-over detection via
    :meth:`check_termination`.
    """

    def __init__(self, grid: DungeonGrid, event_log_path: Path) -> None:
        self._grid = grid
        self._event_log_path = event_log_path
        self._validator = InteractionValidator()

        # Authoritative game state — mutated on each successful action.
        self._agent_positions: dict[AgentID, Position] = grid.get_agent_start_positions()
        self._key_held_by: AgentID | None = None
        self._door_unlocked: bool = False

        # Stuck detection: turn number of the last successful move action.
        # None means no move has succeeded yet.
        self._last_successful_move_turn: TurnNumber | None = None

        # Ensure the event log directory exists.
        event_log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_intention(
        self,
        intention: IntentionEvent,
        current_world_state: WorldState,
    ) -> OutcomeEvent:
        """Validate *intention* and, if valid, apply the resulting state mutation.

        Both the ``IntentionEvent`` and the produced ``OutcomeEvent`` are
        appended to the event log (intention first, then outcome).

        Parameters
        ----------
        intention:
            The agent's intended action for this turn.
        current_world_state:
            The authoritative world state at the start of this action.
            Passed for contextual reference; the orchestrator's internal state
            is kept consistent with it.

        Returns
        -------
        OutcomeEvent
            Frozen event describing whether the action succeeded and the
            resulting world state.
        """
        tool = intention.tool_name
        agent_id = intention.agent_id
        turn = intention.turn

        success: bool
        result_description: str

        if tool == "move":
            direction: Direction = intention.tool_args["direction"]
            current_pos = self._agent_positions[agent_id]
            is_valid, reason, new_pos = self._validator.validate_move(
                agent_id, direction, current_pos, self._grid, self._door_unlocked
            )
            success = is_valid
            result_description = reason
            if is_valid and new_pos is not None:
                self._agent_positions[agent_id] = new_pos
                self._last_successful_move_turn = turn

        elif tool == "interact":
            current_pos = self._agent_positions[agent_id]
            is_valid, reason, mutations = self._validator.validate_interact(
                agent_id, current_pos, self._grid, self._key_held_by, self._door_unlocked
            )
            success = is_valid
            result_description = reason
            if is_valid:
                if "key_held_by" in mutations:
                    self._key_held_by = mutations["key_held_by"]
                if "door_unlocked" in mutations:
                    self._door_unlocked = mutations["door_unlocked"]

        elif tool == "observe":
            current_pos = self._agent_positions[agent_id]
            is_valid, reason = self._validator.validate_observe(
                agent_id, current_pos, self._grid
            )
            success = is_valid
            result_description = reason

        elif tool == "communicate":
            recipient: AgentID = intention.tool_args["recipient"]
            content: str = intention.tool_args["message"]
            is_valid, reason = self._validator.validate_communicate(
                agent_id, recipient, content
            )
            success = is_valid
            result_description = reason

        else:
            success = False
            result_description = f"Unknown tool '{tool}' for agent {agent_id}."

        # Build the updated world state.
        world_state_after = self._grid.to_world_state(
            run_id=intention.run_id,
            turn=turn,
            agent_positions=self._agent_positions,
            key_held_by=self._key_held_by,
            door_unlocked=self._door_unlocked,
        )

        outcome = OutcomeEvent(
            event_type="outcome",
            run_id=intention.run_id,
            turn=turn,
            agent_id=agent_id,
            tool_name=tool,
            success=success,
            result_description=result_description,
            world_state_after=world_state_after,
            divergence_score=None,
            timestamp=datetime.now(tz=timezone.utc),
        )

        # Append intention then outcome to the event log.
        self._append_event(intention)
        self._append_event(outcome)

        return outcome

    def check_termination(
        self, world_state: WorldState, turn: TurnNumber
    ) -> TerminationEvent | None:
        """Check whether the game has reached a terminal state.

        Parameters
        ----------
        world_state:
            The authoritative world state at the end of the current turn.
        turn:
            The current turn number.

        Returns
        -------
        TerminationEvent
            ``reason="win"`` — all player agents are on the ``exit`` cell.

            ``reason="turn_limit"`` — *turn* has reached or exceeded
            :data:`~packages.shared.constants.TURN_LIMIT`.

            ``reason="stuck"`` — no agent successfully moved in the last
            :data:`_STUCK_TURN_THRESHOLD` consecutive turns.
        None
            The game continues.
        """
        run_id = world_state.run_id

        # Collect all exit-cell positions from the ground-truth grid.
        exit_positions: set[Position] = {
            (cell.row, cell.col)
            for row in world_state.grid
            for cell in row
            if cell.cell_type == "exit"
        }

        # Win: every player agent (non-DM) stands on an exit cell.
        player_agents: list[AgentID] = [
            a for a in world_state.agent_positions if a != "dungeon_master"
        ]
        if exit_positions and player_agents and all(
            world_state.agent_positions.get(a) in exit_positions
            for a in player_agents
        ):
            return TerminationEvent(
                event_type="termination",
                run_id=run_id,
                final_turn=turn,
                reason="win",
                winner=True,
                timestamp=datetime.now(tz=timezone.utc),
            )

        # Turn limit.
        if turn >= TURN_LIMIT:
            return TerminationEvent(
                event_type="termination",
                run_id=run_id,
                final_turn=turn,
                reason="turn_limit",
                winner=False,
                timestamp=datetime.now(tz=timezone.utc),
            )

        # Stuck detection.
        if self._is_stuck(int(turn)):
            return TerminationEvent(
                event_type="termination",
                run_id=run_id,
                final_turn=turn,
                reason="stuck",
                winner=False,
                timestamp=datetime.now(tz=timezone.utc),
            )

        return None

    @staticmethod
    def replay_from_log(event_log_path: Path) -> list[WorldState]:
        """Replay all events from *event_log_path* and return world-state snapshots.

        Reads every JSON line from the ``.jsonl`` file in chronological order,
        deserialises each as an :data:`~apps.simulation.schemas.events.AnyEvent`,
        and collects the ``world_state_after`` field of every
        :class:`~apps.simulation.schemas.events.OutcomeEvent`.

        Parameters
        ----------
        event_log_path:
            Path to an existing ``.jsonl`` run file.

        Returns
        -------
        list[WorldState]
            Ordered world-state snapshots — one per
            :class:`~apps.simulation.schemas.events.OutcomeEvent` in the log.
        """
        snapshots: list[WorldState] = []
        with event_log_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                event = _EVENT_ADAPTER.validate_json(line)
                if isinstance(event, OutcomeEvent):
                    snapshots.append(event.world_state_after)
        return snapshots

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_stuck(self, turn: int) -> bool:
        """Return True if no agent has moved successfully for the last
        ``_STUCK_TURN_THRESHOLD`` consecutive turns."""
        if self._last_successful_move_turn is None:
            # No successful move has ever occurred.
            return turn >= _STUCK_TURN_THRESHOLD
        return turn - int(self._last_successful_move_turn) >= _STUCK_TURN_THRESHOLD

    def _append_event(
        self,
        event: IntentionEvent | OutcomeEvent | TerminationEvent | MessageEvent,
    ) -> None:
        """Serialise *event* as a single JSON line and append it to the log."""
        line = event.model_dump_json() + "\n"
        with self._event_log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
