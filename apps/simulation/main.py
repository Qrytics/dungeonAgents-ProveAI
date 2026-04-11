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
--live-viz
    Serve the run log over HTTP on 127.0.0.1 (see --live-viz-port) for the React live dashboard.
--live-viz-port INT
    Port for the live-viz helper (default: 8765).
--live-viz-open
    Open the browser on the live visualizer URL (implies --live-viz).
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
    parser.add_argument(
        "--live-viz",
        action="store_true",
        default=False,
        help=(
            "Start a local HTTP helper on 127.0.0.1 (see --live-viz-port) so the "
            "React visualizer can poll this run as the log grows. "
            "Start the UI first: cd apps/visualizer && npm run dev"
        ),
    )
    parser.add_argument(
        "--live-viz-port",
        type=int,
        default=8765,
        metavar="INT",
        help="Port for --live-viz (default: 8765)",
    )
    parser.add_argument(
        "--live-viz-open",
        action="store_true",
        default=False,
        help="Try to open the default browser on the live visualizer URL (implies --live-viz)",
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

    live_viz = args.live_viz or args.live_viz_open
    if live_viz:
        from apps.simulation.live_viz_server import start_live_viz_server

        start_live_viz_server(runs_dir, port=int(args.live_viz_port))
        viz_base = os.environ.get("LIVE_VIZ_URL", "http://localhost:5173")
        live_url = f"{viz_base.rstrip('/')}/?run={run_id}&live=1"
        print("")
        print("Live React visualizer (polls this run as it progresses):")
        print(f"  {live_url}")
        print(
            f"  API: http://127.0.0.1:{args.live_viz_port}/api/runs/<run_id>/raw "
            "(proxied as /api when using Vite dev server)"
        )
        print("  Ensure the visualizer is running: cd apps/visualizer && npm run dev")
        print("")
        if args.live_viz_open:
            import webbrowser

            webbrowser.open(live_url, new=1)

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
