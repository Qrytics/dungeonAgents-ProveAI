from __future__ import annotations

import json
from pathlib import Path
from pydantic import TypeAdapter

from apps.simulation.schemas import AgentBeliefState, AnyEvent, OutcomeEvent, WorldState
from packages.shared.types import AgentID, CellType, Position, TurnNumber

_event_adapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)


def compute_divergence_score(
    belief: AgentBeliefState,
    truth: WorldState,
) -> float:
    """
    Compute the epistemic divergence score for an agent at a given turn.

    Score = (number of cells in belief map that differ from ground truth)
            / (total cells in agent's belief map)

    Range: 0.0 (perfect knowledge) to 1.0 (all known cells are wrong).
    Returns 0.0 if belief map is empty.
    """
    if not belief.believed_grid:
        return 0.0

    # Build a fast lookup from position to ground-truth cell_type
    ground_truth: dict[Position, CellType] = {
        (cell.row, cell.col): cell.cell_type
        for row in truth.grid
        for cell in row
    }

    mismatched = sum(
        1
        for pos, believed_type in belief.believed_grid.items()
        if ground_truth.get(pos) != believed_type
    )

    return mismatched / len(belief.believed_grid)


def compute_divergence_timeseries(
    event_log_path: Path,
) -> dict[AgentID, list[tuple[TurnNumber, float]]]:
    """
    Replay an event log and compute divergence score at every turn for each agent.
    Returns a dict mapping agent_id → list of (turn, score) tuples.

    Belief state is reconstructed incrementally: at each OutcomeEvent the agent's
    believed_grid is updated with the cells that were visible to that agent in
    world_state_after (i.e. cells whose is_visible_to tuple contains the agent).
    """
    # Running believed_grid for each agent (position → cell_type)
    running_beliefs: dict[AgentID, dict[Position, CellType]] = {}
    timeseries: dict[AgentID, list[tuple[TurnNumber, float]]] = {}

    with event_log_path.open() as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            event = _event_adapter.validate_json(raw_line)

            if not isinstance(event, OutcomeEvent):
                continue

            agent_id: AgentID = event.agent_id
            world: WorldState = event.world_state_after
            turn: TurnNumber = event.turn

            # Ensure per-agent state is initialised
            if agent_id not in running_beliefs:
                running_beliefs[agent_id] = {}
            if agent_id not in timeseries:
                timeseries[agent_id] = []

            # Update belief: merge cells visible to this agent
            for row in world.grid:
                for cell in row:
                    if agent_id in cell.is_visible_to:
                        pos: Position = (cell.row, cell.col)
                        running_beliefs[agent_id][pos] = cell.cell_type

            # Build a transient AgentBeliefState snapshot for score computation
            belief_snapshot = AgentBeliefState(
                agent_id=agent_id,
                turn=turn,
                believed_position=world.agent_positions.get(agent_id, (0, 0)),
                believed_grid=dict(running_beliefs[agent_id]),
                has_key=(world.key_held_by == agent_id),
                known_agent_positions={},
            )

            score = compute_divergence_score(belief_snapshot, world)
            timeseries[agent_id].append((turn, score))

    return timeseries


def find_divergence_spikes(
    timeseries: dict[AgentID, list[tuple[TurnNumber, float]]],
    threshold: float = 0.3,
) -> dict[AgentID, list[TurnNumber]]:
    """
    Returns turns where divergence exceeded threshold.
    These are candidate root-cause turns for failure analysis.
    """
    return {
        agent_id: [turn for turn, score in turns if score > threshold]
        for agent_id, turns in timeseries.items()
    }
