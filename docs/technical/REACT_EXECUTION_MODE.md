# ReAct Execution Mode

| Version | Date | ADR |
|---------|------|-----|
| 1.0 | 2026-04-09 | [ADR-070](../architecture/ADR-070-ReAct-Execution-Mode.md) |

## Table of Contents

1. [Overview](#overview)
2. [Pipeline vs ReAct](#pipeline-vs-react)
3. [Architecture](#architecture)
4. [Graph Wiring](#graph-wiring)
5. [Nodes](#nodes)
6. [Tool System](#tool-system)
7. [HITL in ReAct](#hitl-in-react)
8. [Token Tracking](#token-tracking)
9. [Skills Integration](#skills-integration)
10. [Configuration](#configuration)
11. [Streaming Step Visibility](#streaming-step-visibility-v1162)
12. [Key Files](#key-files)

---

## Overview

ReAct (Reasoning + Acting, Yao et al. 2022) is an alternative execution mode to the pipeline. Instead of planning all steps upfront then executing them, the LLM iteratively reasons about each tool result and decides the next action autonomously.

The user toggles between modes via a frontend toggle (Zap icon). The preference is persisted in the `users.execution_mode` column (`"pipeline"` or `"react"`).

## Pipeline vs ReAct

| Aspect | Pipeline | ReAct |
|--------|----------|-------|
| **Flow** | Router → Planner → Orchestrator → Agents → Response | Router → ReAct Loop → Response |
| **Planning** | Upfront (ExecutionPlan DSL) | None — LLM decides step by step |
| **Adaptability** | Rigid — follows plan | Adaptive — pivots on tool results |
| **Tool selection** | Planner selects by domain | LLM chooses from all available tools |
| **Token cost** | Lower (1 planner + 1 response LLM call) | Higher (1 LLM call per iteration) |
| **Best for** | Well-structured requests, multi-domain | Exploratory, research, ambiguous queries |
| **HITL** | Plan-level approval + tool-level drafts | Tool-level interrupt per mutation |
| **Initiative** | Dedicated initiative_node (LLM evaluation) | Integrated in ReAct prompt (CROSS-CHECK step) |

## Architecture

Custom ReAct loop as **4 nodes in the parent LangGraph graph** (not a `create_react_agent` subgraph — avoided due to LangGraph bugs with dynamic tool interrupts, GitHub #5863/#4796):

```
                          ┌──────────────────────────┐
                          │       Router Node        │
                          └──────────┬───────────────┘
                 execution_mode?     │
              ┌──────────────────────┼──────────────────────┐
              │ "pipeline"           │ "react"               │
              ▼                      ▼                       │
       ┌──────────┐          ┌──────────────┐               │
       │ Planner  │          │ react_setup  │               │
       └────┬─────┘          └──────┬───────┘               │
            │                       │                       │
            ▼                       ▼                       │
     ┌──────────────┐       ┌───────────────┐              │
     │ Orchestrator │       │react_call_model│◄────┐       │
     └──────┬───────┘       └───────┬───────┘     │       │
            │                       │              │       │
            ▼                tool_calls?           │       │
     ┌──────────┐          yes │        no │       │       │
     │ Agents   │              ▼           ▼       │       │
     └────┬─────┘   ┌─────────────────┐ ┌────────┐│       │
          │         │react_exec_tools │ │finalize││       │
          ▼         └────────┬────────┘ └───┬────┘│       │
     ┌──────────┐            │              │      │       │
     │Initiative│            └──────────────┘      │       │
     └────┬─────┘                                  │       │
          │                                        │       │
          ▼                                        ▼       │
       ┌─────────────────────────────────────────────┐     │
       │              Response Node                   │     │
       └─────────────────────────────────────────────┘     │
```

Each node benefits from the parent graph's PostgreSQL checkpointer, so `interrupt()` works natively in `react_execute_tools` for HITL on mutation tools.

## Graph Wiring

```python
# graph.py — ReAct edges
graph.add_edge(NODE_REACT_SETUP, NODE_REACT_CALL_MODEL)
graph.add_conditional_edges(
    NODE_REACT_CALL_MODEL,
    route_from_react_call_model,  # → execute_tools or finalize
    {
        NODE_REACT_EXECUTE_TOOLS: NODE_REACT_EXECUTE_TOOLS,
        NODE_REACT_FINALIZE: NODE_REACT_FINALIZE,
    },
)
graph.add_edge(NODE_REACT_EXECUTE_TOOLS, NODE_REACT_CALL_MODEL)  # Loop
graph.add_edge(NODE_REACT_FINALIZE, NODE_RESPONSE)
```

Routing from router: when `execution_mode == "react"` and the router classifies the query as actionable, it routes to `NODE_REACT_SETUP` instead of `NODE_PLANNER`.

## Nodes

### react_setup

Prepares tools, system prompt, and context for the ReAct loop:
- Selects ALL available tools via `ReactToolSelector` (filtered by active connectors)
- Builds system prompt from `react_agent_prompt.txt`
- Injects memory context (resolved references + memory facts)
- Injects active skills catalogue (L1, filtered by `active_skills_ctx`)
- Sets `react_start_time` for timeout enforcement
- Stores tool names and HITL map in state (JSON-serializable)

### react_call_model

Calls the ReAct LLM with bound tools:
- Recreates LLM and tool bindings each iteration (~1-2ms)
- Applies message windowing (preserves current turn, windows history)
- Returns AIMessage with or without `tool_calls`

### react_execute_tools

Executes tools from the last AIMessage:
- HITL: mutation tools trigger `interrupt()` for user approval
- Idempotence: on re-execution after interrupt resume, already-resolved tool calls are skipped
- ToolRuntime injection via `_build_tool_runtime()` (same pattern as pipeline)
- Registry items accumulated across iterations via `current_turn_registry` merge

### react_finalize

Collects iteration count and prepares metadata for the response node:
- Records Prometheus metrics (iterations, duration, executions)
- Sets `react_agent_result` for the response node passthrough

## Tool System

The ReAct agent receives ALL available tools (not domain-filtered like the planner):
- Filtered by active connectors (`get_request_tool_manifests()`)
- Capped by `REACT_AGENT_MAX_TOOLS` (default: 25)
- Wrapped in `ReactToolWrapper` for string conversion + registry collection
- HITL map built from tool manifests (`permissions.hitl_required`)

Tools are NOT stored in state (non-serializable). Tool names and HITL map are stored instead, and tools are rebuilt in each node that needs them.

## HITL in ReAct

Mutation tools (e.g., `send_email_tool`, `create_event_tool`) trigger `interrupt()` in `react_execute_tools`. The graph pauses and waits for user approval.

On resume, LangGraph replays the node. The idempotence pattern skips tool calls that already have a `ToolMessage` in state (matched by `tool_call_id`).

## Token Tracking

Token tracking works for all providers through the `TokenTrackingCallback`:
- The `node_breakdown` in tracking summary aggregates tokens by node name (sum across iterations)
- For OpenAI models using the Responses API with tools, the call is redirected to Chat Completions which provides `usage_metadata` on the response

Safety limits:
- **Max iterations**: `REACT_AGENT_MAX_ITERATIONS` (default: 15)
- **Hard timeout**: `REACT_AGENT_TIMEOUT_SECONDS` (default: 120s), checked in routing function

## Skills Integration

Skills are available to the ReAct agent through the same mechanism as the pipeline:
- The filtered L1 skills catalogue is injected as a `SystemMessage` in `react_setup`
- The 3 existing skill tools (`activate_skill_tool`, `run_skill_script`, `read_skill_resource`) are in the tool catalogue and available to the ReAct agent
- Active skill filtering uses `active_skills_ctx` (same per-request context as pipeline)

## Configuration

```env
# .env
REACT_AGENT_ENABLED=true              # Feature flag
REACT_AGENT_MAX_ITERATIONS=15         # Max ReAct loop iterations
REACT_AGENT_TIMEOUT_SECONDS=120       # Hard timeout for entire execution
REACT_AGENT_MAX_TOOLS=25              # Max tools bound to LLM
REACT_AGENT_HISTORY_WINDOW_TURNS=5    # Conversation history window
```

LLM type: `react_agent` — configurable in admin LLM config panel.
Default: `qwen3.5-plus`, temperature 0.0, reasoning_effort medium, max_tokens 16000.

## Streaming Step Visibility (v1.16.2)

During ReAct execution, the frontend displays accumulated execution steps in real time:

1. **Node-level steps**: Each ReAct node transition (`react_setup` → `react_call_model` → `react_execute_tools` → `react_finalize`) emits an `execution_step` SSE event via the "updates" stream mode.

2. **Per-tool steps**: When `react_call_model` produces an AIMessage with `tool_calls`, the streaming service inspects the state delta and emits individual `execution_step` events for each tool (e.g., "Retrieving contacts...", "Retrieving events..."), using the tool catalogue's `DisplayMetadata` for emoji and i18n_key.

3. **Reasoning detail**: The AIMessage content (reasoning text) from `react_call_model` is extracted, cleaned of markdown formatting, truncated to 120 characters, and included as a `detail` field in the node-level execution_step event.

4. **Frontend accumulation**: Steps are accumulated in a multi-line progress message (not replaced). All steps remain visible until the first response token arrives. Deduplication by `i18n_key` prevents duplicates.

## Key Files

| File | Purpose |
|------|---------|
| `src/domains/agents/nodes/react_nodes.py` | 4 node functions |
| `src/domains/agents/tools/react_tool_wrapper.py` | Tool wrapper (string output + registry) |
| `src/domains/agents/services/react_tool_selector.py` | Tool selection (all available, capped) |
| `src/domains/agents/prompts/v1/react_agent_prompt.txt` | System prompt |
| `src/domains/agents/nodes/routing.py` | `route_from_react_call_model()` |
| `src/domains/agents/graph.py` | Graph wiring (edges + conditional) |
| `src/domains/agents/models.py` | State fields (react_*, schema 1.2) |
| `src/domains/agents/utils/execution_metadata.py` | Debug panel display metadata |
| `docs/architecture/ADR-070-ReAct-Execution-Mode.md` | Architecture decision record |
