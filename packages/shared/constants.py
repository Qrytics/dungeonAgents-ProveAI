from pathlib import Path

GRID_MIN_SIZE: int = 8

TURN_LIMIT: int = 100

FOG_RADIUS: int = 1

COMM_LAG_TURNS: int = 1

# Relative to the project root; callers must run from the repository root.
RUNS_DIR: Path = Path("runs/")

TRACES_DIR: Path = Path("traces/")

LANGFUSE_PROJECT: str = "dungeonAgents-ProveAI"
