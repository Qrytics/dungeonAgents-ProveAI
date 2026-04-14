"""Generate a rich 30-turn demo run JSONL for all dashboards.

This script creates a deterministic, self-contained simulation of two agents
navigating an 8×8 dungeon over 30 turns (turns 0–29).  It produces:

  1. ``runs/demo_30turn_run.jsonl``          — for the Legibility / Streamlit dashboard.
  2. ``apps/visualizer/public/sample_visualizer_demo.jsonl`` — for the React replay UI.

The demo uses seed=42 and tells the following story:
  - Both agents start by exploring wrong areas (turns 0–9, failures and fog-of-war).
  - Agent B discovers the exit first; Agent A finds the key (turns 10–15).
  - Agent A picks up the key, walks to unlock the door, then rushes to the exit.
  - Both agents reach the exit at turn 29 → WIN.

All outcome events include ``is_visible_to`` populated from each acting agent's
Moore-neighbourhood (FOG_RADIUS=1), enabling correct belief-state rendering in
the Legibility heatmaps and replay view.

All intention events are included so the Timeline view shows both halves of
each turn.

Divergence scores are computed per-event based on the acting agent's cumulative
belief vs ground truth at that point in the run.

Run from the repository root (after ``pip install -e .``):
    python scripts/generate_demo_run.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

RUNS_OUT = Path("runs/demo_30turn_run.jsonl")
VIZ_OUT = Path("apps/visualizer/public/sample_visualizer_demo.jsonl")
RUN_ID = "00000000-0000-4000-a000-00000000dem0"
SEED = 42

# ---------------------------------------------------------------------------
# Hard-coded grid for seed=42  (8×8)
# Row/col types derived from DungeonGrid(rows=8, cols=8, seed=42).
# ---------------------------------------------------------------------------
#
#  Col:   0  1  2  3  4  5  6  7
# Row 0:  W  W  W  W  W  W  W  W
# Row 1:  W  F  W  F  F  F  F  W
# Row 2:  W  F  W  F  W  F  F  W
# Row 3:  W  W  W  F  F  F  F  W
# Row 4:  W  F  W  F  F  F  W  W
# Row 5:  W  F  F  W  W  F  E  W   ← E=exit at (5,6)
# Row 6:  W  D  F  F  F  F  K  W   ← D=locked_door at (6,1); K=key at (6,6)
# Row 7:  W  W  W  W  W  W  W  W
#
# Legend: W=wall, F=floor, E=exit, D=locked_door, K=key

_GRID_RAW: list[list[str]] = [
    ["wall", "wall",        "wall",        "wall",        "wall",        "wall",        "wall",  "wall"],
    ["wall", "floor",       "wall",        "floor",       "floor",       "floor",       "floor", "wall"],
    ["wall", "floor",       "wall",        "floor",       "wall",        "floor",       "floor", "wall"],
    ["wall", "wall",        "wall",        "floor",       "floor",       "floor",       "floor", "wall"],
    ["wall", "floor",       "wall",        "floor",       "floor",       "floor",       "wall",  "wall"],
    ["wall", "floor",       "floor",       "wall",        "wall",        "floor",       "exit",  "wall"],
    ["wall", "locked_door", "floor",       "floor",       "floor",       "floor",       "key",   "wall"],
    ["wall", "wall",        "wall",        "wall",        "wall",        "wall",        "wall",  "wall"],
]

ROWS = 8
COLS = 8

# FOG_RADIUS = 1 → Moore neighbourhood (3×3 centred on agent)
FOG_RADIUS = 1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def cell_at(r: int, c: int, dynamic: dict[tuple[int, int], str]) -> str:
    """Return the cell type at (r,c), consulting the mutable dynamic overlay."""
    return dynamic.get((r, c), _GRID_RAW[r][c])


def moore_neighborhood(r: int, c: int) -> list[tuple[int, int]]:
    """Return all (row, col) pairs within FOG_RADIUS of (r, c)."""
    cells = []
    for dr in range(-FOG_RADIUS, FOG_RADIUS + 1):
        for dc in range(-FOG_RADIUS, FOG_RADIUS + 1):
            nr, nc = r + dr, c + dc
            if 0 <= nr < ROWS and 0 <= nc < COLS:
                cells.append((nr, nc))
    return cells


def build_world_state(
    turn: int,
    pos_a: tuple[int, int],
    pos_b: tuple[int, int],
    key_held_by: str | None,
    door_unlocked: bool,
    dynamic: dict[tuple[int, int], str],
    visible_to_a: list[tuple[int, int]],
    visible_to_b: list[tuple[int, int]],
) -> dict:
    """Construct a world_state_after dict with is_visible_to populated."""
    visible_a_set = set(visible_to_a)
    visible_b_set = set(visible_to_b)

    grid = []
    for r in range(ROWS):
        row = []
        for c in range(COLS):
            ct = cell_at(r, c, dynamic)
            visible = []
            if (r, c) in visible_a_set:
                visible.append("agent_a")
            if (r, c) in visible_b_set:
                visible.append("agent_b")
            row.append({
                "row": r,
                "col": c,
                "cell_type": ct,
                "is_visible_to": visible,
            })
        grid.append(row)

    return {
        "run_id": RUN_ID,
        "turn": turn,
        "grid": grid,
        "agent_positions": {"agent_a": list(pos_a), "agent_b": list(pos_b)},
        "key_held_by": key_held_by,
        "door_unlocked": door_unlocked,
    }


def compute_divergence(
    agent_id: str,
    cumulative_belief: dict[tuple[int, int], str],
    dynamic: dict[tuple[int, int], str],
) -> float:
    """Fraction of believed cells that differ from current ground truth."""
    if not cumulative_belief:
        return 0.0
    mismatched = sum(
        1
        for pos, believed in cumulative_belief.items()
        if cell_at(pos[0], pos[1], dynamic) != believed
    )
    return round(mismatched / len(cumulative_belief), 4)


def ts(offset_ms: int) -> str:
    """Return an ISO timestamp offset_ms milliseconds after the base time."""
    base = datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc)
    total_us = offset_ms * 1000
    sec = total_us // 1_000_000
    us = total_us % 1_000_000
    from datetime import timedelta
    t = base + timedelta(seconds=sec, microseconds=us)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# ---------------------------------------------------------------------------
# Script events
# ---------------------------------------------------------------------------
# Each entry: (turn, agent, action_type, detail)
# action_type: "move", "observe", "interact", "communicate", "fail_move"
# detail for move/fail_move: direction string
# detail for communicate: (recipient, message_content)
# detail for observe/interact: descriptive string for result_description

_SCRIPT: list[tuple] = [
    # ── Turn 0: Initial observation ─────────────────────────────────────
    (0,  "agent_a", "observe",    "Agent A surveys the dungeon from (3,4). Nearby walls to north and west."),
    (0,  "agent_b", "observe",    "Agent B surveys the dungeon from (1,5). Wall to west; floor south."),

    # ── Turn 1: First moves — A probes wrong way; B heads south ─────────
    (1,  "agent_a", "fail_move",  "north"),   # (2,4) is wall
    (1,  "agent_b", "move",       "south"),   # (1,5)→(2,5)

    # ── Turn 2: A corrects; B scans new area ────────────────────────────
    (2,  "agent_a", "move",       "west"),    # (3,4)→(3,3)
    (2,  "agent_b", "observe",    "Agent B at (2,5). Passage opens south. Dim light ahead."),

    # ── Turn 3: A explores dead-end corridor; B continues south ─────────
    (3,  "agent_a", "move",       "south"),   # (3,3)→(4,3)
    (3,  "agent_b", "move",       "south"),   # (2,5)→(3,5)

    # ── Turn 4: A hits southern wall; B scans and calls out ─────────────
    (4,  "agent_a", "fail_move",  "south"),   # (5,3) is wall
    (4,  "agent_b", "communicate", ("agent_a", "Heading south through open corridor. Walls blocking east from here. You?")),

    # ── Turn 5: A responds; B continues south ───────────────────────────
    (5,  "agent_a", "communicate", ("agent_b", "Southern passage blocked. Walls everywhere west. Moving east to find an opening.")),
    (5,  "agent_b", "move",       "south"),   # (3,5)→(4,5)

    # ── Turn 6: A moves east; B hits east wall and scans ────────────────
    (6,  "agent_a", "move",       "east"),    # (4,3)→(4,4)
    (6,  "agent_b", "fail_move",  "east"),    # (4,6) is wall

    # ── Turn 7: A continues east; B goes south ──────────────────────────
    (7,  "agent_a", "move",       "east"),    # (4,4)→(4,5)
    (7,  "agent_b", "move",       "south"),   # (4,5)→(5,5)

    # ── Turn 8: A goes south too; B observes — B spots exit + key! ──────
    (8,  "agent_a", "move",       "south"),   # (4,5)→(5,5)
    (8,  "agent_b", "observe",    "Agent B at (5,5) SPOTS the EXIT at (5,6) and KEY at (6,6)! Major discovery!"),

    # ── Turn 9: A observes same area; B races to exit ───────────────────
    (9,  "agent_a", "observe",    "Agent A at (5,5) also sees the EXIT at (5,6) and KEY at (6,6). Plans forming!"),
    (9,  "agent_b", "move",       "east"),    # (5,5)→(5,6)  B reaches EXIT

    # ── Turn 10: A & B coordinate plan ──────────────────────────────────
    (10, "agent_a", "communicate", ("agent_b", "I see the key at (6,6)! I will retrieve it. You secure the exit.")),
    (10, "agent_b", "communicate", ("agent_a", "I am AT exit (5,6)! You get the key, unlock door at (6,1), then come here.")),

    # ── Turn 11: A heads south toward key; B holds ──────────────────────
    (11, "agent_a", "move",       "south"),   # (5,5)→(6,5)
    (11, "agent_b", "observe",    "Agent B waits at exit (5,6), watching Agent A's progress to the south."),

    # ── Turn 12: A moves east to key cell; B waits ──────────────────────
    (12, "agent_a", "move",       "east"),    # (6,5)→(6,6)
    (12, "agent_b", "observe",    "Agent B holds at (5,6). Monitoring. No changes yet."),

    # ── Turn 13: A picks up key! B signals progress check ───────────────
    (13, "agent_a", "interact",   "Agent A picks up the KEY at (6,6)! Key now in possession."),
    (13, "agent_b", "communicate", ("agent_a", "Status check. Door is at (6,1) — you must stand adjacent at (6,2) to unlock.")),

    # ── Turn 14: A plans; B receives progress update ─────────────────────
    (14, "agent_a", "observe",    "Agent A at (6,6) has the key. Scanning route to door at (6,1)."),
    (14, "agent_b", "observe",    "Agent B at exit receives A's key pickup. Ready to proceed on unlock."),

    # ── Turn 15: A announces key pickup; B waits ────────────────────────
    (15, "agent_a", "communicate", ("agent_b", "KEY SECURED! Moving west along row 6 to unlock door at (6,1). ETA 6 turns.")),
    (15, "agent_b", "observe",    "Agent B maintains position at (5,6). Awaiting door unlock."),

    # ── Turn 16: A starts west trek; B waits ────────────────────────────
    (16, "agent_a", "move",       "west"),    # (6,6)→(6,5)
    (16, "agent_b", "observe",    "Agent B at exit. Patience. Agent A is carrying the key westward."),

    # ── Turn 17: A continues west; B reports readiness ──────────────────
    (17, "agent_a", "move",       "west"),    # (6,5)→(6,4)
    (17, "agent_b", "communicate", ("agent_a", "Copy that. Standing by at exit. Confirm when door is unlocked.")),

    # ── Turn 18: A continues west; B waits ──────────────────────────────
    (18, "agent_a", "move",       "west"),    # (6,4)→(6,3)
    (18, "agent_b", "observe",    "Agent B scans the dungeon from (5,6). Watching for door status."),

    # ── Turn 19: A reaches unlock position; B waits ─────────────────────
    (19, "agent_a", "move",       "west"),    # (6,3)→(6,2)  adjacent to door!
    (19, "agent_b", "observe",    "Agent B holds at exit. Agent A should be near the door now."),

    # ── Turn 20: A UNLOCKS the door! B checks in ────────────────────────
    (20, "agent_a", "interact",   "Agent A UNLOCKS the DOOR at (6,1)! Dungeon passage now open!"),
    (20, "agent_b", "communicate", ("agent_a", "Is the door unlocked? I hear something shifting in the dungeon...")),

    # ── Turn 21: A confirms unlock; B receives ──────────────────────────
    (21, "agent_a", "communicate", ("agent_b", "DOOR UNLOCKED! Retracing east. ETA 5 turns to exit. Hold position!")),
    (21, "agent_b", "observe",    "Agent B receives unlock confirmation. Victory close. Holding exit."),

    # ── Turn 22: A races east; B waits ──────────────────────────────────
    (22, "agent_a", "move",       "east"),    # (6,2)→(6,3)
    (22, "agent_b", "observe",    "Agent B at exit. Door is open. Awaiting Agent A's arrival."),

    # ── Turn 23: A continues east; B waits ──────────────────────────────
    (23, "agent_a", "move",       "east"),    # (6,3)→(6,4)
    (23, "agent_b", "observe",    "Agent B steady at (5,6). Almost there."),

    # ── Turn 24: A continues east; B waits ──────────────────────────────
    (24, "agent_a", "move",       "east"),    # (6,4)→(6,5)
    (24, "agent_b", "observe",    "Agent B observes approach corridor from exit position."),

    # ── Turn 25: A reaches (6,6); B waits ───────────────────────────────
    (25, "agent_a", "move",       "east"),    # (6,5)→(6,6)
    (25, "agent_b", "observe",    "Agent B spots Agent A entering the south key chamber."),

    # ── Turn 26: A announces final approach; B readies ──────────────────
    (26, "agent_a", "communicate", ("agent_b", "At (6,6) now! Moving north to exit NEXT TURN. Get ready!")),
    (26, "agent_b", "observe",    "Agent B at (5,6). Receives A's final approach message. Bracing for victory."),

    # ── Turn 27: A observes; B gives all-clear ───────────────────────────
    (27, "agent_a", "observe",    "Agent A at (6,6) sees the exit clearly at (5,6). One step away!"),
    (27, "agent_b", "communicate", ("agent_a", "EXIT IS CLEAR. No obstacles. Come now!")),

    # ── Turn 28: A receives all-clear; B holds ───────────────────────────
    (28, "agent_a", "observe",    "Agent A at (6,6) receives all-clear signal. Ready to take final step."),
    (28, "agent_b", "observe",    "Agent B at (5,6) holds steady. One step away from completing mission."),

    # ── Turn 29: A steps onto EXIT tile → WIN! ───────────────────────────
    (29, "agent_a", "move",       "north"),   # (6,6)→(5,6)  A reaches EXIT → WIN!
    (29, "agent_b", "observe",    "Agent B watches Agent A step onto the EXIT tile — BOTH AGENTS AT EXIT! MISSION COMPLETE!"),
]

# ── Termination at the end of turn 29 ───────────────────────────────────────


def _generate() -> None:
    pos_a: tuple[int, int] = (3, 4)
    pos_b: tuple[int, int] = (1, 5)
    key_held_by: str | None = None
    door_unlocked: bool = False

    # Mutable overlay for the grid (captures state changes)
    dynamic: dict[tuple[int, int], str] = {}

    # Cumulative agent beliefs (position → cell_type they've observed)
    beliefs: dict[str, dict[tuple[int, int], str]] = {
        "agent_a": {},
        "agent_b": {},
    }

    # Direction deltas
    dir_delta = {
        "north": (-1, 0),
        "south": (1, 0),
        "east": (0, 1),
        "west": (0, -1),
    }

    lines_runs: list[str] = []
    lines_viz: list[str] = []  # outcome only (for React)
    event_ts = 0  # running millisecond offset

    # Process events turn by turn
    turn_events: dict[int, list[tuple]] = {}
    for entry in _SCRIPT:
        t = entry[0]
        turn_events.setdefault(t, []).append(entry[1:])

    max_turn = max(turn_events.keys())

    for turn in range(max_turn + 1):
        for entry in turn_events.get(turn, []):
            agent_id, action, detail = entry[0], entry[1], entry[2]
            pos = pos_a if agent_id == "agent_a" else pos_b

            # ── Build intention event ────────────────────────────────
            if action == "communicate":
                recipient, content = detail
                tool_name = "communicate"
                tool_args = {"recipient": recipient, "message": content}
                llm_output = f"communicate to {recipient}: {content}"
            elif action in ("move", "fail_move"):
                direction = detail
                tool_name = "move"
                tool_args = {"direction": direction}
                llm_output = f"move {direction}"
            elif action == "observe":
                tool_name = "observe"
                tool_args = {}
                llm_output = "observe"
            elif action == "interact":
                tool_name = "interact"
                tool_args = {}
                llm_output = "interact"
            else:
                tool_name = action
                tool_args = {}
                llm_output = action

            intention = {
                "event_type": "intention",
                "run_id": RUN_ID,
                "turn": turn,
                "agent_id": agent_id,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "llm_prompt_tokens": 380 + turn * 12 + (5 if agent_id == "agent_b" else 0),
                "llm_completion_tokens": len(llm_output.split()) + 1,
                "latency_ms": 120.0 + turn * 3.5,
                "raw_llm_output": llm_output,
                "timestamp": ts(event_ts),
            }
            lines_runs.append(json.dumps(intention, separators=(",", ":")))
            event_ts += 50

            # ── Apply state mutations ────────────────────────────────
            success = True
            result_desc = ""

            if action == "move":
                dr, dc = dir_delta[detail]
                new_r, new_c = pos[0] + dr, pos[1] + dc
                target = cell_at(new_r, new_c, dynamic)
                if target == "wall":
                    success = False
                    result_desc = f"Agent {agent_id} cannot move {detail}: wall at ({new_r},{new_c})."
                elif target == "locked_door" and not door_unlocked:
                    success = False
                    result_desc = f"Agent {agent_id} cannot move {detail}: door at ({new_r},{new_c}) is locked."
                else:
                    pos = (new_r, new_c)
                    result_desc = f"Agent {agent_id} moves {detail} to {pos} ({target})."
                    if agent_id == "agent_a":
                        pos_a = pos
                    else:
                        pos_b = pos

            elif action == "fail_move":
                direction = detail
                dr, dc = dir_delta[direction]
                new_r, new_c = pos[0] + dr, pos[1] + dc
                target = cell_at(new_r, new_c, dynamic)
                success = False
                result_desc = f"Agent {agent_id} cannot move {direction}: {target} at ({new_r},{new_c})."

            elif action == "observe":
                success = True
                result_desc = detail  # provided directly in script

            elif action == "interact":
                current_cell = cell_at(pos[0], pos[1], dynamic)
                if current_cell == "key" and key_held_by is None:
                    key_held_by = agent_id
                    success = True
                    result_desc = detail
                else:
                    # Check adjacent locked_door
                    adj_door = None
                    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nr, nc = pos[0] + dr, pos[1] + dc
                        if 0 <= nr < ROWS and 0 <= nc < COLS:
                            if cell_at(nr, nc, dynamic) == "locked_door":
                                adj_door = (nr, nc)
                                break
                    if adj_door and key_held_by == agent_id and not door_unlocked:
                        door_unlocked = True
                        success = True
                        result_desc = detail
                    else:
                        success = False
                        result_desc = f"Agent {agent_id}: nothing to interact with at {pos}."

            elif action == "communicate":
                recipient, content = detail
                success = True
                result_desc = f"Agent {agent_id} sends message to {recipient}."

                # Emit message event
                message_evt = {
                    "event_type": "message",
                    "run_id": RUN_ID,
                    "turn_sent": turn,
                    "turn_delivered": turn + 1,
                    "sender": agent_id,
                    "recipient": recipient,
                    "content": content,
                    "timestamp": ts(event_ts),
                }
                lines_runs.append(json.dumps(message_evt, separators=(",", ":")))
                event_ts += 20

            # ── Compute is_visible_to ────────────────────────────────
            # Only the acting agent's neighbourhood is visible in this event.
            acting_pos = pos_a if agent_id == "agent_a" else pos_b
            visible_a = moore_neighborhood(*pos_a) if agent_id == "agent_a" else []
            visible_b = moore_neighborhood(*pos_b) if agent_id == "agent_b" else []

            # ── Update cumulative beliefs ────────────────────────────
            for cell_pos in (visible_a if agent_id == "agent_a" else visible_b):
                r, c = cell_pos
                beliefs[agent_id][(r, c)] = cell_at(r, c, dynamic)

            # ── Divergence score ─────────────────────────────────────
            div_score = compute_divergence(agent_id, beliefs[agent_id], dynamic)

            # ── Build outcome event ──────────────────────────────────
            world = build_world_state(
                turn=turn,
                pos_a=pos_a,
                pos_b=pos_b,
                key_held_by=key_held_by,
                door_unlocked=door_unlocked,
                dynamic=dynamic,
                visible_to_a=visible_a,
                visible_to_b=visible_b,
            )

            outcome = {
                "event_type": "outcome",
                "run_id": RUN_ID,
                "turn": turn,
                "agent_id": agent_id,
                "tool_name": tool_name,
                "success": success,
                "result_description": result_desc,
                "world_state_after": world,
                "divergence_score": div_score,
                "timestamp": ts(event_ts),
            }
            line = json.dumps(outcome, separators=(",", ":"))
            lines_runs.append(line)
            lines_viz.append(line)  # React visualiser only needs outcome events
            event_ts += 60

    # ── Termination event ─────────────────────────────────────────────────
    termination = {
        "event_type": "termination",
        "run_id": RUN_ID,
        "final_turn": max_turn,
        "reason": "win",
        "winner": True,
        "timestamp": ts(event_ts),
    }
    lines_runs.append(json.dumps(termination, separators=(",", ":")))

    # ── Write output files ────────────────────────────────────────────────
    RUNS_OUT.parent.mkdir(parents=True, exist_ok=True)
    RUNS_OUT.write_text("\n".join(lines_runs) + "\n", encoding="utf-8")

    VIZ_OUT.parent.mkdir(parents=True, exist_ok=True)
    VIZ_OUT.write_text("\n".join(lines_viz) + "\n", encoding="utf-8")

    n_events = len(lines_runs)
    n_viz = len(lines_viz)
    n_intentions = sum(1 for l in lines_runs if '"intention"' in l)
    n_outcomes = sum(1 for l in lines_runs if '"outcome"' in l)
    n_messages = sum(1 for l in lines_runs if '"message"' in l)

    print(f"Demo run generated  (seed={SEED}, turns 0–{max_turn}, WIN)")
    print(f"  Total events    : {n_events}")
    print(f"  Intentions      : {n_intentions}")
    print(f"  Outcomes        : {n_outcomes}")
    print(f"  Messages        : {n_messages}")
    print(f"  Termination     : 1")
    print(f"  → {RUNS_OUT}  ({RUNS_OUT.stat().st_size} bytes)")
    print(f"  → {VIZ_OUT}  ({VIZ_OUT.stat().st_size} bytes)  [{n_viz} frames]")


if __name__ == "__main__":
    _generate()
