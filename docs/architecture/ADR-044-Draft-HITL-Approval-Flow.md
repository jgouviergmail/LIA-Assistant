# ADR-044: Draft & HITL Approval Flow

**Status**: ✅ IMPLEMENTED (2025-12-21) - SUPERSEDED by Architecture v3
**Deciders**: Equipe architecture LIA
**Technical Story**: Human-in-the-Loop pattern for deferred action execution with user confirmation
**Related ADRs**: ADR-009, ADR-018, ADR-043

> **Note Architecture v3 (2026-01)**: Le `draft_critique_node.py` reference dans cet ADR a ete supprime.
> La fonctionnalite HITL est maintenant geree par les composants dans `services/hitl/`:
> - `schemas.py` (HitlSeverity, unified schemas)
> - `scope_detector.py` (ScopeRisk detection)
> - `destructive_confirm.py` (DestructiveConfirmInteraction)
> Voir [HITL.md](../technical/HITL.md) pour la documentation actuelle.

---

## Context and Problem Statement

Les actions sensibles nécessitent une confirmation utilisateur avant exécution :

1. **Write Operations** : Envoi d'emails, création d'événements, modification de contacts
2. **User Control** : L'utilisateur doit pouvoir éditer ou annuler avant exécution
3. **Audit Trail** : Traçabilité complète des décisions utilisateur
4. **Rich Preview** : Prévisualisation détaillée avant confirmation

**Question** : Comment implémenter un pattern de confirmation utilisateur robuste pour les actions déférées ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Draft Lifecycle** : PENDING → CONFIRMED → EXECUTED
2. **HITL Interrupt** : Pause du graphe pour confirmation
3. **User Actions** : Confirm, Edit, Cancel
4. **Type Safety** : Schémas typés par type d'action

### Nice-to-Have:

- Internationalization (6 langues)
- Detailed preview for frontend
- Draft re-confirmation after edit

---

## Decision Outcome

**Chosen option**: "**Draft Service + Critique Node + Executor Registry**"

### Architecture Overview

```
Tool Creates Draft → Draft Critique (HITL) → User Decision → Draft Execution → Response Synthesis
```

### Draft Lifecycle

```python
# apps/api/src/domains/agents/drafts/models.py

class DraftType(str, Enum):
    # Email operations
    EMAIL = "email"
    EMAIL_REPLY = "email_reply"
    EMAIL_FORWARD = "email_forward"
    EMAIL_DELETE = "email_delete"

    # Calendar operations
    EVENT = "event"
    EVENT_UPDATE = "event_update"
    EVENT_DELETE = "event_delete"

    # Contact operations
    CONTACT = "contact"
    CONTACT_UPDATE = "contact_update"
    CONTACT_DELETE = "contact_delete"

    # Task operations
    TASK = "task"
    TASK_UPDATE = "task_update"
    TASK_DELETE = "task_delete"

    # File operations
    FILE_DELETE = "file_delete"

class DraftStatus(str, Enum):
    PENDING = "pending"         # Awaiting user confirmation
    MODIFIED = "modified"       # User edited, awaiting re-confirmation
    CONFIRMED = "confirmed"     # User confirmed, ready for execution
    EXECUTED = "executed"       # Action completed successfully
    FAILED = "failed"           # Execution failed
    CANCELLED = "cancelled"     # User cancelled
```

### Draft Input Schemas

```python
class EmailDraftInput(BaseDraftInput):
    to: str
    subject: str
    body: str
    cc: str | None = None
    bcc: str | None = None
    is_html: bool = False

    def to_send_email_args(self) -> dict[str, Any]:
        """Convert to args for send_email_tool execution."""
        return {
            "to": self.to,
            "subject": self.subject,
            "body": self.body,
            "cc": self.cc,
            "bcc": self.bcc,
            "is_html": self.is_html,
        }

class EventDraftInput(BaseDraftInput):
    summary: str
    start_datetime: str
    end_datetime: str
    description: str | None = None
    location: str | None = None
    attendees: list[str] = []
    timezone: str = "Europe/Paris"
    calendar_id: str | None = None

    def to_create_event_args(self) -> dict[str, Any]:
        """Convert to args for create_event_tool execution."""
        return {
            "summary": self.summary,
            "start_datetime": self.start_datetime,
            "end_datetime": self.end_datetime,
            "description": self.description,
            "location": self.location,
            "attendees": self.attendees,
            "timezone": self.timezone,
            "calendar_id": self.calendar_id,
        }
```

### Draft Service (Creation)

```python
# apps/api/src/domains/agents/drafts/service.py

class DraftService:
    """Service for creating and managing drafts."""

    def create_draft(
        self,
        draft_type: DraftType,
        content: dict[str, Any],
        related_registry_ids: list[str] | None = None,
        source_tool: str | None = None,
        user_language: str = "fr",
    ) -> StandardToolOutput:
        """
        Create a draft of any type.

        Process:
        1. Create Draft object with PENDING status
        2. Convert to RegistryItem (type=DRAFT)
        3. Build LLM summary with detailed preview
        4. Track metrics (Prometheus)
        5. Return StandardToolOutput with registry updates
        """
        draft = Draft(
            type=draft_type,
            content=content,
            related_registry_ids=related_registry_ids or [],
            source_tool=source_tool,
        )

        registry_item = self._draft_to_registry_item(
            draft=draft,
            source_tool=source_tool,
            user_language=user_language,
        )

        summary = self._build_draft_summary(draft, user_language)
        self._track_draft_created(draft_type)

        return StandardToolOutput(
            summary_for_llm=summary,
            registry_updates={draft.id: registry_item},
            tool_metadata={
                "draft_id": draft.id,
                "draft_type": draft_type.value,
                "requires_confirmation": True,
            },
        )
```

### Draft to RegistryItem

```python
def _draft_to_registry_item(
    self,
    draft: Draft,
    source_tool: str | None = None,
    user_language: str = "fr",
) -> RegistryItem:
    """Convert Draft to RegistryItem for frontend display."""
    return RegistryItem(
        id=draft.id,
        type=RegistryItemType.DRAFT,
        payload={
            "draft_type": draft.type.value,
            "status": draft.status.value,
            "content": draft.content,
            "summary": draft.get_summary(user_language),
            "detailed_preview": draft.get_detailed_preview(user_language),
            "actions": ["confirm", "edit", "cancel"],
            "requires_confirmation": True,
        },
        meta=RegistryItemMeta(
            source="draft_service",
            domain="drafts",
            tool_name=source_tool,
        ),
    )
```

### Draft Critique Node (HITL Interrupt)

```python
# apps/api/src/domains/agents/nodes/draft_critique_node.py

async def draft_critique_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """
    Draft Critique Node - Data Registry Draft/Critique HITL.

    Process:
    1. Check if pending_draft_critique exists in state
    2. If not, pass through to response_node
    3. If yes, build draft critique request
    4. Call interrupt() to pause and wait for user decision
    5. Process decision: CONFIRM → execute, EDIT → update, CANCEL → response
    """
    if not settings.tool_approval_enabled:
        return {"draft_action_result": {"action": "confirm", "auto_approved": True}}

    pending_draft_data = state.get("pending_draft_critique")
    if not pending_draft_data:
        return {}

    if isinstance(pending_draft_data, dict):
        pending_draft = PendingDraftInfo(**pending_draft_data)
    else:
        pending_draft = pending_draft_data

    # Build interrupt payload for HITL
    interrupt_payload = _build_draft_critique_payload(pending_draft, user_language)

    # CRITICAL: Interrupt and wait for user decision
    decision_data = interrupt(interrupt_payload)

    if not decision_data:
        return {
            "draft_action_result": {
                "action": "cancel",
                "draft_id": pending_draft.draft_id,
                "reason": "No decision received",
            },
            "pending_draft_critique": None,
        }

    action, updated_content, error = _process_draft_action(decision_data, pending_draft)

    result = {"pending_draft_critique": None}

    if action == "confirm":
        result["draft_action_result"] = {
            "action": "confirm",
            "draft_id": pending_draft.draft_id,
            "draft_type": pending_draft.draft_type,
            "draft_content": pending_draft.draft_content,
        }
    elif action == "edit":
        result["draft_action_result"] = {
            "action": "edit",
            "draft_id": pending_draft.draft_id,
            "updated_content": updated_content,
            "needs_reconfirmation": True,
        }
    elif action == "cancel":
        result["draft_action_result"] = {
            "action": "cancel",
            "draft_id": pending_draft.draft_id,
            "reason": error or "User cancelled",
        }

    return result
```

### Interrupt Payload Structure

```python
def _build_draft_critique_payload(
    pending_draft: PendingDraftInfo,
    user_language: str = "fr",
) -> dict[str, Any]:
    """Build interrupt payload for draft critique HITL."""
    return {
        "action_requests": [
            {
                "type": "draft_critique",
                "draft_id": pending_draft.draft_id,
                "draft_type": pending_draft.draft_type,
                "draft_content": pending_draft.draft_content,
                "registry_ids": pending_draft.registry_ids,
                "tool_name": pending_draft.tool_name,
                "step_id": pending_draft.step_id,
            }
        ],
        "generate_question_streaming": True,
        "user_language": user_language,
        "hitl_type": "draft_critique",
    }
```

### User Decision Processing (HITLOrchestrator)

```python
# apps/api/src/domains/agents/services/hitl_orchestrator.py

def parse_draft_action_if_json(user_message: str) -> dict[str, Any] | None:
    """
    Parse user message as draft action JSON if applicable.

    Frontend sends structured JSON:
        {
            "type": "draft_action",
            "draft_id": "draft_abc123",
            "action": "confirm" | "edit" | "cancel",
            "updated_content": {...} | null
        }
    """
    if not user_message or not user_message.strip().startswith("{"):
        return None

    try:
        parsed = json.loads(user_message.strip())
        if parsed.get("type") != "draft_action":
            return None
        if "action" not in parsed or "draft_id" not in parsed:
            return None

        valid_actions = {"confirm", "edit", "cancel"}
        if parsed.get("action") not in valid_actions:
            return None

        return parsed
    except json.JSONDecodeError:
        return None
```

### Draft Executor (Execution Phase)

```python
# apps/api/src/domains/agents/services/draft_executor.py

# Registry of executor functions per draft type
_EXECUTOR_REGISTRY: dict[str, ExecutorFn] = {}

def _ensure_executors_registered() -> None:
    """Lazy-load executor functions to avoid circular imports."""
    if _EXECUTOR_REGISTRY:
        return

    from src.domains.agents.tools.emails_tools import execute_email_draft
    from src.domains.agents.tools.calendar_tools import execute_event_draft
    from src.domains.agents.tools.google_contacts_tools import execute_contact_draft

    register_executor(DraftType.EMAIL.value, execute_email_draft)
    register_executor(DraftType.EVENT.value, execute_event_draft)
    register_executor(DraftType.CONTACT.value, execute_contact_draft)
    # ... more executors

async def execute_draft_if_confirmed(
    draft_action_result: dict[str, Any] | None,
    config: RunnableConfig,
    run_id: str,
    user_language: str = "fr",
) -> DraftExecutionResult | None:
    """Execute draft if user confirmed via HITL."""
    _ensure_executors_registered()

    if not draft_action_result:
        return None

    action = draft_action_result.get("action")
    draft_id = draft_action_result.get("draft_id")
    draft_type = draft_action_result.get("draft_type")

    if action == "confirm":
        return await _execute_confirmed_draft(
            draft_action_result, config, run_id, user_language
        )
    elif action == "edit":
        return DraftExecutionResult(
            success=True,
            draft_id=draft_id,
            draft_type=draft_type,
            action="edit",
            result_data={"needs_reconfirmation": True},
        )
    elif action == "cancel":
        registry_drafts_executed_total.labels(
            draft_type=draft_type, outcome="cancelled"
        ).inc()
        return DraftExecutionResult(
            success=True,
            draft_id=draft_id,
            draft_type=draft_type,
            action="cancel",
        )

    return None
```

### Response Node Integration

```python
# apps/api/src/domains/agents/nodes/response_node.py

async def response_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """Generate conversational response with draft execution."""

    draft_action_result = state.get(STATE_KEY_DRAFT_ACTION_RESULT)

    if draft_action_result:
        execution_result = await execute_draft_if_confirmed(
            draft_action_result=draft_action_result,
            config=config,
            run_id=run_id,
            user_language=user_language,
        )

        if execution_result:
            agent_results["draft_execution"] = execution_result.to_agent_result()

    # Generate response with execution result included
    # ...
```

### Immutable Draft Lifecycle Pattern

```python
# Draft.mark_*() methods return new copies (immutable pattern)
draft = Draft(type=DraftType.EMAIL, status=DraftStatus.PENDING, ...)

# User edits
modified_draft = draft.mark_modified({**draft.content, "subject": "New"})
# Returns: Draft(..., status=MODIFIED, modified_at=now())

# User confirms
confirmed_draft = modified_draft.mark_confirmed()
# Returns: Draft(..., status=CONFIRMED)

# Execution completes
executed_draft = confirmed_draft.mark_executed({"message_id": "msg_123"})
# Returns: Draft(..., status=EXECUTED, executed_at=now())
```

### Metrics Tracking

```python
# Draft creation
registry_drafts_created_total.labels(draft_type="email").inc()

# Draft execution outcomes
registry_drafts_executed_total.labels(
    draft_type="email",
    outcome="success" | "failed" | "cancelled"
).inc()
```

### Consequences

**Positive**:
- ✅ **User Control** : Confirmation avant chaque action sensible
- ✅ **Edit Capability** : Modification du draft avant exécution
- ✅ **Type Safety** : Schémas typés par type d'action
- ✅ **Immutable Lifecycle** : Traçabilité complète des états
- ✅ **Registry Integration** : Preview riche pour frontend
- ✅ **Internationalization** : 6 langues supportées

**Negative**:
- ⚠️ Latence additionnelle (attente utilisateur)
- ⚠️ Complexité du flow multi-étapes

---

## Validation

**Acceptance Criteria**:
- [x] ✅ DraftType/DraftStatus enums
- [x] ✅ DraftService pour création
- [x] ✅ draft_critique_node avec interrupt()
- [x] ✅ Executor registry avec lazy loading
- [x] ✅ Response node integration
- [x] ✅ Immutable lifecycle pattern
- [x] ✅ Metrics tracking (Prometheus)

---

## References

### Source Code
- **Draft Models**: `apps/api/src/domains/agents/drafts/models.py`
- **Draft Service**: `apps/api/src/domains/agents/drafts/service.py`
- **Critique Node**: `apps/api/src/domains/agents/nodes/draft_critique_node.py`
- **Executor**: `apps/api/src/domains/agents/services/draft_executor.py`
- **HITL Orchestrator**: `apps/api/src/domains/agents/services/hitl_orchestrator.py`

---

**Fin de ADR-044** - Draft & HITL Approval Flow Decision Record.
