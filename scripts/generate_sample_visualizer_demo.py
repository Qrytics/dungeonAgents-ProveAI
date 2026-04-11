"""Write a deterministic demo `.jsonl` for the React replay visualizer.

Run from repo root:
    python scripts/generate_sample_visualizer_demo.py

Outputs `apps/visualizer/public/sample_visualizer_demo.jsonl` (outcome events only).
Uses a real :class:`DungeonGrid` layout so cells and moves are physically valid.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from apps.simulation.environment.grid import DungeonGrid
from apps.simulation.schemas.events import OutcomeEvent
from packages.shared.types import AgentID, Position, RunID, TurnNumber

RUN_ID = RunID("00000000-0000-4000-8000-00000000d3m0")
SEED = 42
OUT_PATH = Path("apps/visualizer/public/sample_visualizer_demo.jsonl")


def _passable(grid: DungeonGrid, pos: Position) -> bool:
    r, c = pos
    if not (0 <= r < grid.rows and 0 <= c < grid.cols):
        return False
    return grid.is_passable(pos)


def _find_cell(grid: DungeonGrid, cell_type: str) -> Position:
    for r in range(grid.rows):
        for c in range(grid.cols):
            if grid.get_cell((r, c)).cell_type == cell_type:
                return (r, c)
    raise SystemExit(f"No {cell_type} cell in grid")


def _shortest_path(
    grid: DungeonGrid, start: Position, goal: Position
) -> list[Position]:
    """BFS path start -> goal over passable cells (inclusive)."""
    if start == goal:
        return [start]
    q: deque[Position] = deque([start])
    prev: dict[Position, Position | None] = {start: None}
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        r, c = cur
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nxt = (r + dr, c + dc)
            if nxt in prev or not _passable(grid, nxt):
                continue
            prev[nxt] = cur
            q.append(nxt)
    if goal not in prev:
        raise SystemExit(f"No path from {start} to {goal}")
    out: list[Position] = []
    cur: Position | None = goal
    while cur is not None:
        out.append(cur)
        cur = prev[cur]
    out.reverse()
    return out


def main() -> None:
    grid = DungeonGrid(rows=8, cols=8, seed=SEED)
    pos: dict[AgentID, Position] = dict(grid.get_agent_start_positions())
    key_held_by: AgentID | None = None
    door_unlocked = False

    key_pos = _find_cell(grid, "key")
    exit_pos = _find_cell(grid, "exit")

    path_a = _shortest_path(grid, pos["agent_a"], key_pos)
    path_b = _shortest_path(grid, pos["agent_b"], exit_pos)

    # Interleave A/B moves so both agents visibly travel (same turn number for each pair).
    script: list[tuple[int, AgentID, str, str, Position | None]] = [
        (0, "agent_a", "observe", "Demo: Agent A observes the dungeon.", None),
        (0, "agent_b", "observe", "Demo: Agent B observes the dungeon.", None),
    ]

    turn = 1
    ia, ib = 1, 1
    while ia < len(path_a) or ib < len(path_b):
        if ia < len(path_a):
            script.append(
                (
                    turn,
                    "agent_a",
                    "move",
                    f"Demo: A steps toward the key ({path_a[ia]}).",
                    path_a[ia],
                )
            )
            ia += 1
        if ib < len(path_b):
            script.append(
                (
                    turn,
                    "agent_b",
                    "move",
                    f"Demo: B steps toward the exit ({path_b[ib]}).",
                    path_b[ib],
                )
            )
            ib += 1
        turn += 1

    script.append(
        (
            turn,
            "agent_a",
            "interact",
            "Demo: A interacts at the key (picked up — see Key held by).",
            None,
        )
    )
    script.append(
        (
            turn,
            "agent_b",
            "observe",
            "Demo: B observes from the exit area.",
            None,
        )
    )

    lines: list[str] = []
    ts = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)

    for turn, agent, tool, desc, new_pos in script:
        if new_pos is not None:
            if not _passable(grid, new_pos):
                raise SystemExit(f"Invalid demo move {agent} -> {new_pos} (not passable)")
            pos = {**pos, agent: new_pos}
        if pos["agent_a"] == key_pos:
            key_held_by = "agent_a"
        world = grid.to_world_state(
            RUN_ID,
            TurnNumber(turn),
            dict(pos),
            key_held_by,
            door_unlocked,
        )
        event = OutcomeEvent(
            event_type="outcome",
            run_id=RUN_ID,
            turn=TurnNumber(turn),
            agent_id=agent,
            tool_name=tool,  # type: ignore[arg-type]
            success=True,
            result_description=desc,
            world_state_after=world,
            divergence_score=None,
            timestamp=ts,
        )
        payload = json.loads(event.model_dump_json())
        lines.append(json.dumps(payload, separators=(",", ":")))
        ts = ts.replace(microsecond=min(ts.microsecond + 1, 999999))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} outcome lines to {OUT_PATH}")


if __name__ == "__main__":
    main()
