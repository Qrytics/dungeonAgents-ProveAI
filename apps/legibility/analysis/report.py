from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from apps.legibility.analysis.divergence import (
    compute_divergence_timeseries,
    find_divergence_spikes,
)
from apps.simulation.schemas import AnyEvent, IntentionEvent, MessageEvent, OutcomeEvent, TerminationEvent
from packages.shared.types import AgentID, RunID, TerminationReason, TurnNumber

_event_adapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)

# Lower temperature for more deterministic, fact-grounded report generation.
_LLM_TEMPERATURE = 0.2


class CausalIncidentReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: RunID
    termination_reason: TerminationReason
    final_turn: TurnNumber

    summary: str                                          # 2-3 sentence plain English summary
    timeline: list[str]                                   # Chronological list of key events
    root_cause_turns: dict[AgentID, list[TurnNumber]]     # Divergence spike turns per agent
    root_cause_explanation: str                           # Plain English explanation of root cause
    recommendations: list[str]                            # Actionable suggestions for next run


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_timeline(event_log_path: Path) -> list[str]:
    """Replay the event log and return a chronological list of human-readable event strings."""
    entries: list[str] = []
    with event_log_path.open() as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            event = _event_adapter.validate_json(raw_line)
            if isinstance(event, IntentionEvent):
                entries.append(
                    f"Turn {event.turn} | {event.agent_id} intends to {event.tool_name}"
                )
            elif isinstance(event, OutcomeEvent):
                status = "succeeded" if event.success else "failed"
                entries.append(
                    f"Turn {event.turn} | {event.agent_id} {event.tool_name} {status}: {event.result_description}"
                )
            elif isinstance(event, MessageEvent):
                entries.append(
                    f"Turn {event.turn_sent} | {event.sender} → {event.recipient}: \"{event.content}\""
                )
            elif isinstance(event, TerminationEvent):
                entries.append(
                    f"Turn {event.final_turn} | TERMINATION — reason={event.reason}, win={event.winner}"
                )
    return entries


def _call_llm(prompt: str) -> str:
    """Call the configured LLM and return the text response.

    Supports OpenAI models (e.g. gpt-4o-mini) and Google Gemini models
    (e.g. gemini-2.0-flash) via Gemini's OpenAI-compatible endpoint.
    The model is selected by the AGENT_LLM_MODEL environment variable.
    """
    try:
        from openai import OpenAI  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("openai package is required for generate_report()") from exc

    model = os.environ.get("AGENT_LLM_MODEL", "gpt-4o-mini")

    if model.startswith("gemini"):
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY environment variable is not set. "
                "Set it before calling generate_report() with a Gemini model."
            )
        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY environment variable is not set. "
                "Set it before calling generate_report()."
            )
        client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=_LLM_TEMPERATURE,
    )
    return response.choices[0].message.content or ""


def _generate_natural_language(
    termination_event: TerminationEvent,
    timeline: list[str],
    root_cause_turns: dict[AgentID, list[TurnNumber]],
) -> tuple[str, str, list[str]]:
    """Use the LLM to produce summary, root_cause_explanation, and recommendations."""
    timeline_text = "\n".join(timeline) if timeline else "(no events recorded)"
    spike_lines = []
    for agent_id, turns in root_cause_turns.items():
        if turns:
            spike_lines.append(f"  {agent_id}: turns {turns}")
    spikes_text = "\n".join(spike_lines) if spike_lines else "  (no divergence spikes detected)"

    prompt = (
        "You are an AI assistant analyzing a failed dungeon simulation run.\n\n"
        f"Run ID: {termination_event.run_id}\n"
        f"Termination reason: {termination_event.reason}\n"
        f"Final turn: {termination_event.final_turn}\n\n"
        "=== Event Timeline ===\n"
        f"{timeline_text}\n\n"
        "=== Epistemic Divergence Spike Turns (turns where agent beliefs were most wrong) ===\n"
        f"{spikes_text}\n\n"
        "Answer the following three questions. Format your response as JSON with exactly "
        "these keys: \"summary\", \"root_cause_explanation\", \"recommendations\".\n"
        "- \"summary\": A 2-3 sentence plain English description of what happened in this run.\n"
        "- \"root_cause_explanation\": A plain English explanation of why the run failed, "
        "referencing the divergence spike turns if relevant.\n"
        "- \"recommendations\": A JSON array of 2-4 short actionable suggestions for improving "
        "performance in the next run.\n"
        "Return only the JSON object, no markdown fences."
    )

    raw = _call_llm(prompt)

    # Attempt to parse JSON; fall back to sensible defaults if LLM output is malformed.
    try:
        parsed = json.loads(raw)
        summary: str = str(parsed.get("summary", "")).strip()
        explanation: str = str(parsed.get("root_cause_explanation", "")).strip()
        recs_raw = parsed.get("recommendations", [])
        recommendations: list[str] = [str(r).strip() for r in recs_raw if str(r).strip()]
    except (json.JSONDecodeError, AttributeError, TypeError):
        summary = raw.strip()
        explanation = f"Termination reason: {termination_event.reason}."
        recommendations = ["Review agent coordination and belief-state accuracy."]

    if not summary:
        summary = (
            f"The simulation ended on turn {termination_event.final_turn} "
            f"due to '{termination_event.reason}'. "
            "Agents did not reach the exit before the run was terminated."
        )
    if not explanation:
        explanation = (
            f"The run was terminated because of: {termination_event.reason}. "
            "Review the divergence spike turns for details on where agent beliefs diverged most."
        )
    if not recommendations:
        recommendations = ["Review agent coordination and belief-state accuracy."]

    return summary, explanation, recommendations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(
    event_log_path: Path,
    termination_event: TerminationEvent,
) -> CausalIncidentReport:
    """Generate a structured Causal Incident Report for a failed simulation run.

    Steps:
    1. Replay the event log to build a human-readable timeline.
    2. Compute per-agent divergence timeseries (M-14).
    3. Identify root-cause turns via divergence spikes.
    4. Call the configured LLM to produce natural-language narrative sections.
    5. Return a frozen CausalIncidentReport.
    """
    timeline = _build_timeline(event_log_path)

    timeseries = compute_divergence_timeseries(event_log_path)
    root_cause_turns: dict[AgentID, list[TurnNumber]] = find_divergence_spikes(timeseries)

    summary, root_cause_explanation, recommendations = _generate_natural_language(
        termination_event=termination_event,
        timeline=timeline,
        root_cause_turns=root_cause_turns,
    )

    return CausalIncidentReport(
        run_id=termination_event.run_id,
        termination_reason=termination_event.reason,
        final_turn=termination_event.final_turn,
        summary=summary,
        timeline=timeline,
        root_cause_turns=root_cause_turns,
        root_cause_explanation=root_cause_explanation,
        recommendations=recommendations,
    )


def generate_report_no_llm(
    event_log_path: Path,
    termination_event: TerminationEvent,
) -> CausalIncidentReport:
    """Generate a Causal Incident Report using only computed data (no LLM call).

    Produces a structurally complete report with auto-generated narrative text
    derived directly from the event log and divergence analysis — useful when
    no API key is available or when a fast, offline analysis is preferred.

    Parameters
    ----------
    event_log_path:
        Path to the ``.jsonl`` run file.
    termination_event:
        The parsed ``TerminationEvent`` from the run.

    Returns
    -------
    CausalIncidentReport
        A fully populated report (no LLM required).
    """
    timeline = _build_timeline(event_log_path)
    timeseries = compute_divergence_timeseries(event_log_path)
    root_cause_turns: dict[AgentID, list[TurnNumber]] = find_divergence_spikes(timeseries)

    reason = termination_event.reason
    final_turn = int(termination_event.final_turn)

    # Auto-compose a summary based on reason
    if reason == "win":
        summary = (
            f"Both agents successfully reached the exit at turn {final_turn}. "
            "Agent A retrieved the key and unlocked the door; Agent B secured the exit. "
            "All mission objectives were completed with no critical divergence detected."
        )
        explanation = (
            "The simulation ended in a WIN. No significant epistemic divergence spikes "
            "were detected — agents maintained accurate world models throughout the run. "
            "Effective communication between agents enabled coordinated task completion."
        )
        recommendations = [
            "Reduce turn count by optimising initial exploration (agents explored redundant areas).",
            "Consider giving agents pre-shared knowledge of the dungeon layout to skip early fog-of-war exploration.",
            "Evaluate whether one agent could retrieve the key and reach the exit independently in fewer turns.",
        ]
    elif reason == "turn_limit":
        spike_agents = [a for a, turns in root_cause_turns.items() if turns]
        spike_summary = (
            f"Divergence spikes detected for: {', '.join(spike_agents)}."
            if spike_agents else "No significant divergence spikes detected."
        )
        summary = (
            f"The simulation reached the turn limit ({final_turn} turns) without agents winning. "
            f"{spike_summary} Agents failed to complete the key–door–exit sequence in time."
        )
        explanation = (
            "Agents hit the turn limit. "
            + (f"Divergence spikes for {spike_agents} indicate belief-reality gaps that may have caused suboptimal decisions. "
               if spike_agents else "")
            + "Review agent pathfinding and coordination efficiency."
        )
        recommendations = [
            "Add explicit goal-oriented pathfinding to prevent aimless exploration.",
            "Improve inter-agent communication frequency to share key/exit locations earlier.",
            "Review divergence spike turns to identify where beliefs diverged from reality.",
        ]
    else:
        # stuck
        summary = (
            f"The simulation terminated at turn {final_turn} because both agents became stuck — "
            "no successful action was recorded for 10 consecutive turns."
        )
        explanation = (
            "Both agents stopped making progress. This is often caused by wall-bumping loops "
            "or communication failures that prevented agents from discovering new paths."
        )
        recommendations = [
            "Add stuck-detection to agent reasoning so they actively try alternative directions.",
            "Increase communication frequency to break coordination deadlocks.",
            "Consider sharing partial map data between agents to reveal blocked corridors sooner.",
        ]

    return CausalIncidentReport(
        run_id=termination_event.run_id,
        termination_reason=termination_event.reason,
        final_turn=termination_event.final_turn,
        summary=summary,
        timeline=timeline,
        root_cause_turns=root_cause_turns,
        root_cause_explanation=explanation,
        recommendations=recommendations,
    )

