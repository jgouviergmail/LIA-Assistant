# ADR-041: LangGraph State Schema Evolution

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: State versioning and migration for LangGraph checkpoints
**Related Documentation**: `docs/technical/STATE_AND_CHECKPOINT.md`

---

## Context and Problem Statement

Les checkpoints LangGraph persistent en base de données, nécessitant une gestion des évolutions :

1. **Schema Versioning** : Détecter les états obsolètes
2. **Migration Functions** : Migrer les états vers la version courante
3. **Backward Compatibility** : Charger les anciens checkpoints
4. **Custom Reducers** : Token truncation et registry merging

**Question** : Comment gérer l'évolution du schéma MessagesState sans casser les conversations existantes ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **`_schema_version` Field** : Version tracking dans l'état
2. **Migration Functions** : Upgrade automatique au chargement
3. **Custom Reducers** : Token truncation, registry LRU
4. **State Validation** : Détection des inconsistances

### Nice-to-Have:

- Observability via Prometheus
- Checkpoint size tracking
- Validation on critical nodes

---

## Decision Outcome

**Chosen option**: "**Schema Versioning + Migration Functions + Custom Reducers + Validation**"

### Architecture Overview

```mermaid
graph TB
    subgraph "STATE SCHEMA"
        STATE[MessagesState TypedDict<br/>30+ fields]
        VERSION[_schema_version<br/>"1.0" current]
        REDUCERS[Custom Reducers<br/>add_messages_with_truncate<br/>merge_registry]
    end

    subgraph "CHECKPOINT PERSISTENCE"
        SAVER[InstrumentedAsyncPostgresSaver]
        TABLES[(checkpoints<br/>checkpoint_blobs<br/>checkpoint_writes)]
        METRICS[Prometheus Metrics<br/>save/load duration, size]
    end

    subgraph "MIGRATION"
        DETECT[needs_migration()<br/>Version check]
        MIGRATE[migrate_state_to_current()<br/>Apply migrations]
        VALIDATE[validate_state_consistency()<br/>Detect issues]
    end

    STATE --> VERSION
    STATE --> REDUCERS
    SAVER --> TABLES
    SAVER --> METRICS
    DETECT --> MIGRATE
    MIGRATE --> VALIDATE

    style STATE fill:#4CAF50,stroke:#2E7D32,color:#fff
    style SAVER fill:#2196F3,stroke:#1565C0,color:#fff
    style MIGRATE fill:#FF9800,stroke:#F57C00,color:#fff
```

### MessagesState Definition

```python
# apps/api/src/domains/agents/models.py

class MessagesState(TypedDict):
    """
    Complete agent state schema with versioning.

    Version 1.0 (2025-10-27):
    - Added _schema_version field
    - 30+ fields organized by category
    """

    # ═══════════════════════════════════════════════════════════════
    # SCHEMA VERSIONING
    # ═══════════════════════════════════════════════════════════════
    _schema_version: str  # "1.0" current

    # ═══════════════════════════════════════════════════════════════
    # CORE CONVERSATION
    # ═══════════════════════════════════════════════════════════════
    messages: Annotated[list[BaseMessage], add_messages_with_truncate]
    metadata: dict[str, Any]
    current_turn_id: int
    session_id: str

    # ═══════════════════════════════════════════════════════════════
    # USER PREFERENCES
    # ═══════════════════════════════════════════════════════════════
    user_timezone: str | None
    user_language: str | None
    user_location: dict[str, Any] | None
    oauth_scopes: dict[str, list[str]]
    personality_instruction: str | None

    # ═══════════════════════════════════════════════════════════════
    # ROUTING & PLANNING
    # ═══════════════════════════════════════════════════════════════
    routing_history: list[str]
    orchestration_plan: OrchestrationPlan | None
    execution_plan: ExecutionPlan | None
    planner_metadata: dict[str, Any] | None
    planner_error: str | None

    # ═══════════════════════════════════════════════════════════════
    # AGENT EXECUTION
    # ═══════════════════════════════════════════════════════════════
    agent_results: dict[str, Any]  # "{turn_id}:{agent_name}" → results
    completed_steps: set[str]  # Phase 5.2B asyncio

    # ═══════════════════════════════════════════════════════════════
    # HITL APPROVAL
    # ═══════════════════════════════════════════════════════════════
    validation_result: ValidationResult | None
    approval_evaluation: ApprovalEvaluation | None
    plan_approved: bool | None
    plan_rejection_reason: str | None

    # ═══════════════════════════════════════════════════════════════
    # SEMANTIC VALIDATION
    # ═══════════════════════════════════════════════════════════════
    semantic_validation: SemanticValidation | None
    clarification_response: str | None
    needs_replan: bool
    planner_iteration: int

    # ═══════════════════════════════════════════════════════════════
    # CONTEXT RESOLUTION
    # ═══════════════════════════════════════════════════════════════
    last_action_turn_id: int | None
    turn_type: str | None
    resolved_context: dict[str, Any] | None

    # ═══════════════════════════════════════════════════════════════
    # DATA REGISTRY
    # ═══════════════════════════════════════════════════════════════
    registry: Annotated[dict[str, RegistryItem], merge_registry]
    pending_draft_critique: str | None
    draft_action_result: str | None

    # ═══════════════════════════════════════════════════════════════
    # POST-PROCESSING
    # ═══════════════════════════════════════════════════════════════
    content_final_replacement: str | None


CURRENT_SCHEMA_VERSION = "1.0"
```

### Schema Versioning Functions

```python
# apps/api/src/domains/agents/models.py

def get_state_schema_version(state: MessagesState) -> str:
    """
    Get schema version from state.

    Returns "0.0" for legacy states without version field.
    """
    return state.get("_schema_version", "0.0")


def needs_migration(state: MessagesState) -> bool:
    """Check if state needs migration to current version."""
    return get_state_schema_version(state) != CURRENT_SCHEMA_VERSION


def migrate_state_to_current(state: MessagesState) -> MessagesState:
    """
    Apply all migrations to reach CURRENT_SCHEMA_VERSION.

    Migrations are applied sequentially:
    - v0.0 → v1.0: Add _schema_version field
    - v1.0 → v1.1: (future) Add new_field with default
    - etc.

    Returns:
        Updated state at CURRENT_SCHEMA_VERSION
    """
    current_version = get_state_schema_version(state)

    # Migration: v0.0 → v1.0
    if current_version == "0.0":
        logger.info("migrating_state_0.0_to_1.0")
        state["_schema_version"] = "1.0"
        current_version = "1.0"

    # Future migration example: v1.0 → v1.1
    # if current_version == "1.0":
    #     logger.info("migrating_state_1.0_to_1.1")
    #     state["new_field"] = default_value
    #     state["_schema_version"] = "1.1"
    #     current_version = "1.1"

    return state
```

### Custom Reducer: add_messages_with_truncate

```python
# apps/api/src/domains/agents/models.py

def add_messages_with_truncate(
    left: list[BaseMessage],
    right: list[BaseMessage] | BaseMessage,
) -> list[BaseMessage]:
    """
    Custom reducer with 4-step truncation strategy.

    Performance: 93% token reduction (500K → 7K in long conversations)

    Steps:
    1. add_messages() - Handle RemoveMessage for replacement
    2. trim_messages() - Token-based truncation (100K max)
    3. Fallback - Count-based truncation (50 messages max)
    4. Validate - Remove orphan ToolMessages (OpenAI compatibility)
    """
    # Step 1: Merge messages (handles RemoveMessage)
    combined = add_messages(left, right if isinstance(right, list) else [right])

    # Step 2: Token-based truncation
    try:
        encoding = tiktoken.get_encoding("o200k_base")

        def count_tokens(messages: list[BaseMessage]) -> int:
            return sum(len(encoding.encode(m.content or "")) for m in messages)

        truncated = trim_messages(
            combined,
            max_tokens=settings.max_tokens_history,  # Default: 100,000
            token_counter=count_tokens,
            strategy="last",  # Keep most recent
            include_system=True,
        )
    except Exception as e:
        logger.warning("token_truncation_failed", error=str(e))
        # Step 3: Fallback to count-based truncation
        truncated = combined[-settings.max_messages_history:]  # Default: 50

    # Step 4: Validate (remove orphan ToolMessages)
    return remove_orphan_tool_messages(truncated)


def remove_orphan_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Remove ToolMessages without corresponding AIMessage with tool_calls.

    Prevents OpenAI API errors after truncation.
    """
    valid_tool_call_ids: set[str] = set()

    # Collect valid tool_call_ids from AIMessages
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tool_call in msg.tool_calls:
                valid_tool_call_ids.add(tool_call["id"])

    # Filter ToolMessages
    return [
        msg for msg in messages
        if not isinstance(msg, ToolMessage)
        or msg.tool_call_id in valid_tool_call_ids
    ]
```

### Custom Reducer: merge_registry

```python
# apps/api/src/domains/agents/data_registry/state.py

REGISTRY_MAX_ITEMS = 100  # LRU eviction threshold


def merge_registry(
    current: dict[str, RegistryItem],
    updates: dict[str, RegistryItem],
) -> dict[str, RegistryItem]:
    """
    Merge registry with LRU eviction.

    Strategy:
    1. Last-write-wins: New items overwrite existing
    2. LRU eviction: When exceeds REGISTRY_MAX_ITEMS,
       evict oldest items (by meta.timestamp)

    Pure function contract: No side effects
    """
    # Merge with last-write-wins
    merged = {**current, **updates}

    # LRU eviction if needed
    if len(merged) > REGISTRY_MAX_ITEMS:
        # Sort by timestamp (oldest first)
        sorted_items = sorted(
            merged.items(),
            key=lambda x: x[1].meta.timestamp,
        )
        # Keep most recent
        merged = dict(sorted_items[-REGISTRY_MAX_ITEMS:])

    return merged


# Type alias for state definition
RegistryField = Annotated[dict[str, RegistryItem], merge_registry]
```

### State Validation

```python
# apps/api/src/domains/agents/models.py

def validate_state_consistency(state: MessagesState) -> list[str]:
    """
    Validate state for inconsistencies.

    Returns list of issues (empty = valid).

    Called at critical checkpoints:
    - After router_node execution
    - Before response_node execution
    - After state updates in reducers
    """
    issues: list[str] = []

    # Check 1: Negative turn_id
    turn_id = state.get("current_turn_id", 0)
    if turn_id < 0:
        issues.append(f"Negative turn_id detected: {turn_id}")

    # Check 2: agent_results key format
    agent_results = state.get("agent_results", {})
    for key in agent_results:
        if ":" not in key:
            issues.append(f"Invalid agent_results key format: '{key}'")
            continue

        # Check 3: Future turn_id references
        key_turn_id = int(key.split(":")[0])
        if key_turn_id > turn_id:
            issues.append(f"Future turn detected: {key} (current={turn_id})")

    # Check 4: Plan-result alignment
    orchestration_plan = state.get("orchestration_plan")
    if orchestration_plan:
        planned_agents = set(orchestration_plan.selected_agents)
        result_agents = {k.split(":")[1] for k in agent_results if ":" in k}

        unexpected = result_agents - planned_agents
        if unexpected:
            issues.append(f"Unexpected agent results: {unexpected} (not in plan)")

    # Check 5: Messages type
    if not isinstance(state.get("messages", []), list):
        issues.append("messages is not a list")

    # Check 6: Metadata type
    if not isinstance(state.get("metadata", {}), dict):
        issues.append("metadata is not a dict")

    return issues
```

### Checkpoint Usage Pattern

```python
# apps/api/src/domains/conversations/checkpointer.py

class InstrumentedAsyncPostgresSaver:
    """Checkpointer with metrics and migration support."""

    async def aget(self, config: RunnableConfig) -> Checkpoint | None:
        """Load checkpoint with migration."""
        start = time.perf_counter()

        try:
            checkpoint = await self._saver.aget(config)

            if checkpoint:
                state = checkpoint["channel_values"]

                # Check and migrate state
                if needs_migration(state):
                    logger.info(
                        "migrating_checkpoint_state",
                        from_version=get_state_schema_version(state),
                        to_version=CURRENT_SCHEMA_VERSION,
                    )
                    state = migrate_state_to_current(state)
                    checkpoint["channel_values"] = state

                # Track metrics
                checkpoint_load_duration_seconds.labels(
                    node_name="checkpoint_load"
                ).observe(time.perf_counter() - start)

            return checkpoint

        except Exception as e:
            checkpoint_errors_total.labels(
                error_type=self._classify_error(e),
                operation="load",
            ).inc()
            raise

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: dict[str, Any],
        new_versions: dict[str, int],
    ) -> None:
        """Save checkpoint with metrics."""
        start = time.perf_counter()

        try:
            await self._saver.aput(config, checkpoint, metadata, new_versions)

            # Track metrics
            node_name = metadata.get("source", "unknown")
            checkpoint_save_duration_seconds.labels(node_name=node_name).observe(
                time.perf_counter() - start
            )

            # Track size
            size = len(pickle.dumps(checkpoint))
            checkpoint_size_bytes.labels(node_name=node_name).observe(size)

        except Exception as e:
            checkpoint_errors_total.labels(
                error_type=self._classify_error(e),
                operation="save",
            ).inc()
            raise
```

### Registry Item Model

```python
# apps/api/src/domains/agents/data_registry/models.py

class RegistryItemType(str, Enum):
    """Extensible item types."""

    # Google Workspace
    CONTACT = "contact"
    EMAIL = "email"
    EVENT = "event"
    TASK = "task"
    FILE = "file"
    CALENDAR = "calendar"

    # External APIs
    PLACE = "place"
    WEATHER = "weather"
    WIKIPEDIA_ARTICLE = "wikipedia_article"
    SEARCH_RESULT = "search_result"

    # HITL
    DRAFT = "draft"

    # Visualization
    CHART = "chart"

    # Utility
    NOTE = "note"
    CALENDAR_SLOT = "calendar_slot"


class RegistryItemMeta(BaseModel):
    """Metadata for registry items."""

    source: str                      # e.g., 'google_contacts', 'gmail'
    domain: str | None = None        # e.g., 'contacts', 'emails'
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tool_name: str | None = None     # Tool that created item
    step_id: str | None = None       # ExecutionPlan step ID
    ttl_seconds: int | None = None   # Time-to-live for cache
    turn_id: int | None = None       # Turn when created


class RegistryItem(BaseModel):
    """Data registry item with deterministic ID."""

    id: str                          # SHA256 hash of unique_key
    type: RegistryItemType
    payload: dict[str, Any]          # Domain-specific data
    meta: RegistryItemMeta

    @classmethod
    def create(
        cls,
        type: RegistryItemType,
        unique_key: str,
        payload: dict[str, Any],
        **meta_kwargs,
    ) -> "RegistryItem":
        """Create item with deterministic ID."""
        item_id = hashlib.sha256(unique_key.encode()).hexdigest()[:16]
        return cls(
            id=item_id,
            type=type,
            payload=payload,
            meta=RegistryItemMeta(**meta_kwargs),
        )
```

### Thread Isolation

```python
# Thread ID = Conversation ID
config = RunnableConfig(
    configurable={
        "thread_id": str(conversation.id),  # UUID as string
    }
)

# All checkpoints isolated by thread_id
result = await graph.ainvoke(input_state, config=config)

# Cleanup on conversation reset
await checkpointer.adelete_thread(str(conversation.id))
```

### Consequences

**Positive**:
- ✅ **Schema Versioning** : `_schema_version` field tracking
- ✅ **Migration Functions** : Automatic upgrade at load time
- ✅ **Custom Reducers** : Token truncation (93% reduction), LRU registry
- ✅ **State Validation** : Detect inconsistencies early
- ✅ **Observability** : Prometheus metrics for checkpoints
- ✅ **Thread Isolation** : Conversation-level state separation

**Negative**:
- ⚠️ Migration complexity grows with schema versions
- ⚠️ Large checkpoints can slow load times

---

## Validation

**Acceptance Criteria**:
- [x] ✅ `_schema_version` field in MessagesState
- [x] ✅ Migration functions (v0.0 → v1.0)
- [x] ✅ add_messages_with_truncate reducer
- [x] ✅ merge_registry reducer with LRU
- [x] ✅ validate_state_consistency function
- [x] ✅ InstrumentedAsyncPostgresSaver with metrics
- [x] ✅ Thread isolation via conversation ID

---

## References

### Source Code
- **State Models**: `apps/api/src/domains/agents/models.py`
- **Checkpointer**: `apps/api/src/domains/conversations/checkpointer.py`
- **Instrumented Checkpointer**: `apps/api/src/domains/conversations/instrumented_checkpointer.py`
- **Data Registry**: `apps/api/src/domains/agents/data_registry/models.py`
- **Documentation**: `docs/technical/STATE_AND_CHECKPOINT.md`

---

**Fin de ADR-041** - LangGraph State Schema Evolution Decision Record.
