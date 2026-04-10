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

_BG_PAPER = "#0d0d1a"
_BG_PLOT = "#1a1a2e"
_FONT_COLOR = "#e0e0e0"
_GRID_COLOR = "#2a2a4a"

# Heatmap: 0.0 = no divergence (dark green), 1.0 = full divergence (red)
_DIVERGENCE_COLORSCALE = [
    [0.0, "#0f3460"],   # perfect belief — dark blue
    [0.3, "#1a6e3a"],   # low divergence — dark green
    [0.6, "#e2b714"],   # moderate — yellow
    [1.0, "#c94040"],   # high divergence — red
]
_UNKNOWN_ALPHA = "rgba(13,13,26,0.5)"  # fog of war overlay colour


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_world_states(event_log_path: Path) -> dict[TurnNumber, WorldState]:
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


def _compute_cell_divergence(
    world_states: dict[TurnNumber, WorldState],
    agent_id: AgentID,
    up_to_turn: TurnNumber,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """Compute per-cell divergence score for ``agent_id`` at ``up_to_turn``.

    Divergence at a cell:
    - 1.0 if the agent believes a different cell type than ground truth.
    - 0.0 if the agent's belief is correct.
    - NaN if the cell has never been observed (fog of war).

    Returns (z_divergence, z_mask, n_rows, n_cols) where z_mask is True for
    cells the agent has never observed (used to overlay fog-of-war styling).
    """
    # Determine grid dimensions from any world state
    sample_world = next(iter(world_states.values()))
    n_rows = len(sample_world.grid)
    n_cols = len(sample_world.grid[0]) if n_rows else 0

    believed_grid: dict[Position, CellType] = {}

    for turn in sorted(world_states):
        if turn > up_to_turn:
            break
        world = world_states[turn]
        for row in world.grid:
            for cell in row:
                if agent_id in cell.is_visible_to:
                    pos: Position = (cell.row, cell.col)
                    believed_grid[pos] = cell.cell_type

    # Ground truth at up_to_turn (latest available ≤ up_to_turn)
    available = [t for t in sorted(world_states) if t <= up_to_turn]
    current_world = world_states[available[-1]] if available else sample_world
    ground_truth: dict[Position, CellType] = {
        (cell.row, cell.col): cell.cell_type
        for row in current_world.grid
        for cell in row
    }

    z = np.full((n_rows, n_cols), np.nan)
    fog_mask = np.ones((n_rows, n_cols), dtype=bool)

    for (r, c), believed_type in believed_grid.items():
        if 0 <= r < n_rows and 0 <= c < n_cols:
            fog_mask[r, c] = False
            truth = ground_truth.get((r, c))
            z[r, c] = 0.0 if truth == believed_type else 1.0

    return z, fog_mask, n_rows, n_cols


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_heatmaps(
    event_log_path: Path,
    selected_agent: AgentID,
    selected_turn: int,
) -> None:
    """Render belief confidence and divergence heatmaps using Plotly.

    Shows a dungeon grid where each cell is coloured by its per-cell
    divergence score (0 = correct belief, 1 = wrong belief, fog = unobserved).
    A turn slider lets the user scrub through turns; ``selected_turn`` is the
    initial slider value.  ``selected_agent`` selects whose belief to analyse.
    """
    world_states = _load_world_states(event_log_path)
    if not world_states:
        st.warning("No outcome events found in the event log.")
        return

    turns = sorted(world_states)
    min_turn = int(turns[0])
    max_turn = int(turns[-1])

    col_agent, col_turn = st.columns([1, 2])
    with col_agent:
        agent_ids: list[AgentID] = ["agent_a", "agent_b"]
        agent: AgentID = st.selectbox(  # type: ignore[assignment]
            "Agent:",
            options=agent_ids,
            index=agent_ids.index(selected_agent) if selected_agent in agent_ids else 0,
            format_func=lambda a: a.replace("_", " ").title(),
            key="heatmap_agent_select",
        )
    with col_turn:
        turn_val: int = st.slider(
            "Turn",
            min_value=min_turn,
            max_value=max_turn,
            value=max(min_turn, min(selected_turn, max_turn)),
            step=1,
            key="heatmap_turn_slider",
        )

    current_turn = TurnNumber(turn_val)

    z, fog_mask, n_rows, n_cols = _compute_cell_divergence(
        world_states, agent, current_turn
    )

    # Replace NaN (fog cells) with a sentinel below the colorscale range
    # so they render distinctly.  We draw a separate overlay instead.
    z_display = np.where(fog_mask, np.nan, z)

    hover_text: list[list[str]] = []
    for r in range(n_rows):
        row_text: list[str] = []
        for c in range(n_cols):
            if fog_mask[r, c]:
                row_text.append(f"Row {r}, Col {c}<br>Unobserved (fog of war)")
            else:
                score = z[r, c]
                label = "correct" if score == 0.0 else "incorrect"
                row_text.append(f"Row {r}, Col {c}<br>Divergence: {score:.2f} ({label})")
        hover_text.append(row_text)

    fig = go.Figure()

    # Divergence heatmap layer
    fig.add_trace(
        go.Heatmap(
            z=z_display,
            text=hover_text,
            hoverinfo="text",
            colorscale=_DIVERGENCE_COLORSCALE,
            zmin=0.0,
            zmax=1.0,
            showscale=True,
            colorbar=dict(
                title=dict(text="Divergence", font=dict(color=_FONT_COLOR)),
                tickfont=dict(color=_FONT_COLOR),
                bgcolor="#1a1a2e",
                bordercolor="#444",
            ),
        )
    )

    # Fog-of-war overlay layer (unknown cells)
    fog_z = np.where(fog_mask, 0.5, np.nan)
    fig.add_trace(
        go.Heatmap(
            z=fog_z,
            colorscale=[[0.0, "#0d0d1a"], [1.0, "#0d0d1a"]],
            showscale=False,
            opacity=0.75,
            hoverinfo="skip",
        )
    )

    agent_label = agent.replace("_", " ").title()
    fig.update_layout(
        title=dict(
            text=f"Belief Divergence Heatmap — {agent_label} — Turn {turn_val}",
            font=dict(color=_FONT_COLOR, size=15),
        ),
        xaxis=dict(
            title="Column",
            color=_FONT_COLOR,
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            title="Row",
            color=_FONT_COLOR,
            showgrid=False,
            zeroline=False,
            autorange="reversed",
        ),
        paper_bgcolor=_BG_PAPER,
        plot_bgcolor=_BG_PLOT,
        font=dict(color=_FONT_COLOR),
        margin=dict(l=60, r=60, t=60, b=60),
        height=520,
    )

    st.plotly_chart(fig, use_container_width=True, key="heatmap_chart")

    st.markdown(
        "<div style='color:#e0e0e0;font-size:12px'>"
        "<span style='color:#0f3460'>■</span> Perfect belief &nbsp;"
        "<span style='color:#1a6e3a'>■</span> Low divergence &nbsp;"
        "<span style='color:#e2b714'>■</span> Moderate &nbsp;"
        "<span style='color:#c94040'>■</span> High divergence &nbsp;"
        "<span style='color:#0d0d1a;background:#555'>■</span> Unobserved"
        "</div>",
        unsafe_allow_html=True,
    )
