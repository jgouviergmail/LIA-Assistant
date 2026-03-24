# Guide Pratique : Debugging et Diagnostic

**Version** : 1.3
**Derniere mise a jour** : 2026-03-08
**Statut** : ✅ Stable

---

## Table des matières

1. [Introduction](#introduction)
2. [Stratégies de Debugging](#stratégies-de-debugging)
3. [Debugging Agents LangGraph](#debugging-agents-langgraph)
4. [Debugging Tools](#debugging-tools)
5. [Debugging Prompts LLM](#debugging-prompts-llm)
6. [Debugging State & Checkpoint](#debugging-state--checkpoint)
7. [Debugging OAuth & Connectors](#debugging-oauth--connectors)
8. [Observabilité et Logs](#observabilité-et-logs)
9. [Debugging HITL Flow](#debugging-hitl-flow)
10. [Debugging Performance](#debugging-performance)
11. [Outils et IDE](#outils-et-ide)
12. [Patterns de Diagnostic](#patterns-de-diagnostic)
13. [Debugging MCP (Model Context Protocol)](#debugging-mcp-model-context-protocol)
14. [Debugging Telegram (Multi-Channel)](#debugging-telegram-multi-channel)
15. [Debugging Heartbeat (Notifications Proactives)](#debugging-heartbeat-notifications-proactives)
16. [Debugging Scheduled Actions](#debugging-scheduled-actions)
17. [Troubleshooting Commun](#troubleshooting-commun)
18. [Références](#références)

---

## Introduction

### Objectif du guide

Ce guide fournit une approche systématique pour **déboguer et diagnostiquer** les problèmes dans LIA. Il couvre :

- **Agents LangGraph** : debugging StateGraph, nodes, routing, flow
- **Tools** : debugging OAuth, rate limiting, caching, API calls
- **Prompts LLM** : validation JSON schema, hallucinations, structured output
- **State management** : checkpoint, reducers, state bloat
- **Observabilité** : logs structurés, traces, métriques Prometheus
- **Performance** : profiling, latence, token optimization

### Public cible

- **Développeurs backend** : debugging FastAPI, SQLAlchemy, LangGraph
- **Développeurs agents** : debugging StateGraph, nodes, plans
- **DevOps** : debugging infrastructure, observabilité, logs
- **Support** : diagnostic rapide des incidents production

### Prérequis

- **Connaissances** : Python async, LangGraph, Prometheus, structlog
- **Accès** : Grafana dashboards, logs Loki, DB PostgreSQL
- **Outils** : VSCode debugger, curl, psql, redis-cli

---

## Stratégies de Debugging

### Méthodologie Générale

**Approche scientifique du debugging** :

1. **Observer** : collecter symptômes, erreurs, logs
2. **Hypothèse** : formuler théorie sur cause racine
3. **Test** : valider hypothèse avec debugging ciblé
4. **Fix** : corriger root cause (pas symptôme)
5. **Verify** : tester le fix, vérifier régression

### Types de Debugging

| Type | Usage | Outils |
|------|-------|--------|
| **Logs** | Erreurs runtime, flow debugging | structlog, Loki, Grafana |
| **Traces** | Debugging distribué, latence | OpenTelemetry, Tempo, Langfuse |
| **Metrics** | Patterns, anomalies, SLO | Prometheus, Grafana dashboards |
| **Breakpoints** | Step debugging, inspection variables | VSCode debugger, pdb |
| **Profiling** | Hotspots performance, mémoire | cProfile, py-spy, memory_profiler |

### Niveau de Logs

```python
# src/core/config.py
class Settings(BaseSettings):
    log_level: str = Field(default="INFO")  # DEBUG, INFO, WARNING, ERROR
    log_level_uvicorn: str = Field(default="INFO")
    log_level_sqlalchemy: str = Field(default="WARNING")  # DB queries
    log_level_httpx: str = Field(default="WARNING")  # HTTP calls
```

**Activer debug logs** :

```bash
# .env
LOG_LEVEL=DEBUG
LOG_LEVEL_SQLALCHEMY=INFO  # Voir toutes les queries SQL
LOG_LEVEL_HTTPX=DEBUG  # Voir tous les appels HTTP externes
```

---

## Debugging Agents LangGraph

### Debug Mode LangGraph

**Activer verbose logging** :

```python
# apps/api/src/domains/agents/graph.py
async def build_graph(
    config: Settings | None = None,
    checkpointer: AsyncPostgresSaver | None = None,
    debug: bool = False,  # ✅ Activer debug mode
) -> CompiledStateGraph:
    """Build LangGraph with debug mode."""
    graph = StateGraph(MessagesState)

    # ... add nodes

    compiled = graph.compile(
        checkpointer=checkpointer,
        debug=debug,  # ✅ Active verbose logging
    )

    return compiled
```

**Logs debug LangGraph** :

```json
{
  "event": "graph_node_start",
  "node": "router_node",
  "trace_id": "135a20fdc30eaf9a5711c54d34d9db2b",
  "timestamp": "2025-01-15T12:34:56.789Z"
}
{
  "event": "graph_node_complete",
  "node": "router_node",
  "duration_ms": 234,
  "updates": {"routing_history": ["router"]}
}
```

### Debugging Node Execution

**Problème** : Node ne s'exécute pas comme prévu.

**Stratégie** :

1. **Logs structurés** dans le node

```python
# apps/api/src/domains/agents/nodes/router_node_v3.py
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

async def router_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """Router node with extensive debug logging."""
    logger.info(
        "router_node_start",
        messages_count=len(state[STATE_KEY_MESSAGES]),
        current_turn_id=state.get(STATE_KEY_CURRENT_TURN_ID),
    )

    # Log windowed messages
    windowed_messages = get_windowed_messages(
        state,
        window_size=settings.router_message_window_size,
    )
    logger.debug(
        "router_windowed_messages",
        window_size=settings.router_message_window_size,
        windowed_count=len(windowed_messages),
        original_count=len(state[STATE_KEY_MESSAGES]),
    )

    # Call LLM
    router_output = await _call_router_llm(windowed_messages)

    logger.info(
        "router_decision",
        intent=router_output.intent,
        confidence=router_output.confidence,
        requires_plan=router_output.requires_plan,
        data_presumption_applied=router_output.data_presumption_applied,
    )

    # Track data presumption metric (RULE #5)
    if router_output.data_presumption_applied:
        logger.warning(
            "router_data_presumption_triggered",
            reason=router_output.data_presumption_reason,
            fallback_to="direct_response",
        )

    return {
        STATE_KEY_ROUTING_HISTORY: [router_output.intent],
        # ... other updates
    }
```

2. **Inspecter state avant/après node**

```python
# Debug wrapper pour nodes
from functools import wraps
import json

def debug_node(func):
    """Decorator pour logger state avant/après node."""
    @wraps(func)
    async def wrapper(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
        logger = get_logger(func.__name__)

        # Log state BEFORE
        logger.debug(
            f"{func.__name__}_state_before",
            state_keys=list(state.keys()),
            messages_count=len(state.get(STATE_KEY_MESSAGES, [])),
            plan_approved=state.get(STATE_KEY_PLAN_APPROVED),
        )

        # Execute node
        updates = await func(state, config)

        # Log state AFTER (updates)
        logger.debug(
            f"{func.__name__}_state_after",
            updates_keys=list(updates.keys()),
            updates=json.dumps(updates, default=str, indent=2),  # Pretty print
        )

        return updates

    return wrapper

# Usage
@debug_node
async def router_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    # ... implementation
    pass
```

3. **Breakpoint dans le node**

```python
async def router_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    # ✅ Breakpoint pour debugging interactif
    breakpoint()  # En dev uniquement !

    # Inspect state
    messages = state[STATE_KEY_MESSAGES]
    routing_history = state.get(STATE_KEY_ROUTING_HISTORY, [])

    # ... rest of node
```

### Debugging Routing Logic

**Problème** : Graph route vers mauvais node.

**Diagnostic** :

```python
# apps/api/src/domains/agents/nodes/routing.py
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

def route_from_router(state: MessagesState) -> str:
    """Route from router node with debug logging."""
    routing_history = state.get(STATE_KEY_ROUTING_HISTORY, [])
    last_intent = routing_history[-1] if routing_history else None

    logger.info(
        "route_from_router",
        last_intent=last_intent,
        routing_history=routing_history,
        requires_plan=state.get(STATE_KEY_REQUIRES_PLAN),
    )

    # Routing logic
    if last_intent == "plan_required":
        next_node = NODE_PLANNER
    elif last_intent == "direct_response":
        next_node = NODE_RESPONSE
    else:
        logger.warning(
            "route_from_router_fallback",
            last_intent=last_intent,
            fallback_to=NODE_RESPONSE,
        )
        next_node = NODE_RESPONSE

    logger.info("route_from_router_decision", next_node=next_node)

    return next_node
```

**Vérifier routing history dans Grafana** :

```promql
# Query Prometheus pour routing history
sum by (intent) (
  increase(router_decisions_total[5m])
)
```

### Debugging Graph Interrupts (HITL)

**Problème** : Interrupt HITL ne se déclenche pas.

**Diagnostic** :

```python
# apps/api/src/domains/agents/nodes/approval_gate_node.py
from langgraph.errors import GraphInterrupt

logger = get_logger(__name__)

async def approval_gate_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """Approval gate with debug logging."""
    plan = state.get(STATE_KEY_PLAN)
    tool_approval_enabled = state.get(STATE_KEY_TOOL_APPROVAL_ENABLED, False)

    logger.info(
        "approval_gate_node_start",
        tool_approval_enabled=tool_approval_enabled,
        plan_steps_count=len(plan["steps"]) if plan else 0,
    )

    if not tool_approval_enabled:
        logger.info("approval_gate_skipped", reason="tool_approval_disabled")
        return {STATE_KEY_PLAN_APPROVED: True}

    # Extract action requests
    action_requests = _extract_action_requests(plan)

    logger.info(
        "approval_gate_interrupt_trigger",
        action_requests_count=len(action_requests),
        interrupt_type="approval",
    )

    # ✅ Trigger HITL interrupt
    raise GraphInterrupt(
        {
            "type": "approval",
            "action_requests": action_requests,
            "review_configs": [{"approval_type": "required"}],
            "interrupt_ts": time.time(),
        }
    )
```

**Vérifier interrupts dans checkpointer** :

```python
# Script debug : list_graph_interrupts.py
from src.infrastructure.database.session import async_session_maker
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def list_interrupts(thread_id: str):
    """Liste tous les interrupts pour un thread."""
    async with async_session_maker() as session:
        checkpointer = AsyncPostgresSaver(session.bind)

        state_snapshot = await checkpointer.aget({"configurable": {"thread_id": thread_id}})

        if state_snapshot and state_snapshot.pending_writes:
            print(f"Pending interrupts: {len(state_snapshot.pending_writes)}")
            for i, write in enumerate(state_snapshot.pending_writes):
                print(f"  [{i}] {write}")
        else:
            print("No pending interrupts")

# Usage
import asyncio
asyncio.run(list_interrupts("conversation_abc123"))
```

### Debugging Graph Flow

**Visualiser graph flow** :

```python
# apps/api/src/domains/agents/graph.py
from langgraph.graph import StateGraph

def visualize_graph():
    """Generate Mermaid diagram of graph."""
    graph = StateGraph(MessagesState)

    # Add nodes and edges
    # ...

    # Generate Mermaid
    mermaid = graph.get_graph().draw_mermaid()

    print(mermaid)

# Output Mermaid diagram
"""
graph TD
    START --> router_node
    router_node --> planner_node
    router_node --> response_node
    planner_node --> approval_gate_node
    approval_gate_node --> task_orchestrator_node
    approval_gate_node --> response_node
    task_orchestrator_node --> response_node
    response_node --> END
"""
```

---

## Debugging Tools

### Debug Tool Execution

**Problème** : Tool ne retourne pas résultat attendu.

**Stratégie** :

```python
# apps/api/src/domains/agents/tools/google_contacts_tools.py
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

@connector_tool
class SearchContactsTool(ConnectorTool):
    """Search Google Contacts with debug logging."""

    async def execute(self, query: str, max_results: int = 10) -> dict:
        """Search contacts with extensive logging."""
        logger.info(
            "search_contacts_tool_start",
            query=query,
            max_results=max_results,
        )

        try:
            # ✅ Log client state
            logger.debug(
                "search_contacts_client_status",
                client_authenticated=self.client.is_authenticated(),
                token_expires_at=self.client.token_expires_at,
            )

            # Call API
            contacts = await self.client.search_contacts(query, max_results)

            logger.info(
                "search_contacts_tool_success",
                results_count=len(contacts),
                cache_hit=self.client.last_request_cached,
            )

            return {
                "success": True,
                "data": {"contacts": contacts, "count": len(contacts)},
                "message": f"Trouvé {len(contacts)} contact(s)",
            }

        except Exception as e:
            logger.error(
                "search_contacts_tool_error",
                error_type=type(e).__name__,
                error_message=str(e),
                query=query,
                exc_info=True,  # Include full traceback
            )

            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }
```

### Debug OAuth Token Refresh

**Problème** : Token refresh loop infini.

**Diagnostic** :

```python
# apps/api/src/domains/connectors/clients/google_people.py
logger = get_logger(__name__)

class GooglePeopleClient:
    """Google People API client with OAuth debug."""

    async def _ensure_valid_token(self):
        """Ensure token is valid with debug logging."""
        if not self.connector.access_token:
            logger.error("oauth_no_token", connector_id=self.connector.id)
            raise ValueError("No access token")

        # Check expiry
        now = datetime.now(timezone.utc)
        expires_at = self.connector.token_expires_at

        logger.debug(
            "oauth_token_check",
            expires_at=expires_at,
            now=now,
            is_expired=expires_at < now if expires_at else True,
        )

        if expires_at and expires_at < now + timedelta(minutes=5):
            logger.info("oauth_token_refresh_needed", expires_at=expires_at)

            # ✅ Track refresh attempts to detect loop
            refresh_attempt_key = f"oauth_refresh_attempt:{self.connector.id}"
            attempt_count = await redis_client.incr(refresh_attempt_key)
            await redis_client.expire(refresh_attempt_key, 60)  # 1 min TTL

            if attempt_count > 3:
                logger.error(
                    "oauth_refresh_loop_detected",
                    connector_id=self.connector.id,
                    attempt_count=attempt_count,
                )
                raise Exception("OAuth refresh loop detected")

            # Refresh token
            await self._refresh_access_token()

            logger.info("oauth_token_refreshed", new_expires_at=self.connector.token_expires_at)
```

### Debug Rate Limiting

**Problème** : Rate limiting bloque requêtes légitimes.

**Diagnostic** :

```python
# apps/api/src/infrastructure/cache/rate_limiting.py
logger = get_logger(__name__)

async def check_rate_limit(key: str, max_calls: int, period: int) -> bool:
    """Check rate limit with debug logging."""
    # Get current count
    count = await redis_client.get(key)
    current_count = int(count) if count else 0

    logger.debug(
        "rate_limit_check",
        key=key,
        current_count=current_count,
        max_calls=max_calls,
        period=period,
    )

    if current_count >= max_calls:
        logger.warning(
            "rate_limit_exceeded",
            key=key,
            current_count=current_count,
            max_calls=max_calls,
        )
        return False

    # Increment counter
    pipeline = redis_client.pipeline()
    pipeline.incr(key)
    pipeline.expire(key, period)
    await pipeline.execute()

    logger.debug("rate_limit_allowed", key=key, new_count=current_count + 1)

    return True
```

**Vérifier rate limit dans Redis** :

```bash
# redis-cli
redis-cli -n 0

# List all rate limit keys
KEYS "rate_limit:*"

# Check specific key
GET "rate_limit:google_contacts:search:user_123"
# Output: "8" (8 calls dans la période)

# Check TTL
TTL "rate_limit:google_contacts:search:user_123"
# Output: 42 (42 secondes restantes)
```

### Debug Caching

**Problème** : Cache ne hit pas alors qu'il devrait.

**Diagnostic** :

```python
# apps/api/src/infrastructure/cache/redis.py
logger = get_logger(__name__)

async def get_cached(key: str) -> Any | None:
    """Get cached value with debug logging."""
    logger.debug("cache_get_attempt", key=key)

    value = await redis_client.get(key)

    if value:
        logger.info("cache_hit", key=key, value_length=len(value))
    else:
        logger.info("cache_miss", key=key)

    return value

async def set_cached(key: str, value: Any, ttl: int):
    """Set cached value with debug logging."""
    logger.debug(
        "cache_set",
        key=key,
        value_length=len(str(value)),
        ttl=ttl,
    )

    await redis_client.setex(key, ttl, value)

    logger.info("cache_set_success", key=key)
```

**Analyser cache hit rate** :

```bash
# redis-cli
redis-cli INFO stats | grep keyspace_hits
# Output:
# keyspace_hits:1234567
# keyspace_misses:234567
# Hit rate = 1234567 / (1234567 + 234567) = 84%
```

---

## Debugging Prompts LLM

### Debug JSON Schema Validation

**Problème** : Structured output échoue avec validation error.

**Diagnostic** :

```python
# apps/api/src/domains/agents/nodes/router_node_v3.py
from pydantic import ValidationError

logger = get_logger(__name__)

async def _call_router_llm(messages: list[BaseMessage]) -> RouterOutput:
    """Call router LLM with structured output validation."""
    llm = get_llm("router")

    try:
        # Get structured output
        llm_with_structure = get_structured_output(llm, RouterOutput)

        logger.debug(
            "router_llm_call",
            messages_count=len(messages),
            schema=RouterOutput.model_json_schema(),
        )

        # Invoke LLM
        result = await llm_with_structure.ainvoke(messages)

        logger.info(
            "router_llm_success",
            intent=result.intent,
            confidence=result.confidence,
        )

        return result

    except ValidationError as e:
        logger.error(
            "router_llm_validation_error",
            error=str(e),
            validation_errors=e.errors(),
            exc_info=True,
        )

        # ✅ Log raw LLM response for debugging
        try:
            raw_response = await llm.ainvoke(messages)
            logger.error(
                "router_llm_raw_response",
                raw_response=raw_response.content if hasattr(raw_response, 'content') else str(raw_response),
            )
        except Exception:
            pass

        raise
```

**Exemple log d'erreur** :

```json
{
  "event": "router_llm_validation_error",
  "error": "1 validation error for RouterOutput\nintent\n  Input should be 'plan_required' or 'direct_response' (type=value_error.enum)",
  "validation_errors": [
    {
      "loc": ["intent"],
      "msg": "Input should be 'plan_required' or 'direct_response'",
      "type": "value_error.enum",
      "ctx": {"expected": "'plan_required' or 'direct_response'"}
    }
  ],
  "raw_response": "{\"intent\": \"needs_planning\", \"confidence\": 0.9}"
}
```

**Solution** : Corriger le prompt pour respecter enum.

### Debug Hallucinations

**Problème** : LLM hallucine des outils inexistants.

**Diagnostic** :

```python
# apps/api/src/domains/agents/nodes/planner_node_v3.py
logger = get_logger(__name__)

async def planner_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """Planner with hallucination detection."""
    # Get available tools
    available_tools = _get_available_tools_from_catalogue(state)
    available_tool_names = {tool["name"] for tool in available_tools}

    logger.debug(
        "planner_available_tools",
        tools_count=len(available_tools),
        tool_names=list(available_tool_names),
    )

    # Call planner LLM
    plan = await _call_planner_llm(state, available_tools)

    # ✅ Validate plan actions against available tools
    hallucinated_actions = []
    for step in plan["steps"]:
        if step["action"] not in available_tool_names:
            hallucinated_actions.append(step["action"])

    if hallucinated_actions:
        logger.warning(
            "planner_hallucination_detected",
            hallucinated_actions=hallucinated_actions,
            available_tools=list(available_tool_names),
            plan=plan,
        )

        # Auto-reject plan (trigger replan)
        return {
            STATE_KEY_PLAN: None,
            STATE_KEY_PLAN_APPROVED: False,
            STATE_KEY_PLAN_REJECTION_REASON: f"Hallucinated tools: {hallucinated_actions}",
        }

    return {STATE_KEY_PLAN: plan}
```

### Debug Prompt Caching

**Problème** : Cache prompt OpenAI ne fonctionne pas.

**Diagnostic** :

```python
# apps/api/src/infrastructure/llm/instrumentation.py
logger = get_logger(__name__)

class TokenTrackingCallback(BaseCallbackHandler):
    """Callback with cache debugging."""

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Track token usage with cache info."""
        for generation in response.generations:
            for gen in generation:
                if hasattr(gen, "message") and hasattr(gen.message, "response_metadata"):
                    metadata = gen.message.response_metadata
                    usage = metadata.get("usage", {})

                    # ✅ Extract cache info (OpenAI)
                    cached_tokens = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
                    total_prompt_tokens = usage.get("prompt_tokens", 0)

                    cache_hit_rate = (cached_tokens / total_prompt_tokens * 100) if total_prompt_tokens > 0 else 0

                    logger.info(
                        "llm_cache_usage",
                        total_prompt_tokens=total_prompt_tokens,
                        cached_tokens=cached_tokens,
                        cache_hit_rate=f"{cache_hit_rate:.1f}%",
                        model=metadata.get("model_name"),
                    )

                    if cached_tokens == 0 and total_prompt_tokens >= 1024:
                        logger.warning(
                            "llm_cache_miss_unexpected",
                            prompt_tokens=total_prompt_tokens,
                            reason="Cache should have hit for prompt >=1024 tokens",
                        )
```

---

## Debugging State & Checkpoint

### Inspect Checkpoint State

**Problème** : State semble corrompu après resumption.

**Diagnostic** :

```python
# Script debug: inspect_checkpoint.py
from src.infrastructure.database.session import async_session_maker
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import json

async def inspect_checkpoint(thread_id: str):
    """Inspect checkpoint state for debugging."""
    async with async_session_maker() as session:
        checkpointer = AsyncPostgresSaver(session.bind)

        # Get latest checkpoint
        config = {"configurable": {"thread_id": thread_id}}
        state_snapshot = await checkpointer.aget(config)

        if not state_snapshot:
            print(f"No checkpoint found for thread_id: {thread_id}")
            return

        print(f"Checkpoint found:")
        print(f"  Thread ID: {state_snapshot.config['configurable']['thread_id']}")
        print(f"  Checkpoint ID: {state_snapshot.config['configurable'].get('checkpoint_id')}")
        print(f"  Values:")

        # Pretty print state
        for key, value in state_snapshot.values.items():
            print(f"    {key}: {json.dumps(value, default=str, indent=6)}")

        # Check for pending writes (interrupts)
        if state_snapshot.pending_writes:
            print(f"\n  Pending writes (interrupts): {len(state_snapshot.pending_writes)}")
            for write in state_snapshot.pending_writes:
                print(f"    - {write}")

# Usage
import asyncio
asyncio.run(inspect_checkpoint("conversation_abc123"))
```

**Output exemple** :

```
Checkpoint found:
  Thread ID: conversation_abc123
  Checkpoint ID: 1ef5c3d2-1234-5678-9abc-def012345678
  Values:
    messages: [
      {
        "role": "user",
        "content": "Recherche jean dans mes contacts"
      }
    ]
    routing_history: ["router"]
    plan: {
      "steps": [
        {"action": "search_contacts_tool", "args": {"query": "jean"}}
      ]
    }
    plan_approved: null

  Pending writes (interrupts): 1
    - ('approval_gate_node', {'type': 'approval', 'action_requests': [...]})
```

### Debug State Reducers

**Problème** : Reducer ne merge pas state correctement.

**Diagnostic** :

```python
# apps/api/src/domains/agents/models.py
from typing import Annotated
from langgraph.graph.message import add_messages

logger = get_logger(__name__)

def debug_add_messages(left: list, right: list) -> list:
    """add_messages reducer with debug logging."""
    logger.debug(
        "reducer_add_messages",
        left_count=len(left),
        right_count=len(right),
        left_last=left[-1] if left else None,
        right_last=right[-1] if right else None,
    )

    result = add_messages(left, right)

    logger.debug(
        "reducer_add_messages_result",
        result_count=len(result),
        appended_count=len(result) - len(left),
    )

    return result

# Usage in MessagesState
class MessagesState(TypedDict):
    messages: Annotated[list[BaseMessage], debug_add_messages]
    # ... other fields
```

### Debug State Bloat

**Problème** : State trop large (> 100KB).

**Diagnostic** :

```python
# apps/api/src/domains/agents/utils/state_diagnostics.py
import sys
import json

def diagnose_state_bloat(state: MessagesState) -> dict:
    """Diagnose state bloat issues."""
    diagnostics = {}

    # Check each field size
    for key, value in state.items():
        size_bytes = sys.getsizeof(json.dumps(value, default=str))
        diagnostics[key] = {
            "size_bytes": size_bytes,
            "size_kb": round(size_bytes / 1024, 2),
            "item_count": len(value) if isinstance(value, (list, dict)) else 1,
        }

    # Total size
    total_size = sum(d["size_bytes"] for d in diagnostics.values())
    diagnostics["_total"] = {
        "size_bytes": total_size,
        "size_kb": round(total_size / 1024, 2),
        "size_mb": round(total_size / 1024 / 1024, 2),
    }

    return diagnostics

# Usage in node
async def router_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    # Diagnose state bloat
    diagnostics = diagnose_state_bloat(state)

    if diagnostics["_total"]["size_kb"] > 100:  # 100KB threshold
        logger.warning(
            "state_bloat_detected",
            total_size_kb=diagnostics["_total"]["size_kb"],
            largest_fields={
                k: v["size_kb"]
                for k, v in sorted(diagnostics.items(), key=lambda x: x[1].get("size_kb", 0), reverse=True)[:5]
            },
        )

    # ... rest of node
```

---

## Debugging OAuth & Connectors

### Debug OAuth Flow

**Problème** : OAuth callback échoue.

**Diagnostic** :

```python
# apps/api/src/domains/auth/oauth/google.py
logger = get_logger(__name__)

async def handle_oauth_callback(code: str, state: str) -> dict:
    """Handle OAuth callback with debug logging."""
    logger.info(
        "oauth_callback_received",
        code_length=len(code),
        state=state,
    )

    # Verify state (CSRF protection)
    stored_state = await redis_client.get(f"oauth_state:{state}")

    if not stored_state:
        logger.error(
            "oauth_state_mismatch",
            state=state,
            reason="State not found in Redis (expired or invalid)",
        )
        raise ValueError("Invalid OAuth state")

    logger.debug("oauth_state_verified", state=state)

    # Exchange code for tokens
    try:
        logger.info("oauth_token_exchange_start", code_length=len(code))

        token_response = await httpx_client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )

        logger.info(
            "oauth_token_exchange_response",
            status_code=token_response.status_code,
        )

        if token_response.status_code != 200:
            logger.error(
                "oauth_token_exchange_failed",
                status_code=token_response.status_code,
                response=token_response.text,
            )
            raise Exception("Token exchange failed")

        tokens = token_response.json()

        logger.info(
            "oauth_token_exchange_success",
            has_access_token=bool(tokens.get("access_token")),
            has_refresh_token=bool(tokens.get("refresh_token")),
            expires_in=tokens.get("expires_in"),
        )

        return tokens

    except Exception as e:
        logger.error(
            "oauth_callback_error",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise
```

### Debug Connector State

**Script debug** :

```python
# scripts/debug_connector.py
from src.infrastructure.database.session import async_session_maker
from src.domains.connectors.models import Connector
from sqlalchemy import select
import json

async def debug_connector(user_id: str):
    """Debug connector state for user."""
    async with async_session_maker() as session:
        stmt = select(Connector).where(Connector.user_id == user_id)
        result = await session.execute(stmt)
        connectors = result.scalars().all()

        print(f"Connectors for user {user_id}:")

        for conn in connectors:
            print(f"\n  Connector ID: {conn.id}")
            print(f"  Type: {conn.connector_type}")
            print(f"  Status: {conn.status}")
            print(f"  Access Token: {'***' + conn.access_token[-10:] if conn.access_token else None}")
            print(f"  Refresh Token: {'***' + conn.refresh_token[-10:] if conn.refresh_token else None}")
            print(f"  Expires At: {conn.token_expires_at}")
            print(f"  Scopes: {json.dumps(conn.scopes, indent=4)}")

# Usage
import asyncio
asyncio.run(debug_connector("user-uuid-here"))
```

---

## Observabilité et Logs

### Logs Structurés (structlog)

**Configuration** :

```python
# src/infrastructure/observability/logging.py
import structlog

# Get logger
logger = structlog.get_logger(__name__)

# Log with structured fields
logger.info(
    "user_login",
    user_id=user.id,
    email=user.email,  # ⚠️ Will be pseudonymized by PII filter
    ip_address=request.client.host,
    user_agent=request.headers.get("user-agent"),
)
```

**Output JSON** :

```json
{
  "event": "user_login",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "email": "sha256:a3c5e...",  // Pseudonymized
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0...",
  "timestamp": "2025-01-15T12:34:56.789Z",
  "level": "info",
  "logger": "src.domains.auth.service",
  "trace_id": "135a20fdc30eaf9a5711c54d34d9db2b",
  "span_id": "5711c54d34d9db2b"
}
```

### Querying Logs dans Grafana Loki

**LogQL queries** :

```logql
# Tous les logs d'erreur
{job="lia-api"} |= "level" |= "error"

# Logs pour un user spécifique
{job="lia-api"} | json | user_id="123e4567-e89b-12d3-a456-426614174000"

# Logs OAuth errors
{job="lia-api"} | json | event=~"oauth_.*" | level="error"

# Router decisions avec low confidence
{job="lia-api"} | json | event="router_decision" | confidence < 0.5

# Rate limit exceeded events
{job="lia-api"} | json | event="rate_limit_exceeded" | line_format "User {{.user_id}} exceeded rate limit for {{.key}}"

# Count errors par type
sum by (error_type) (count_over_time({job="lia-api"} | json | level="error" [5m]))
```

### Traces OpenTelemetry

**Corrélation logs → traces** :

```python
# apps/api/src/domains/agents/nodes/router_node_v3.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)
logger = get_logger(__name__)

async def router_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """Router node with tracing."""
    with tracer.start_as_current_span("router_node") as span:
        # Add span attributes
        span.set_attribute("messages_count", len(state[STATE_KEY_MESSAGES]))
        span.set_attribute("current_turn_id", state.get(STATE_KEY_CURRENT_TURN_ID))

        # Log with trace context (auto-injected)
        logger.info(
            "router_node_start",
            messages_count=len(state[STATE_KEY_MESSAGES]),
        )

        # ... node logic

        # Add result attributes
        span.set_attribute("router_intent", router_output.intent)
        span.set_attribute("router_confidence", router_output.confidence)

        return updates
```

**Query traces dans Tempo** :

```
# Rechercher traces par service
{ service.name = "lia-api" }

# Traces avec erreurs
{ status.code = "error" }

# Traces lentes (> 5s duration)
{ duration > 5s }

# Traces pour un user spécifique
{ resource.user_id = "123e4567-e89b-12d3-a456-426614174000" }
```

### Métriques Prometheus

**Query debugging metrics** :

```promql
# Router decisions par intent (last 5 min)
sum by (intent) (
  increase(router_decisions_total[5m])
)

# Graph node errors rate
rate(graph_exceptions_total[5m])

# HITL classification latency P95
histogram_quantile(0.95,
  sum(rate(hitl_classification_duration_seconds_bucket[5m])) by (le)
)

# LLM token usage par model
sum by (model) (
  increase(llm_tokens_total{type="prompt"}[1h])
)

# Cache hit rate
sum(rate(cache_hits_total[5m])) /
sum(rate(cache_requests_total[5m])) * 100
```

---

## Debugging HITL Flow

### Debug Classification

**Problème** : Classification HITL toujours "AMBIGUOUS".

**Diagnostic** :

```python
# apps/api/src/domains/agents/services/hitl_classifier.py
logger = get_logger(__name__)

async def classify(
    self,
    user_response: str,
    action_context: list[dict],
) -> HitlClassificationResult:
    """Classify HITL response with debug logging."""
    logger.info(
        "hitl_classification_start",
        user_response=user_response,
        action_context_count=len(action_context),
    )

    # Call classifier LLM
    result = await self._call_classifier_llm(user_response, action_context)

    logger.info(
        "hitl_classification_result",
        decision=result.decision,
        confidence=result.confidence,
        reasoning=result.reasoning,
        has_edited_params=bool(result.edited_params),
        has_clarification_question=bool(result.clarification_question),
    )

    # ✅ Warn if confidence too low
    if result.confidence < 0.5:
        logger.warning(
            "hitl_classification_low_confidence",
            decision=result.decision,
            confidence=result.confidence,
            user_response=user_response,
            reasoning=result.reasoning,
        )

    # ✅ Warn if always AMBIGUOUS
    if result.decision == "AMBIGUOUS":
        logger.warning(
            "hitl_classification_ambiguous",
            user_response=user_response,
            clarification_question=result.clarification_question,
        )

    return result
```

### Debug Resumption

**Problème** : Graph resumption après HITL échoue.

**Diagnostic** :

```python
# apps/api/src/domains/agents/api/service.py
logger = get_logger(__name__)

async def handle_hitl_response(
    self,
    interrupt_id: str,
    user_response: str,
    user: User,
    db: AsyncSession,
) -> dict:
    """Handle HITL response with debug logging."""
    logger.info(
        "hitl_resumption_start",
        interrupt_id=interrupt_id,
        user_response=user_response,
        user_id=user.id,
    )

    # Get checkpoint state
    try:
        config = {"configurable": {"thread_id": interrupt_id}}
        state_snapshot = await self.checkpointer.aget(config)

        if not state_snapshot:
            logger.error(
                "hitl_resumption_no_checkpoint",
                interrupt_id=interrupt_id,
            )
            raise ValueError(f"No checkpoint found for interrupt_id: {interrupt_id}")

        logger.debug(
            "hitl_resumption_checkpoint_found",
            interrupt_id=interrupt_id,
            pending_writes=len(state_snapshot.pending_writes) if state_snapshot.pending_writes else 0,
        )

    except Exception as e:
        logger.error(
            "hitl_resumption_checkpoint_error",
            interrupt_id=interrupt_id,
            error=str(e),
            exc_info=True,
        )
        raise

    # Classify response
    classification = await self.hitl_classifier.classify(user_response, action_context)

    logger.info(
        "hitl_resumption_classification",
        decision=classification.decision,
        confidence=classification.confidence,
    )

    # Resume graph with updates
    try:
        updates = {
            STATE_KEY_PLAN_APPROVED: classification.decision == "APPROVE",
            STATE_KEY_PLAN_REJECTION_REASON: classification.reasoning if classification.decision == "REJECT" else None,
        }

        logger.info(
            "hitl_resumption_updates",
            updates=updates,
        )

        # Resume graph execution
        async for event in self.graph.astream(updates, config=config):
            logger.debug("hitl_resumption_event", event=event)
            # ... process events

        logger.info("hitl_resumption_success", interrupt_id=interrupt_id)

    except Exception as e:
        logger.error(
            "hitl_resumption_graph_error",
            interrupt_id=interrupt_id,
            error=str(e),
            exc_info=True,
        )
        raise
```

---

## Debugging Performance

### Profiling avec cProfile

```python
# scripts/profile_agent_execution.py
import cProfile
import pstats
import asyncio
from src.domains.agents.api.service import AgentService

async def profile_chat():
    """Profile agent execution."""
    service = AgentService()

    # Profile execution
    profiler = cProfile.Profile()
    profiler.enable()

    # Execute chat
    await service.chat(
        message="Recherche jean dans mes contacts",
        user_id="test-user",
    )

    profiler.disable()

    # Print stats
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(20)  # Top 20 functions

# Run
asyncio.run(profile_chat())
```

**Output** :

```
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    2.345    2.345 service.py:45(chat)
       12    0.023    0.002    1.876    0.156 router_node_v3.py:80(router_node_v3)
        5    0.012    0.002    0.987    0.197 planner_node_v3.py:65(planner_node_v3)
      234    0.456    0.002    0.678    0.003 httpx.py:234(request)
       ...
```

### Memory Profiling

```python
# scripts/profile_memory.py
from memory_profiler import profile
import asyncio

@profile
async def memory_intensive_operation():
    """Profile memory usage."""
    # ... operation
    pass

asyncio.run(memory_intensive_operation())
```

### Query Slow Logs

**PostgreSQL slow queries** :

```sql
-- Enable slow query logging (postgresql.conf)
-- log_min_duration_statement = 1000  # Log queries > 1s

-- Query slow queries log
SELECT
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
WHERE mean_time > 1000  -- > 1 second
ORDER BY mean_time DESC
LIMIT 20;
```

---

## Outils et IDE

### VSCode Debugger

**Configuration** (.vscode/launch.json) :

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI Debug",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "src.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--log-level", "debug"
      ],
      "jinja": true,
      "justMyCode": false,
      "env": {
        "PYTHONPATH": "${workspaceFolder}/apps/api",
        "LOG_LEVEL": "DEBUG"
      },
      "cwd": "${workspaceFolder}/apps/api"
    },
    {
      "name": "Debug Current Test",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "${file}",
        "-v",
        "-s"
      ],
      "console": "integratedTerminal",
      "justMyCode": false,
      "cwd": "${workspaceFolder}/apps/api"
    }
  ]
}
```

**Breakpoints** :

```python
# Set breakpoint in VSCode (F9) or code
async def router_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    breakpoint()  # ✅ Debugger stops here

    # Inspect variables in Debug Console
    # > state[STATE_KEY_MESSAGES]
    # > len(state[STATE_KEY_MESSAGES])
```

### Python Debugger (pdb)

```python
import pdb

async def router_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    # Start debugger
    pdb.set_trace()

    # Commands:
    # n - next line
    # s - step into
    # c - continue
    # p variable - print variable
    # l - list code
    # q - quit
```

### Redis CLI Debug

```bash
# Connect to Redis
redis-cli -n 0  # Cache DB
redis-cli -n 1  # Session DB

# List keys
KEYS "*"
KEYS "cache:*"
KEYS "rate_limit:*"

# Get value
GET "cache:router:hash123"

# Delete key
DEL "cache:router:hash123"

# Monitor live commands
MONITOR

# Get info
INFO
INFO stats
INFO memory
```

### PostgreSQL Debug

```bash
# Connect to DB
psql -h localhost -U lia -d lia

# List tables
\dt

# Describe table
\d checkpoints

# Query checkpoints
SELECT thread_id, checkpoint_id, created_at
FROM checkpoints
ORDER BY created_at DESC
LIMIT 10;

# Query token usage
SELECT model, SUM(prompt_tokens), SUM(completion_tokens)
FROM token_usage_logs
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY model;

# Explain query plan
EXPLAIN ANALYZE
SELECT * FROM conversations WHERE user_id = 'abc123';
```

---

## Patterns de Diagnostic

### Pattern 1: Binary Search Debugging

**Problème** : Bug quelque part dans pipeline complexe.

**Approche** : Diviser pour régner.

```python
# Test middle point
logger.info("checkpoint_1_router_start")  # ✅ OK
# ... router logic
logger.info("checkpoint_2_router_end")    # ✅ OK

logger.info("checkpoint_3_planner_start") # ✅ OK
# ... planner logic
logger.info("checkpoint_4_planner_end")   # ❌ FAIL - Bug is in planner!
```

### Pattern 2: Differential Debugging

**Problème** : Fonctionnait hier, échoue aujourd'hui.

**Approche** : Comparer état avant/après.

```bash
# Git diff
git diff HEAD~1 apps/api/src/domains/agents/nodes/router_node_v3.py

# Compare logs
diff logs_yesterday.json logs_today.json

# Compare metrics
# Grafana: compare time ranges (yesterday vs today)
```

### Pattern 3: Hypothesis Testing

**Problème** : Classification HITL échoue.

**Hypothèses** :
1. ❌ Prompt mal formaté → Test : log prompt → Prompt OK
2. ❌ LLM timeout → Test : check latence → Latence 2s OK
3. ✅ JSON schema trop strict → Test : relax enum → WORKS!

### Pattern 4: Rubber Duck Debugging

**Expliquer problème à haute voix** (ou à un collègue) force clarification mentale.

---

## Debugging MCP (Model Context Protocol)

### Loggers spécifiques

Les modules MCP utilisent `structlog.get_logger(__name__)` avec les noms de loggers suivants :

| Logger | Module | Description |
|--------|--------|-------------|
| `src.infrastructure.mcp.client_manager` | `client_manager.py` | Lifecycle admin MCP (connexion, discovery, shutdown) |
| `src.infrastructure.mcp.user_pool` | `user_pool.py` | Pool per-user MCP (connexions éphémères, eviction, rate limiting) |
| `src.infrastructure.mcp.tool_adapter` | `tool_adapter.py` | Adaptation outils MCP → LangChain BaseTool (admin) |
| `src.infrastructure.mcp.user_tool_adapter` | `user_tool_adapter.py` | Adaptation outils MCP → BaseTool (per-user, JSON parsing) |
| `src.infrastructure.mcp.registration` | `registration.py` | Enregistrement des outils dans le registry |
| `src.infrastructure.mcp.security` | `security.py` | Validation SSRF, URL whitelisting |
| `src.infrastructure.mcp.oauth_flow` | `oauth_flow.py` | OAuth flow pour serveurs MCP |
| `src.infrastructure.mcp.user_context` | `user_context.py` | ContextVar pour isolation per-request |
| `src.infrastructure.mcp.excalidraw.iterative_builder` | `excalidraw/iterative_builder.py` | LLM-driven Excalidraw diagram builder (intent-only mode) |

**Activer les logs DEBUG MCP** :

```bash
# .env
LOG_LEVEL=DEBUG
# Ou filtrer par logger dans Loki/Grafana :
# {job="lia-api"} | json | logger=~"src.infrastructure.mcp.*"
```

### Problèmes courants

#### Timeout de connexion MCP

**Symptôme** : `asyncio.TimeoutError` lors de `initialize()` ou `call_tool()`.

**Diagnostic** :

```python
# Vérifier les événements de retry dans les logs
# Events à chercher :
#   mcp_server_connection_attempt_failed  (admin, avec attempt count)
#   mcp_server_connection_failed          (admin, tous les retries échoués)
#   mcp_ephemeral_call_exception_group    (user, ExceptionGroup déplié)
```

**Solutions** :
1. Vérifier que le serveur MCP est accessible : `curl -v <server_url>`
2. Augmenter le timeout : `MCP_TOOL_TIMEOUT_SECONDS=60` dans `.env`
3. Vérifier `MCP_CONNECTION_RETRY_MAX` (défaut : 3 retries avec backoff exponentiel)
4. Pour les serveurs stdio : vérifier que la commande et les args sont corrects dans la config JSON

#### Erreurs JSON parsing (per-user MCP)

**Symptôme** : Résultat MCP non structuré, un seul RegistryItem au lieu de N.

**Diagnostic** :

```python
# UserMCPToolAdapter._arun() parse le JSON arrays en N RegistryItems
# Si le parsing échoue, fallback sur un seul wrapper
# Chercher dans les logs :
#   "user_mcp_tool_result_parsed" (succès, avec item_count)
#   "user_mcp_tool_result_fallback" (fallback, contenu non-JSON)
```

**Solutions** :
1. Vérifier que le serveur MCP retourne du JSON valide
2. Vérifier les logs `mcp_ephemeral_call_tool_args` pour les arguments envoyés
3. Tester manuellement via l'endpoint admin `/api/v1/mcp/test-connection`

#### SSRF bloqué

**Symptôme** : `MCPSecurityError: URL blocked by SSRF protection`.

**Diagnostic** :

```python
# security.py valide les URLs des serveurs MCP
# Logs : mcp_server_config_invalid avec errors=["SSRF blocked: ..."]
```

**Solutions** :
1. Vérifier que l'URL du serveur n'est pas sur une adresse privée (127.0.0.1, 10.x, 192.168.x)
2. Pour le développement local, ajuster la configuration SSRF si nécessaire

#### OAuth token refresh MCP

**Symptôme** : `HTTP 401` lors des appels user MCP après expiration du token OAuth.

**Diagnostic** :

```python
# Les tokens OAuth sont rafraîchis par le ConnectorService
# Le pool user MCP met à jour auth dans get_or_connect()
# Chercher : mcp_ephemeral_call_exception_group avec sub_exception "401"
```

**Solutions** :
1. Vérifier que le `refresh_token` est valide dans la table `connectors`
2. Vérifier les logs du scheduler `token_refresh` pour les erreurs de renouvellement
3. Reconnecter le connecteur MCP depuis les paramètres utilisateur

### Debugging MCP Apps (iframes interactives)

**Problème** : Widget MCP App ne s'affiche pas dans le chat.

**Diagnostic** :

```python
# Vérifier côté serveur :
# 1. Le tool expose-t-il meta.ui.resourceUri ? → Logs : extract_app_meta
# 2. Le read_resource retourne-t-il du HTML ? → Logs : mcp_read_resource_failed
# 3. La taille HTML dépasse-t-elle la limite ? → Logs : mcp_read_resource_too_large

# Vérifier côté frontend :
# 1. Ouvrir les DevTools du navigateur
# 2. Vérifier la console pour les erreurs COEP/CORS
# 3. Vérifier que l'iframe charge bien l'URL blob://
# 4. Vérifier le PostMessage JSON-RPC bridge dans la console (events "message")
```

**Headers COEP** : Le frontend utilise `Cross-Origin-Embedder-Policy: credentialless` (pas `require-corp`). Cela permet aux iframes MCP App de charger des ressources externes (esm.sh, fonts) sans headers CORP. Trade-off : SharedArrayBuffer indisponible sur Safari iOS uniquement.

### Debugging Excalidraw (Iterative Builder)

**Problème** : Diagramme Excalidraw mal généré (overlaps, flèches manquantes).

**Diagnostic** :

```python
# Le builder fait 1 seul appel LLM qui génère tous les éléments (shapes + arrows)
# Excalidraw utilise désormais l'intent-only mode : le planner génère un intent JSON
# (pas des raw elements), et build_from_intent() construit le diagramme complet.
# Logger : src.infrastructure.mcp.excalidraw.iterative_builder

# Events clés :
#   excalidraw_build_from_intent_start   → intent JSON reçu
#   excalidraw_diagram_generated         → résultat de l'appel LLM (tous les éléments)
```

**Solutions** :
1. Vérifier les settings `MCP_EXCALIDRAW_LLM_PROVIDER` et `MCP_EXCALIDRAW_LLM_MODEL` dans `.env`
2. Vérifier que le provider Anthropic n'envoie pas `temperature` + `top_p` ensemble (Claude 4.5+ rejette cette combinaison)
3. Activer `LOG_LEVEL=DEBUG` pour voir les éléments générés par le LLM

### LogQL queries MCP

```logql
# Tous les événements MCP admin
{job="lia-api"} | json | logger=~"src.infrastructure.mcp.client_manager"

# Erreurs de connexion MCP
{job="lia-api"} | json | event=~"mcp_server_connection.*failed"

# Appels MCP per-user avec ExceptionGroup
{job="lia-api"} | json | event="mcp_ephemeral_call_exception_group"

# Rate limiting MCP
{job="lia-api"} | json | event=~".*rate_limit.*" | logger=~".*mcp.*"

# Pool user MCP : connexions et evictions
{job="lia-api"} | json | event=~"user_mcp_pool_(connected|disconnected|evicted_idle)"
```

---

## Debugging Telegram (Multi-Channel)

### Loggers spécifiques

| Logger | Module | Description |
|--------|--------|-------------|
| `src.infrastructure.channels.telegram.bot` | `bot.py` | Lifecycle bot (init, webhook setup, shutdown) |
| `src.infrastructure.channels.telegram.webhook_handler` | `webhook_handler.py` | Validation signature, parsing Updates |
| `src.infrastructure.channels.telegram.sender` | `sender.py` | Envoi messages, typing, rate limiting Telegram |
| `src.infrastructure.channels.telegram.voice` | `voice.py` | Traitement messages vocaux (ffmpeg + STT) |
| `src.domains.channels.message_router` | `message_router.py` | Routage messages entrants vers le pipeline agent |
| `src.domains.channels.inbound_handler` | `inbound_handler.py` | Handler générique messages entrants |
| `src.domains.channels.service` | `service.py` | Service binding OTP + gestion channels |
| `src.domains.channels.router` | `router.py` | Routes API channels |

### Problèmes courants

#### Webhook non reçu

**Symptôme** : Le bot ne répond pas aux messages Telegram.

**Diagnostic** :

```bash
# 1. Vérifier que le webhook est configuré
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo

# Réponse attendue :
# {
#   "url": "https://your-domain.com/api/v1/channels/telegram/webhook",
#   "has_custom_certificate": false,
#   "pending_update_count": 0,
#   "last_error_date": ...,
#   "last_error_message": "..."
# }

# 2. Vérifier les logs du webhook
# Events : telegram_webhook_no_secret_configured, telegram_webhook_signature_invalid

# 3. En développement local, utiliser ngrok :
ngrok http 8000
# Puis configurer le webhook :
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<ngrok-url>/api/v1/channels/telegram/webhook&secret_token=<SECRET>"
```

**Solutions** :
1. Vérifier `CHANNELS_ENABLED=true` et `TELEGRAM_BOT_TOKEN` dans `.env`
2. Vérifier `TELEGRAM_WEBHOOK_SECRET` si configuré
3. Le webhook retourne 200 immédiatement, le traitement se fait dans `asyncio.create_task()` — les erreurs sont dans les logs, pas dans la réponse HTTP
4. Vérifier que le certificat SSL est valide (Telegram n'envoie pas à des URLs HTTP)

#### OTP expired

**Symptôme** : L'utilisateur envoie le code OTP mais reçoit "Code expiré".

**Diagnostic** :

```bash
# Vérifier les clés OTP dans Redis
redis-cli -n 2
KEYS "channel_otp:*"
TTL "channel_otp:<code>"

# L'OTP a un TTL configurable (défaut : 5 minutes)
# Vérifier CHANNEL_OTP_TTL_SECONDS dans .env
```

**Solutions** :
1. Augmenter `CHANNEL_OTP_TTL_SECONDS` si les utilisateurs sont trop lents
2. Vérifier les logs `channel_otp_expired` et `channel_otp_verified`
3. Vérifier que Redis est accessible et que la DB de cache (DB2) fonctionne

#### Bot token invalide

**Symptôme** : `telegram.error.InvalidToken` au démarrage.

**Diagnostic** :

```bash
# Tester le token manuellement
curl https://api.telegram.org/bot<TOKEN>/getMe
# Doit retourner les infos du bot (id, username, etc.)
```

**Solutions** :
1. Régénérer le token via BotFather (`/revoke` puis `/newbot` ou `/token`)
2. Vérifier qu'il n'y a pas d'espaces ou de caractères invisibles dans `TELEGRAM_BOT_TOKEN`

#### Rate limiting Telegram

**Symptôme** : `telegram.error.RetryAfter` avec délai en secondes.

**Diagnostic** :

```python
# Le sender gère automatiquement RetryAfter avec asyncio.sleep()
# Logs : telegram_rate_limited avec retry_after_seconds
# Aussi : telegram_send_forbidden (bot bloqué par l'utilisateur)
#         telegram_send_bad_request (format message invalide)
```

### HITL via Telegram (inline keyboards)

**Problème** : Les boutons d'approbation ne fonctionnent pas.

**Diagnostic** :

```python
# Le module hitl_keyboard.py crée des InlineKeyboardMarkup
# Les callbacks sont traités par le webhook_handler
# Events à chercher :
#   telegram_callback_query_received
#   telegram_hitl_approval_processed
#   telegram_hitl_rejection_processed

# Vérifier que le callback_data respecte le format attendu :
# "hitl:approve:<interrupt_id>" ou "hitl:reject:<interrupt_id>"
```

### LogQL queries Telegram

```logql
# Tous les événements Telegram
{job="lia-api"} | json | logger=~"src.infrastructure.channels.telegram.*"

# Webhooks reçus et traités
{job="lia-api"} | json | logger=~".*webhook_handler" | level="info"

# Erreurs d'envoi Telegram
{job="lia-api"} | json | logger=~".*telegram.sender" | level=~"error|warning"

# Messages routés depuis Telegram
{job="lia-api"} | json | logger=~".*message_router" | event=~"channel_message.*"
```

---

## Debugging Heartbeat (Notifications Proactives)

### Loggers spécifiques

| Logger | Module | Description |
|--------|--------|-------------|
| `src.domains.heartbeat.proactive_task` | `proactive_task.py` | Décision LLM + génération message |
| `src.domains.heartbeat.context_aggregator` | `context_aggregator.py` | Agrégation contexte multi-sources |
| `src.domains.heartbeat.prompts` | `prompts.py` | Prompts LLM (décision + rewrite) |
| `src.domains.heartbeat.repository` | `repository.py` | Persistance notifications heartbeat |
| `src.domains.heartbeat.router` | `router.py` | Routes API heartbeat |
| `src.infrastructure.proactive.runner` | `runner.py` | Orchestration batch ProactiveTask |
| `src.infrastructure.proactive.eligibility` | `eligibility.py` | Vérification éligibilité (quotas, cooldowns, fenêtres horaires) |
| `src.infrastructure.proactive.notification` | `notification.py` | Dispatch multi-canal (archive + SSE + FCM + Telegram) |
| `src.infrastructure.scheduler.heartbeat_notification` | `heartbeat_notification.py` | Job APScheduler déclencheur |

### Problèmes courants

#### Context aggregation timeout

**Symptôme** : Le heartbeat ne se déclenche pas ou est très lent.

**Diagnostic** :

```python
# Le ContextAggregator fetch 8 sources en parallèle (asyncio.gather)
# Chaque source est indépendamment failable
# Events à chercher :
#   heartbeat_context_aggregation_start
#   heartbeat_context_source_failed  (source individuelle en erreur)
#   heartbeat_context_aggregation_complete (avec durée)
```

**Solutions** :
1. Vérifier les connecteurs Google (Calendar, Tasks) : tokens expirés ?
2. Vérifier l'API météo : quota dépassé ? Clé invalide ?
3. Le timeout global est dans `MCP_TOOL_TIMEOUT_SECONDS` — chaque source a son propre timeout plus court
4. Une source en erreur n'empêche pas les autres de fonctionner (graceful degradation)

#### Eligibility check rejections

**Symptôme** : Aucune notification envoyée malgré le scheduler qui tourne.

**Diagnostic** :

```python
# L'EligibilityChecker vérifie dans l'ordre :
# 1. heartbeat_enabled sur le User (opt-in)
# 2. Fenêtre horaire (heartbeat_notify_start_hour / heartbeat_notify_end_hour)
# 3. Quota journalier (max notifications par jour)
# 4. Cooldown (délai minimum entre 2 notifications)
# 5. Déduplication cross-type (pas de doublon avec les notifications interests)

# Events à chercher :
#   proactive_user_not_eligible (avec reason)
#   proactive_quota_exceeded
#   proactive_cooldown_active
#   proactive_time_window_outside
```

**Solutions** :
1. Vérifier que `heartbeat_enabled=true` pour l'utilisateur en base
2. Vérifier les heures : `heartbeat_notify_start_hour` et `heartbeat_notify_end_hour` (timezone utilisateur)
3. Vérifier les quotas Redis :

```bash
redis-cli -n 2
KEYS "proactive:quota:heartbeat:*"
KEYS "proactive:cooldown:heartbeat:*"
```

#### Weather API errors

**Symptôme** : Le contexte météo est toujours vide.

**Diagnostic** :

```python
# Le ContextAggregator appelle le service météo avec change detection
# (rain start/end, temp drop, wind alert)
# Events : heartbeat_context_source_failed avec source="weather"
```

**Solutions** :
1. Vérifier la clé API météo dans `.env`
2. Vérifier que l'utilisateur a une localisation configurée
3. Tester manuellement l'API météo depuis le conteneur

#### Forcer une exécution immédiate

```bash
# Shell dans le conteneur API
task shell:api

# Déclencher manuellement le job heartbeat
python -c "
import asyncio
from src.infrastructure.scheduler.heartbeat_notification import run_heartbeat_notification
asyncio.run(run_heartbeat_notification())
"
```

### LogQL queries Heartbeat

```logql
# Pipeline complet heartbeat
{job="lia-api"} | json | logger=~"src.domains.heartbeat.*"

# Décisions LLM (skip vs notify)
{job="lia-api"} | json | event=~"heartbeat_decision.*"

# Éligibilité
{job="lia-api"} | json | logger=~".*proactive.eligibility" | event=~"proactive_user.*"

# Notifications envoyées
{job="lia-api"} | json | logger=~".*proactive.notification" | event=~"proactive_notification.*"

# Contexte agrégé
{job="lia-api"} | json | event=~"heartbeat_context.*"
```

---

## Debugging Scheduled Actions

### Loggers spécifiques

| Logger | Module | Description |
|--------|--------|-------------|
| `src.infrastructure.scheduler.scheduled_action_executor` | `scheduled_action_executor.py` | Exécution des actions planifiées |
| `src.domains.scheduled_actions.service` | `service.py` | CRUD et gestion des actions |
| `src.domains.scheduled_actions.repository` | `repository.py` | Persistance et queries DB |

Le scheduler principal APScheduler est initialisé dans `main.py` (lifespan). Chaque job utilise un `SchedulerLock` Redis pour éviter les exécutions dupliquées avec plusieurs workers uvicorn.

### Problèmes courants

#### Timezone issues

**Symptôme** : Les actions se déclenchent à la mauvaise heure.

**Diagnostic** :

```python
# Le scheduled_action_executor utilise CronTrigger avec la timezone utilisateur
# Events à chercher :
#   scheduled_action_trigger_calculated (avec next_trigger_at et timezone)
#   scheduled_action_due (action sélectionnée pour exécution)

# Vérifier la timezone stockée sur l'action :
# SELECT id, cron_expression, timezone, next_trigger_at FROM scheduled_actions WHERE user_id = '...';
```

**Solutions** :
1. Vérifier que la timezone utilisateur est correcte (`User.timezone`)
2. Vérifier que le serveur a les bons fichiers tzdata installés
3. Comparer `next_trigger_at` (UTC en base) avec l'heure locale attendue

#### Actions auto-disabled

**Symptôme** : Les actions ne s'exécutent plus, statut `disabled` en base.

**Diagnostic** :

```python
# Après N échecs consécutifs (SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES),
# l'action est automatiquement désactivée
# Events :
#   scheduled_action_auto_disabled (avec consecutive_failures count)
#   scheduled_action_execution_failed (avec error detail)
```

**Solutions** :
1. Vérifier le champ `consecutive_failures` en base
2. Consulter les logs d'erreur de la dernière exécution
3. Corriger la cause racine (token expiré, service indisponible, etc.)
4. Réactiver manuellement l'action via l'API ou en base :

```sql
UPDATE scheduled_actions SET enabled = true, consecutive_failures = 0 WHERE id = '<action_id>';
```

#### Distributed lock conflicts

**Symptôme** : Les actions s'exécutent en double ou pas du tout.

**Diagnostic** :

```bash
# Vérifier les locks Redis du scheduler
redis-cli -n 2
KEYS "scheduler_lock:*"
TTL "scheduler_lock:scheduled_action_executor"

# Un TTL très long indique un lock orphelin (crash sans release)
```

**Solutions** :
1. Si un lock est orphelin (TTL anormalement long), le supprimer manuellement :

```bash
redis-cli -n 2
DEL "scheduler_lock:scheduled_action_executor"
```

2. Vérifier que le nombre de workers uvicorn est cohérent
3. Les locks ont un TTL de sécurité — si le job crash, le lock sera automatiquement libéré après expiration

#### Leader election stale lock

**Symptôme** : Aucun job schedulé ne s'exécute après un redémarrage du conteneur. Les logs montrent `scheduler_leader_stale_lock_detected` au démarrage suivi de `scheduler_leader_starting_re_election`.

**Diagnostic** :

```bash
# Vérifier le lock leader dans Redis (DB2 = cache)
redis-cli -n 2
GET "scheduler:leader"        # Qui détient le lock
TTL "scheduler:leader"        # Temps restant

# Vérifier les logs
# Events à chercher :
#   scheduler_leader_elected (method=immediate | re_election)
#   scheduler_leader_stale_lock_detected (lock_holder, lock_ttl_remaining)
#   scheduler_leader_starting_re_election
```

**Solutions** :
1. **Attendre** : le lock expire automatiquement (TTL 120s) et la re-election background le récupère (~5s après expiration)
2. Si urgence, supprimer manuellement : `DEL "scheduler:leader"`
3. Un `docker restart` du conteneur API déclenche le même cycle

#### Vérifier les jobs APScheduler

```bash
# Shell dans le conteneur API
task shell:api

# Lister les jobs enregistrés
python -c "
from src.main import app
# Les jobs sont visibles dans les logs au démarrage :
# scheduler_job_added avec job_id, trigger, next_run_time
"

# Vérifier les métriques Prometheus
# background_job_duration_seconds{job_name="scheduled_action_executor"}
# background_job_errors_total{job_name="scheduled_action_executor"}
```

### LogQL queries Scheduled Actions

```logql
# Exécution des actions planifiées
{job="lia-api"} | json | logger=~".*scheduled_action_executor"

# Actions en erreur
{job="lia-api"} | json | event=~"scheduled_action.*failed"

# Actions auto-désactivées
{job="lia-api"} | json | event="scheduled_action_auto_disabled"

# Locks distribués
{job="lia-api"} | json | event=~"scheduler_lock.*"

# Tous les jobs scheduler
{job="lia-api"} | json | logger=~"src.infrastructure.scheduler.*" | level=~"info|warning|error"
```

---

## Troubleshooting Commun

### Problème : GraphInterrupt non capturé

**Symptôme** : HITL interrupt ne se déclenche pas.

**Solutions** :

1. **Vérifier tool_approval_enabled** :

```python
logger.info("tool_approval_setting", tool_approval_enabled=state.get(STATE_KEY_TOOL_APPROVAL_ENABLED))
```

2. **Vérifier interrupt levée** :

```python
# approval_gate_node.py
logger.info("raising_graph_interrupt")
raise GraphInterrupt({...})
```

3. **Vérifier catch dans service** :

```python
# service.py
try:
    async for event in self.graph.astream(...):
        # ...
except GraphInterrupt as interrupt:
    logger.info("graph_interrupt_caught", interrupt=interrupt.args[0])
    # ... handle interrupt
```

### Problème : Token usage = 0

**Symptôme** : Métriques token = 0 alors que LLM appelé.

**Solutions** :

1. **Vérifier callback chain** :

```python
# infrastructure/llm/factory.py
logger.debug(
    "llm_callbacks_configured",
    callbacks=[type(cb).__name__ for cb in callbacks],
)
# Expected: ['MetricsCallback', 'LangfuseCallback', 'TokenTrackingCallback']
```

2. **Vérifier extraction tokens** :

```python
# instrumentation.py
logger.debug(
    "token_extraction",
    strategy=strategy,  # Should be: 'usage_metadata', 'llm_output', or 'fallback'
    prompt_tokens=prompt_tokens,
    completion_tokens=completion_tokens,
)
```

### Problème : Rate limit loop

**Symptôme** : Requêtes bloquées en permanence.

**Solutions** :

```bash
# Check Redis rate limit keys
redis-cli
KEYS "rate_limit:*"

# Delete specific key to reset
DEL "rate_limit:google_contacts:search:user_123"

# Or flush all (dev only!)
FLUSHDB
```

### Problème : OAuth refresh loop

**Symptôme** : Token refresh en boucle infinie.

**Solutions** :

```python
# Add circuit breaker
refresh_attempt_key = f"oauth_refresh_attempt:{connector_id}"
attempt_count = await redis_client.incr(refresh_attempt_key)
await redis_client.expire(refresh_attempt_key, 60)

if attempt_count > 3:
    logger.error("oauth_refresh_loop_detected")
    raise Exception("OAuth refresh loop - check refresh token validity")
```

### Problème : Checkpoint state bloat

**Symptôme** : DB checkpoint table > 10GB.

**Solutions** :

```sql
-- Clean old checkpoints (older than 30 days)
DELETE FROM checkpoints
WHERE created_at < NOW() - INTERVAL '30 days';

-- Vacuum to reclaim space
VACUUM FULL checkpoints;
```

### Problème : API inaccessible depuis le réseau local (Docker Desktop Windows)

**Symptôme** : L'API répond sur `localhost:8000` mais pas sur l'IP du réseau local (`192.168.0.x:8000`).

**Diagnostic** :

```bash
# Test depuis Windows
curl -k https://localhost:8000/health     # ✅ OK
curl -k https://YOUR_LOCAL_IP:8000/health  # ❌ Timeout

# Test depuis l'intérieur du conteneur - confirme que l'API fonctionne
docker exec lia-api-dev python -c "import httpx; r = httpx.get('https://127.0.0.1:8000/health', verify=False); print(r.status_code)"
# Output: 200
```

**Cause** : Docker Desktop Windows utilise WSL2 avec un NAT interne. Les ports exposés (`0.0.0.0:8000` dans docker-compose) ne sont bindés qu'à l'interface localhost de Windows, pas aux interfaces réseau physiques.

**Solutions** :

1. **Port Forwarding Windows (netsh)** - Recommandé :

```powershell
# PowerShell en Administrateur
# Remplacer YOUR_LOCAL_IP par votre IP (voir: ipconfig)

netsh interface portproxy add v4tov4 listenaddress=YOUR_LOCAL_IP listenport=8000 connectaddress=127.0.0.1 connectport=8000

# Vérifier
netsh interface portproxy show v4tov4

# Pour le frontend aussi
netsh interface portproxy add v4tov4 listenaddress=YOUR_LOCAL_IP listenport=3000 connectaddress=127.0.0.1 connectport=3000
```

2. **Autoriser le port dans le pare-feu Windows** :

```powershell
# PowerShell en Administrateur
New-NetFirewallRule -DisplayName "Docker API 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "Docker Web 3000" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow
```

3. **Utiliser un reverse proxy** (Caddy, nginx) :

```bash
# Avec Caddy (simple)
caddy reverse-proxy --from :8000 --to localhost:8000
```

**Note** : Ce problème est spécifique à Docker Desktop Windows avec WSL2. Sur Linux natif ou macOS, les ports sont exposés sur toutes les interfaces par défaut.

**Logs à vérifier** :

```bash
# Vérifier que Docker expose bien le port
docker port lia-api-dev
# Output attendu: 8000/tcp -> 0.0.0.0:8000

# Vérifier les connexions actives dans le conteneur
docker exec lia-api-dev sh -c "cat /proc/net/tcp | grep ':1F40'"
```

---

### Problème : Logs manquants dans Loki

**Symptôme** : Logs n'apparaissent pas dans Grafana.

**Solutions** :

1. **Vérifier Promtail** :

```bash
# Check Promtail status
docker-compose logs promtail

# Check Promtail config
cat infrastructure/observability/promtail/config.yml
```

2. **Vérifier format logs** :

```python
# Logs MUST be JSON for Loki parsing
logger.info("test_event", key="value")  # ✅ OK

print("test event")  # ❌ BAD - not structured
```

3. **Query Loki directly** :

```bash
# Check Loki API
curl -G http://localhost:3100/loki/api/v1/query \
  --data-urlencode 'query={job="lia-api"}' \
  --data-urlencode 'limit=10'
```

---

## Références

### Documentation Officielle

- **LangGraph Debug** : [https://langchain-ai.github.io/langgraph/how-tos/debug/](https://langchain-ai.github.io/langgraph/how-tos/debug/)
- **structlog** : [https://www.structlog.org](https://www.structlog.org)
- **OpenTelemetry Python** : [https://opentelemetry-python.readthedocs.io](https://opentelemetry-python.readthedocs.io)
- **Prometheus** : [https://prometheus.io/docs](https://prometheus.io/docs)
- **Grafana Loki** : [https://grafana.com/docs/loki](https://grafana.com/docs/loki)

### Documentation Interne

- [GRAPH_AND_AGENTS_ARCHITECTURE.md](../technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) : architecture agents
- [OBSERVABILITY_AND_MONITORING.md](../technical/OBSERVABILITY_AND_MONITORING.md) : observabilité complète
- [MCP_INTEGRATION.md](../technical/MCP_INTEGRATION.md) : intégration MCP (admin + per-user + OAuth)
- [CHANNELS_INTEGRATION.md](../technical/CHANNELS_INTEGRATION.md) : intégration multi-channel (Telegram)
- [HEARTBEAT_AUTONOME.md](../technical/HEARTBEAT_AUTONOME.md) : heartbeat autonome (notifications proactives)
- [GUIDE_TESTING.md](./GUIDE_TESTING.md) : tests et debugging
- [GUIDE_PERFORMANCE_TUNING.md](./GUIDE_PERFORMANCE_TUNING.md) : optimisation performance

### Outils

- **VSCode Extensions** : Python, Pylance, Python Debugger
- **Browser Extensions** : JSON Viewer, ModHeader (OAuth debug)
- **CLI Tools** : jq, httpie, redis-cli, psql

---

**Fin du Guide Pratique : Debugging et Diagnostic**

Pour toute question, consulter :
- **Équipe développement** : debugging complexe agents LangGraph
- **DevOps** : debugging infrastructure, observabilité
- **Issues GitHub** : signaler bugs avec logs/traces complètes
