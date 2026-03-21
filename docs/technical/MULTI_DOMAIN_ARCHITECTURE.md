# Multi-Domain Architecture

> **Technical Documentation** - Multi-Domain Query Processing
>
> **Version**: 2.0
> **Date**: 2025-12-26
> **Architecture**: parallel_executor based

## Overview

The Multi-Domain Architecture enables the LIA assistant to handle queries spanning multiple domains (contacts, emails, calendar, tasks, drive, weather, etc.) in a single request, with automatic domain detection, parallel execution, and intelligent result composition.

## Architecture Components

### Core Pipeline

```
User Input
    |
    v
+-------------------+
|   router_node     |  Intent classification (actionable vs conversational)
|   (gpt-4.1-mini)   |  Returns: routing_history, detected_domains
+--------+----------+
         |
    [ACTIONABLE]
         v
+-------------------+
|   planner_node    |  Generates ExecutionPlan with steps
|   (gpt-4.1-mini)   |  Validates semantic correctness
+--------+----------+
         |
         v
+-------------------+
| semantic_validator|  Validates plan semantics
|   (gpt-4.1-mini)   |  May trigger clarification
+--------+----------+
         |
         v
+-------------------+
| approval_gate     |  HITL: User approves plan
|   (interrupt)     |  Cost estimation
+--------+----------+
         |
         v
+------------------------+
| task_orchestrator_node |  Dispatches to parallel_executor
|                        |  Manages execution flow
+--------+---------------+
         |
         v
+-------------------+
| parallel_executor |  Executes tools in parallel waves
| (asyncio.gather)  |  Handles dependencies
+--------+----------+
         |
         v
+-------------------+
|   response_node   |  Synthesizes results (INTELLIA v10)
|   (gpt-4.1-mini)   |  JSON + Few-Shot formatting
+-------------------+
         |
         v
    [SSE Response]
```

### File Structure

```
apps/api/src/domains/agents/
|-- nodes/
|   |-- router_node_v3.py           # Intent classification
|   |-- planner_node_v3.py          # Plan generation (1574 lines)
|   |-- task_orchestrator_node.py # Execution dispatcher
|   |-- response_node.py         # Response synthesis
|   `-- semantic_validator.py    # Plan validation
|
|-- orchestration/
|   |-- __init__.py              # Public exports
|   |-- parallel_executor.py     # Parallel execution engine
|   |-- schemas.py               # ExecutionPlan, StepResult, etc.
|   |-- mappers.py               # Result mapping
|   |-- condition_evaluator.py   # Conditional step logic
|   |-- dependency_graph.py      # Dependency analysis
|   |-- adaptive_replanner.py    # INTELLIPLANNER Phase E
|   `-- validator.py             # Plan validation
|
|-- tools/
|   |-- contacts_tools.py        # Google Contacts tools
|   |-- emails_tools.py          # Email tools (Gmail, Outlook)
|   |-- calendar_tools.py        # Google Calendar tools
|   |-- drive_tools.py           # Google Drive tools
|   |-- tasks_tools.py           # Google Tasks tools
|   |-- weather_tools.py         # OpenWeatherMap tools
|   |-- wikipedia_tools.py       # Wikipedia tools
|   |-- perplexity_tools.py      # Perplexity search tools
|   `-- hue_tools.py             # Philips Hue smart home tools
```

## Component Details

### 1. Router Node

Classifies user intent and detects relevant domains.

```python
# Output structure
RouterOutput:
    classification: "actionable" | "conversational"
    confidence: float  # 0.0 - 1.0
    detected_domains: list[str]  # ["contacts", "emails", ...]
    reasoning: str
```

### 2. Planner Node

Generates structured execution plans.

```python
# ExecutionPlan structure
ExecutionPlan:
    plan_id: str
    steps: list[ExecutionStep]
    metadata: PlanMetadata

ExecutionStep:
    step_id: str
    tool_name: str
    args: dict
    depends_on: list[str]  # Step dependencies
    condition: str | None  # "$steps.0.total_count > 0"
    on_success: str | None  # Next step on success
    on_fail: str | None     # Next step on failure
```

### 3. Parallel Executor

Executes tools in dependency-ordered waves using `asyncio.gather()`.

```python
# Wave-based execution
Wave 1: [step_0, step_1]  # Independent steps
Wave 2: [step_2]          # Depends on step_0
Wave 3: [step_3, step_4]  # Depend on step_2
```

**Key Features**:
- True parallel execution within waves
- Conditional step evaluation
- Adaptive re-planning (INTELLIPLANNER Phase E)
- Data registry for result storage

### 4. Response Node (INTELLIA v10)

Synthesizes tool results into conversational responses.

```python
# Uses JSON + Few-Shot pattern
1. Groups results by domain type
2. Loads domain-specific few-shot examples
3. LLM generates Markdown response
```

## Active Domains (11 Total)

| Domain | Connector Type | Tools |
|--------|---------------|-------|
| Contacts | OAuth/Google | search, get_details |
| Emails | OAuth/Google | search, get_details, send |
| Calendar | OAuth/Google | search, get_details, create, update, delete |
| Drive | OAuth/Google | search, list, get_content |
| Tasks | OAuth/Google | list, create, complete |
| Weather | API Key | current, forecast |
| Wikipedia | Public API | search, get_article |
| Perplexity | API Key | search, ask |
| Places | OAuth/Google | search, nearby, details |
| Hue | Hybrid (API Key + OAuth) | list_lights, control_light, list_rooms, control_room, list_scenes, activate_scene |
| Query | Internal | analyze, filter, detect_duplicates |

## Data Registry (LOT 5.2)

Centralized storage for tool execution results.

```python
# RegistryItem structure
RegistryItem:
    id: str           # "contact_abc123"
    type: str         # "CONTACT", "EMAIL", "EVENT", "HUE_LIGHT", etc.
    payload: dict     # API response data
    meta:
        source: str       # "google_contacts"
        domain: str       # "contacts"
        timestamp: str
        ttl: int          # seconds
        from_cache: bool
```

## HITL (Human-in-the-Loop)

Three levels of user interaction:

1. **Clarification** (semantic_validator): When query is ambiguous
2. **Plan Approval** (approval_gate): Before executing actions
3. **Draft Critique** (LOT 6): Review generated content before sending

```python
# Interrupt pattern
from langgraph.types import interrupt

decision = interrupt(ClarificationInteraction(
    question="Quel Jean voulez-vous contacter?",
    options=["Jean Dupont", "Jean Martin"],
))
```

## Configuration

### Settings (config/agents.py)

```python
# Message windowing
router_message_window_size = 5
planner_message_window_size = 10
response_message_window_size = 20

# Execution limits
agent_max_iterations = 10

# HITL thresholds
approval_cost_threshold_usd = 5.00
semantic_validation_confidence_threshold = 0.7
```

## Metrics & Observability

### Prometheus Metrics

- `planner_node_duration_seconds`: Plan generation time
- `parallel_executor_duration_seconds`: Execution time
- `tool_execution_total`: Tool calls by domain
- `hitl_interrupts_total`: User interactions

### Langfuse Tracing

All nodes are instrumented with `@trace_node()` decorator:
- Span creation for each node
- Token counting
- Error tracking

## Best Practices

### Adding a New Domain

1. Create tools in `tools/{domain}_tools.py`
2. Add to tool catalogue in `registry/catalogue_manifests.py`
3. Add few-shot examples in `prompts/v1/fewshot/`
4. Register in domain constants

### Error Handling

```python
try:
    result = await tool.execute(...)
except GraphInterrupt:
    raise  # Propagate HITL interrupts
except Exception as e:
    logger.error("tool_execution_failed", error=str(e))
    return error_response(...)
```

### Performance

- Use message windowing to reduce LLM tokens
- Leverage data registry caching
- Execute independent steps in parallel

## Migration Notes

### From v1.0 (domain_handler based) to v2.0 (parallel_executor)

**Removed Components**:
- `domain_handler.py`
- `domain_registry.py`
- `multi_domain_composer.py`
- `relation_engine.py`
- `plan_executor.py`

**New Components**:
- `parallel_executor.py` - Unified execution engine
- `condition_evaluator.py` - Step conditions
- `adaptive_replanner.py` - Re-planning logic

## References

- [ARCHITECTURE_LANGRAPH.md](../ARCHITECTURE_LANGRAPH.md) - Detailed LangGraph pipeline
- [ARCHITECTURE_AGENT.md](../ARCHITECTURE_AGENT.md) - Agent integration guide
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture
