import type { CellType } from "./types";

export const CELL_COLORS: Record<CellType, string> = {
  wall: "#16213e",
  floor: "#0f3460",
  key: "#e2b714",
  locked_door: "#c94040",
  exit: "#4fc3f7",
};

export const AGENT_COLORS: Record<string, string> = {
  agent_a: "#9c27b0",
  agent_b: "#00b894",
};

export const UNKNOWN_AGENT_COLOR = "#6c5ce7";
