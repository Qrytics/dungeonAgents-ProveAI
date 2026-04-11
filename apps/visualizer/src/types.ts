export type CellType = "wall" | "floor" | "key" | "locked_door" | "exit";

export type Position = [number, number];

export interface CellState {
  row: number;
  col: number;
  cell_type: CellType;
  is_visible_to: string[];
}

export interface WorldState {
  run_id: string;
  turn: number;
  grid: CellState[][];
  agent_positions: Record<string, Position>;
  key_held_by: string | null;
  door_unlocked: boolean;
}

export interface ReplayFrame {
  frameIndex: number;
  turn: number;
  agentId: string;
  toolName: string;
  resultDescription: string;
  worldState: WorldState;
}
