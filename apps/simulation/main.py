"""M-12 — Simulation Entry Point.

CLI entry point for launching a dungeon simulation run.  Parses arguments,
initialises all components via :class:`~apps.simulation.game_loop.loop.GameLoop`,
executes the game loop, and reports final results to stdout.

Usage
-----
::

    python -m apps.simulation.main [OPTIONS]

Options
-------
--rows INT
    Grid rows (default: 8, min: 8).
--cols INT
    Grid columns (default: 8, min: 8).
--seed INT
    Random seed for reproducible layout.
--model TEXT
    LLM model name (default: gpt-4o-mini).
--runs-dir PATH
    Output directory for event logs (default: runs/).
--verbose
    Print turn-by-turn narration to stdout.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()
from pathlib import Path

from apps.simulation.game_loop.loop import GameConfig, GameLoop
from packages.shared.constants import GRID_MIN_SIZE, RUNS_DIR
from packages.shared.types import RunID


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apps.simulation.main",
        description="Run a dungeon simulation.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=8,
        metavar="INT",
        help=f"Grid rows (default: 8, min: {GRID_MIN_SIZE})",
    )
    parser.add_argument(
        "--cols",
        type=int,
        default=8,
        metavar="INT",
        help=f"Grid columns (default: 8, min: {GRID_MIN_SIZE})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="INT",
        help="Random seed for reproducible layout",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("AGENT_LLM_MODEL", "gpt-4o-mini"),
        metavar="TEXT",
        help="LLM model name (default: gpt-4o-mini, or AGENT_LLM_MODEL env var)",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=RUNS_DIR,
        metavar="PATH",
        help="Output directory for event logs (default: runs/)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print turn-by-turn narration to stdout",
    )
    return parser


_REASON_LABELS: dict[str, str] = {
    "win": "WIN",
    "turn_limit": "TURN_LIMIT",
    "stuck": "STUCK",
}


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the simulation, and print results.

    Parameters
    ----------
    argv:
        Argument list (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Exit code: 0 on success.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Validate minimums.
    if args.rows < GRID_MIN_SIZE:
        parser.error(f"--rows must be >= {GRID_MIN_SIZE} (got {args.rows})")
    if args.cols < GRID_MIN_SIZE:
        parser.error(f"--cols must be >= {GRID_MIN_SIZE} (got {args.cols})")

    # Configure logging: always WARNING for third-party noise; verbose output
    # is handled separately via GameConfig.verbose / print().
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    # Ensure the runs directory exists.
    runs_dir: Path = args.runs_dir
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_id = RunID(str(uuid.uuid4()))

    config = GameConfig(
        run_id=run_id,
        grid_rows=args.rows,
        grid_cols=args.cols,
        seed=args.seed,
        llm_model=args.model,
        event_log_dir=runs_dir,
        verbose=args.verbose,
    )

    loop = GameLoop(config)
    termination = loop.run()

    result_label = _REASON_LABELS.get(termination.reason, termination.reason.upper())
    event_log_path = runs_dir / f"{run_id}.jsonl"

    print(f"Run ID: {run_id}")
    print(f"Result: {result_label}")
    print(f"Turns: {int(termination.final_turn)}")
    print(f"Event log: {event_log_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
