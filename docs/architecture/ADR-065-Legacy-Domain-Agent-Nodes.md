# ADR-065: Legacy Domain Agent LangGraph Nodes — Dead Code Analysis

**Status**: ✅ ACCEPTED
**Date**: 2026-03-26
**Deciders**: JGO, Claude Code
**Technical Story**: Debug panel investigation revealed domain agent LLM types are never invoked

---

## Context and Problem Statement

While investigating why domain agent LLM types (e.g., `event_agent`, `contact_agent`) configured
in Administration > LLM Configuration did not appear in the debug panel's LLM Pipeline section,
we discovered that **domain agent LangGraph nodes are never traversed** in the current architecture.

**Question**: Are domain agent LangGraph nodes (built with `create_agent_wrapper_node`) still
reachable in the current graph routing, or are they dead code?

---

## Decision Drivers

### Must-Have (Non-Negotiable):
1. Zero risk of breaking existing functionality
2. Clear documentation of legacy vs active code paths
3. Understanding of which LLM types in admin are actually used at runtime

### Nice-to-Have:
- Reduced graph complexity and memory footprint
- Fewer misleading LLM configuration options in admin panel
- Cleaner codebase

---

## Investigation Findings

### Architecture Evolution

The LangGraph graph evolved through several phases:

| Phase | Architecture | Domain Agents |
|-------|-------------|---------------|
| V1 (Legacy) | Router → TaskOrchestrator → **Agent Nodes** → Response | ✅ Used as ReAct agents |
| V2 (Phase 5.2B) | Router → Planner → TaskOrchestrator → `execute_plan_parallel()` → Response | ❌ Bypassed |
| V3 (Phase 6) | Binary Router (planner/response only) | ❌ Unreachable |

### Current Flow (V3)

```
User Message
  → Router (binary: planner | response)
  → Planner (generates ExecutionPlan)
  → SemanticValidator → ApprovalGate
  → TaskOrchestrator
      → _handle_execution_plan()
      → execute_plan_parallel()  ← calls tools DIRECTLY, no agent LLM
  → Initiative
  → Response
```

The `parallel_executor` calls tools (e.g., `get_events_tool`) via direct invocation.
It does **not** invoke domain agent ReAct loops (which would use the configured LLM).

### Why Agent Nodes Are Unreachable

1. **`route_from_router()`** returns only `NODE_PLANNER` or `NODE_RESPONSE` — never a domain agent
2. **`task_orchestrator_node()`** checks for `execution_plan` first (always present from planner)
   and calls `_handle_execution_plan()` which returns directly
3. The legacy path (`create_orchestration_plan()` + `get_next_agent_from_plan()`) is only
   reached when `execution_plan` is `None`, which cannot happen when the planner runs
4. Even the safety guard redirects any legacy `"task_orchestrator"` router output to `"planner"`

### Proof from Production Logs

Token tracking callback events for query "mes deux prochains rdv ?":

```
1. semantic_pivot      ← LLM call ✅
2. query_analyzer      ← LLM call ✅
3. planner_single_domain ← LLM call ✅
4. (tools executed directly by parallel_executor — NO LLM)
5. initiative          ← LLM call ✅
6. response            ← LLM call ✅
```

No domain agent LLM call recorded. The `event_agent` node was never invoked.

### Affected Components

#### Dead Code (Graph Nodes)

| File | Lines | Content |
|------|-------|---------|
| `graph.py` | 464-577 | 13 `build_agent_wrapper()` + `graph.add_node()` calls |
| `graph.py` | 660-684 | Conditional edges from orchestrator to agent nodes |
| `graph.py` | 691-704 | Static edges from agents to `NODE_INITIATIVE` |
| `orchestrator.py` | 37-109 | `create_orchestration_plan()` (legacy routing) |
| `orchestrator.py` | 142-210 | `get_next_agent_from_plan()` (legacy sequential) |
| `base_agent_builder.py` | 369-611 | `create_agent_wrapper_node()` (wrapper for graph nodes) |

#### Still Used (Keep)

| Component | Reason |
|-----------|--------|
| `AGENT_*` constants | Used in domain taxonomy, manifests, result tracking, tool context |
| `*_agent_builder.py` files | `build_generic_agent()` creates agents, but they're only registered in graph nodes that are never called. The tools themselves are direct LangChain `@tool` functions. |
| Tool files (`*_tools.py`) | Called directly by `parallel_executor` — these are the active code |
| LLM types in `LLM_TYPES_REGISTRY` | Configured but unused at runtime for domain agents |

#### Admin LLM Configuration (Misleading)

These LLM types appear in Admin > LLM Configuration but are **never invoked at runtime**:

- `contact_agent`, `email_agent`, `event_agent`, `file_agent`, `task_agent`
- `query_agent`, `weather_agent`, `wikipedia_agent`, `perplexity_agent`
- `place_agent`, `route_agent`, `brave_agent`, `web_search_agent`, `web_fetch_agent`
- `browser_agent`, `hue_agent` (browser uses `ReactSubAgentRunner` directly via tool)

---

## Considered Options

### Option 1: Document and Keep (Current Decision)

**Approach**: Document the dead code, add inline comments, keep nodes in graph for safety.

**Pros**:
- ✅ Zero risk of regression
- ✅ Serves as architectural documentation
- ✅ Legacy path available as theoretical fallback
- ✅ No code changes needed

**Cons**:
- ❌ ~300 lines of dead code in graph.py
- ❌ 15 unused LLM types in admin panel confuse administrators
- ❌ Misleading debug panel (users expect to see agent LLM calls)

**Verdict**: ✅ ACCEPTED (short-term)

### Option 2: Remove Agent Nodes from Graph

**Approach**: Remove all `graph.add_node(AGENT_*)` calls, associated edges, and legacy
orchestration plan logic. Keep constants, tools, and manifests.

**Pros**:
- ✅ Cleaner graph (~300 fewer lines)
- ✅ Reduced memory (no compiled agent subgraphs)
- ✅ No misleading LLM types in admin
- ✅ Clearer architecture for contributors

**Cons**:
- ❌ Requires thorough testing
- ❌ Removes theoretical fallback path
- ❌ Must verify no edge case triggers legacy path

**Verdict**: 🎯 PROPOSED for future cleanup (Phase 2)

### Option 3: Repurpose Agent Nodes as Enhanced Execution

**Approach**: Instead of removing, make domain agent nodes the execution path again
by routing `parallel_executor` through agent ReAct loops for complex multi-step tool calls.

**Pros**:
- ✅ Agent LLMs would be used (justifies admin config)
- ✅ ReAct loop can handle tool errors and retry
- ✅ More intelligent tool parameter inference

**Cons**:
- ❌ Higher token cost (agent LLM call + tool call vs just tool call)
- ❌ Higher latency (additional LLM roundtrip per domain)
- ❌ Planner already handles parameter inference
- ❌ Significant refactoring effort

**Verdict**: ❌ REJECTED (cost/latency outweigh benefits)

---

## Decision Outcome

**Chosen option: Option 1 (Document and Keep)**

The domain agent LangGraph nodes are legacy dead code since Phase 5.2B (parallel executor).
They are documented here and marked with inline comments. A future cleanup PR (Option 2)
can remove them when the team is confident the legacy path is no longer needed.

### Immediate Actions
- [x] Document findings in this ADR
- [ ] Add `# LEGACY: Dead code since Phase 5.2B` comments to affected code
- [ ] Consider hiding unused LLM types from admin panel
- [ ] Consider future cleanup PR to remove agent nodes

### Impact on Debug Panel
The debug panel correctly shows all LLM calls that actually occur. Domain agent LLM calls
do not appear because they are never made — this is expected behavior, not a bug.

---

## References

- ADR-014: ExecutionPlan & Parallel Executor Pattern (introduced the bypass)
- `src/domains/agents/graph.py` — Graph construction with agent nodes
- `src/domains/agents/nodes/task_orchestrator_node.py` — Execution plan dispatch
- `src/domains/agents/orchestration/parallel_executor.py` — Direct tool execution
- `src/domains/agents/graphs/base_agent_builder.py` — Agent wrapper (unused)
