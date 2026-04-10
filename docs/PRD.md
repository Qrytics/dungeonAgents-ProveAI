# Product Requirements Document — dungeonAgents-ProveAI

> **How to use this document**
> Each section below is a **self-contained module** (M-XX). Parallel agents can be assigned any module independently without needing context from other modules, except where **Dependencies** are listed. Read only your module and its listed dependencies before starting work.

---

## Meta

| Field | Value |
|---|---|
| Project | dungeonAgents-ProveAI |
| Language | Python 3.12+ |
| Agent Framework | LangGraph |
| Observability | Langfuse + OpenTelemetry |
| State & Validation | Pydantic V2 |
| UI Layer | Streamlit |
| Event Storage | Immutable `.jsonl` flat files |
| Source of Truth | `docs/GROUND_TRUTH.md` |
| Architecture Reference | `docs/repo_arch.md` |

---

## Dependency Map (read before assigning modules)

```
M-01 (Shared Types & Constants)
  └─► M-02 (Pydantic Schemas)
        └─► M-03 (Environment: Grid)
              └─► M-04 (Environment: Perception & Fog-of-War)
                    └─► M-05 (Environment: Interaction & Validation)
                          └─► M-06 (Environment: Orchestrator / Dungeon Master Logic)
M-01, M-02, M-03, M-04, M-05, M-06
  └─► M-07 (Agent Tools)
        └─► M-08 (Agent Belief State)
              └─► M-09 (LLM Agents: Agent A & Agent B)
                    └─► M-10 (LLM Agents: Dungeon Master Agent)
M-07, M-08, M-09, M-10
  └─► M-11 (Game Loop & Message Queue)
        └─► M-12 (Simulation Entry Point)
M-01
  └─► M-13 (Observability Package)
        └─► M-14 (Legibility: Divergence Analysis)
              └─► M-15 (Legibility: Causal Incident Report)
M-14, M-15
  └─► M-16 (Legibility: Dashboard Views)
        └─► M-17 (Legibility: Streamlit App Entry Point)
M-18 (Configuration & DevOps)        ← no dependencies
M-19 (Tests: Environment)             ← depends on M-03, M-04
M-20 (Tests: Agent Tools)             ← depends on M-07, M-08
M-21 (Tests: Legibility / Divergence) ← depends on M-14
```

---

## M-01 — Shared Types & Constants

**File:** `packages/shared/types.py`, `packages/shared/constants.py`
**Owner module:** `packages/shared/`
**Dependencies:** None

### Purpose
Define the primitive type aliases and project-wide constants that every other module imports. This is the foundation layer — nothing else can be built until these types exist.

### Deliverables

#### `packages/shared/types.py`
Define the following as Python `TypeAlias` or `NewType` entries using standard `typing`:

| Name | Base Type | Description |
|---|---|---|
| `AgentID` | `Literal["agent_a", "agent_b", "dungeon_master"]` | Identifies which agent |
| `Position` | `tuple[int, int]` | `(row, col)` coordinate on the grid |
| `CellType` | `Literal["floor", "wall", "key", "locked_door", "exit", "agent"]` | Enumerated cell states |
| `Direction` | `Literal["north", "south", "east", "west"]` | Cardinal movement directions |
| `TurnNumber` | `int` | Non-negative integer; 0-indexed |
| `RunID` | `str` | UUID4 string identifying a simulation run |
| `ToolName` | `Literal["move", "observe", "interact", "communicate"]` | Valid tool call names |
| `TerminationReason` | `Literal["win", "turn_limit", "stuck"]` | Why the game ended |

#### `packages/shared/constants.py`
Define the following module-level constants:

| Constant | Value | Description |
|---|---|---|
| `GRID_MIN_SIZE` | `8` | Minimum grid dimension (both rows and cols) |
| `TURN_LIMIT` | `100` | Maximum turns before forced termination |
| `FOG_RADIUS` | `1` | How many cells in each direction an agent can see |
| `COMM_LAG_TURNS` | `1` | Messages sent on turn N arrive on turn N+1 |
| `RUNS_DIR` | `Path("runs/")` | Where `.jsonl` run files are saved |
| `TRACES_DIR` | `Path("traces/")` | Where exported traces are saved |
| `LANGFUSE_PROJECT` | `"dungeonAgents-ProveAI"` | Langfuse project name |

### Acceptance Criteria
- [ ] All types importable from `packages.shared.types`
- [ ] All constants importable from `packages.shared.constants`
- [ ] No circular imports
- [ ] No third-party dependencies (stdlib only)

---

## M-02 — Pydantic Schemas (Events & World State)

**Files:** `apps/simulation/schemas/events.py`, `apps/simulation/schemas/state.py`
**Owner module:** `apps/simulation/schemas/`
**Dependencies:** M-01

### Purpose
Define the Pydantic V2 data models that form the backbone of event sourcing and state validation. Everything logged to disk and every state passed between components must conform to these schemas.

### Deliverables

#### `apps/simulation/schemas/state.py`
Define Pydantic V2 `BaseModel` classes:

**`CellState`**
```
row: int
col: int
cell_type: CellType
is_visible_to: list[AgentID]   # which agents currently see this cell
```

**`WorldState`**
```
run_id: RunID
turn: TurnNumber
grid: list[list[CellState]]    # full 8×8 (or larger) grid; ground truth
agent_positions: dict[AgentID, Position]
key_held_by: AgentID | None
door_unlocked: bool
```

**`AgentPerception`**
```
agent_id: AgentID
turn: TurnNumber
visible_cells: list[CellState]   # only cells within FOG_RADIUS
position: Position
has_key: bool
pending_messages: list[str]      # messages delivered this turn (sent N-1)
```

**`AgentBeliefState`**
```
agent_id: AgentID
turn: TurnNumber
believed_position: Position
believed_grid: dict[Position, CellType]   # agent's internal world map
has_key: bool
known_agent_positions: dict[AgentID, Position]  # may be stale
```

#### `apps/simulation/schemas/events.py`
Define Pydantic V2 `BaseModel` classes:

**`IntentionEvent`**
```
event_type: Literal["intention"]
run_id: RunID
turn: TurnNumber
agent_id: AgentID
tool_name: ToolName
tool_args: dict[str, Any]
llm_prompt_tokens: int
llm_completion_tokens: int
latency_ms: float
raw_llm_output: str
timestamp: datetime
```

**`OutcomeEvent`**
```
event_type: Literal["outcome"]
run_id: RunID
turn: TurnNumber
agent_id: AgentID
tool_name: ToolName
success: bool
result_description: str
world_state_after: WorldState
divergence_score: float | None   # populated post-hoc; None until computed
timestamp: datetime
```

**`MessageEvent`**
```
event_type: Literal["message"]
run_id: RunID
turn_sent: TurnNumber
turn_delivered: TurnNumber      # always turn_sent + COMM_LAG_TURNS
sender: AgentID
recipient: AgentID
content: str
timestamp: datetime
```

**`TerminationEvent`**
```
event_type: Literal["termination"]
run_id: RunID
final_turn: TurnNumber
reason: TerminationReason
winner: bool                    # True if agents won
timestamp: datetime
```

**`AnyEvent`**: `Annotated[Union[IntentionEvent, OutcomeEvent, MessageEvent, TerminationEvent], Field(discriminator="event_type")]`

### Serialization Requirements
- All models must use `model_config = ConfigDict(frozen=True)` (immutable once created)
- JSON serialization must use `model.model_dump_json()` for `.jsonl` file writes
- `datetime` fields must serialize to ISO 8601

### Acceptance Criteria
- [ ] All models importable from `apps.simulation.schemas.events` and `apps.simulation.schemas.state`
- [ ] `AnyEvent` discriminated union works with `TypeAdapter`
- [ ] All models are frozen (immutable)
- [ ] Round-trip JSON serialization is lossless
- [ ] Unit tests covered by M-19

---

## M-03 — Environment: Grid State Machine

**File:** `apps/simulation/environment/grid.py`
**Owner module:** `apps/simulation/environment/`
**Dependencies:** M-01, M-02

### Purpose
Implement the dungeon grid — the authoritative source of physical truth. The grid is the only component that knows where walls, the key, the locked door, and the exit are located. It is initialized once per run, then mutated exclusively through validated outcome events.

### Deliverables

#### `DungeonGrid` class
**Constructor:** `DungeonGrid(rows: int = 8, cols: int = 8, seed: int | None = None)`
- Validates `rows >= GRID_MIN_SIZE` and `cols >= GRID_MIN_SIZE`
- Generates a grid with randomized layout using `seed` for reproducibility

**Grid Generation Rules (must be enforced):**
- Outer boundary: all walls
- Interior: random floor tiles with ~20% wall density
- Required placements (exactly one of each): `key`, `locked_door`, `exit`
- `key` and `exit` must be on floor tiles; `locked_door` must be adjacent to a wall on at least one side
- Starting positions for `agent_a` and `agent_b` must be on floor tiles and at least 3 cells apart (Manhattan distance)

**Methods:**
```python
def get_cell(self, pos: Position) -> CellState
def set_cell(self, pos: Position, cell_type: CellType) -> None
def is_passable(self, pos: Position) -> bool   # floor, key, exit; not wall or locked_door
def get_agent_start_positions(self) -> dict[AgentID, Position]
def to_world_state(self, run_id: RunID, turn: TurnNumber, ...) -> WorldState
def serialize(self) -> str   # returns JSON string of the full grid
```

### Acceptance Criteria
- [ ] Grid always has exactly one key, one locked door, one exit
- [ ] Agent start positions never overlap with walls or each other
- [ ] Same seed always produces same layout
- [ ] `to_world_state()` produces a valid `WorldState` schema
- [ ] Unit tests in `tests/test_environment/test_grid.py`

---

## M-04 — Environment: Perception & Fog-of-War Engine

**File:** `apps/simulation/environment/perception.py`
**Owner module:** `apps/simulation/environment/`
**Dependencies:** M-01, M-02, M-03

### Purpose
Implement the fog-of-war system. Each agent sees only cells within `FOG_RADIUS` (1 cell) of their current position. This module computes what an agent can perceive each turn and produces an `AgentPerception` object.

### Deliverables

#### `PerceptionEngine` class

**Methods:**
```python
def compute_viewport(
    self,
    agent_id: AgentID,
    position: Position,
    grid: DungeonGrid,
    pending_messages: list[str],
    has_key: bool,
    turn: TurnNumber,
) -> AgentPerception
```
- Returns all `CellState` objects within `FOG_RADIUS` (Moore neighborhood: up to 8 adjacent + self = 9 cells max)
- Clips at grid boundaries (corner/edge agents see fewer cells)
- Does **not** reveal cell contents outside the viewport (critical: no information leakage)

```python
def mask_world_state(
    self,
    agent_id: AgentID,
    world_state: WorldState,
    position: Position,
) -> AgentPerception
```
- Derives perception from a full `WorldState`; used for testing

### Acceptance Criteria
- [ ] Agent at corner position sees exactly 4 cells (self + 3 adjacent)
- [ ] Agent at edge position sees exactly 6 cells
- [ ] Agent at interior position sees exactly 9 cells
- [ ] No cell outside `FOG_RADIUS` is ever included in `visible_cells`
- [ ] Unit tests in `tests/test_environment/test_perception.py`

---

## M-05 — Environment: Interaction & Action Validation

**File:** `apps/simulation/environment/interaction.py`
**Owner module:** `apps/simulation/environment/`
**Dependencies:** M-01, M-02, M-03

### Purpose
Validate every agent action before it is applied. No mutation to the grid or game state happens without passing through this module. This is the physics engine of the dungeon.

### Deliverables

#### `InteractionValidator` class

**Methods:**
```python
def validate_move(
    self,
    agent_id: AgentID,
    direction: Direction,
    current_pos: Position,
    grid: DungeonGrid,
    door_unlocked: bool,
) -> tuple[bool, str, Position | None]
# Returns: (is_valid, reason_message, new_position_if_valid)
```
- Invalid if target cell is a wall
- Invalid if target cell is `locked_door` and `door_unlocked` is False
- Valid moves: floor, key, exit, unlocked door

```python
def validate_interact(
    self,
    agent_id: AgentID,
    current_pos: Position,
    grid: DungeonGrid,
    key_held_by: AgentID | None,
    door_unlocked: bool,
) -> tuple[bool, str, dict]
# Returns: (is_valid, reason_message, state_mutations_dict)
```
- "Pick up key": valid only if agent is on key cell and no agent holds key
- "Unlock door": valid only if agent is adjacent to locked_door and agent holds key
- `state_mutations_dict` describes what changes: `{"key_held_by": agent_id}` or `{"door_unlocked": True}`

```python
def validate_observe(
    self,
    agent_id: AgentID,
    position: Position,
    grid: DungeonGrid,
) -> tuple[bool, str]
# Always returns (True, ...) — observe is always valid but produces no mutation
```

```python
def validate_communicate(
    self,
    sender: AgentID,
    recipient: AgentID,
    content: str,
) -> tuple[bool, str]
# Invalid only if sender == recipient or content is empty
```

### Acceptance Criteria
- [ ] Move into wall returns `(False, reason, None)`
- [ ] Move into locked door when unlocked returns `(True, reason, new_pos)`
- [ ] Key pick-up produces correct `state_mutations_dict`
- [ ] Unlocking door requires adjacent position to door, not standing on it
- [ ] All edge cases from GROUND_TRUTH.md section 1 & 2 are covered

---

## M-06 — Environment: Orchestrator (Dungeon Master Logic)

**File:** `apps/simulation/environment/orchestrator.py`
**Owner module:** `apps/simulation/environment/`
**Dependencies:** M-01, M-02, M-03, M-04, M-05

### Purpose
The Orchestrator is the single authoritative decision-maker for applying agent intentions to world state. It receives `IntentionEvent`s, validates them via M-05, applies mutations to the `DungeonGrid`, and emits `OutcomeEvent`s to the event log.

### Deliverables

#### `EnvironmentOrchestrator` class

**Constructor:** `EnvironmentOrchestrator(grid: DungeonGrid, event_log_path: Path)`

**Methods:**
```python
def apply_intention(
    self,
    intention: IntentionEvent,
    current_world_state: WorldState,
) -> OutcomeEvent
```
- Validates the intention using `InteractionValidator`
- Applies state mutations if valid
- Constructs and returns a frozen `OutcomeEvent`
- Appends the event to the `.jsonl` event log file atomically (one JSON line per event)

```python
def check_termination(
    self, world_state: WorldState, turn: TurnNumber
) -> TerminationEvent | None
```
- Returns `TerminationEvent(reason="win")` if both agents are on `exit` cell
- Returns `TerminationEvent(reason="turn_limit")` if `turn >= TURN_LIMIT`
- Returns `TerminationEvent(reason="stuck")` if all agents have no valid moves for 3 consecutive turns
- Returns `None` if game continues

```python
def replay_from_log(self, event_log_path: Path) -> list[WorldState]
```
- Reads all events from a `.jsonl` file and replays them in order
- Returns ordered list of `WorldState` snapshots (one per turn)
- Used by the legibility layer for deterministic replay

### Event Log Format
- File path: `runs/{run_id}.jsonl`
- One JSON object per line, in chronological order
- Objects are serialized `AnyEvent` instances

### Acceptance Criteria
- [ ] Successful move mutates agent position in the returned `OutcomeEvent`
- [ ] Failed validation produces `OutcomeEvent(success=False)` without mutating grid
- [ ] Event log is append-only; no event is ever modified or deleted
- [ ] `replay_from_log()` produces identical `WorldState` sequence every time for same log
- [ ] Win condition is detected on the same turn both agents reach exit

---

## M-07 — Agent Tools

**File:** `apps/simulation/agents/tools.py`
**Owner module:** `apps/simulation/agents/`
**Dependencies:** M-01, M-02, M-05

### Purpose
Define the four LangGraph tool functions (`move`, `observe`, `interact`, `communicate`) that agents can call each turn. These are the only interface agents have with the world.

### Deliverables

Each tool is a Python function decorated with `@tool` (LangGraph/LangChain tool decorator) that:
1. Constructs an `IntentionEvent` with token counts and latency
2. Passes it to the Orchestrator
3. Returns a human-readable string result to the agent

#### Tool Signatures

```python
@tool
def move(direction: Direction) -> str:
    """
    Move the agent one cell in the specified direction.
    Returns a description of the result (success or reason for failure).
    """

@tool
def observe() -> str:
    """
    Observe all cells within your field of vision (adjacent cells only).
    Returns a formatted description of visible cells, including cell types and positions.
    """

@tool
def interact() -> str:
    """
    Interact with the current cell or adjacent items.
    Picks up the key if on the key cell. Unlocks the door if adjacent and holding the key.
    Returns result description.
    """

@tool
def communicate(recipient: AgentID, message: str) -> str:
    """
    Send a message to the other agent. Message will be delivered on the NEXT turn (communication lag).
    Returns confirmation of message queued.
    """
```

#### Tool Context Injection
- Tools must access the current `WorldState` and `AgentID` through a **context mechanism** (not global state): use LangGraph's `RunnableConfig` or a `ToolContext` injectable. The approach must be deterministic and testable.

### Acceptance Criteria
- [ ] Each tool produces a valid `IntentionEvent`
- [ ] Tools do not mutate state directly; they emit intentions to the Orchestrator
- [ ] Tool docstrings are the agent's only documentation of their capabilities
- [ ] `communicate` tool queues via `MessageQueue` (M-11), not direct delivery

---

## M-08 — Agent Belief State

**File:** `apps/simulation/agents/state.py`
**Owner module:** `apps/simulation/agents/`
**Dependencies:** M-01, M-02

### Purpose
Implement the agent's internal world model — the subjective, potentially stale map of the dungeon that the agent builds from its observations. This is the "belief" side of the epistemic divergence equation.

### Deliverables

#### `AgentBeliefStateManager` class

**Constructor:** `AgentBeliefStateManager(agent_id: AgentID)`

**Methods:**
```python
def update_from_perception(self, perception: AgentPerception) -> AgentBeliefState
```
- Merges newly perceived cells into the agent's running belief map
- Updates `believed_position` from `perception.position`
- Applies any `pending_messages` (may update `known_agent_positions`)

```python
def get_current_belief(self) -> AgentBeliefState
```
- Returns the latest frozen `AgentBeliefState` snapshot

```python
def to_llm_prompt_context(self) -> str
```
- Formats the belief state as a human-readable string for injection into the LLM prompt
- Must include: current position, visible layout, known agent positions (with staleness note), key status, pending messages

### Belief Update Rules
- Agent never "forgets" cells it has previously seen (belief map is additive)
- Agent positions in belief may be stale — must be annotated with the turn they were last observed
- Key location is removed from belief map once it is picked up (by either agent)

### Acceptance Criteria
- [ ] Belief map grows monotonically as agent explores
- [ ] Stale agent positions are preserved in belief until updated
- [ ] `to_llm_prompt_context()` output is deterministic for the same belief state
- [ ] No ground-truth information leaks into belief state

---

## M-09 — LLM Agents: Agent A & Agent B

**Files:** `apps/simulation/agents/agent_a.py`, `apps/simulation/agents/agent_b.py`
**Owner module:** `apps/simulation/agents/`
**Dependencies:** M-01, M-02, M-07, M-08, M-13

### Purpose
Implement the two LangGraph agent nodes that operate in the dungeon. Each agent is an LLM with tool access. Their goal is to cooperate to get both agents to the exit with the key unlocking the door.

### Deliverables

Both agents share the same structure (agent_a.py and agent_b.py are symmetric). Each file defines:

#### `AgentNode` class (or LangGraph node function)

**LangGraph Node Signature:**
```python
def agent_a_node(state: LangGraphState) -> LangGraphState:
    ...
```

**Each agent turn must:**
1. Retrieve its current `AgentBeliefState` (from belief manager)
2. Build system + user prompt (see Prompt Contract below)
3. Call LLM with bound tools (`move`, `observe`, `interact`, `communicate`)
4. Emit the resulting `IntentionEvent` (with token counts + latency) via the observability span
5. Return updated `LangGraphState`

#### Prompt Contract
**System Prompt must include:**
- Agent identity (`agent_a` or `agent_b`)
- Objective: both agents exit; one needs key to unlock door
- Fog-of-war constraint: "You can only see adjacent cells"
- Communication lag: "Messages arrive on the next turn"
- Available tools (names + descriptions, auto-populated from tool docstrings)

**User Prompt (injected each turn) must include:**
- Output of `AgentBeliefStateManager.to_llm_prompt_context()`
- Current turn number

#### Observability Integration (M-13)
- Each agent turn must open a parent OTel span (`perception → reasoning → action`)
- Span attributes: `agent_id`, `turn`, `tool_name`, `latency_ms`, `divergence_score` (if available), `llm_model`
- Must log to Langfuse via the tracer initialized in M-13

### Acceptance Criteria
- [ ] Agent always selects exactly one tool call per turn
- [ ] Agent never receives ground truth information (only its belief state and perception)
- [ ] Token counts and latency are captured for every LLM call
- [ ] Observability spans are correctly nested (perception → reasoning → action)
- [ ] Agent can operate with any OpenAI-compatible LLM specified by `AGENT_LLM_MODEL` env var

---

## M-10 — LLM Agents: Dungeon Master Agent

**File:** `apps/simulation/agents/dungeon_master.py`
**Owner module:** `apps/simulation/agents/`
**Dependencies:** M-01, M-02, M-06, M-13

### Purpose
The Dungeon Master (DM) is a third LLM agent that observes the full simulation but acts on state that is **2 turns stale**. It does not play the game; it narrates, annotates, and can inject events (e.g., spawn a hazard, add a wall) subject to configurable rules. Its primary role is adding observability narrative and stress-testing agent robustness.

### Deliverables

#### `DungeonMasterAgent` class

**Constructor:** `DungeonMasterAgent(orchestrator: EnvironmentOrchestrator)`

**Turn invocation:**
```python
def act(self, stale_world_state: WorldState, turn: TurnNumber) -> str | None
```
- Receives `WorldState` from turn `turn - 2` (2 turns stale)
- LLM call produces a narrative annotation string (logged as metadata, not as an event)
- Optionally returns an `IntentionEvent` for a DM-controlled action (optional stretch goal)

**DM Prompt must include:**
- Full grid layout (DM sees everything, no fog)
- Stale state annotation: "This is the world as it was 2 turns ago"
- Current turn number

### Acceptance Criteria
- [ ] DM always receives state from exactly 2 turns ago, never current
- [ ] DM annotations are logged to Langfuse as trace metadata
- [ ] DM cannot modify ground truth state unless explicitly given Orchestrator write permission

---

## M-11 — Game Loop & Message Queue

**Files:** `apps/simulation/game_loop/loop.py`, `apps/simulation/game_loop/message_queue.py`
**Owner module:** `apps/simulation/game_loop/`
**Dependencies:** M-01, M-02, M-06, M-07, M-08, M-09, M-10

### Purpose
Implement the turn-based execution engine and the message delivery queue that enforces communication lag.

### Deliverables

#### `MessageQueue` class (`message_queue.py`)

```python
class MessageQueue:
    def enqueue(self, event: MessageEvent) -> None
    # Stores message; sets turn_delivered = turn_sent + COMM_LAG_TURNS

    def deliver(self, turn: TurnNumber, recipient: AgentID) -> list[str]
    # Returns messages whose turn_delivered == turn for the given recipient
    # Consumed messages are removed from the queue
```

#### `GameLoop` class (`loop.py`)

**Constructor:** `GameLoop(config: GameConfig)`

```python
@dataclass
class GameConfig:
    run_id: RunID
    grid_rows: int = 8
    grid_cols: int = 8
    seed: int | None = None
    llm_model: str = "gpt-4o-mini"
    event_log_dir: Path = RUNS_DIR
```

**Main method:**
```python
def run(self) -> TerminationEvent:
```
Execution order each turn:
1. Compute perception for both agents via M-04
2. Deliver pending messages to each agent via `MessageQueue.deliver()`
3. Update each agent's belief state via M-08
4. Agent A takes its turn → `IntentionEvent` → Orchestrator → `OutcomeEvent`
5. Agent B takes its turn → `IntentionEvent` → Orchestrator → `OutcomeEvent`
6. DM Agent acts on stale state (turn - 2)
7. Check termination via M-06
8. Increment turn counter

**Stuck Detection:** Track consecutive turns where no agent successfully moved. If 3 consecutive turns with no valid moves, terminate with `reason="stuck"`.

### Acceptance Criteria
- [ ] Messages sent on turn N are always delivered on turn N+1
- [ ] Turn order is always: Agent A → Agent B → DM check
- [ ] Event log contains every intention and outcome in strict chronological order
- [ ] `run()` returns a `TerminationEvent` in all cases (no infinite loops)
- [ ] Stuck detection fires correctly at 3 consecutive no-move turns

---

## M-12 — Simulation Entry Point

**File:** `apps/simulation/main.py`
**Owner module:** `apps/simulation/`
**Dependencies:** All M-01 through M-11

### Purpose
The CLI entry point for launching a simulation run. Parses arguments, initializes all components, runs the game loop, and reports final results.

### Deliverables

CLI interface using `argparse` or `typer`:

```
python -m apps.simulation.main [OPTIONS]

Options:
  --rows INT          Grid rows (default: 8, min: 8)
  --cols INT          Grid columns (default: 8, min: 8)
  --seed INT          Random seed for reproducible layout
  --model TEXT        LLM model name (default: gpt-4o-mini)
  --runs-dir PATH     Output directory for event logs (default: runs/)
  --verbose           Print turn-by-turn narration to stdout
```

**On completion, must print:**
```
Run ID: <uuid>
Result: WIN | TURN_LIMIT | STUCK
Turns: <n>
Event log: runs/<uuid>.jsonl
```

### Acceptance Criteria
- [ ] Runs end-to-end without error for a valid configuration
- [ ] `--seed` produces identical game layout and turn sequence (given same LLM responses)
- [ ] Event log file exists and is non-empty after run completes

---

## M-13 — Observability Package

**Files:** `packages/observability/tracer.py`, `packages/observability/spans.py`, `packages/observability/metrics.py`
**Owner module:** `packages/observability/`
**Dependencies:** M-01

### Purpose
Shared observability infrastructure used by all agent and game loop components. Integrates OpenTelemetry and Langfuse to capture every LLM call, tool invocation, and state transition as a structured, exportable trace.

### Deliverables

#### `packages/observability/tracer.py`

```python
def init_tracer(run_id: RunID) -> tuple[Tracer, LangfuseClient]:
    """
    Initialize the OTel TracerProvider and Langfuse client.
    Reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST from environment.
    Returns both for use throughout the run.
    """
```

- OTel exporter: OTLP HTTP exporter (configured by `configs/otel.yaml`)
- Langfuse: initialized with project name `LANGFUSE_PROJECT` from M-01 constants
- Tracer must be a singleton per run (keyed by `run_id`)

#### `packages/observability/spans.py`

Define span-creating context managers:

```python
@contextmanager
def perception_span(tracer: Tracer, agent_id: AgentID, turn: TurnNumber) -> Iterator[Span]:
    """Parent span for the perception phase of a turn."""

@contextmanager
def reasoning_span(tracer: Tracer, agent_id: AgentID, turn: TurnNumber, parent: Span) -> Iterator[Span]:
    """Child span for LLM reasoning (prompt construction + LLM call)."""

@contextmanager
def action_span(tracer: Tracer, agent_id: AgentID, turn: TurnNumber, tool_name: ToolName, parent: Span) -> Iterator[Span]:
    """Child span for tool execution and outcome application."""
```

Required span attributes:
- `agent_id`, `turn`, `run_id`
- `llm.prompt_tokens`, `llm.completion_tokens`, `llm.model`
- `tool.name`, `tool.success`
- `divergence_score` (set post-hoc via `span.set_attribute(...)`)
- `latency_ms`

#### `packages/observability/metrics.py`

```python
def record_divergence_score(meter: Meter, agent_id: AgentID, turn: TurnNumber, score: float) -> None
def record_token_usage(meter: Meter, agent_id: AgentID, prompt_tokens: int, completion_tokens: int) -> None
def record_turn_latency(meter: Meter, agent_id: AgentID, turn: TurnNumber, latency_ms: float) -> None
```

### Configuration
- `configs/langfuse.yaml`: must contain `host`, `project`, `flush_interval_ms`
- `configs/otel.yaml`: must contain `exporter_endpoint`, `service_name`, `batch_size`

### Environment Variables (add to `.env.example`)
```
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
OPENAI_API_KEY=
AGENT_LLM_MODEL=gpt-4o-mini
```

### Acceptance Criteria
- [ ] Every agent turn produces a Langfuse trace visible in the dashboard
- [ ] OTel spans nest correctly: `run → turn → perception → reasoning → action`
- [ ] `divergence_score` attribute is present on every `action_span`
- [ ] Traces are exportable to `traces/` directory as JSON
- [ ] Package works independently; no circular imports with `apps/`

---

## M-14 — Legibility: Epistemic Divergence Analysis

**File:** `apps/legibility/analysis/divergence.py`
**Owner module:** `apps/legibility/analysis/`
**Dependencies:** M-01, M-02

### Purpose
Implement the core epistemic divergence metric: the quantified gap between an agent's `AgentBeliefState` and the actual `WorldState` at each turn. This metric is the diagnostic heartbeat of the legibility layer.

### Deliverables

#### `compute_divergence_score` function

```python
def compute_divergence_score(
    belief: AgentBeliefState,
    truth: WorldState,
) -> float:
    """
    Compute the epistemic divergence score for an agent at a given turn.

    Score = (number of cells in belief map that differ from ground truth)
            / (total cells in agent's belief map)

    Range: 0.0 (perfect knowledge) to 1.0 (all known cells are wrong).
    Returns 0.0 if belief map is empty.
    """
```

#### `compute_divergence_timeseries` function

```python
def compute_divergence_timeseries(
    event_log_path: Path,
) -> dict[AgentID, list[tuple[TurnNumber, float]]]:
    """
    Replay an event log and compute divergence score at every turn for each agent.
    Returns a dict mapping agent_id → list of (turn, score) tuples.
    """
```

#### `find_divergence_spikes` function

```python
def find_divergence_spikes(
    timeseries: dict[AgentID, list[tuple[TurnNumber, float]]],
    threshold: float = 0.3,
) -> dict[AgentID, list[TurnNumber]]:
    """
    Returns turns where divergence exceeded threshold.
    These are candidate root-cause turns for failure analysis.
    """
```

### Acceptance Criteria
- [ ] Score is 0.0 for an agent whose every belief matches ground truth
- [ ] Score is 1.0 for an agent whose entire belief map is wrong
- [ ] Timeseries derived from a replayed log matches turn-by-turn divergence
- [ ] Unit tests in `tests/test_legibility/test_divergence.py`

---

## M-15 — Legibility: Causal Incident Report Generator

**File:** `apps/legibility/analysis/report.py`
**Owner module:** `apps/legibility/analysis/`
**Dependencies:** M-01, M-02, M-14

### Purpose
Generate a structured human-readable "Causal Incident Report" for any failed simulation run. The report must answer the three core legibility questions: What happened? Why did it happen? What should change next time?

### Deliverables

#### `CausalIncidentReport` Pydantic model

```python
class CausalIncidentReport(BaseModel):
    run_id: RunID
    termination_reason: TerminationReason
    final_turn: TurnNumber

    summary: str                          # 2-3 sentence plain English summary
    timeline: list[str]                   # Chronological list of key events
    root_cause_turns: dict[AgentID, list[TurnNumber]]  # Divergence spike turns
    root_cause_explanation: str           # Plain English explanation of root cause
    recommendations: list[str]            # Actionable suggestions for next run
```

#### `generate_report` function

```python
def generate_report(
    event_log_path: Path,
    termination_event: TerminationEvent,
) -> CausalIncidentReport:
```

- Replays the event log using M-06's `replay_from_log()`
- Computes divergence timeseries using M-14
- Identifies root cause turns (divergence spikes)
- Generates natural language sections using LLM call (model: `AGENT_LLM_MODEL`)
- Returns a frozen `CausalIncidentReport`

### Acceptance Criteria
- [ ] Report is generated for every failed run (non-win termination)
- [ ] `root_cause_turns` always contains divergence spike turns from M-14
- [ ] `recommendations` list is never empty for failed runs
- [ ] Report serializes to JSON cleanly

---

## M-16 — Legibility: Dashboard Views

**Files:** `apps/legibility/views/replay.py`, `apps/legibility/views/causal_graph.py`, `apps/legibility/views/timeline.py`, `apps/legibility/views/heatmaps.py`
**Owner module:** `apps/legibility/views/`
**Dependencies:** M-02, M-14, M-15

### Purpose
Implement the four Streamlit dashboard view components. Each view is a standalone function that renders a section of the legibility dashboard.

### Deliverables

#### `replay.py` — Dual-Perspective Replay
```python
def render_replay(event_log_path: Path, selected_turn: int) -> None:
```
- Two side-by-side grid renderings: "Ground Truth" (left) and "Agent A Belief" / "Agent B Belief" (selectable)
- Grid cells colored by type: wall (dark), floor (light), key (yellow), door (red/green), exit (blue), agent (purple)
- Turn slider to scrub through turns

#### `causal_graph.py` — Causal Failure Graph
```python
def render_causal_graph(report: CausalIncidentReport, event_log_path: Path) -> None:
```
- Directed acyclic graph (DAG) showing: root cause turn → decision → outcome → termination
- Nodes: divergence spike events; edges: causal relationships
- Use `streamlit-agraph` or `pyvis` for graph rendering

#### `timeline.py` — Gantt-Style Activity Timeline
```python
def render_timeline(event_log_path: Path) -> None:
```
- Horizontal Gantt chart: X-axis = turns, Y-axis = agents
- Bars colored by action type: move (green), observe (blue), interact (orange), communicate (purple), failed action (red)
- Uses Plotly for rendering

#### `heatmaps.py` — Belief Confidence & Divergence Heatmaps
```python
def render_heatmaps(event_log_path: Path, selected_agent: AgentID, selected_turn: int) -> None:
```
- Grid heatmap overlaid on dungeon layout
- Color intensity = divergence score at each cell position
- Turn slider to scrub through turns
- Uses Plotly heatmap

### Styling Requirements
- Must **not** use default Streamlit/Plotly color themes
- Use a dark dungeon aesthetic: dark background (`#1a1a2e`), muted cell colors, high-contrast agent markers
- All charts must have meaningful titles, axis labels, and legends

### Acceptance Criteria
- [ ] Each view renders without error when given a valid event log path
- [ ] Turn slider in replay view updates both ground truth and belief grids simultaneously
- [ ] Causal graph shows at least one edge from root cause to termination node
- [ ] Timeline shows all four tool types distinctly
- [ ] No default Streamlit blue/white/gray color scheme anywhere

---

## M-17 — Legibility: Streamlit App Entry Point

**File:** `apps/legibility/app.py`
**Owner module:** `apps/legibility/`
**Dependencies:** M-15, M-16

### Purpose
Wire the four dashboard views into a single Streamlit multi-page application. This is the human-facing diagnostic tool.

### Deliverables

**App structure:**
- Sidebar: run selector (dropdown of all `.jsonl` files in `runs/`) + refresh button
- Main area: tabbed interface with tabs: "Replay", "Causal Graph", "Timeline", "Heatmaps"
- Footer: run metadata (run ID, termination reason, final turn count)

**Tab routing:**
```python
tab1, tab2, tab3, tab4 = st.tabs(["🔁 Replay", "🔗 Causal Graph", "📊 Timeline", "🌡 Heatmaps"])
with tab1: render_replay(...)
with tab2: render_causal_graph(...)
with tab3: render_timeline(...)
with tab4: render_heatmaps(...)
```

**Launch command:** `streamlit run apps/legibility/app.py`

### Acceptance Criteria
- [ ] App loads without error when `runs/` directory is empty (shows "No runs found" message)
- [ ] Selecting a run loads all four tabs with correct data
- [ ] App is launchable with single command from repo root

---

## M-18 — Configuration & DevOps

**Files:** `pyproject.toml`, `requirements.txt`, `.env.example`, `configs/langfuse.yaml`, `configs/otel.yaml`
**Dependencies:** None

### Purpose
Set up project dependencies, configuration files, and environment variable templates. This must be completed before any other module can be run.

### Deliverables

#### `pyproject.toml`
```toml
[project]
name = "dungeon-agents-prove-ai"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "langgraph>=0.2",
    "langchain-openai>=0.2",
    "langfuse>=2.0",
    "opentelemetry-sdk>=1.24",
    "opentelemetry-exporter-otlp>=1.24",
    "pydantic>=2.7",
    "streamlit>=1.35",
    "plotly>=5.22",
    "pyvis>=0.3",       # or streamlit-agraph
    "python-dotenv>=1.0",
    "typer>=0.12",
    "uuid>=1.30",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

#### `requirements.txt`
Pin exact versions of all dependencies above (run `pip freeze` after `pyproject.toml` install).

#### `.env.example`
```
LANGFUSE_PUBLIC_KEY=your_key_here
LANGFUSE_SECRET_KEY=your_secret_here
LANGFUSE_HOST=https://cloud.langfuse.com
OPENAI_API_KEY=your_openai_key_here
AGENT_LLM_MODEL=gpt-4o-mini
```

#### `configs/langfuse.yaml`
```yaml
project: dungeonAgents-ProveAI
host: ${LANGFUSE_HOST}
flush_interval_ms: 500
debug: false
```

#### `configs/otel.yaml`
```yaml
service_name: dungeonAgents-ProveAI
exporter_endpoint: http://localhost:4318/v1/traces
batch_size: 512
export_interval_ms: 1000
```

### Acceptance Criteria
- [ ] `pip install -e .` succeeds from repo root
- [ ] `pytest tests/` runs without import errors (tests may fail if LLM keys are absent)
- [ ] `.env.example` documents every required environment variable

---

## M-19 — Tests: Environment

**Files:** `tests/test_environment/test_grid.py`, `tests/test_environment/test_perception.py`
**Dependencies:** M-03, M-04

### Purpose
Unit test the grid state machine and fog-of-war engine. These tests must not require LLM API keys or network access.

### Test Cases

#### `test_grid.py`
- `test_grid_minimum_size`: assert 8×8 grid is created
- `test_required_elements`: assert exactly one key, one door, one exit
- `test_no_agent_overlap`: assert agent start positions are on floor tiles and differ
- `test_seed_reproducibility`: same seed → identical grids
- `test_passable_cells`: walls and locked doors return `False` from `is_passable()`

#### `test_perception.py`
- `test_corner_agent_sees_4_cells`
- `test_edge_agent_sees_6_cells`
- `test_interior_agent_sees_9_cells`
- `test_no_information_leak`: cells outside viewport not in `visible_cells`
- `test_perception_at_boundary`: agent at (0,0) sees only (0,0), (0,1), (1,0), (1,1)

### Acceptance Criteria
- [ ] All tests pass with `pytest tests/test_environment/`
- [ ] No network calls in any test
- [ ] Tests are deterministic (use fixed seeds)

---

## M-20 — Tests: Agent Tools

**File:** `tests/test_agents/test_tools.py`
**Dependencies:** M-07, M-08

### Purpose
Unit test agent tool validation and belief state updates without requiring LLM calls.

### Test Cases
- `test_move_into_wall_fails`: `validate_move()` returns `(False, ...)`
- `test_move_into_floor_succeeds`: returns `(True, ..., new_pos)`
- `test_pick_up_key_succeeds`: correct `state_mutations_dict`
- `test_unlock_door_requires_key`: fails without key
- `test_communicate_self_fails`: sender == recipient returns `(False, ...)`
- `test_belief_updates_from_perception`: belief map grows after each perception
- `test_belief_preserves_stale_positions`: previously seen agent position retained

### Acceptance Criteria
- [ ] All tests pass with `pytest tests/test_agents/`
- [ ] Mock the Orchestrator; no real game state needed

---

## M-21 — Tests: Legibility / Divergence

**File:** `tests/test_legibility/test_divergence.py`
**Dependencies:** M-14

### Purpose
Unit test the divergence computation with synthetic belief and world state fixtures.

### Test Cases
- `test_zero_divergence`: belief matches truth → score = 0.0
- `test_full_divergence`: all beliefs wrong → score = 1.0
- `test_partial_divergence`: known formula → exact float comparison
- `test_empty_belief_map`: returns 0.0 (not ZeroDivisionError)
- `test_spike_detection_threshold`: spike detected above 0.3, not below

### Acceptance Criteria
- [ ] All tests pass with `pytest tests/test_legibility/`
- [ ] No network calls; all fixtures are synthetic

---

## Non-Functional Requirements (applies to all modules)

| Requirement | Specification |
|---|---|
| **Immutability** | All Pydantic models must be frozen. Event logs are append-only. |
| **Determinism** | Same seed + same LLM responses → identical game replay |
| **No Information Leakage** | Agents never see ground truth. Strictly enforce fog-of-war. |
| **Commit History** | Regular commits from first working module. Do not squash. |
| **AI Tool Logs** | All AI assistant conversations must be preserved (do not delete) |
| **Run Artifacts** | Produce at least 3 runs: 1 win, 1 turn_limit, 1 stuck (or 2 of any failure type) |
| **Trace Export** | Export Langfuse traces to `traces/` as JSON after each successful run |
| **Video Deliverable** | 1–3 minute Loom video walkthrough required (out of scope for code agents) |

---

## Build Order Recommendation (for sequential builds)

```
Phase 1 (Foundation):    M-18 → M-01 → M-02
Phase 2 (Environment):   M-03 → M-04 → M-05 → M-06
Phase 3 (Agent Infra):   M-07 → M-08 → M-13
Phase 4 (LLM Agents):    M-09 → M-10
Phase 5 (Game Loop):     M-11 → M-12
Phase 6 (Legibility):    M-14 → M-15 → M-16 → M-17
Phase 7 (Tests):         M-19 → M-20 → M-21
```

## Parallel Build Opportunities

| Parallel Group | Modules | Can start after |
|---|---|---|
| Group A | M-18, (M-01 if stubs ready) | — |
| Group B | M-03, M-04, M-05 | M-01, M-02 complete |
| Group C | M-13, M-08 | M-01, M-02 complete |
| Group D | M-14, M-15 | M-02 complete |
| Group E | M-19, M-20, M-21 | Their deps complete |
| Group F | M-16, M-17 | M-14, M-15 complete |
