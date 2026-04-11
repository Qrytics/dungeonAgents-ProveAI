import type { ReplayFrame, WorldState } from "./types";

function isCell(candidate: unknown): boolean {
  if (!candidate || typeof candidate !== "object") {
    return false;
  }
  const c = candidate as Record<string, unknown>;
  return (
    typeof c.row === "number" &&
    typeof c.col === "number" &&
    typeof c.cell_type === "string" &&
    Array.isArray(c.is_visible_to)
  );
}

function isWorldState(candidate: unknown): candidate is WorldState {
  if (!candidate || typeof candidate !== "object") {
    return false;
  }
  const state = candidate as Record<string, unknown>;
  return (
    typeof state.run_id === "string" &&
    typeof state.turn === "number" &&
    Array.isArray(state.grid) &&
    state.grid.every((row) => Array.isArray(row) && row.every(isCell)) &&
    !!state.agent_positions &&
    typeof state.agent_positions === "object" &&
    typeof state.door_unlocked === "boolean"
  );
}

export function parseRunJsonl(raw: string): {
  frames: ReplayFrame[];
  ignoredLines: number;
} {
  const frames: ReplayFrame[] = [];
  let ignoredLines = 0;
  const lines = raw.split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      ignoredLines += 1;
      continue;
    }

    if (!parsed || typeof parsed !== "object") {
      ignoredLines += 1;
      continue;
    }

    const event = parsed as Record<string, unknown>;
    if (event.event_type !== "outcome" || !isWorldState(event.world_state_after)) {
      continue;
    }

    frames.push({
      frameIndex: frames.length,
      turn: typeof event.turn === "number" ? event.turn : event.world_state_after.turn,
      agentId: typeof event.agent_id === "string" ? event.agent_id : "unknown_agent",
      toolName: typeof event.tool_name === "string" ? event.tool_name : "unknown_tool",
      resultDescription:
        typeof event.result_description === "string"
          ? event.result_description
          : "No description.",
      worldState: event.world_state_after,
    });
  }

  return { frames, ignoredLines };
}
