from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from pydantic import TypeAdapter
from pyvis.network import Network

from apps.legibility.analysis.report import CausalIncidentReport
from apps.simulation.schemas import AnyEvent, OutcomeEvent, TerminationEvent
from packages.shared.types import AgentID, TurnNumber

_event_adapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)

# ---------------------------------------------------------------------------
# Colour palette — dark dungeon aesthetic
# ---------------------------------------------------------------------------

_BG_COLOR = "#0d0d1a"
_NODE_COLORS: dict[str, str] = {
    "root_cause": "#c94040",     # red — divergence spike / root cause
    "decision": "#e2b714",       # yellow — agent decision turn
    "outcome": "#4fc3f7",        # blue — outcome / consequence
    "termination": "#9c27b0",    # purple — simulation end
}
_EDGE_COLOR = "#888888"
_FONT_COLOR = "#e0e0e0"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_outcome_turns(event_log_path: Path) -> dict[TurnNumber, dict[AgentID, bool]]:
    """Return a mapping of turn → {agent_id: success} from OutcomeEvents."""
    outcomes: dict[TurnNumber, dict[AgentID, bool]] = {}
    with event_log_path.open() as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            event = _event_adapter.validate_json(raw_line)
            if isinstance(event, OutcomeEvent):
                outcomes.setdefault(event.turn, {})[event.agent_id] = event.success
    return outcomes


def _load_termination(event_log_path: Path) -> TerminationEvent | None:
    termination: TerminationEvent | None = None
    with event_log_path.open() as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            event = _event_adapter.validate_json(raw_line)
            if isinstance(event, TerminationEvent):
                termination = event
    return termination


def _build_dag(report: CausalIncidentReport, event_log_path: Path) -> Network:
    """Construct a pyvis Network DAG for the causal failure graph."""
    net = Network(
        height="500px",
        width="100%",
        bgcolor=_BG_COLOR,
        font_color=_FONT_COLOR,
        directed=True,
    )

    outcome_turns = _load_outcome_turns(event_log_path)
    termination = _load_termination(event_log_path)

    added_nodes: set[str] = set()

    def _add_node(node_id: str, label: str, kind: str, title: str = "") -> None:
        if node_id not in added_nodes:
            net.add_node(
                node_id,
                label=label,
                color=_NODE_COLORS[kind],
                title=title or label,
                font={"color": _FONT_COLOR, "size": 13},
                size=20,
            )
            added_nodes.add(node_id)

    def _add_edge(src: str, dst: str, label: str = "") -> None:
        net.add_edge(src, dst, color=_EDGE_COLOR, label=label, font={"color": _FONT_COLOR})

    # Termination node
    term_node = "termination"
    term_label = (
        f"Termination\nTurn {report.final_turn}\n{report.termination_reason}"
    )
    _add_node(term_node, term_label, "termination", title=report.summary)

    # For each agent with divergence spike turns, build the chain
    for agent_id, spike_turns in report.root_cause_turns.items():
        if not spike_turns:
            continue

        prev_node: str | None = None
        for spike_turn in sorted(spike_turns):
            # Root cause node — divergence spike
            rc_node = f"rc_{agent_id}_{spike_turn}"
            rc_label = f"Divergence Spike\n{agent_id}\nTurn {spike_turn}"
            _add_node(rc_node, rc_label, "root_cause", title=f"High epistemic divergence at turn {spike_turn}")

            # Decision node — what the agent did at that turn
            dec_node = f"dec_{agent_id}_{spike_turn}"
            turn_outcomes = outcome_turns.get(TurnNumber(spike_turn), {})
            success = turn_outcomes.get(agent_id, None)  # type: ignore[arg-type]
            success_str = "succeeded" if success else ("failed" if success is False else "unknown")
            dec_label = f"Decision\n{agent_id}\nTurn {spike_turn}\n({success_str})"
            _add_node(dec_node, dec_label, "decision", title=f"Agent action at turn {spike_turn}: {success_str}")

            # Outcome node
            out_node = f"out_{agent_id}_{spike_turn}"
            out_label = f"Outcome\nTurn {spike_turn}"
            _add_node(out_node, out_label, "outcome", title="Consequence of decision under diverged belief")

            # Chain: root_cause → decision → outcome
            _add_edge(rc_node, dec_node, label="drives")
            _add_edge(dec_node, out_node, label="produces")

            # Chain between consecutive spikes
            if prev_node is not None:
                _add_edge(prev_node, rc_node, label="leads to")

            # Last outcome node connects to termination
            last_spike = sorted(spike_turns)[-1]
            if spike_turn == last_spike:
                _add_edge(out_node, term_node, label="causes")

            prev_node = out_node

    # Fallback: if no spike turns at all, add a direct summary → termination edge
    if not any(report.root_cause_turns.values()):
        cause_node = "cause_summary"
        _add_node(
            cause_node,
            "Root Cause\n(see report)",
            "root_cause",
            title=report.root_cause_explanation,
        )
        _add_edge(cause_node, term_node, label="causes")

    net.set_options(
        """
        var options = {
          "edges": {
            "arrows": { "to": { "enabled": true } },
            "smooth": { "type": "curvedCW", "roundness": 0.2 }
          },
          "physics": {
            "enabled": true,
            "solver": "forceAtlas2Based"
          }
        }
        """
    )
    return net


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _divergence_chart(event_log_path: Path) -> go.Figure:
    """Return a Plotly line chart of per-agent divergence over turns."""
    from apps.legibility.analysis.divergence import compute_divergence_timeseries

    ts = compute_divergence_timeseries(event_log_path)

    fig = go.Figure()
    palette = {"agent_a": "#e2b714", "agent_b": "#4fc3f7"}

    for agent_id, pairs in ts.items():
        if not pairs:
            continue
        turns = [int(t) for t, _ in pairs]
        scores = [s for _, s in pairs]
        fig.add_trace(
            go.Scatter(
                x=turns,
                y=scores,
                mode="lines+markers",
                name=agent_id.replace("_", " ").title(),
                line=dict(color=palette.get(agent_id, "#ffffff"), width=2),
                marker=dict(size=5),
            )
        )

    fig.update_layout(
        title=dict(text="Epistemic Divergence over Time", font=dict(color="#e0e0e0", size=14)),
        xaxis=dict(title="Turn", color="#e0e0e0", gridcolor="#2a2a4a", zeroline=False, dtick=2),
        yaxis=dict(
            title="Divergence score",
            color="#e0e0e0",
            gridcolor="#2a2a4a",
            zeroline=False,
            range=[-0.05, 1.05],
        ),
        paper_bgcolor="#0d0d1a",
        plot_bgcolor="#1a1a2e",
        font=dict(color="#e0e0e0"),
        legend=dict(bgcolor="#1a1a2e", bordercolor="#444", borderwidth=1, font=dict(color="#e0e0e0")),
        margin=dict(l=60, r=40, t=50, b=50),
        height=260,
        shapes=[
            dict(
                type="line",
                x0=0, x1=1, xref="paper",
                y0=0.3, y1=0.3,
                line=dict(color="#c94040", dash="dash", width=1),
            )
        ],
        annotations=[
            dict(
                x=1, y=0.3, xref="paper", yref="y",
                text="spike threshold (0.30)",
                showarrow=False,
                font=dict(color="#c94040", size=10),
                xanchor="right",
            )
        ],
    )
    return fig


def render_causal_graph(report: CausalIncidentReport, event_log_path: Path) -> None:
    """Render the causal analysis panel.

    Shows:
    * Run metadata and outcome summary.
    * Epistemic divergence chart (per-agent divergence over turns).
    * Interactive DAG (pyvis) showing divergence-spike → decision → outcome chains.
    * Root cause explanation and recommendations.
    * Scrollable event timeline.
    """
    # ── Header ──────────────────────────────────────────────────────────
    outcome_icon = "🏆" if report.termination_reason == "win" else "💀"
    reason_label = {
        "win": "WIN — both agents reached the exit",
        "turn_limit": "TURN LIMIT — agents ran out of turns",
        "stuck": "STUCK — agents stopped making progress",
    }.get(report.termination_reason, report.termination_reason)

    st.markdown(
        f"<p style='color:#888;font-size:12px'>"
        f"{outcome_icon} Run <code>{report.run_id}</code> · "
        f"Turn {report.final_turn} · <strong style='color:#e0e0e0'>{reason_label}</strong>"
        f"</p>",
        unsafe_allow_html=True,
    )

    # ── Summary ─────────────────────────────────────────────────────────
    st.info(report.summary)

    # ── Divergence chart ─────────────────────────────────────────────────
    st.plotly_chart(_divergence_chart(event_log_path), use_container_width=True, key="causal_div_chart")

    # ── DAG ─────────────────────────────────────────────────────────────
    st.subheader("Causal Chain Graph")
    dag = _build_dag(report, event_log_path)

    html_str = dag.generate_html()
    components.html(html_str, height=480, scrolling=False)

    # Legend
    st.markdown(
        "<div style='color:#e0e0e0;font-size:12px'>"
        "<span style='color:#c94040'>■</span> Divergence spike &nbsp;"
        "<span style='color:#e2b714'>■</span> Decision &nbsp;"
        "<span style='color:#4fc3f7'>■</span> Outcome &nbsp;"
        "<span style='color:#9c27b0'>■</span> Termination"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Root cause + recommendations ─────────────────────────────────────
    col_exp, col_rec = st.columns(2)
    with col_exp:
        with st.expander("Root cause explanation", expanded=True):
            st.markdown(
                f"<p style='color:#e0e0e0;font-size:0.93rem'>{report.root_cause_explanation}</p>",
                unsafe_allow_html=True,
            )
    with col_rec:
        with st.expander("Recommendations", expanded=True):
            for i, rec in enumerate(report.recommendations, 1):
                st.markdown(
                    f"<p style='color:#b8e0b8;font-size:0.93rem'>{i}. {rec}</p>",
                    unsafe_allow_html=True,
                )

    # ── Event timeline ───────────────────────────────────────────────────
    with st.expander(f"Full event timeline ({len(report.timeline)} events)"):
        timeline_text = "\n".join(report.timeline)
        st.code(timeline_text, language=None)
