from __future__ import annotations

from pathlib import Path

import streamlit as st
from pydantic import TypeAdapter

from apps.legibility.analysis.report import CausalIncidentReport, generate_report, generate_report_no_llm
from apps.legibility.views.causal_graph import render_causal_graph
from apps.legibility.views.heatmaps import render_heatmaps
from apps.legibility.views.replay import render_replay
from apps.legibility.views.timeline import render_timeline
from apps.simulation.schemas import AnyEvent, TerminationEvent
from packages.shared.types import AgentID

_RUNS_DIR = Path("runs")
_event_adapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="dungeonAgents — Legibility Dashboard",
    page_icon="🏰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Dark custom CSS to reinforce the dungeon aesthetic
st.markdown(
    """
    <style>
        body, .stApp { background-color: #0d0d1a; color: #e0e0e0; }
        .stSidebar { background-color: #1a1a2e; }
        footer { color: #666; font-size: 11px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _list_runs() -> list[Path]:
    """Return all .jsonl files in the runs/ directory, sorted by name."""
    if not _RUNS_DIR.exists():
        return []
    return sorted(_RUNS_DIR.glob("*.jsonl"))


@st.cache_data(show_spinner="Generating causal incident report…")
def _load_report(event_log_path_str: str) -> CausalIncidentReport | None:
    """Load the TerminationEvent and generate a CausalIncidentReport (cached).

    First attempts to generate an LLM-powered narrative report.  If that fails
    (e.g. no API key), falls back to a purely structural report computed from
    the event log and divergence analysis — no LLM required.
    """
    event_log_path = Path(event_log_path_str)
    termination: TerminationEvent | None = None
    try:
        with event_log_path.open() as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                event = _event_adapter.validate_json(raw_line)
                if isinstance(event, TerminationEvent):
                    termination = event
    except OSError:
        return None

    if termination is None:
        return None

    # Try the LLM-powered report first; fall back to the no-LLM version.
    try:
        return generate_report(event_log_path, termination)
    except Exception:  # noqa: BLE001
        pass

    try:
        return generate_report_no_llm(event_log_path, termination)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not generate causal report: {exc}")
        return None


def _load_termination_only(event_log_path: Path) -> TerminationEvent | None:
    """Return the TerminationEvent from the event log without calling the LLM."""
    try:
        with event_log_path.open() as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                event = _event_adapter.validate_json(raw_line)
                if isinstance(event, TerminationEvent):
                    return event
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🏰 dungeonAgents")
    st.caption("Legibility Dashboard")
    st.divider()

    runs = _list_runs()

    if st.button("🔄 Refresh runs", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    if not runs:
        st.info("No runs found in `runs/`.")
        selected_path: Path | None = None
    else:
        run_names = [p.name for p in runs]
        # Default to the demo run if it exists
        _demo_name = "demo_30turn_run.jsonl"
        default_idx = run_names.index(_demo_name) if _demo_name in run_names else 0
        selected_name: str = st.selectbox(
            "Select a run:",
            options=run_names,
            index=default_idx,
            key="run_selector",
        )
        selected_path = _RUNS_DIR / selected_name
        if selected_name == _demo_name:
            st.success("🎮 30-turn demo run loaded")

    st.divider()
    st.caption("Launch: `streamlit run apps/legibility/app.py`")
    st.caption("Generate demo: `python scripts/generate_demo_run.py`")


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("🏰 Legibility Dashboard")

if selected_path is None:
    st.info("No runs found in the `runs/` directory. Run a simulation first, then refresh.")
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(
    ["🔁 Replay", "🔗 Causal Graph", "📊 Timeline", "🌡 Heatmaps"]
)

with tab1:
    render_replay(selected_path, selected_turn=1)

with tab2:
    report = _load_report(str(selected_path))
    if report is None:
        st.warning(
            "Could not generate a causal incident report for this run. "
            "Ensure the event log contains a TerminationEvent."
        )
    else:
        render_causal_graph(report, selected_path)

with tab3:
    render_timeline(selected_path)

with tab4:
    default_agent: AgentID = "agent_a"
    render_heatmaps(selected_path, selected_agent=default_agent, selected_turn=1)


# ---------------------------------------------------------------------------
# Footer — run metadata
# ---------------------------------------------------------------------------

termination = _load_termination_only(selected_path)

st.divider()
if termination is not None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Run ID", termination.run_id)
    col2.metric("Termination reason", termination.reason)
    col3.metric("Final turn", int(termination.final_turn))
else:
    st.caption(f"Run: `{selected_path.name}` — no termination event found yet.")
