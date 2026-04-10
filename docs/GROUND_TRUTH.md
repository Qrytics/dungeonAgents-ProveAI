# Project Constraints: Dungeon Agents

This document serves as the absolute "Source of Truth" for the project requirements and deliverable specifications.

## 1. World & Simulation Rules
* **Grid Size:** The dungeon must be at least an $8\times8$ grid.
* **Required Elements:** The world must include a locked door, a key, random obstacles or interior walls, and an exit.
* **Starting Positions:** Agent starting positions must be randomized.
* **Success Condition:** Both agents must reach the exit to meet the shared objective; one specifically needs the key for the door.
* **Fog of War:** Each agent is strictly limited to seeing only adjacent cells.
* **Information Parity:** Agents must not have more information than what is currently available to them in their local state.

## 2. Agent & Turn Mechanics
* **Tooling:** Each agent is an LLM equipped with tools to move, observe surroundings, interact with items, and communicate.
* **Execution Loop:** Agents take turns; each turn, an agent receives its observable state and picks exactly one tool call.
* **Communication Lag:** Messages between agents must be delivered on the following turn, not instantly.
* **Termination:** The game ends when the objective is met, a turn limit is hit, or both agents are stuck.

## 3. Observability & Traces (The Priority)
* **Tool Integration:** An observability tool (e.g., Langfuse or OpenTelemetry) must be integrated to capture and export all traces.
* **Trace Scope:** Traces must include tool calls, full LLM inputs/outputs, and latency.
* **Event Schema:** You must design and log a structured event record at each agent step.
* **Diagnostic Goal:** Traces must help a human determine if a failure was in a single agent's decision, the interaction between agents, or emergent from the system.

## 4. The Legibility Layer
* **Core Questions:** The layer must help a human answer: What happened? Why did it happen? What should change next?.
* **Human Intent:** The output must feel intentional and reflect human "taste" and opinions, explicitly avoiding "default AI styling".

## 5. Submission & Process Requirements
* **Version Control:** Use a GitHub repo with regular commits from the start; do not squash the history.
* **Required Files:**
    * Full source code.
    * Exported traces from the observability tool.
    * Multiple runs as structured JSON, including both "successes" and "failures".
    * **Full AI conversation history:** Complete logs from AI coding tools are required as high-priority signal.
* **Video Component:** A 1 to 3-minute Loom video walking through the decisions and the "why" behind the build.
