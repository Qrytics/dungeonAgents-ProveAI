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

# Scale factor for computing marker pixel size from turn count.
# Chosen so that a 30-turn run gets markers ~14px wide; a 100-turn run gets ~4px.
_MARKER_SIZE_SCALE_FACTOR = 420


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

    Below the main chart a per-agent action-count summary is shown.
    """
    bars = _load_bars(event_log_path)
    if not bars:
        st.warning("No action events found in the event log.")
        return

    # ── Main Gantt chart ─────────────────────────────────────────────────
    fig = go.Figure()

    # Group bars by colour bucket
    buckets: dict[str, list[dict]] = {k: [] for k in _ACTION_COLORS}
    for bar in bars:
        bucket = bar["tool"] if bar["success"] else "failed"
        if bucket in buckets:
            buckets[bucket].append(bar)

    # Y-axis: only agents that appear in the data
    active_agents = sorted({b["agent"] for b in bars})
    # Keep canonical ordering (agent_a first)
    agent_order = [a for a in list(_AGENT_LABELS.keys()) if a in active_agents]
    y_map: dict[str, int] = {a: i for i, a in enumerate(agent_order)}

    max_turn = max((b["turn"] for b in bars), default=0)

    for bucket, color in _ACTION_COLORS.items():
        bucket_bars = buckets.get(bucket, [])
        if not bucket_bars:
            continue

        x_vals: list[float] = []
        y_vals: list[float] = []
        hover: list[str] = []
        for bar in bucket_bars:
            if bar["agent"] not in y_map:
                continue
            x_vals.append(bar["turn"])
            y_vals.append(float(y_map[bar["agent"]]))
            status = "✓ success" if bar["success"] else "✗ failed"
            hover.append(
                f"<b>{_AGENT_LABELS.get(bar['agent'], bar['agent'])}</b><br>"
                f"Turn: {bar['turn']}<br>"
                f"Action: {bar['tool']}<br>"
                f"Status: {status}"
            )

        # Use taller, wider square markers so they look like proper Gantt bars
        marker_size = max(12, min(22, int(_MARKER_SIZE_SCALE_FACTOR / max(max_turn + 1, 1))))
        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="markers",
                marker=dict(
                    symbol="square",
                    size=marker_size,
                    color=color,
                    line=dict(width=1, color="#0d0d1a"),
                    opacity=0.92,
                ),
                name=bucket.replace("_", " ").capitalize(),
                hovertemplate="%{text}<extra></extra>",
                text=hover,
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
            dtick=max(1, max_turn // 20),
            range=[-0.5, max_turn + 0.5],
        ),
        yaxis=dict(
            title="Agent",
            color=_FONT_COLOR,
            gridcolor=_GRID_COLOR,
            zeroline=False,
            tickvals=list(y_map.values()),
            ticktext=[_AGENT_LABELS.get(a, a) for a in agent_order],
            range=[-0.6, len(agent_order) - 0.4],
        ),
        paper_bgcolor=_BG_PAPER,
        plot_bgcolor=_BG_PLOT,
        font=dict(color=_FONT_COLOR),
        legend=dict(
            bgcolor="#1a1a2e",
            bordercolor="#444",
            borderwidth=1,
            font=dict(color=_FONT_COLOR),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
        margin=dict(l=110, r=40, t=80, b=60),
        height=220 + 80 * len(agent_order),
    )

    st.plotly_chart(fig, use_container_width=True, key="timeline_chart")

    # ── Action-count breakdown table ──────────────────────────────────────
    st.markdown(
        "<p style='color:#888;font-size:12px;margin-top:4px'>"
        "Action breakdown per agent</p>",
        unsafe_allow_html=True,
    )
    breakdown: dict[str, dict[str, int]] = {}
    for bar in bars:
        agent = _AGENT_LABELS.get(bar["agent"], bar["agent"])
        bucket = bar["tool"] if bar["success"] else "failed"
        breakdown.setdefault(agent, {}).setdefault(bucket, 0)
        breakdown[agent][bucket] += 1

    # Render as compact metric columns
    all_tools = list(_ACTION_COLORS.keys())
    cols = st.columns(len(breakdown))
    for col, (agent_label, counts) in zip(cols, breakdown.items()):
        with col:
            st.markdown(
                f"<p style='color:#e0e0e0;font-weight:600;margin-bottom:4px'>{agent_label}</p>",
                unsafe_allow_html=True,
            )
            for tool in all_tools:
                n = counts.get(tool, 0)
                if n:
                    color = _ACTION_COLORS[tool]
                    st.markdown(
                        f"<span style='color:{color}'>■</span>"
                        f" <span style='color:#d0d0d0;font-size:0.88rem'>"
                        f"{tool.capitalize()}: {n}</span>",
                        unsafe_allow_html=True,
                    )

