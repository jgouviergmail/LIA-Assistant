# ADR-043: Subgraph Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: LangGraph hierarchical agent orchestration with domain isolation
**Related ADRs**: ADR-009, ADR-010, ADR-018, ADR-021

---

## Context and Problem Statement

L'application nécessitait une architecture multi-agents sophistiquée :

1. **Domain Isolation** : Chaque domaine (Gmail, Contacts, Calendar) a ses propres outils
2. **Supervision Pattern** : Orchestration centralisée des agents spécialisés
3. **Parallel Execution** : Exécution concurrente de plusieurs agents
4. **State Sharing** : Partage d'état cohérent entre graphe parent et subgraphs

**Question** : Comment structurer une architecture de subgraphs LangGraph pour orchestrer efficacement des agents spécialisés ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Hierarchical Graph Structure** : Parent graph supervisant les subgraphs
2. **Domain Agent Isolation** : Outils spécifiques par domaine
3. **Callback Propagation** : Metrics et observabilité propagés aux subgraphs
4. **State Consistency** : MessagesState unifié avec custom reducers

### Nice-to-Have:

- Parallel agent execution
- Dynamic agent loading
- Turn-based isolation

---

## Decision Outcome

**Chosen option**: "**Supervisor Pattern with Agent Registry and Deep Callback Propagation**"

### Architecture Overview

```
PARENT GRAPH (Main Orchestrator)
├── Entry: Router Node
├── Planner Node (LLM-based multi-step planning)
├── Semantic Validator Node (validation + clarification HITL)
├── Approval Gate Node (plan-level HITL)
├── Task Orchestrator Node (coordinator)
├── SUBGRAPH AGENTS (Domain Isolation):
│   ├── contacts_agent (Google Contacts - ReAct loop)
│   ├── emails_agent (Gmail - ReAct loop)
│   ├── calendar_agent (Google Calendar - ReAct loop)
│   ├── drive_agent (Google Drive)
│   ├── tasks_agent (Google Tasks)
│   ├── weather_agent (API-based)
│   ├── wikipedia_agent (API-based)
│   ├── perplexity_agent (API-based)
│   └── places_agent (API-based)
├── Draft Critique Node (requires_confirmation HITL)
└── Response Node (synthesis + memory injection)
```

### Graph Construction Pattern

```python
# apps/api/src/domains/agents/graph.py

graph = StateGraph(MessagesState)

# Add system nodes
graph.add_node(NODE_ROUTER, router_node)
graph.add_node(NODE_PLANNER, planner_node)
graph.add_node(NODE_SEMANTIC_VALIDATOR, semantic_validator_node)
graph.add_node(NODE_APPROVAL_GATE, approval_gate_node)
graph.add_node(NODE_TASK_ORCHESTRATOR, task_orchestrator_node)

# Add AGENT SUBGRAPH NODES dynamically from registry
registry_for_wrapper = get_global_registry()

contacts_agent_runnable = registry_for_wrapper.get_agent("contacts_agent")
contacts_agent_node = build_agent_wrapper(
    agent_runnable=contacts_agent_runnable,
    agent_name="contacts_agent",
    agent_constant=AGENT_CONTACTS,
)
graph.add_node(AGENT_CONTACTS, contacts_agent_node)

# Set entry and edges
graph.set_entry_point(NODE_ROUTER)
graph.add_conditional_edges(NODE_ROUTER, route_from_router)
```

### Domain Agent Builder (Factory Pattern)

```python
# apps/api/src/domains/agents/graphs/base_agent_builder.py

def build_generic_agent(config: AgentConfig) -> Any:
    """
    Build LangChain v1.0 agent with:
    - Specific domain tools (contacts, emails, calendar, etc.)
    - Middleware stack (Retry, Summarization, MessageHistory)
    - HITL for tool approval (if enabled)
    """
    middleware = create_agent_middleware_stack(agent_name)
    middleware.append(MessageHistoryMiddleware(
        keep_last_n=settings.agent_history_keep_last,
        max_tokens=settings.max_tokens_history,
    ))

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
        checkpointer=registry.get_checkpointer(),
        store=registry.get_store(),
    )
    return agent
```

### Domain Agent Examples

```python
# contacts_agent_builder.py
def build_contacts_agent() -> Any:
    tools = [
        search_contacts_tool,
        list_contacts_tool,
        get_contact_details_tool,
        create_contact_tool,
        update_contact_tool,
        delete_contact_tool,
        # Context resolution tools
        resolve_reference,
        get_context_list,
        set_current_item,
    ]

    config = create_agent_config_from_settings(
        agent_name="contacts_agent",
        tools=tools,
        system_prompt=CONTACTS_AGENT_PROMPT,
    )

    return build_generic_agent(config)
```

### Agent Wrapper Pattern (Callback Propagation)

```python
# Critical fix for Phase 2.1.6: Deep callback propagation

def create_agent_wrapper_node(
    agent_runnable: Any,
    agent_name: str,
    agent_constant: str,
) -> Any:
    """
    Wrapper factory with DEEP callback propagation.

    PROBLEM (RC3): Agent subgraphs don't receive parent callbacks
    → Missing 65% of tokens from DB
    → No Langfuse traces

    SOLUTION: Deep merge parent config + propagate to subgraph
    """

    async def agent_wrapper_node(state: MessagesState, config: RunnableConfig) -> dict:
        parent_callbacks = config.get("callbacks", [])
        parent_metadata = config.get("metadata", {})

        # DEEP MERGE: Preserve config + propagate parent context
        merged_config = {
            **config,
            "callbacks": parent_callbacks,  # Propagate callbacks ← KEY FIX
            "metadata": {
                **config.get("metadata", {}),
                **parent_metadata,
                "subgraph": agent_constant,
                "parent_node": "main_graph",
            },
        }

        result = await agent_runnable.ainvoke(state, merged_config)

        # Store results for response_node
        agent_results = state.get(STATE_KEY_AGENT_RESULTS, {})
        turn_id = state.get(STATE_KEY_CURRENT_TURN_ID, 0)
        composite_key = make_agent_result_key(turn_id, agent_constant)

        agent_results[composite_key] = {
            FIELD_AGENT_NAME: agent_constant,
            FIELD_STATUS: "success",
            "data": result.get(STATE_KEY_MESSAGES, [])[-1].content,
        }

        return {
            STATE_KEY_MESSAGES: result.get(STATE_KEY_MESSAGES, []),
            STATE_KEY_AGENT_RESULTS: agent_results,
            "registry": result.get("registry", {}),
        }

    return agent_wrapper_node
```

### Unified State Schema

```python
# apps/api/src/domains/agents/models.py

class MessagesState(TypedDict):
    """Unified state for parent graph and all subgraphs."""

    # Message history (with automatic truncation reducer)
    messages: Annotated[list[BaseMessage], add_messages_with_truncate]

    # Agent results (keyed as "turn_id:agent_name")
    agent_results: dict[str, Any]

    # Execution plan from planner
    execution_plan: Any | None

    # Validation & approval state (HITL)
    validation_result: Any | None
    plan_approved: bool | None

    # User preferences (injected into subgraph prompts)
    user_timezone: str
    user_language: str
    personality_instruction: str | None
    oauth_scopes: list[str]

    # Data Registry (rich rendering)
    registry: Annotated[dict[str, RegistryItem], merge_registry]
```

### Message Truncation Reducer

```python
def add_messages_with_truncate(
    left: list[BaseMessage], right: list[BaseMessage]
) -> list[BaseMessage]:
    """
    Reducer function for messages with automatic truncation.

    Strategy:
    1. Handle RemoveMessage properly
    2. Truncate by tokens (MAX_TOKENS_HISTORY)
    3. Fallback: Limit by count
    4. Always preserve SystemMessage
    5. Validate OpenAI message sequence
    """
    all_messages = add_messages(left, right)

    trimmed = trim_messages(
        all_messages,
        max_tokens=settings.max_tokens_history,
        strategy="last",
        include_system=True,
    )

    if len(trimmed) > settings.max_messages_history:
        system_msgs = [m for m in trimmed if isinstance(m, SystemMessage)]
        recent_msgs = trimmed[-settings.max_messages_history:]
        trimmed = system_msgs + recent_msgs

    validated = remove_orphan_tool_messages(list(trimmed))
    return validated
```

### Conditional Routing

```python
def route_from_router(state: MessagesState) -> str:
    """
    Phase 6 - Binary Routing:
    - Router classifies: actionable vs conversational
    - ALL actionable → planner
    - Conversational → response
    """
    routing_history = state.get(STATE_KEY_ROUTING_HISTORY, [])
    router_output = routing_history[-1]

    intention = router_output.intention
    confidence = router_output.confidence
    next_node = router_output.next_node

    if confidence >= settings.router_confidence_high:
        return next_node  # "planner" or "response"
    else:
        return NODE_RESPONSE  # Low confidence → fallback

def route_from_orchestrator(state: MessagesState) -> str:
    """
    Routes to:
    1. draft_critique: If requires_confirmation tools exist
    2. next_agent: For multi-step plans
    3. response: If all agents done
    """
    pending_draft = state.get("pending_draft_critique")
    if pending_draft:
        return NODE_DRAFT_CRITIQUE

    next_agent = get_next_agent_from_plan(state)
    return next_agent if next_agent else NODE_RESPONSE
```

### Agent Registry Pattern (Lazy Initialization)

```python
class AgentRegistry:
    def __init__(self, checkpointer, store):
        self._checkpointer = checkpointer
        self._store = store
        self._agents = {}  # Lazy cache

    def get_agent(self, name: str):
        if name not in self._agents:
            builder = AGENT_BUILDERS[name]
            self._agents[name] = builder()
        return self._agents[name]

# In graph.py
registry_for_wrapper = get_global_registry()
contacts_agent = registry_for_wrapper.get_agent("contacts_agent")
```

### Turn-Based Isolation

```python
# Per-turn agent result isolation
state["current_turn_id"] = state.get("current_turn_id", 0) + 1

# Agent results keyed as "turn_id:agent_name"
make_agent_result_key(turn_id=3, agent_name="contacts_agent")
# → "3:contacts_agent"

# Cleanup on new turn
cleanup_dict_by_turn_id(agent_results, current_turn_id, keep_last=2)
```

### Consequences

**Positive**:
- ✅ **Domain Isolation** : Chaque agent a ses propres outils
- ✅ **Supervisor Pattern** : Orchestration centralisée
- ✅ **Callback Propagation** : 100% des tokens trackés (vs 35% avant fix)
- ✅ **State Consistency** : Custom reducers pour messages et registry
- ✅ **Lazy Loading** : Agents initialisés à la demande
- ✅ **Turn Isolation** : Résultats isolés par tour

**Negative**:
- ⚠️ Complexité du routing multi-niveaux
- ⚠️ Debugging des subgraphs plus difficile

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Graph parent avec nodes système
- [x] ✅ Subgraphs par domaine (contacts, emails, calendar, etc.)
- [x] ✅ Agent wrappers avec callback propagation
- [x] ✅ MessagesState unifié avec reducers
- [x] ✅ Routing conditionnel multi-niveaux
- [x] ✅ Turn-based isolation des résultats
- [x] ✅ Lazy agent initialization via registry

---

## References

### Source Code
- **Graph Construction**: `apps/api/src/domains/agents/graph.py`
- **Agent Builders**: `apps/api/src/domains/agents/graphs/`
- **State Models**: `apps/api/src/domains/agents/models.py`
- **Routing**: `apps/api/src/domains/agents/nodes/routing.py`
- **Task Orchestrator**: `apps/api/src/domains/agents/nodes/task_orchestrator_node.py`

---

**Fin de ADR-043** - Subgraph Architecture Decision Record.
