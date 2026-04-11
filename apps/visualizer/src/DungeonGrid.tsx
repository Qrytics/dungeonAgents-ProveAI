import { AGENT_COLORS, CELL_COLORS, UNKNOWN_AGENT_COLOR } from "./cellColors";
import type { ReplayFrame } from "./types";

interface DungeonGridProps {
  frame: ReplayFrame;
}

function toAgentLabel(agentId: string): string {
  if (agentId === "agent_a") return "A";
  if (agentId === "agent_b") return "B";
  return "?";
}

export function DungeonGrid({ frame }: DungeonGridProps): JSX.Element {
  const world = frame.worldState;
  const rows = world.grid.length;
  const cols = rows > 0 ? world.grid[0].length : 0;

  const agentAt = new Map<string, string>();
  for (const [agentId, [row, col]] of Object.entries(world.agent_positions)) {
    agentAt.set(`${row}:${col}`, agentId);
  }

  return (
    <section className="grid-panel">
      <div className="grid-header">
        <h2>Dungeon Grid</h2>
        <span>
          {rows}x{cols}
        </span>
      </div>

      <div
        className="dungeon-grid"
        style={{
          gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
        }}
      >
        {world.grid.flatMap((row) =>
          row.map((cell) => {
            const key = `${cell.row}-${cell.col}`;
            const agentId = agentAt.get(`${cell.row}:${cell.col}`);
            const hasAgent = !!agentId;
            return (
              <div
                key={key}
                className="grid-cell"
                title={`(${cell.row}, ${cell.col}) ${cell.cell_type}`}
                style={{
                  backgroundColor: CELL_COLORS[cell.cell_type],
                }}
              >
                {hasAgent && (
                  <div
                    className="agent-token"
                    style={{
                      backgroundColor: AGENT_COLORS[agentId] ?? UNKNOWN_AGENT_COLOR,
                    }}
                  >
                    {toAgentLabel(agentId)}
                  </div>
                )}
              </div>
            );
          }),
        )}
      </div>
    </section>
  );
}
