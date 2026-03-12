# ADR-051: Reminder & Notification System

**Status**: ✅ IMPLEMENTED (2025-12-28)
**Deciders**: Équipe architecture LIA
**Technical Story**: Système de rappels personnalisés avec notifications push FCM
**Related ADRs**: ADR-046 (Background Jobs), ADR-019 (Agent Catalogue), ADR-039 (Token Management)

---

## Context and Problem Statement

L'application nécessitait un système de rappels permettant aux utilisateurs de :

1. **Créer des rappels** : "Rappelle-moi d'appeler le médecin dans 2 heures"
2. **Recevoir des notifications** : Push FCM multi-plateforme (Android, iOS, Web)
3. **Personnalisation intelligente** : Message généré par LLM avec personnalité et mémoires
4. **Gestion complète** : Liste, annulation, références naturelles

**Question** : Comment implémenter un système de rappels robuste, scalable et personnalisé ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Conversion timezone** : L'utilisateur parle en heure locale, stockage en UTC
2. **Push notifications** : FCM multi-plateforme (Android, iOS, Web)
3. **Concurrence-safe** : Pas de notifications dupliquées (multi-worker)
4. **Personnalisation LLM** : Message adapté à la personnalité + mémoires
5. **One-shot behavior** : Suppression après notification (pas d'accumulation)

### Nice-to-Have:

- Références naturelles ("annule le prochain rappel")
- Token tracking pour coûts
- Archivage en conversation
- SSE real-time

---

## Decision Outcome

**Chosen option**: "**APScheduler + FCM + FOR UPDATE SKIP LOCKED + LLM Personalization**"

### Architecture Overview

```mermaid
graph TB
    subgraph "USER INTERACTION"
        USER[Utilisateur] --> |"rappelle-moi de..."| AGENT[reminder_agent]
        AGENT --> TOOLS[reminder_tools.py]
        TOOLS --> |create/list/cancel| SERVICE[ReminderService]
        SERVICE --> |CRUD| DB[(PostgreSQL<br/>reminders table)]
    end

    subgraph "BACKGROUND PROCESSING"
        SCHEDULER[APScheduler<br/>@every minute] --> JOB[reminder_notification.py]
        JOB --> |FOR UPDATE SKIP LOCKED| DB
        JOB --> |load context| CONTEXT[User + Personality + Memories]
        CONTEXT --> LLM[LLM Response<br/>Message Generation]
        LLM --> FCM[Firebase Cloud Messaging]
        FCM --> |push| DEVICES[Android/iOS/Web]
        JOB --> |archive| CONV[(Conversation<br/>History)]
        JOB --> |real-time| REDIS[Redis Pub/Sub]
        REDIS --> SSE[SSE Stream]
    end

    subgraph "DATA MODEL"
        DB --> REMINDER[Reminder<br/>id, content, trigger_at UTC<br/>status, retry_count]
        DB --> FCM_TOKEN[UserFCMToken<br/>token, device_type<br/>is_active, last_used_at]
    end

    style JOB fill:#4CAF50,stroke:#2E7D32,color:#fff
    style FCM fill:#FF9800,stroke:#F57C00,color:#fff
    style LLM fill:#2196F3,stroke:#1565C0,color:#fff
```

### Processing Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           REMINDER LIFECYCLE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. CREATION                                                                │
│     User: "rappelle-moi de X dans 2h"                                       │
│            ↓                                                                │
│     Router → Planner → reminder_agent → create_reminder_tool                │
│            ↓                                                                │
│     Local time → UTC conversion → INSERT (status=PENDING)                   │
│                                                                             │
│  2. SCHEDULING (APScheduler @every minute)                                  │
│     SELECT ... WHERE status='pending' AND trigger_at <= NOW()               │
│            FOR UPDATE SKIP LOCKED                                           │
│            ↓                                                                │
│     status → PROCESSING (atomic lock)                                       │
│                                                                             │
│  3. NOTIFICATION                                                            │
│     a. Load user context (personality, timezone, language)                  │
│     b. Search relevant memories (semantic)                                  │
│     c. Generate personalized message (LLM)                                  │
│     d. Send FCM push notification                                           │
│     e. Archive in conversation history (with token tracking)                │
│     f. Publish to Redis for SSE real-time                                   │
│     g. DELETE reminder (one-shot behavior)                                  │
│                                                                             │
│  4. ERROR HANDLING                                                          │
│     On failure: retry_count++ → status=PENDING (retry)                      │
│     After MAX_RETRIES (3): DELETE + log error                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### Data Model

```python
# apps/api/src/domains/reminders/models.py

class ReminderStatus(str, Enum):
    """Status of a reminder."""
    PENDING = "pending"      # En attente de notification
    PROCESSING = "processing"  # En cours (verrouillé)
    CANCELLED = "cancelled"   # Annulé par l'utilisateur

class Reminder(BaseModel):
    """
    Reminder model - All times stored in UTC.

    Note: Reminders are deleted after successful notification (one-shot).
    """
    __tablename__ = "reminders"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # Content
    content: Mapped[str]           # "appeler le médecin"
    original_message: Mapped[str]  # "rappelle-moi d'appeler le médecin"

    # Scheduling - ALWAYS IN UTC
    trigger_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    user_timezone: Mapped[str]     # "Europe/Paris" at creation

    # Status with index for scheduler
    status: Mapped[str] = mapped_column(
        default=ReminderStatus.PENDING.value,
        index=True,
    )

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(default=0)
    notification_error: Mapped[str | None]
```

### FCM Token Management

```python
# apps/api/src/domains/notifications/models.py

class UserFCMToken(BaseModel):
    """
    FCM token for push notifications.
    Each user can have multiple tokens (one per device).
    """
    __tablename__ = "user_fcm_tokens"

    user_id: Mapped[UUID]
    token: Mapped[str]              # FCM token (unique)
    device_type: Mapped[str]        # 'android', 'ios', 'web'
    device_name: Mapped[str | None] # "iPhone de Jean"
    is_active: Mapped[bool]         # False if FCM reports invalid
    last_used_at: Mapped[datetime | None]
    last_error: Mapped[str | None]  # For debugging
```

### Timezone Conversion

```python
# apps/api/src/domains/reminders/service.py

def convert_to_utc(local_dt: datetime, user_timezone: str) -> datetime:
    """
    Convert a local datetime to UTC.

    Args:
        local_dt: Datetime in user's local timezone (may be naive or aware)
        user_timezone: IANA timezone string (e.g., 'Europe/Paris')

    Returns:
        Datetime in UTC with timezone info
    """
    tz = pytz.timezone(user_timezone)

    # If datetime is naive, localize it
    if local_dt.tzinfo is None:
        local_aware = tz.localize(local_dt)
    else:
        local_aware = local_dt.astimezone(tz)

    # Convert to UTC
    return local_aware.astimezone(pytz.UTC)

class ReminderService:
    async def create_reminder(
        self,
        user_id: UUID,
        data: ReminderCreate,
        user_timezone: str,
    ) -> Reminder:
        # Convert local time to UTC
        trigger_at_utc = convert_to_utc(data.trigger_at, user_timezone)

        reminder = await self.repository.create({
            "user_id": user_id,
            "content": data.content,
            "original_message": data.original_message,
            "trigger_at": trigger_at_utc,
            "user_timezone": user_timezone,
            "status": ReminderStatus.PENDING.value,
        })

        return reminder
```

### Concurrence-Safe Locking

```python
# apps/api/src/domains/reminders/repository.py

async def get_and_lock_pending_reminders(
    self,
    limit: int = 100,
) -> list[Reminder]:
    """
    Get pending reminders due for notification AND lock them atomically.

    Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing:
    - Locks selected rows
    - Skips rows already locked by another transaction
    - Prevents duplicate notifications
    """
    now = datetime.now(UTC)

    stmt = (
        select(Reminder)
        .where(Reminder.status == ReminderStatus.PENDING.value)
        .where(Reminder.trigger_at <= now)
        .order_by(Reminder.trigger_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)  # Critical for concurrency!
    )

    result = await self.db.execute(stmt)
    reminders = list(result.scalars().all())

    # Immediately transition to PROCESSING to release lock
    for reminder in reminders:
        reminder.status = ReminderStatus.PROCESSING.value

    await self.db.flush()
    return reminders
```

### LLM Message Personalization

```python
# apps/api/src/infrastructure/scheduler/reminder_notification.py

async def generate_reminder_message(
    original_message: str,
    reminder_content: str,
    created_at: datetime,
    user_timezone: str,
    personality: Any | None,
    memories: list[dict],
    language: str,
) -> ReminderMessageResult:
    """
    Generate a personalized reminder message using LLM.

    Includes:
    - Elapsed time since creation ("il y a 2 heures")
    - Creation date/time ("le 27/12 à 15:30")
    - User personality adaptation
    - Relevant memories for context
    """
    # Calculate elapsed time
    elapsed = datetime.now(UTC) - created_at
    elapsed_text = format_elapsed_time(elapsed, language)

    # Format creation datetime
    created_at_text = format_creation_datetime(created_at, user_timezone, language)

    # Build personality context
    if personality and hasattr(personality, "system_prompt"):
        persona_prompt = personality.system_prompt
    else:
        persona_prompt = "Tu es un assistant amical et efficace."

    # Build memory context (top 5 relevant)
    memory_section = ""
    if memories:
        memory_lines = [f"- {m.get('content', '')}" for m in memories[:5]]
        memory_section = f"MÉMOIRES PERTINENTES :\n" + "\n".join(memory_lines)

    # Load prompt template
    template = load_prompt_with_fallback("reminder_prompt", version="v1")

    system_prompt = template.format(
        persona_prompt=persona_prompt,
        original_message=original_message,
        reminder_content=reminder_content,
        elapsed_text=elapsed_text,
        created_at_text=created_at_text,
        memory_section=memory_section,
        user_language=language,
    )

    # Generate with response LLM
    config: LLMConfig = {"temperature": 0.7, "max_tokens": 150}
    llm = get_llm("response", config_override=config)
    response = await llm.ainvoke(system_prompt)

    return ReminderMessageResult(
        message=str(response.content).strip(),
        tokens_in=response.usage_metadata.get("input_tokens", 0),
        tokens_out=response.usage_metadata.get("output_tokens", 0),
        tokens_cache=response.usage_metadata.get("cache_read_input_tokens", 0),
        model_name=response.response_metadata.get("model", ""),
    )
```

### Memory Search for Personalization

```python
# apps/api/src/infrastructure/scheduler/reminder_notification.py

async def get_relevant_memories(user_id: str, reminder_content: str) -> list[dict]:
    """
    Search for relevant memories to personalize the reminder message.
    """
    try:
        store = await get_tool_context_store()

        results = await store.asearch(
            (user_id, "memories"),
            query=reminder_content[:500],
            limit=5,
        )

        # Filter by score (minimum 0.6)
        MEMORY_MIN_SCORE = 0.6
        return [r.value for r in results if getattr(r, "score", 1.0) >= MEMORY_MIN_SCORE]

    except Exception as e:
        logger.warning("reminder_memory_search_failed", user_id=user_id, error=str(e))
        return []
```

### FCM Notification Sending

```python
# apps/api/src/domains/notifications/service.py

class FCMNotificationService:
    async def send_reminder_notification(
        self,
        user_id: UUID,
        title: str,
        body: str,
        reminder_id: str,
    ) -> FCMBatchResult:
        """Send a reminder notification to all user's active devices."""
        return await self.send_to_user(
            user_id=user_id,
            title=title,
            body=body,
            data={
                "type": "reminder",
                "reminder_id": reminder_id,
                "click_action": "OPEN_CHAT",
            },
        )

    async def _send_to_token(
        self,
        token: str,
        title: str,
        body: str,
        data: dict | None = None,
    ) -> FCMSendResult:
        """Send notification to a single FCM token."""
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=token,
            # Android config
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    click_action="OPEN_CHAT",
                    channel_id="reminders",
                ),
            ),
            # iOS (APNs) config
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(title=title, body=body),
                        sound="default",
                        badge=1,
                    ),
                ),
            ),
            # Web config
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title,
                    body=body,
                    icon="/icon-192x192.png",
                    require_interaction=True,
                ),
            ),
        )

        response = messaging.send(message)
        return FCMSendResult(success=True, message_id=response, token=token)
```

### Scheduler Integration

```python
# apps/api/src/main.py

scheduler.add_job(
    process_pending_reminders,
    trigger="interval",
    minutes=1,
    id=SCHEDULER_JOB_REMINDER_NOTIFICATION,
    name="Process pending reminders and send notifications",
    replace_existing=True,
)
logger.info("reminder_notification_job_scheduled", interval_minutes=1)
```

### Agent Tools

```python
# apps/api/src/domains/agents/tools/reminder_tools.py

@tool
@track_tool_metrics(tool_name="create_reminder", agent_name="reminder_agent")
@rate_limit(max_calls=5, window_seconds=60, scope="user")
async def create_reminder_tool(
    content: Annotated[str, "Ce dont l'utilisateur veut être rappelé"],
    trigger_datetime: Annotated[str, "Date/heure ISO en heure LOCALE"],
    original_message: Annotated[str, "Message original de l'utilisateur"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Crée un rappel pour l'utilisateur."""
    # ... implementation

@tool
@track_tool_metrics(tool_name="list_reminders", agent_name="reminder_agent")
@rate_limit(max_calls=20, window_seconds=60, scope="user")
async def list_reminders_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Liste les rappels en attente de l'utilisateur."""
    # ... implementation

@tool
@track_tool_metrics(tool_name="cancel_reminder", agent_name="reminder_agent")
@rate_limit(max_calls=5, window_seconds=60, scope="user")
async def cancel_reminder_tool(
    reminder_identifier: Annotated[str, "ID ou référence naturelle"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """
    Annule un rappel en attente.

    Supports:
    - UUID direct
    - "next", "le prochain", "prochain" → earliest pending
    - Numeric index (1, 2, 3...) from list
    - Content match ("médecin" → matches "appeler le médecin")
    """
    # ... implementation

REMINDER_TOOLS = [
    create_reminder_tool,
    list_reminders_tool,
    cancel_reminder_tool,
]
```

### Domain Configuration

```python
# apps/api/src/domains/agents/registry/domain_taxonomy.py

"reminder": DomainConfig(
    name="reminder",
    display_name="Rappels",
    description="Create, list, cancel reminders",
    keywords=[
        # French
        "rappel", "rappelle", "rappelle-moi", "rappeler", "notification",
        # English
        "remind", "remind me", "reminder", "reminders",
        # Time triggers
        "dans", "d'ici", "à", "vers", "demain", "ce soir", "plus tard",
        "in", "at", "later", "tomorrow", "tonight",
        # Actions
        "annule rappel", "cancel reminder", "mes rappels", "my reminders",
    ],
    agent_names=["reminder_agent"],
    related_domains=[],  # Standalone
    priority=9,  # High priority: override tasks/calendar for reminders
    metadata={
        "provider": "internal",
        "requires_oauth": False,
        "requires_hitl": False,
        "notification_type": "fcm",
    },
),
```

---

## Prometheus Metrics

```python
# Metrics for observability
background_job_duration_seconds.labels(job_name="reminder_notification").observe(duration)
background_job_errors_total.labels(job_name="reminder_notification").inc()

# Pending metrics (to add):
# reminder_notifications_sent_total{status="success"|"failed"}
```

---

## Error Handling

### Retry Logic

```python
MAX_RETRIES = 3

# On failure:
reminder.retry_count += 1

if reminder.retry_count >= MAX_RETRIES:
    # Delete failed reminder after max retries
    await reminder_repo.delete(reminder)
    logger.error("reminder_failed_permanently_deleted", ...)
else:
    # Revert to pending for retry
    reminder.status = ReminderStatus.PENDING.value
    reminder.notification_error = str(e)
    logger.warning("reminder_retry_scheduled", retry_count=reminder.retry_count)
```

### Graceful Fallback

```python
# If LLM generation fails, use simple fallback message
try:
    result = await generate_reminder_message(...)
except Exception:
    # Fallback to simple message (no token usage)
    if language == "fr":
        fallback_msg = f"C'est l'heure ! Rappel ({created_at_text}) : {content}"
    else:
        fallback_msg = f"It's time! Reminder ({created_at_text}): {content}"
    result = ReminderMessageResult(message=fallback_msg)
```

---

## Token Tracking

```python
# After LLM generation, store token summary for cost tracking
if result.tokens_in > 0 or result.tokens_out > 0:
    # Calculate cost
    cost_eur = await pricing_service.calculate_token_cost_at_date(
        model=result.model_name,
        input_tokens=result.tokens_in,
        output_tokens=result.tokens_out,
        cached_tokens=result.tokens_cache,
        at_date=datetime.now(UTC),
    )

    # Store token summary
    await chat_repo.create_or_update_token_summary(
        run_id=f"reminder_{reminder.id}_{uuid.uuid4().hex[:8]}",
        user_id=reminder.user_id,
        session_id=f"reminder_{reminder.id}",
        conversation_id=conversation.id,
        summary_data={
            FIELD_TOKENS_IN: result.tokens_in,
            FIELD_TOKENS_OUT: result.tokens_out,
            FIELD_TOKENS_CACHE: result.tokens_cache,
            FIELD_COST_EUR: cost_eur,
        },
    )
```

---

## Real-time Updates (SSE)

```python
# Publish to Redis for SSE real-time notification
redis = await get_redis_cache()
if redis:
    channel = f"user_notifications:{reminder.user_id}"
    await redis.publish(
        channel,
        json.dumps({
            "type": "reminder",
            "content": message,
            "reminder_id": str(reminder.id),
            "title": title,
        }, ensure_ascii=False),
    )
```

---

## Consequences

### Positive

- ✅ **Concurrence-safe** : FOR UPDATE SKIP LOCKED prevents duplicates
- ✅ **Timezone handling** : User speaks local, system stores UTC
- ✅ **Personalized messages** : LLM with personality + memories
- ✅ **Multi-platform FCM** : Android, iOS, Web push notifications
- ✅ **One-shot cleanup** : No reminder accumulation
- ✅ **Retry logic** : 3 attempts before permanent failure
- ✅ **Token tracking** : Full cost visibility per reminder
- ✅ **Real-time SSE** : Immediate web notification
- ✅ **Natural references** : "annule le prochain rappel"

### Negative

- ⚠️ LLM cost per reminder (~150 tokens output)
- ⚠️ Minute-level precision (not second-level)
- ⚠️ Requires Firebase project setup

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Reminder creation with timezone conversion
- [x] ✅ APScheduler job @every minute
- [x] ✅ FOR UPDATE SKIP LOCKED for concurrency
- [x] ✅ LLM personalized message generation
- [x] ✅ FCM push notifications (Android/iOS/Web)
- [x] ✅ Conversation archival with token tracking
- [x] ✅ Redis pub/sub for SSE real-time
- [x] ✅ Retry logic with MAX_RETRIES=3
- [x] ✅ Natural language cancel references
- [x] ✅ Domain taxonomy integration (priority=9)

---

## Database Migrations

```sql
-- 2025_12_28_0001-add_reminders_table.py
CREATE TABLE reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    original_message TEXT NOT NULL,
    trigger_at TIMESTAMPTZ NOT NULL,
    user_timezone VARCHAR(50) NOT NULL DEFAULT 'Europe/Paris',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    notification_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_reminders_user_id ON reminders(user_id);
CREATE INDEX ix_reminders_trigger_at ON reminders(trigger_at);
CREATE INDEX ix_reminders_status ON reminders(status);

-- 2025_12_28_0002-add_user_fcm_tokens_table.py
CREATE TABLE user_fcm_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    device_type VARCHAR(20) NOT NULL,
    device_name VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_used_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_user_fcm_tokens_user_id ON user_fcm_tokens(user_id);
```

---

## References

### Source Code
- **Models**: `apps/api/src/domains/reminders/models.py`
- **Schemas**: `apps/api/src/domains/reminders/schemas.py`
- **Service**: `apps/api/src/domains/reminders/service.py`
- **Repository**: `apps/api/src/domains/reminders/repository.py`
- **Scheduler Job**: `apps/api/src/infrastructure/scheduler/reminder_notification.py`
- **Agent Tools**: `apps/api/src/domains/agents/tools/reminder_tools.py`
- **Agent Manifests**: `apps/api/src/domains/agents/reminders/catalogue_manifests.py`
- **Domain Config**: `apps/api/src/domains/agents/registry/domain_taxonomy.py`
- **FCM Service**: `apps/api/src/domains/notifications/service.py`
- **FCM Models**: `apps/api/src/domains/notifications/models.py`
- **Constants**: `apps/api/src/core/constants.py`

### Migrations
- `apps/api/alembic/versions/2025_12_28_0001-add_reminders_table.py`
- `apps/api/alembic/versions/2025_12_28_0002-add_user_fcm_tokens_table.py`

### Documentation
- [GUIDE_BACKGROUND_JOBS_APSCHEDULER.md](../guides/GUIDE_BACKGROUND_JOBS_APSCHEDULER.md) - Guide complet APScheduler
- [GUIDE_FCM_PUSH_NOTIFICATIONS.md](../guides/GUIDE_FCM_PUSH_NOTIFICATIONS.md) - Guide complet FCM
- [README_REMINDERS.md](../readme/README_REMINDERS.md) - Guide développeur rappels

---

**Fin de ADR-051** - Reminder & Notification System Decision Record.
