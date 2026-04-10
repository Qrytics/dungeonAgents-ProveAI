from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from pydantic import TypeAdapter

from apps.simulation.schemas import AnyEvent, IntentionEvent, MessageEvent, OutcomeEvent
from packages.shared.types import AgentID, ToolName

_event_adapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)

# ---------------------------------------------------------------------------
# Colour palette — dark dungeon aesthetic
# ---------------------------------------------------------------------------

_BG_PAPER = "#0d0d1a"
_BG_PLOT = "#1a1a2e"
_FONT_COLOR = "#e0e0e0"
_GRID_COLOR = "#2a2a4a"

# Action-type bar colours
_ACTION_COLORS: dict[str, str] = {
    "move": "#4caf50",        # green
    "observe": "#4fc3f7",     # blue
    "interact": "#ff9800",    # orange
    "communicate": "#9c27b0", # purple
    "failed": "#c94040",      # red
}

_AGENT_LABELS: dict[AgentID, str] = {
    "agent_a": "Agent A",
    "agent_b": "Agent B",
    "dungeon_master": "Dungeon Master",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_bars(
    event_log_path: Path,
) -> list[dict]:
    """Replay the event log and return a list of bar-segment descriptors.

    Each bar segment represents one agent action at one turn:
    ``{agent, turn, tool, success}``.
    """
    # Collect per-(agent, turn) outcome info
    outcomes: dict[tuple[AgentID, int], tuple[ToolName, bool]] = {}
    with event_log_path.open() as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            event = _event_adapter.validate_json(raw_line)
            if isinstance(event, OutcomeEvent):
                outcomes[(event.agent_id, int(event.turn))] = (event.tool_name, event.success)
            elif isinstance(event, MessageEvent):
                # Represent message as a communicate action at turn_sent
                key = (event.sender, int(event.turn_sent))
                if key not in outcomes:
                    outcomes[key] = ("communicate", True)

    bars: list[dict] = []
    for (agent_id, turn), (tool, success) in outcomes.items():
        bars.append(
            {
                "agent": agent_id,
                "turn": turn,
                "tool": tool,
                "success": success,
            }
        )

    bars.sort(key=lambda b: (b["agent"], b["turn"]))
    return bars


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_timeline(event_log_path: Path) -> None:
    """Render a Gantt-style activity timeline using Plotly.

    X-axis = simulation turns; Y-axis = agents.
    Each bar segment is coloured by action type:
    move (green), observe (blue), interact (orange),
    communicate (purple), failed action (red).
    """
    bars = _load_bars(event_log_path)
    if not bars:
        st.warning("No action events found in the event log.")
        return

    # Build one Scatter trace per (tool, success) combination for the legend
    fig = go.Figure()

    # Group bars by colour bucket
    buckets: dict[str, list[dict]] = {k: [] for k in _ACTION_COLORS}
    for bar in bars:
        bucket = bar["tool"] if bar["success"] else "failed"
        if bucket in buckets:
            buckets[bucket].append(bar)

    agents = list(_AGENT_LABELS.keys())
    y_map: dict[str, int] = {a: i for i, a in enumerate(agents)}

    for bucket, color in _ACTION_COLORS.items():
        bucket_bars = buckets.get(bucket, [])
        if not bucket_bars:
            continue

        x_vals: list[float] = []
        y_vals: list[float] = []
        hover: list[str] = []
        for bar in bucket_bars:
            x_vals.append(bar["turn"])
            y_vals.append(float(y_map.get(bar["agent"], 0)))  # type: ignore[arg-type]
            hover.append(
                f"Agent: {bar['agent']}<br>Turn: {bar['turn']}<br>"
                f"Tool: {bar['tool']}<br>Success: {bar['success']}"
            )

        # Render as wide markers to simulate Gantt bars
        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="markers",
                marker=dict(
                    symbol="square",
                    size=18,
                    color=color,
                    line=dict(width=1, color="#0d0d1a"),
                ),
                name=bucket.capitalize(),
                text=hover,
                hoverinfo="text",
                legendgroup=bucket,
            )
        )

    fig.update_layout(
        title=dict(text="Agent Activity Timeline", font=dict(color=_FONT_COLOR, size=16)),
        xaxis=dict(
            title="Turn",
            color=_FONT_COLOR,
            gridcolor=_GRID_COLOR,
            zeroline=False,
            dtick=1,
        ),
        yaxis=dict(
            title="Agent",
            color=_FONT_COLOR,
            gridcolor=_GRID_COLOR,
            zeroline=False,
            tickvals=list(y_map.values()),
            ticktext=[_AGENT_LABELS.get(a, a) for a in y_map],  # type: ignore[arg-type]
        ),
        paper_bgcolor=_BG_PAPER,
        plot_bgcolor=_BG_PLOT,
        font=dict(color=_FONT_COLOR),
        legend=dict(
            bgcolor="#1a1a2e",
            bordercolor="#444",
            borderwidth=1,
            font=dict(color=_FONT_COLOR),
        ),
        margin=dict(l=80, r=40, t=60, b=60),
        height=340,
    )

    st.plotly_chart(fig, use_container_width=True, key="timeline_chart")
