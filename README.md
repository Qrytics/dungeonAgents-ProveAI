# dungeonAgents-ProveAI

> Two LLM-powered agents navigate an 8×8 dungeon. The goal isn't to win — it's to **prove** what happened and why. Every decision is traced, every epistemic gap is measured, and every failure is made legible to a human diagnoser.

---

## What Is This Project?

**dungeonAgents-ProveAI** is a multi-agent simulation built to explore observability and explainability in agentic AI systems. Two agents operate inside a dungeon grid, subject to fog-of-war and communication lag, while a full observability stack captures every tool call, LLM input/output, and state transition.

The primary deliverable is **not** agent intelligence — it is the quality of traces and the legibility of the diagnostic output. A human reviewer should be able to look at any failed run and answer:

1. **What happened?**
2. **Why did it happen?**
3. **What should change next time?**

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12+ |
| Agent Framework | LangGraph |
| LLM Providers | OpenAI (gpt-4o-mini, gpt-4o) **and** Google Gemini (gemini-2.0-flash, gemini-1.5-pro) |
| Observability | Langfuse + OpenTelemetry (OTel) |
| State & Validation | Pydantic V2 |
| Legibility UI | Streamlit |
| Event Storage | Immutable `.jsonl` flat files |

---

## Prerequisites

- **Python 3.12 or higher** — verify with `python --version`
- **pip** — comes bundled with Python
- An API key for at least one LLM provider:
  - **Google Gemini** (recommended): get a free key at https://aistudio.google.com/app/apikey
  - **OpenAI**: get a key at https://platform.openai.com/api-keys
- (Optional) **Langfuse** account for trace storage: https://cloud.langfuse.com

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Qrytics/dungeonAgents-ProveAI.git
cd dungeonAgents-ProveAI
```

### 2. Create and activate a virtual environment

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -e .
```

> This installs the project in editable mode along with all runtime dependencies
> including `langchain-google-genai` (Gemini) and `langchain-openai`.

### 4. Configure environment variables

Copy the example file and fill in your keys:

```bash
cp .env.example .env
```

Then open `.env` and set the values.  You only need the key for the provider you intend to use.

**Minimal setup for Gemini (recommended):**
```
GOOGLE_API_KEY=your_google_api_key_here
AGENT_LLM_MODEL=gemini-2.0-flash

LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com
```

**Minimal setup for OpenAI:**
```
OPENAI_API_KEY=your_openai_key_here
AGENT_LLM_MODEL=gpt-4o-mini

LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com
```

#### Setting variables without a `.env` file (PowerShell)

If you prefer to set variables directly in your shell session:

```powershell
$env:GOOGLE_API_KEY = "your_google_api_key_here"
$env:AGENT_LLM_MODEL = "gemini-2.0-flash"
$env:LANGFUSE_PUBLIC_KEY = "your_langfuse_public_key"
$env:LANGFUSE_SECRET_KEY = "your_langfuse_secret_key"
$env:LANGFUSE_HOST = "https://cloud.langfuse.com"
```

**macOS / Linux (Bash):**
```bash
export GOOGLE_API_KEY="your_google_api_key_here"
export AGENT_LLM_MODEL="gemini-2.0-flash"
export LANGFUSE_PUBLIC_KEY="your_langfuse_public_key"
export LANGFUSE_SECRET_KEY="your_langfuse_secret_key"
export LANGFUSE_HOST="https://cloud.langfuse.com"
```

#### LLM provider selection

The project auto-selects the right LangChain integration based on the model name set in `AGENT_LLM_MODEL`:

| `AGENT_LLM_MODEL` value | Provider used | Key needed |
|---|---|---|
| `gemini-2.0-flash` | Google Gemini | `GOOGLE_API_KEY` |
| `gemini-1.5-pro` | Google Gemini | `GOOGLE_API_KEY` |
| `gpt-4o-mini` | OpenAI | `OPENAI_API_KEY` |
| `gpt-4o` | OpenAI | `OPENAI_API_KEY` |

Any model name starting with `gemini-` routes to Gemini; everything else routes to OpenAI.

---

## Running the Simulation

The simulation is launched from the repository root using the Python module runner.

### Basic run (default 8×8 grid, uses `AGENT_LLM_MODEL` from env)

```bash
python -m apps.simulation.main
```

### Verbose output (prints turn-by-turn narration)

```bash
python -m apps.simulation.main --verbose
```

### Reproducible run with a fixed seed

```bash
python -m apps.simulation.main --seed 42
```

### Larger grid

```bash
python -m apps.simulation.main --rows 12 --cols 12
```

### Specify a model on the command line

```bash
python -m apps.simulation.main --model gemini-2.0-flash
```

> `--model` overrides the `AGENT_LLM_MODEL` environment variable for that single run.

### All CLI options

```
usage: python -m apps.simulation.main [OPTIONS]

Options:
  --rows INT      Grid rows (default: 8, min: 8)
  --cols INT      Grid columns (default: 8, min: 8)
  --seed INT      Random seed for reproducible layout
  --model TEXT    LLM model name (default: reads AGENT_LLM_MODEL env var)
  --runs-dir PATH Output directory for event logs (default: runs/)
  --verbose       Print turn-by-turn narration to stdout
```

After each run the console prints:
```
Run ID: <uuid>
Result: WIN | TURN_LIMIT | STUCK
Turns: <n>
Event log: runs/<uuid>.jsonl
```

The full event log is saved as a `.jsonl` file under `runs/`.

---

## Running the Legibility Dashboard

The Streamlit dashboard lets you inspect any saved run visually.

```bash
streamlit run apps/legibility/app.py
```

Then open http://localhost:8501 in your browser.  From there you can:

- **Replay** the simulation turn-by-turn (ground truth vs. agent belief side-by-side)
- **Causal graph** — trace failures backward to root cause nodes
- **Gantt timeline** — see concurrent agent activity and idle gaps
- **Belief heatmaps** — spatial view of confidence and epistemic divergence

---

## Running the Tests

All tests use **pytest** and require no API keys — they mock LLM calls.

### Run the full test suite

```bash
pytest
```

### Run a specific test module

```bash
pytest tests/test_environment/test_grid.py
pytest tests/test_environment/test_perception.py
pytest tests/test_agents/test_tools.py
pytest tests/test_legibility/test_divergence.py
```

### Run with verbose output

```bash
pytest -v
```

### Run only tests matching a keyword

```bash
pytest -k "grid"
```

---

## Simulation Rules (Ground Truth)

- **Grid:** 8×8 minimum, with walls, a key, a locked door, and an exit.
- **Agents:** Two agents with randomized starting positions.
- **Fog of War:** Each agent sees only its immediately adjacent cells.
- **Turn Mechanics:** Agents act one at a time; each turn = one tool call.
- **Communication Lag:** Messages sent on Turn N are delivered on Turn N+1.
- **Win Condition:** Both agents reach the exit; one must carry the key to unlock the door.
- **Termination:** Game ends on win, turn-limit hit, or both agents stuck.

---

## File Architecture

```
dungeonAgents-ProveAI/
│
├── README.md                       # This file — project overview & architecture
│
├── docs/                           # Reference documents & research
│   ├── dungeon_agents_v3.pdf       # Original assignment specification
│   ├── GEMINI_DP.pdf               # Gemini Deep Research architectural report
│   ├── GROUND_TRUTH.md             # Extracted hard requirements & deliverables
│   ├── project_logs.md             # Workflow phases & process log
│   ├── PRD.md                      # Product Requirements Document
│   └── repo_arch.md                # Canonical file architecture reference (with env docs)
│
├── apps/
│   │
│   ├── simulation/                 # Core dungeon simulation engine
│   │   ├── main.py                 # Entry point — boots the simulation
│   │   │
│   │   ├── environment/            # The dungeon world (source of truth)
│   │   │   ├── grid.py             # Grid state machine; cell types & layout
│   │   │   ├── perception.py       # Fog-of-war engine; viewport masking per agent
│   │   │   ├── interaction.py      # Validates move, pick-up, and unlock actions
│   │   │   └── orchestrator.py     # Environment Orchestrator / Dungeon Master logic
│   │   │
│   │   ├── agents/                 # LLM agent definitions
│   │   │   ├── llm_factory.py      # Provider-agnostic LLM factory (OpenAI & Gemini)
│   │   │   ├── agent_a.py          # Agent A — LangGraph node definition
│   │   │   ├── agent_b.py          # Agent B — LangGraph node definition
│   │   │   ├── dungeon_master.py   # DM agent — operates on stale state (N-2 turns)
│   │   │   ├── tools.py            # Agent tools: move, observe, interact, communicate
│   │   │   └── state.py            # Agent belief state & internal world model
│   │   │
│   │   ├── game_loop/              # Turn-based execution orchestration
│   │   │   ├── loop.py             # Main game loop; gathers intentions, applies transitions
│   │   │   └── message_queue.py    # Communication queue enforcing turn-N+1 delivery lag
│   │   │
│   │   └── schemas/                # Pydantic V2 event & state schemas
│   │       ├── events.py           # Structured event record logged at each agent step
│   │       └── state.py            # World state, agent state, and perception schemas
│   │
│   └── legibility/                 # Streamlit diagnostic dashboard (Legibility Layer)
│       ├── app.py                  # Streamlit app entry point
│       │
│       ├── views/                  # Individual dashboard view components
│       │   ├── replay.py           # Dual-perspective replay: ground truth vs. agent belief
│       │   ├── causal_graph.py     # Causal graph tracing failures back to root cause
│       │   ├── timeline.py         # Gantt-style timeline of concurrent agent activity
│       │   └── heatmaps.py         # Belief confidence & epistemic divergence heatmaps
│       │
│       └── analysis/               # Automated analysis & report generation
│           ├── divergence.py       # Epistemic divergence metric (belief vs. reality gap)
│           └── report.py           # Causal Incident Report generator for failed runs
│
├── packages/
│   │
│   ├── observability/              # Shared observability & tracing package
│   │   ├── tracer.py               # OpenTelemetry + Langfuse SDK integration & setup
│   │   ├── spans.py                # Span definitions: perception, reasoning, action spans
│   │   └── metrics.py              # Custom metrics: divergence_score, token usage, latency
│   │
│   └── shared/                     # Shared utilities used across apps
│       ├── types.py                # Common type definitions (Cell, Position, AgentID, etc.)
│       └── constants.py            # Project-wide constants (grid size, turn limit, etc.)
│
├── runs/                           # Exported simulation run data (structured JSON)
│   └── .gitkeep                    # Placeholder; runs are saved here as .jsonl files
│
├── traces/                         # Exported Langfuse / OTel traces
│   └── .gitkeep                    # Placeholder; exported traces are stored here
│
├── configs/                        # External service configuration
│   ├── langfuse.yaml               # Langfuse project & endpoint configuration
│   └── otel.yaml                   # OpenTelemetry collector & exporter configuration
│
├── tests/                          # Test suite
│   ├── test_environment/
│   │   ├── test_grid.py            # Unit tests for grid state machine
│   │   └── test_perception.py      # Unit tests for fog-of-war / viewport masking
│   ├── test_agents/
│   │   └── test_tools.py           # Unit tests for agent tools & validators
│   └── test_legibility/
│       └── test_divergence.py      # Unit tests for divergence metric calculations
│
├── .env.example                    # Template for required environment variables
├── .gitignore                      # Git ignore rules
├── pyproject.toml                  # Python project metadata & dependency management
└── requirements.txt                # Pinned runtime dependencies
```

---

## Key Concepts

### Event Sourcing for Autonomous Agents (ESAA)
Agents do not write directly to the simulation state. They emit **Intentions** (e.g., "move North"), which are validated by the Orchestrator and appended to an immutable event log (`runs.jsonl`). The current board state is always a projection of this log. This enables **Deterministic Replay** — any failed run can be re-executed from any turn.

### Epistemic Divergence
The core diagnostic metric. Measures the gap between an agent's internal belief about the world and the actual ground truth at any given turn. Spikes in this metric pinpoint the exact turn where a communication failure or missed observation occurred.

### The Legibility Layer
A Streamlit dashboard that transforms raw JSON traces into human-interpretable visualizations:
- **Dual-Perspective Replay** — ground truth vs. agent subjective map side-by-side.
- **Causal Graph** — traces failures backward to root cause nodes.
- **Gantt Timeline** — shows concurrent agent activity and idle gaps.
- **Belief Heatmaps** — maps confidence and divergence over the grid spatially.

### Observability Stack
Every agent turn generates a parent OTel trace with child spans for: Perception → Reasoning → Action. Key metadata attributes (`belief_coordinates`, `divergence_score`, `tool_name`, `latency`) are logged to Langfuse for filtering and cross-run comparison.

---

## Deliverables

- [ ] Full source code in this repository with continuous commit history
- [ ] Exported Langfuse traces (stored in `traces/`)
- [ ] Multiple simulation runs as structured JSON — successes and failures (stored in `runs/`)
- [ ] Full AI conversation/coding tool history
- [ ] 1–3 minute Loom video walkthrough of decisions and design rationale

