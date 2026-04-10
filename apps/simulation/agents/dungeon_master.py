"""M-10 — LLM Agents: Dungeon Master Agent.

The :class:`DungeonMasterAgent` is a third LLM agent that observes the full
simulation but acts on state that is **2 turns stale**.  It narrates and
annotates the game state via LLM calls, logging output to Langfuse as trace
metadata.  The DM has no fog of war — it sees the complete grid — but it
cannot modify authoritative game state unless explicitly granted orchestrator
write permission.
"""

from __future__ import annotations

import logging
import time

from langchain_core.language_models.chat_models import BaseChatModel
from langfuse import Langfuse

logger = logging.getLogger(__name__)

from apps.simulation.agents.llm_factory import build_llm, get_model_identifier
from apps.simulation.environment.orchestrator import EnvironmentOrchestrator
from apps.simulation.schemas.state import WorldState
from packages.shared.types import CellType, RunID, TurnNumber

# Number of turns the DM lags behind the current turn.
DM_STALENESS: int = 2

# Symbol map for full-grid rendering (DM sees every cell type).
_CELL_SYMBOLS: dict[CellType, str] = {
    "floor": ".",
    "wall": "#",
    "key": "K",
    "locked_door": "D",
    "exit": "E",
    "agent": "@",
}


class DungeonMasterAgent:
    """LLM-powered Dungeon Master that narrates the dungeon simulation.

    The DM receives the authoritative world state from exactly
    :data:`DM_STALENESS` turns ago (enforced by the caller / game loop),
    calls an LLM to produce a brief narrative annotation, and logs that
    annotation to Langfuse as trace metadata.

    The DM **never** writes to the authoritative game state through the
    orchestrator — it holds a reference to the orchestrator only so that
    future stretch-goal injection (e.g. spawning hazards with explicit
    permission) can be added without changing the constructor signature.

    Parameters
    ----------
    orchestrator:
        The :class:`~apps.simulation.environment.orchestrator.EnvironmentOrchestrator`
        for this run.  The DM holds this reference but does not write to it
        unless explicitly granted permission (see class docstring).
    run_id:
        Unique identifier for the current simulation run, used as the
        Langfuse session identifier.
    langfuse_client:
        Initialised :class:`~langfuse.Langfuse` client.  Typically obtained
        from :func:`~packages.observability.tracer.init_tracer`.
    llm_model:
        OpenAI model name to use for narration (default: ``gpt-4o-mini``).
    """

    def __init__(
        self,
        orchestrator: EnvironmentOrchestrator,
        run_id: RunID,
        langfuse_client: Langfuse,
        llm_model: str = "gpt-4o-mini",
        llm: BaseChatModel | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._run_id = run_id
        self._langfuse = langfuse_client
        self._llm = llm if llm is not None else build_llm(llm_model, temperature=0.7)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def act(self, stale_world_state: WorldState, turn: TurnNumber) -> str | None:
        """Generate a narrative annotation from a stale world state.

        The caller **must** pass a world state from exactly ``turn - 2``
        turns ago.  This constraint is not re-validated here because the
        game loop (M-11) is the single source of truth for turn ordering.

        The annotation is logged to Langfuse as trace metadata and is
        **never** applied to the authoritative game state.

        Parameters
        ----------
        stale_world_state:
            The world state from exactly ``turn - 2`` turns ago.
        turn:
            The current game turn number.

        Returns
        -------
        str | None
            The LLM-generated narrative annotation, or ``None`` if the LLM
            call fails (errors are swallowed so the game loop is not
            interrupted).
        """
        prompt = self._build_prompt(stale_world_state, turn)
        start = time.monotonic()
        try:
            response = self._llm.invoke(prompt)
            latency_ms = (time.monotonic() - start) * 1000.0
            annotation: str = str(response.content)
            usage = response.usage_metadata or {}
            prompt_tokens: int = usage.get("input_tokens", 0)
            completion_tokens: int = usage.get("output_tokens", 0)
        except Exception:  # noqa: BLE001 — never crash the game loop
            logger.exception(
                "DungeonMasterAgent LLM call failed on turn %d (stale turn %d); "
                "annotation suppressed.",
                int(turn),
                int(stale_world_state.turn),
            )
            return None

        self._log_to_langfuse(
            annotation=annotation,
            stale_turn=stale_world_state.turn,
            current_turn=turn,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )

        return annotation

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, stale_state: WorldState, current_turn: TurnNumber) -> str:
        """Construct the DM prompt with the full grid and stale-state annotation."""
        grid_ascii = self._render_grid(stale_state)
        stale_turn = stale_state.turn

        agent_lines: list[str] = [
            f"  {agent_id}: row={pos[0]}, col={pos[1]}"
            for agent_id, pos in sorted(stale_state.agent_positions.items())
        ]
        agent_positions_str = "\n".join(agent_lines) if agent_lines else "  (none)"

        key_status = (
            f"held by {stale_state.key_held_by}"
            if stale_state.key_held_by
            else "on the floor"
        )

        return (
            "You are the Dungeon Master narrating a dungeon escape simulation.\n"
            "You observe the full grid — no fog of war — but the state below is STALE.\n\n"
            f"IMPORTANT: This is the world as it was {DM_STALENESS} turns ago "
            f"(turn {stale_turn}). The current turn is {current_turn}.\n\n"
            "Grid layout (# wall, . floor, K key, D locked door, E exit, @ agent):\n"
            f"{grid_ascii}\n\n"
            f"Agent positions (turn {stale_turn}):\n{agent_positions_str}\n\n"
            f"Key: {key_status}\n"
            f"Door unlocked: {'Yes' if stale_state.door_unlocked else 'No'}\n\n"
            "Write a brief, vivid 1–2 sentence narrative annotation of this scene. "
            "Do NOT issue any game commands. Narrate only."
        )

    @staticmethod
    def _render_grid(state: WorldState) -> str:
        """Render the full grid as an ASCII map — the DM sees everything."""
        rows: list[str] = []
        for grid_row in state.grid:
            rows.append("".join(_CELL_SYMBOLS.get(cell.cell_type, "?") for cell in grid_row))
        return "\n".join(rows)

    def _log_to_langfuse(
        self,
        annotation: str,
        stale_turn: TurnNumber,
        current_turn: TurnNumber,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
    ) -> None:
        """Log a DM annotation to Langfuse as trace metadata."""
        with self._langfuse.start_as_current_observation(
            name="dungeon_master_annotation",
            as_type="span",
            metadata={
                "run_id": self._run_id,
                "session_id": self._run_id,
                "current_turn": int(current_turn),
                "stale_turn": int(stale_turn),
                "staleness_turns": DM_STALENESS,
            },
        ):
            with self._langfuse.start_as_current_observation(
                name="dm_narration",
                as_type="generation",
                model=get_model_identifier(self._llm),
                input=f"DM narration request: current_turn={current_turn}, stale_turn={stale_turn}",
                output=annotation,
                usage_details={
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total": prompt_tokens + completion_tokens,
                },
                metadata={
                    "latency_ms": latency_ms,
                    "agent_id": "dungeon_master",
                },
            ):
                pass
