# ADR-070: ReAct Execution Mode

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-04-08 |
| **Related** | ADR-001 (LangGraph Multi-Agent System), ADR-003 (Human-in-the-Loop Plan-Level) |

## Context

LIA's current pipeline (Planner → direct tool execution → Response) is efficient but cannot adapt mid-execution. Once the planner produces an ExecutionPlan and the task orchestrator begins executing tools, the system follows the plan rigidly — it cannot react to unexpected tool outputs, refine its approach based on intermediate results, or autonomously decide to call additional tools.

The **ReAct pattern** (Reasoning + Acting, Yao et al. 2022) enables iterative reasoning interleaved with tool calls: the LLM observes each tool result, reasons about the next step, and decides whether to act again or finalize. This is particularly valuable for exploratory tasks, multi-step research, and scenarios where the optimal tool sequence cannot be determined upfront.

## Decision

### Add an Alternative ReAct Execution Mode

Implement ReAct as a **user-toggleable preference** alongside the existing pipeline mode. The ReAct loop is implemented as **4 nodes in the parent LangGraph graph** (not a subgraph), avoiding known LangGraph bugs with dynamic subgraph interrupts (#5863, #4796).

### Architecture: 4-Node ReAct Loop

```
react_setup → react_call_model ←→ react_execute_tools → react_finalize → response
```

1. **`react_setup`**: Initializes ReAct state (iteration counter, system prompt with tool descriptions, conversation context). Entry point from the router when ReAct mode is active.

2. **`react_call_model`**: Invokes the ReAct LLM with the current message history. The model either produces tool calls (→ `react_execute_tools`) or a final answer (→ `react_finalize`). Conditional edge based on presence of tool calls in the response.

3. **`react_execute_tools`**: Executes the requested tools. HITL approval is handled via native `interrupt()` at this node level (not in a subgraph), ensuring clean checkpoint/resume semantics. Implements an **idempotence pattern** for multi-interrupt re-execution: each tool call is tagged with a unique ID, and completed calls are skipped on resume.

4. **`react_finalize`**: Post-processes the final answer (display card rendering, memory extraction, psyche evaluation) and routes to the standard `response` node.

### Key Design Choices

1. **Parent graph nodes, not subgraph**: LangGraph has known issues with `interrupt()` inside dynamically spawned subgraphs (#5863: checkpoint corruption, #4796: resume routing failures). By placing ReAct nodes directly in the parent graph, we inherit the battle-tested interrupt/resume infrastructure used by the existing pipeline.

2. **Dedicated LLM type `react_agent`**: Configured with `qwen3.5-plus` (thinking medium) — a model with strong reasoning capabilities at moderate cost. Configurable via the existing LLM admin UI like all other LLM types.

3. **User toggle**: Persisted as a user preference in the database (`execution_mode: "pipeline" | "react"`). Exposed as a toggle on the chat page UI. The router node reads this preference to determine which execution path to take.

4. **Shared infrastructure**: ReAct mode reuses the same tool registry, tool implementations, HITL classifier, catalogue manifests, and display components as the pipeline mode. No tool duplication.

5. **Iteration guard**: Maximum iteration count (configurable, default 10) prevents runaway loops. Each iteration is logged with structured metrics for observability.

## Trade-offs

### ReAct Mode

| Aspect | Characteristic |
|--------|----------------|
| **LLM calls** | 3-10x more per conversation turn |
| **Adaptability** | High — can react to unexpected results and adjust strategy |
| **Autonomy** | High — LLM decides tool sequence dynamically |
| **Cost** | Higher token consumption per turn |
| **Latency** | Higher — sequential reasoning/acting cycles |
| **Best for** | Exploratory tasks, research, complex multi-step scenarios |

### Pipeline Mode (existing)

| Aspect | Characteristic |
|--------|----------------|
| **LLM calls** | 2-4 per turn (planner + orchestrator + response) |
| **Adaptability** | Low — follows pre-determined plan |
| **Autonomy** | Low — plan is fixed before execution |
| **Cost** | Economical, predictable |
| **Latency** | Fast — parallel tool execution in orchestrator |
| **Best for** | Well-defined tasks, routine operations, cost-sensitive usage |

### Shared Between Both Modes

- Tool registry and implementations
- HITL approval infrastructure
- Display card rendering
- Memory extraction and psyche evaluation
- Observability (Prometheus metrics, Langfuse tracing)
- SSE streaming to frontend

## Consequences

### Positive

- Users can choose the execution style that best fits their task
- Exploratory and research-heavy queries get significantly better results
- The LLM can recover from tool errors and try alternative approaches
- No disruption to existing pipeline mode — purely additive

### Negative

- Higher token costs when ReAct mode is active (3-10x per turn)
- Additional complexity in the graph definition (4 new nodes, conditional routing)
- Two execution paths to maintain and test
- Potential user confusion about when to use which mode

### Risks

- ReAct loops may hit iteration limits on complex tasks, producing incomplete results
- Cost unpredictability: users may leave ReAct mode enabled for simple tasks
- Model quality dependency: ReAct requires strong reasoning capabilities; weaker models may loop ineffectively

## References

- Yao, S. et al. (2022). ReAct: Synergizing Reasoning and Acting in Language Models. arXiv:2210.03629
- LangGraph issue #5863: Dynamic subgraph interrupt checkpoint corruption
- LangGraph issue #4796: Subgraph resume routing failures
