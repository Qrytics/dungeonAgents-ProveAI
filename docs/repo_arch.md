# Repository Architecture — dungeonAgents-ProveAI

> Source: `README.md` — File Architecture section.
> This file is the canonical reference for the folder and file layout of this monorepo.

---

## Environment Variables

All runtime secrets are read from environment variables (never hard-coded).
Copy `.env.example` to `.env` and fill in the values relevant to your chosen LLM provider.

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini only | Google AI Studio API key. Get it at https://aistudio.google.com/app/apikey |
| `OPENAI_API_KEY` | OpenAI only | OpenAI platform API key. Get it at https://platform.openai.com/api-keys |
| `AGENT_LLM_MODEL` | Yes | LLM model name — drives provider selection (see below) |
| `LANGFUSE_PUBLIC_KEY` | Yes | Langfuse project public key |
| `LANGFUSE_SECRET_KEY` | Yes | Langfuse project secret key |
| `LANGFUSE_HOST` | Yes | Langfuse host (default: `https://cloud.langfuse.com`) |

### Setting `GOOGLE_API_KEY` — platform-specific examples

**Bash / macOS / Linux:**
```bash
export GOOGLE_API_KEY="your_key_here"
export AGENT_LLM_MODEL="gemini-2.0-flash"
```

**Windows PowerShell:**
```powershell
$env:GOOGLE_API_KEY = "your_key_here"
$env:AGENT_LLM_MODEL = "gemini-2.0-flash"
```

**`.env` file (loaded automatically at startup):**
```
GOOGLE_API_KEY=your_key_here
AGENT_LLM_MODEL=gemini-2.0-flash
```

---

## LLM Provider Selection

The `AGENT_LLM_MODEL` environment variable controls which LLM provider is used
for all three agents (Agent A, Agent B, Dungeon Master).  The selection logic
lives in `apps/simulation/agents/llm_factory.py`:

| Model name prefix | Provider class | Required key |
|---|---|---|
| `gemini-*` | `ChatGoogleGenerativeAI` | `GOOGLE_API_KEY` |
| anything else | `ChatOpenAI` | `OPENAI_API_KEY` |

**Recommended Gemini models:**

| Model | Notes |
|---|---|
| `gemini-2.0-flash` | Fast, low-cost — recommended for development |
| `gemini-1.5-pro` | Higher capability |

**Recommended OpenAI models:**

| Model | Notes |
|---|---|
| `gpt-4o-mini` | Default — fast and low-cost |
| `gpt-4o` | Higher capability |

---

## File Layout

```
dungeonAgents-ProveAI/
│
├── README.md                       # Project overview & architecture
│
├── docs/                           # Reference documents & research
│   ├── dungeon_agents_v3.pdf       # Original assignment specification
│   ├── GEMINI_DP.pdf               # Gemini Deep Research architectural report
│   ├── GROUND_TRUTH.md             # Extracted hard requirements & deliverables
│   ├── project_logs.md             # Workflow phases & process log
│   ├── PRD.md                      # Product Requirements Document (modular, agent-assignable)
│   └── repo_arch.md                # This file — repository file architecture reference
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

## Module Ownership Quick Reference

| Path | PRD Module | Description |
|---|---|---|
| `packages/shared/types.py` | M-01 | Primitive type aliases |
| `packages/shared/constants.py` | M-01 | Project-wide constants |
| `apps/simulation/schemas/state.py` | M-02 | World & agent state schemas |
| `apps/simulation/schemas/events.py` | M-02 | Event log schemas |
| `apps/simulation/environment/grid.py` | M-03 | Grid state machine |
| `apps/simulation/environment/perception.py` | M-04 | Fog-of-war engine |
| `apps/simulation/environment/interaction.py` | M-05 | Action validation |
| `apps/simulation/environment/orchestrator.py` | M-06 | Event application & replay |
| `apps/simulation/agents/llm_factory.py` | M-07 | LLM provider factory (OpenAI & Gemini) |
| `apps/simulation/agents/tools.py` | M-07 | LangGraph tool definitions |
| `apps/simulation/agents/state.py` | M-08 | Agent belief state manager |
| `apps/simulation/agents/agent_a.py` | M-09 | Agent A LangGraph node |
| `apps/simulation/agents/agent_b.py` | M-09 | Agent B LangGraph node |
| `apps/simulation/agents/dungeon_master.py` | M-10 | Dungeon Master agent |
| `apps/simulation/game_loop/message_queue.py` | M-11 | Communication lag queue |
| `apps/simulation/game_loop/loop.py` | M-11 | Turn-based game loop |
| `apps/simulation/main.py` | M-12 | CLI entry point |
| `packages/observability/tracer.py` | M-13 | OTel + Langfuse tracer |
| `packages/observability/spans.py` | M-13 | Span context managers |
| `packages/observability/metrics.py` | M-13 | Custom OTel metrics |
| `apps/legibility/analysis/divergence.py` | M-14 | Divergence metric |
| `apps/legibility/analysis/report.py` | M-15 | Causal incident report |
| `apps/legibility/views/replay.py` | M-16 | Replay dashboard view |
| `apps/legibility/views/causal_graph.py` | M-16 | Causal graph view |
| `apps/legibility/views/timeline.py` | M-16 | Gantt timeline view |
| `apps/legibility/views/heatmaps.py` | M-16 | Heatmap view |
| `apps/legibility/app.py` | M-17 | Streamlit app shell |
| `pyproject.toml`, `requirements.txt`, `configs/`, `.env.example` | M-18 | Config & devops |
| `tests/test_environment/` | M-19 | Environment unit tests |
| `tests/test_agents/` | M-20 | Agent tools unit tests |
| `tests/test_legibility/` | M-21 | Legibility unit tests |
