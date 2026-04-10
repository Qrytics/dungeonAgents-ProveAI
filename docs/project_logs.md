# Project Workflow

**Start Time: 10:52 AM**

**End Time: 2:35 PM** (Untested Ver) **[Time Elapsed: 3:35]**

**Test Time: 3:04 PM** 

### Phase 1: Analysis & Requirements Discovery
* **Initial Review:** Perform a comprehensive read-through of the primary specification: `dungeon_agents_v3.pdf`.
* **Requirement Extraction:** Utilize Gemini to extrapolate the absolute "Ground Truths," including deliverable specifications, MVP definitions, and hard technical requirements.
* **Documentation:** Formalize these findings into a `GROUND_TRUTH.md` file to serve as the project's primary reference point.

### Phase 2: Repository & Architecture Setup
* **Monorepo Initialization:** Create a monorepo structure to facilitate integrated file management and polyglot development.
* **Baseline Documentation:** Upload the original assignment PDF and the newly created `GROUND_TRUTH.md` into a dedicated `docs/` folder.
* **Architectural Research:** Engage Gemini "Deep Research" mode to determine the optimal tech stack (e.g., LangGraph, Python, Langfuse) and a robust monorepo architecture.
* **Strategic Planning:** Save the resulting research paper into the `docs/` folder to provide architectural context for the build.

### Phase 3: Automated Scaffolding
* **Agentic Orchestration:** Utilize a Copilot or AI agent to process the research paper and specifications.
* **Repository Bootstrapping:** Have the agent submit a Pull Request (PR) to set up the basic folder scaffolding, including `/apps`, `/packages`, and shared configuration files.

### Phase 4: Modular Implementation
* **Workstream A: Core Engine & State Machine**
    * Implementing the langgraph state transitions for the Dungeon Master (DM) and the Turn-based loop.
    * Ensuring the Deterministic Replay logic is functional for debugging without LLM costs.
* **Workstream B: Agent Perception & Tooling**
    * Building out the Pydantic schemas for Movement, Attack, and Examine tools.
    * Testing the "Fog of War" logic to ensure agents only receive local grid data.
* **Workstream C: Legibility Layer (Dashboard)**
    * Setting up the Streamlit interface to visualize the runs.jsonl output in real-time.
    * Integrating Langfuse trackers to monitor token consumption and "Epistemic Divergence."

### Phase 5: Running & Testing
* **Environment Validation:** Verify Python 3.12+ environment and Langfuse connectivity using the `auth_check()` script.
* **Execution:** Run the primary simulation using the module runner:
    ```bash
    python -m apps.simulation.main --verbose
    ```
* **Trace Verification:** Confirm that traces are appearing in the [Langfuse Dashboard](https://us.cloud.langfuse.com/project/cmnt97hcb00dcad07fvxigbwo/traces) with correct spans for Perception, Reasoning, and Action.
* **Automated Testing:** Execute the suite to ensure modular integrity:
    ```bash
    pytest
    ```
* **Legibility Check:** Launch the Streamlit dashboard to visualize the `runs.jsonl` data:
    ```bash
    streamlit run apps/legibility/app.py
    ```
