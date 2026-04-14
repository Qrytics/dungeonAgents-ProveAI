from __future__ import annotations

from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from pydantic import TypeAdapter

from apps.simulation.schemas import AnyEvent, OutcomeEvent, WorldState
from packages.shared.types import AgentID, CellType, Position, TurnNumber

_event_adapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)

# ---------------------------------------------------------------------------
# Colour palette — dark dungeon aesthetic
# ---------------------------------------------------------------------------

_CELL_NUMERIC: dict[CellType, float] = {
    "wall": 0.0,
    "floor": 0.17,
    "key": 0.33,
    "locked_door": 0.5,
    "exit": 0.67,
    "agent": 0.83,
}
_UNKNOWN_VALUE = 1.0  # rendered as near-black

_COLORSCALE = [
    [0.00, "#16213e"],  # wall
    [0.17, "#0f3460"],  # floor
    [0.33, "#e2b714"],  # key
    [0.50, "#c94040"],  # locked_door
    [0.67, "#4fc3f7"],  # exit
    [0.83, "#9c27b0"],  # agent
    [1.00, "#0d0d1a"],  # unknown (fog of war)
]

_DARK_LAYOUT: dict = dict(
    paper_bgcolor="#0d0d1a",
    plot_bgcolor="#1a1a2e",
    font=dict(color="#e0e0e0"),
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_world_states(event_log_path: Path) -> dict[TurnNumber, WorldState]:
    """Return a mapping from turn → most-recent WorldState for that turn."""
    states: dict[TurnNumber, WorldState] = {}
    with event_log_path.open() as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            event = _event_adapter.validate_json(raw_line)
            if isinstance(event, OutcomeEvent):
                states[event.turn] = event.world_state_after
    return states


def _ground_truth_arrays(
    world: WorldState,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (z, text) arrays for the ground-truth grid, with agents overlaid."""
    grid = world.grid
    rows = len(grid)
    cols = len(grid[0]) if rows else 0

    agent_at: dict[Position, AgentID] = {
        pos: aid for aid, pos in world.agent_positions.items()
    }

    z = np.zeros((rows, cols))
    text: list[list[str]] = []

    for r, row in enumerate(grid):
        text_row: list[str] = []
        for c, cell in enumerate(row):
            cell_type: CellType = cell.cell_type
            if (r, c) in agent_at:
                cell_type = "agent"
            z[r, c] = _CELL_NUMERIC[cell_type]
            text_row.append(cell_type)
        text.append(text_row)

    return z, np.array(text, dtype=object)


def _belief_arrays(
    world_states: dict[TurnNumber, WorldState],
    agent_id: AgentID,
    up_to_turn: TurnNumber,
    grid_rows: int,
    grid_cols: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Build agent belief grid incrementally up to (and including) selected_turn."""
    believed_grid: dict[Position, CellType] = {}
    believed_pos: Position | None = None

    for turn in sorted(world_states):
        if turn > up_to_turn:
            break
        world = world_states[turn]
        for row in world.grid:
            for cell in row:
                if agent_id in cell.is_visible_to:
                    pos: Position = (cell.row, cell.col)
                    believed_grid[pos] = cell.cell_type
        if agent_id in world.agent_positions:
            believed_pos = world.agent_positions[agent_id]

    z = np.full((grid_rows, grid_cols), _UNKNOWN_VALUE)
    text = np.full((grid_rows, grid_cols), "unknown", dtype=object)

    for (r, c), ct in believed_grid.items():
        if 0 <= r < grid_rows and 0 <= c < grid_cols:
            z[r, c] = _CELL_NUMERIC[ct]
            text[r, c] = ct

    if believed_pos is not None:
        r, c = believed_pos
        if 0 <= r < grid_rows and 0 <= c < grid_cols:
            z[r, c] = _CELL_NUMERIC["agent"]
            text[r, c] = "agent"

    return z, text


def _make_grid_figure(z: np.ndarray, text: np.ndarray, title: str) -> go.Figure:
    fig = go.Figure(
        go.Heatmap(
            z=z,
            text=text,
            texttemplate="%{text}",
            textfont=dict(size=7, color="#ffffff"),
            colorscale=_COLORSCALE,
            showscale=False,
            zmin=0.0,
            zmax=1.0,
        )
    )
    fig.update_layout(
        title=dict(text=title, font=dict(color="#e0e0e0", size=14)),
        xaxis=dict(title="Column", color="#e0e0e0", showgrid=False, zeroline=False),
        yaxis=dict(
            title="Row",
            color="#e0e0e0",
            showgrid=False,
            zeroline=False,
            autorange="reversed",
        ),
        margin=dict(l=40, r=40, t=50, b=40),
        **_DARK_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_replay(event_log_path: Path, selected_turn: int) -> None:
    """Render the dual-perspective replay view.

    Shows two side-by-side grids: Ground Truth (left) and the selected
    agent's accumulated belief state (right).  A turn slider lets the user
    scrub through turns; ``selected_turn`` is the initial slider value.
    """
    world_states = _load_world_states(event_log_path)
    if not world_states:
        st.warning("No outcome events found in the event log.")
        return

    turns = sorted(world_states)
    min_turn = int(turns[0])
    max_turn = int(turns[-1])

    # Turn slider — selected_turn is the default/initial value
    turn_val: int = st.slider(
        "Turn",
        min_value=min_turn,
        max_value=max_turn,
        value=max(min_turn, min(selected_turn, max_turn)),
        step=1,
        key="replay_turn_slider",
    )
    current_turn = TurnNumber(turn_val)

    # Find the latest state at or before current_turn
    available = [t for t in turns if t <= current_turn]
    display_turn = available[-1] if available else turns[0]
    current_world = world_states[display_turn]

    n_rows = len(current_world.grid)
    n_cols = len(current_world.grid[0]) if n_rows else 0

    agent_ids: list[AgentID] = ["agent_a", "agent_b"]
    selected_agent: AgentID = st.selectbox(
        "Belief perspective:",
        options=agent_ids,
        format_func=lambda a: a.replace("_", " ").title(),
        key="replay_agent_select",
    )

    gt_z, gt_text = _ground_truth_arrays(current_world)
    belief_z, belief_text = _belief_arrays(
        world_states, selected_agent, display_turn, n_rows, n_cols
    )

    # ── World-state metadata strip ────────────────────────────────────────
    pos_a = current_world.agent_positions.get("agent_a", "?")
    pos_b = current_world.agent_positions.get("agent_b", "?")
    key_holder = current_world.key_held_by or "on floor"
    door_status = "🔓 unlocked" if current_world.door_unlocked else "🔒 locked"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Agent A position", str(tuple(pos_a)) if isinstance(pos_a, list) else str(pos_a))
    m2.metric("Agent B position", str(tuple(pos_b)) if isinstance(pos_b, list) else str(pos_b))
    m3.metric("Key held by", key_holder)
    m4.metric("Door", door_status)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            _make_grid_figure(gt_z, gt_text, f"Ground Truth — Turn {display_turn}"),
            use_container_width=True,
            key="replay_ground_truth",
        )
    with col2:
        label = selected_agent.replace("_", " ").title()
        explored = int(np.sum(belief_z < _UNKNOWN_VALUE))
        total = n_rows * n_cols
        explored_pct = f"{100 * explored // total}% explored" if total else ""
        st.plotly_chart(
            _make_grid_figure(
                belief_z,
                belief_text,
                f"{label} Belief — Turn {display_turn} ({explored_pct})",
            ),
            use_container_width=True,
            key="replay_belief",
        )

    st.markdown(
        "<div style='color:#a0a0a0;font-size:11px;margin-top:2px'>"
        "<span style='background:#16213e;padding:2px 5px;border-radius:3px'>■</span> Wall &nbsp;"
        "<span style='background:#0f3460;padding:2px 5px;border-radius:3px'>■</span> Floor &nbsp;"
        "<span style='background:#e2b714;padding:2px 5px;border-radius:3px;color:#000'>■</span> Key &nbsp;"
        "<span style='background:#c94040;padding:2px 5px;border-radius:3px'>■</span> Locked Door &nbsp;"
        "<span style='background:#4fc3f7;padding:2px 5px;border-radius:3px;color:#000'>■</span> Exit &nbsp;"
        "<span style='background:#9c27b0;padding:2px 5px;border-radius:3px'>■</span> Agent &nbsp;"
        "<span style='background:#0d0d1a;padding:2px 5px;border-radius:3px;border:1px solid #555'>■</span> Unknown (fog)"
        "</div>",
        unsafe_allow_html=True,
    )
