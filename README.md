# dungeonAgents-ProveAI

> Two LLM-powered agents navigate an 8×8 dungeon. The goal isn't to win — it's to **prove** what happened and why. Every decision is traced, every epistemic gap is measured, and every failure is made legible to a human diagnoser.

---

## What Is This Project?

**dungeonAgents-ProveAI** is a multi-agent simulation built to explore observability and explainability in agentic AI systems. Two agents operate inside a dungeon grid, subject to fog-of-war and communication lag, while a full observability stack captures every tool call, LLM input/output, and state transition.

The primary deliverable is **not** agent intelligence — it is the quality of traces and the legibility of the diagnostic output. A human reviewer should be able to look at any run and answer:

1. **What happened?**
2. **Why did it happen?**
3. **What should change next time?**

---

## Quick Start (No API Key Required — Use the Demo)

If you just want to **see the dashboards working**, skip the LLM setup and use the included 30-turn demo run:

```bash
# 1. Clone and install
git clone https://github.com/Qrytics/dungeonAgents-ProveAI.git
cd dungeonAgents-ProveAI
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e .

# 2. Generate (or regenerate) the 30-turn demo data
python scripts/generate_demo_run.py

# 3. Open the Legibility Dashboard (Streamlit)
streamlit run apps/legibility/app.py
# → opens http://localhost:8501 in your browser
# → select "demo_30turn_run.jsonl" from the sidebar (it is pre-selected by default)

# 4. Open the React Replay UI
cd apps/visualizer
npm install   # first time only
npm run dev
# → opens http://localhost:5173 in your browser
# → click "Load bundled demo" (uses the same demo automatically)
```

Both dashboards work fully without any API key when using the demo data.

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
| Live grid UI | React (Vite) + local HTTP helper for in-progress runs |
| Event Storage | Immutable `.jsonl` flat files |

---

## Prerequisites

- **Python 3.12 or higher** — verify with `python --version`
- **pip** — comes bundled with Python
- **Node.js 18+** — only for the React visualizer; verify with `node --version`
- An API key for at least one LLM provider (**only required to run live simulations**):
  - **Google Gemini** (recommended): get a free key at https://aistudio.google.com/app/apikey
  - **OpenAI**: get a key at https://platform.openai.com/api-keys
- (Optional) **Langfuse** account for trace storage: https://cloud.langfuse.com

---

## Full Setup

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

### 3. Install Python dependencies

```bash
pip install -e .
```

> This installs the project in editable mode along with all runtime dependencies
> including `langchain-google-genai` (Gemini) and `langchain-openai`.

### 4. Configure environment variables (required for live LLM runs only)

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

#### LLM provider selection

The project auto-selects the right LangChain integration based on the model name set in `AGENT_LLM_MODEL`:

| `AGENT_LLM_MODEL` value | Provider used | Key needed |
|---|---|---|
| `gemini-2.0-flash` | Google Gemini | `GOOGLE_API_KEY` |
| `gemini-1.5-pro` | Google Gemini | `GOOGLE_API_KEY` |
| `gpt-4o-mini` | OpenAI | `OPENAI_API_KEY` |
| `gpt-4o` | OpenAI | `OPENAI_API_KEY` |

---

## Generating the Demo Data

The repository includes a script that generates a deterministic **30-turn demo run** without requiring any LLM or API key. This demo simulates:

- Agent A exploring the dungeon, finding the key, unlocking the door, and reaching the exit.
- Agent B heading directly toward the exit and waiting there.
- Multiple failed moves, communication exchanges, and fog-of-war observations.
- A **WIN** termination at turn 29.

Run from the **repository root**:

```bash
python scripts/generate_demo_run.py
```

This creates two files:
- `runs/demo_30turn_run.jsonl` — for the Legibility / Streamlit dashboard
- `apps/visualizer/public/sample_visualizer_demo.jsonl` — for the React visualizer "Load bundled demo" button

---

## Running the Legibility Dashboard (Streamlit)

The Streamlit dashboard lets you inspect any saved run visually across four views.

**Step 1 — Generate the demo data (one-time):**
```bash
python scripts/generate_demo_run.py
```

**Step 2 — Launch the dashboard:**
```bash
streamlit run apps/legibility/app.py
```

Open http://localhost:8501 in your browser.

**Step 3 — Select the demo run:**  
In the left sidebar, the dropdown will default to `demo_30turn_run.jsonl` (shown with a 🎮 badge).

The dashboard has four tabs:

| Tab | What it shows |
|---|---|
| 🔁 **Replay** | Dual-perspective grid: Ground Truth vs. agent belief. Scrub the turn slider. Metadata (agent positions, key holder, door status) shown above. |
| 🔗 **Causal Graph** | Epistemic divergence chart + interactive causal-chain DAG + root-cause analysis + recommendations. Works without an LLM API key. |
| 📊 **Timeline** | Gantt-style chart of every action per agent per turn, colour-coded by type. Action count breakdown below. |
| 🌡 **Heatmaps** | Colour-coded spatial views: divergence score, belief confidence, and fog-of-war cells. |

> **No LLM key needed:** The Causal Graph tab generates a structural analysis automatically. If an OpenAI/Gemini key is configured, the narrative will be upgraded by LLM-generated text. Otherwise, a rule-based analysis is shown.

---

## Running the React Replay Visualizer

The React app under `apps/visualizer` shows the ground-truth dungeon grid from every `outcome` event in a run log.

### One-time Node.js setup

```bash
cd apps/visualizer
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173).

### Option A — Load the bundled demo (no simulation required)

1. Start the dev server: `cd apps/visualizer && npm run dev`
2. Open http://localhost:5173
3. Click **"Load bundled demo"** — loads the 30-turn demo automatically

Controls:
- **Play / Pause / Prev / Next** — step through outcome frames
- **Speed selector** — 150 ms to 1000 ms per frame
- **Scrubber** — drag to any frame
- **Sound effects** toggle — Web Audio cues per tool type

### Option B — Load any saved run file

1. Click **"Load .jsonl run"** → pick any file from `runs/`

### Option C — Live dashboard during a simulation (requires LLM key)

You need **two terminals** open at the same time:

```bash
# Terminal 1 — React dev server
cd apps/visualizer && npm run dev

# Terminal 2 — Python simulation with live polling
python -m apps.simulation.main --live-viz
```

The CLI prints a link like: `http://localhost:5173/?run=<uuid>&live=1`  
Open that link in your browser. The grid updates in real time as the simulation runs.

---

## Running the Simulation (Requires LLM API Key)

The simulation is launched from the repository root.

### Basic run

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

### All CLI options

```
usage: python -m apps.simulation.main [OPTIONS]

Options:
  --rows INT           Grid rows (default: 8, min: 8)
  --cols INT           Grid columns (default: 8, min: 8)
  --seed INT           Random seed for reproducible layout
  --model TEXT         LLM model name (default: reads AGENT_LLM_MODEL env var)
  --runs-dir PATH      Output directory for event logs (default: runs/)
  --verbose            Print turn-by-turn narration to stdout
  --live-viz           Serve the growing run log for the React live dashboard (127.0.0.1)
  --live-viz-port INT  Port for --live-viz (default: 8765)
  --live-viz-open      Open the browser on the live visualizer URL (implies --live-viz)
```

After each run the console prints:
```
Run ID: <uuid>
Result: WIN | TURN_LIMIT | STUCK
Turns: <n>
Event log: runs/<uuid>.jsonl
```

The full event log is saved as a `.jsonl` file under `runs/`. You can then load it in either dashboard.

---

## Running the Tests

All tests use **pytest** and require no API keys — they mock LLM calls.

```bash
# Full test suite
pytest

# Specific modules
pytest tests/test_environment/test_grid.py
pytest tests/test_environment/test_perception.py
pytest tests/test_agents/test_tools.py
pytest tests/test_legibility/test_divergence.py

# Verbose output
pytest -v

# Match by keyword
pytest -k "grid"
```

---

## Simulation Rules (Ground Truth)

- **Grid:** 8×8 minimum, with walls, a key, a locked door, and an exit.
- **Agents:** Two agents with randomized starting positions.
- **Fog of War:** Each agent sees only its immediately adjacent cells (Moore neighbourhood, radius 1).
- **Turn Mechanics:** Agents act one at a time; each turn = one tool call per agent.
- **Communication Lag:** Messages sent on Turn N are delivered on Turn N+1.
- **Win Condition:** Both agents must reach the exit; the door must be unlocked first using the key.
- **Termination:** Game ends on win, turn-limit reached (100), or both agents stuck for 10 consecutive turns.

---

## File Architecture

```
dungeonAgents-ProveAI/
│
├── README.md                       # This file — project overview & how to run
│
├── docs/                           # Reference documents & research
│   ├── dungeon_agents_v3.pdf       # Original assignment specification
│   ├── GEMINI_DP.pdf               # Gemini Deep Research architectural report
│   ├── GROUND_TRUTH.md             # Extracted hard requirements & deliverables
│   ├── project_logs.md             # Workflow phases & process log
│   ├── PRD.md                      # Product Requirements Document
│   └── repo_arch.md                # Canonical file architecture reference
│
├── apps/
│   │
│   ├── simulation/                 # Core dungeon simulation engine
│   │   ├── main.py                 # Entry point — boots the simulation
│   │   ├── live_viz_server.py      # HTTP helper for React live polling
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
│   │   │   ├── loop.py             # Main game loop
│   │   │   └── message_queue.py    # Communication queue (turn-N+1 delivery lag)
│   │   │
│   │   └── schemas/                # Pydantic V2 event & state schemas
│   │       ├── events.py           # Structured event records
│   │       └── state.py            # World state, agent state, and perception schemas
│   │
│   ├── visualizer/                 # React + Vite live/replay grid UI
│   │   ├── public/
│   │   │   └── sample_visualizer_demo.jsonl   # 30-turn bundled demo (auto-generated)
│   │   └── src/                    # App, grid, JSONL parser, live API client
│   │
│   └── legibility/                 # Streamlit diagnostic dashboard
│       ├── app.py                  # Streamlit entry point
│       │
│       ├── views/                  # Individual dashboard tabs
│       │   ├── replay.py           # Dual-perspective replay: ground truth vs. belief
│       │   ├── causal_graph.py     # Causal chain DAG + divergence chart
│       │   ├── timeline.py         # Gantt timeline of agent activity
│       │   └── heatmaps.py         # Belief confidence & divergence heatmaps
│       │
│       └── analysis/               # Automated analysis
│           ├── divergence.py       # Epistemic divergence metric
│           └── report.py           # Causal Incident Report generator (LLM + no-LLM fallback)
│
├── packages/
│   ├── observability/              # OTel + Langfuse integration
│   └── shared/                    # Common types and constants
│
├── runs/                           # Simulation run data (.jsonl files)
│   └── demo_30turn_run.jsonl       # Pre-generated 30-turn WIN demo
│
├── scripts/
│   └── generate_demo_run.py        # Generates both demo JSONL files (no API key needed)
│
├── tests/                          # Full pytest suite (no API keys needed)
│
├── .env.example                    # Template for environment variables
├── pyproject.toml                  # Python project metadata & dependencies
└── requirements.txt                # Pinned runtime dependencies
```

---

## Key Concepts

### Event Sourcing for Autonomous Agents (ESAA)
Agents do not write directly to the simulation state. They emit **Intentions** (e.g., "move North"), which are validated by the Orchestrator and appended to an immutable event log (`runs.jsonl`). The current board state is always a projection of this log. This enables **Deterministic Replay** — any run can be re-examined from any turn.

### Epistemic Divergence
The core diagnostic metric. Measures the gap between an agent's internal belief about the world and the actual ground truth at any given turn. Spikes in this metric pinpoint the exact turn where a communication failure or missed observation occurred.

### The Legibility Layer
A Streamlit dashboard that transforms raw JSON traces into human-interpretable visualizations:
- **Dual-Perspective Replay** — ground truth vs. agent subjective map side-by-side.
- **Causal Graph** — traces failures backward to root cause nodes (works without LLM).
- **Gantt Timeline** — shows concurrent agent activity and idle gaps with action counts.
- **Belief Heatmaps** — maps confidence and divergence over the grid spatially.

### Observability Stack
Every agent turn generates a parent OTel trace with child spans for: Perception → Reasoning → Action. Key metadata attributes (`belief_coordinates`, `divergence_score`, `tool_name`, `latency`) are logged to Langfuse for filtering and cross-run comparison.

---

## Deliverables

- [x] Full source code in this repository with continuous commit history
- [x] 30-turn demo run (`runs/demo_30turn_run.jsonl`) — no API key required
- [x] All four Legibility Dashboard views working with demo data
- [x] React Replay Visualizer with bundled demo
- [ ] Exported Langfuse traces (stored in `traces/`)
- [ ] Multiple live simulation runs as structured JSON (stored in `runs/`)
- [ ] Full AI conversation/coding tool history
- [ ] 1–3 minute Loom video walkthrough of decisions and design rationale

