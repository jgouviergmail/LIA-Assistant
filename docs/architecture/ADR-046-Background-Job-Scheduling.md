# ADR-046: Background Job Scheduling

**Status**: ✅ IMPLEMENTED (2025-12-28)
**Deciders**: Équipe architecture LIA
**Technical Story**: APScheduler integration for background tasks with async support
**Related ADRs**: ADR-039, ADR-045, ADR-051

---

## Context and Problem Statement

L'application nécessitait des tâches de fond planifiées :

1. **Currency Sync** : Mise à jour quotidienne des taux de change USD→EUR
2. **Memory Cleanup** : Purge des souvenirs obsolètes avec algorithme de rétention
3. **Memory Extraction** : Extraction asynchrone après chaque réponse
4. **Reminder Notification** : Envoi des rappels à l'heure programmée
5. **Graceful Lifecycle** : Démarrage/arrêt propre avec la lifespan FastAPI

**Question** : Comment implémenter un système de jobs background robuste compatible avec async Python ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Async Support** : Compatible avec asyncio et FastAPI
2. **Cron Scheduling** : Expressions cron pour jobs récurrents
3. **Graceful Shutdown** : Arrêt propre lors du shutdown de l'app
4. **Metrics & Logging** : Observabilité des jobs

### Nice-to-Have:

- Fire-and-forget pattern pour extraction mémoire
- Configuration externalisée
- Retry logic

---

## Decision Outcome

**Chosen option**: "**APScheduler AsyncIOScheduler + Fire-and-Forget Pattern**"

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Application                              │
│                         (main.py lifespan)                               │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
         STARTUP                        SHUTDOWN
              │                             │
              ▼                             ▼
        ┌──────────────┐              Stop Scheduler
        │ APScheduler  │
        │  (start)     │
        └──────┬───────┘
               │
    ┌──────────┼──────────────────────┐
    │          │                      │
    ▼          ▼                      ▼
┌─────────┐ ┌──────────────┐ ┌─────────────────────┐
│ Job 1   │ │ Job 2        │ │ Job 3               │
│ USD→EUR │ │ Memory       │ │ Reminder            │
│ @3AM    │ │ Cleanup @4AM │ │ Notification @1min  │
└─────────┘ └──────────────┘ └─────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
              ┌──────────┐     ┌───────────┐    ┌────────────┐
              │   LLM    │     │    FCM    │    │   Redis    │
              │ Message  │     │   Push    │    │  Pub/Sub   │
              │ Generate │     │  Notify   │    │   (SSE)    │
              └──────────┘     └───────────┘    └────────────┘
```

### APScheduler Integration

```python
# apps/api/src/main.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Global scheduler instance
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""

    # === STARTUP ===

    # 1. Initialize infrastructure
    await get_redis_cache()
    checkpointer = await get_checkpointer()
    store = await get_tool_context_store()

    # 2. Sync currency rates on startup
    try:
        logger.info("currency_rates_startup_sync_starting")
        await sync_currency_rates()
        logger.info("currency_rates_startup_sync_completed")
    except Exception as exc:
        logger.error(
            "currency_rates_startup_sync_failed",
            error=str(exc),
            remediation="Token cost tracking may fail until rates are synced",
        )

    # 3. Register scheduled jobs
    scheduler.add_job(
        sync_currency_rates,
        trigger="cron",
        hour=CURRENCY_SYNC_HOUR,
        minute=CURRENCY_SYNC_MINUTE,
        id=SCHEDULER_JOB_CURRENCY_SYNC,
        name="Sync USD→EUR rates from API to DB",
        replace_existing=True,
    )

    if settings.memory_enabled:
        scheduler.add_job(
            cleanup_memories,
            trigger="cron",
            hour=settings.memory_cleanup_hour,
            minute=settings.memory_cleanup_minute,
            id=SCHEDULER_JOB_MEMORY_CLEANUP,
            name="Cleanup old unused memories (hybrid retention algorithm)",
            replace_existing=True,
        )
        logger.info(
            "memory_cleanup_job_scheduled",
            hour=settings.memory_cleanup_hour,
            minute=settings.memory_cleanup_minute,
        )

    # Reminder Notification Job (@every minute)
    scheduler.add_job(
        process_pending_reminders,
        trigger="interval",
        minutes=1,
        id=SCHEDULER_JOB_REMINDER_NOTIFICATION,
        name="Process pending reminders and send notifications",
        replace_existing=True,
    )
    logger.info("reminder_notification_job_scheduled", interval_minutes=1)

    # 4. Leader election + start scheduler
    # SchedulerLeaderElector handles:
    # - SETNX-based leader election (one scheduler per multi-worker deployment)
    # - Non-blocking background re-election if stale lock exists
    # - Lock renewal (every 30s, TTL 120s)
    # - Graceful shutdown with lock release
    leader_elector = SchedulerLeaderElector(
        await get_redis_cache(), scheduler, on_elected=_on_scheduler_elected,
    )
    await leader_elector.start()
    logger.info("scheduler_started")

    yield  # APP RUNNING

    # === SHUTDOWN ===
    await leader_elector.shutdown()

    # Cleanup resources
    await close_redis()
    await close_db()
```

### Currency Sync Job

```python
# apps/api/src/infrastructure/scheduler/currency_sync.py

async def sync_currency_rates() -> None:
    """
    Sync USD->EUR rate daily at 3:00 AM UTC.

    Creates new active entry and deactivates previous for audit trail.
    """
    start_time = time.perf_counter()
    job_name = "currency_sync"

    async with get_db_context() as db:
        try:
            # Fetch live rate from external API
            api = CurrencyRateService()
            rate = await api.get_rate(_CURRENCY_USD, _CURRENCY_EUR)

            if not rate:
                logger.error("currency_sync_failed_api_unavailable")
                background_job_errors_total.labels(job_name=job_name).inc()
                return

            # Deactivate previous active rate
            stmt = (
                update(CurrencyExchangeRate)
                .where(
                    CurrencyExchangeRate.from_currency == _CURRENCY_USD,
                    CurrencyExchangeRate.to_currency == _CURRENCY_EUR,
                    CurrencyExchangeRate.is_active,
                )
                .values(is_active=False)
            )
            await db.execute(stmt)

            # Insert new active rate
            new_rate = CurrencyExchangeRate(
                from_currency=_CURRENCY_USD,
                to_currency=_CURRENCY_EUR,
                rate=rate,
                effective_from=datetime.now(UTC),
                is_active=True,
            )
            db.add(new_rate)

            duration = time.perf_counter() - start_time
            background_job_duration_seconds.labels(job_name=job_name).observe(duration)

            logger.info(
                "currency_rate_synced",
                from_currency=_CURRENCY_USD,
                to_currency=_CURRENCY_EUR,
                rate=float(rate),
                duration_seconds=round(duration, 3),
            )

        except Exception as e:
            background_job_errors_total.labels(job_name=job_name).inc()
            logger.error("currency_sync_failed", error=str(e))
            raise
```

### Memory Cleanup Job

```python
# apps/api/src/infrastructure/scheduler/memory_cleanup.py

async def cleanup_memories() -> dict:
    """
    Daily memory cleanup job with hybrid retention algorithm.

    Purges memories that:
    - Are older than MEMORY_MAX_AGE_DAYS
    - Have low retention score (< MEMORY_PURGE_THRESHOLD)
    - Are not protected (pinned, sensitive, highly emotional)
    """
    # Implementation with retention scoring...
    pass

def calculate_retention_score(
    memory: dict,
    now: datetime,
    max_age_days: int,
    min_usage_count: int,
) -> float:
    """
    Calculate retention score for a memory (0-1).

    Formula:
    - 40% usage boost (usage_count / min_usage_count, capped at 1.0)
    - 30% importance boost (already 0-1)
    - 30% recency boost (1.0 for new, decays linearly)
    """
    usage_boost = min(1.0, usage_count / max(1, min_usage_count))
    importance_boost = memory.get("importance", 0.7)
    recency_boost = max(0.0, 1.0 - age_days / max(1, max_age_days))

    return 0.4 * usage_boost + 0.3 * importance_boost + 0.3 * recency_boost

def should_purge(memory, now, max_age_days, min_usage_count, purge_threshold):
    """Determine if a memory should be purged."""
    # Protection 1: Pinned
    if memory.get("pinned", False):
        return False, 1.0

    # Protection 2: Protected category (sensitivity)
    if memory.get("category") in PROTECTED_CATEGORIES:
        return False, 1.0

    # Protection 3: High emotional weight
    emotional = memory.get("emotional_weight", 0)
    if abs(emotional) >= settings.memory_emotional_protection_threshold:
        return False, 1.0

    # Protection 4: Too recent
    if age_days < max_age_days:
        return False, 1.0

    retention_score = calculate_retention_score(...)
    return retention_score < purge_threshold, retention_score
```

### Reminder Notification Job

```python
# apps/api/src/infrastructure/scheduler/reminder_notification.py

async def process_pending_reminders() -> dict:
    """
    Process pending reminders and send notifications.

    Runs every minute. For each due reminder:
    1. Lock with FOR UPDATE SKIP LOCKED (concurrency-safe)
    2. Set status = PROCESSING
    3. Load user context (timezone, language, personality)
    4. Search relevant memories (semantic)
    5. Generate personalized message via LLM
    6. Send FCM push notification
    7. Archive in conversation history
    8. Publish to Redis for SSE real-time
    9. DELETE reminder (one-shot behavior)

    Retry logic: 3 attempts, then permanent delete.
    """
    start_time = time.perf_counter()
    job_name = "reminder_notification"

    stats = {
        "processed": 0,
        "notified": 0,
        "failed": 0,
        "no_tokens": 0,
    }

    async with get_db_context() as db:
        reminder_repo = ReminderRepository(db)

        # Get and lock pending reminders atomically
        reminders = await reminder_repo.get_and_lock_pending_reminders(limit=100)

        for reminder in reminders:
            try:
                stats["processed"] += 1

                # Load user context
                user = await user_repo.get_by_id(reminder.user_id)
                personality = await get_personality_for_user(reminder.user_id)
                memories = await get_relevant_memories(
                    str(reminder.user_id),
                    reminder.content
                )

                # Generate personalized message via LLM
                result = await generate_reminder_message(
                    original_message=reminder.original_message,
                    reminder_content=reminder.content,
                    created_at=reminder.created_at,
                    user_timezone=reminder.user_timezone,
                    personality=personality,
                    memories=memories,
                    language=user.language or "fr",
                )

                # Send FCM push notification
                fcm_service = FCMNotificationService(db)
                fcm_result = await fcm_service.send_reminder_notification(
                    user_id=reminder.user_id,
                    title="Rappel",
                    body=result.message,
                    reminder_id=str(reminder.id),
                )

                if fcm_result.success_count > 0:
                    stats["notified"] += 1
                else:
                    stats["no_tokens"] += 1

                # Archive in conversation history
                await archive_reminder_message(
                    user_id=reminder.user_id,
                    message=result.message,
                    reminder=reminder,
                    token_usage=result,
                )

                # Publish to Redis for SSE real-time
                redis = await get_redis_cache()
                if redis:
                    channel = f"user_notifications:{reminder.user_id}"
                    await redis.publish(channel, json.dumps({
                        "type": "reminder",
                        "content": result.message,
                        "reminder_id": str(reminder.id),
                    }))

                # DELETE reminder (one-shot behavior)
                await reminder_repo.delete(reminder)

            except Exception as e:
                stats["failed"] += 1
                reminder.retry_count += 1

                if reminder.retry_count >= MAX_RETRIES:
                    # Permanent failure after max retries
                    await reminder_repo.delete(reminder)
                    logger.error("reminder_failed_permanently", ...)
                else:
                    # Retry next minute
                    reminder.status = ReminderStatus.PENDING.value
                    reminder.notification_error = str(e)

    duration = time.perf_counter() - start_time
    background_job_duration_seconds.labels(job_name=job_name).observe(duration)

    if stats["failed"] > 0:
        background_job_errors_total.labels(job_name=job_name).inc(stats["failed"])

    logger.info("reminder_notification_completed", **stats, duration=duration)
    return stats
```

### Concurrency Safety

#### Option 1: FOR UPDATE SKIP LOCKED (Queue Processing)

Pour les jobs qui traitent une **queue d'items** avec traitement court (reminders, emails).

```python
# apps/api/src/domains/reminders/repository.py

async def get_and_lock_pending_reminders(self, limit: int = 100) -> list[Reminder]:
    """
    Get pending reminders due for notification AND lock them atomically.

    Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing:
    - Locks selected rows
    - Skips rows already locked by another transaction
    - Prevents duplicate notifications in multi-worker deployments
    """
    now = datetime.now(UTC)

    stmt = (
        select(Reminder)
        .where(Reminder.status == ReminderStatus.PENDING.value)
        .where(Reminder.trigger_at <= now)
        .order_by(Reminder.trigger_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)  # Critical!
    )

    result = await self.db.execute(stmt)
    reminders = list(result.scalars().all())

    # Immediately transition to PROCESSING
    for reminder in reminders:
        reminder.status = ReminderStatus.PROCESSING.value

    await self.db.flush()
    return reminders
```

#### Option 2: max_instances + Cooldowns (User Batch Processing)

Pour les jobs avec **traitement long** (10+ secondes) qui font des sous-transactions,
`FOR UPDATE` peut causer des deadlocks. Alternative recommandee :

```python
# Configuration APScheduler
scheduler.add_job(
    interest_notification_job,
    trigger=IntervalTrigger(minutes=5),
    id="interest_notification",
    max_instances=1,  # Un seul job a la fois
    replace_existing=True,
)

# Query SANS FOR UPDATE - cooldowns protegent contre doublons
query = (
    select(User)
    .where(User.is_verified == True)
    .limit(batch_size)
)
```

**Protection** : `max_instances=1` + cooldowns metier (2h global, 24h/topic)

> Voir [ProactiveTaskRunner](../../apps/api/src/infrastructure/proactive/runner.py)

#### Option 3: SchedulerLock (Redis Distributed Lock)

Pour les jobs qui ne sont ni queue ni batch, `SchedulerLock` est un lock Redis SETNX non-bloquant
qui skip silencieusement si le lock est deja pris :

```python
from src.infrastructure.locks import SchedulerLock

async def my_job():
    redis = await get_redis_cache()
    async with SchedulerLock(redis, "my_job_id") as lock:
        if not lock.acquired:
            return  # Another worker executing — skip
        await do_work()
```

> Voir [SchedulerLock](../../apps/api/src/infrastructure/locks/scheduler_lock.py)

#### Option 4: SchedulerLeaderElector (Single Scheduler Instance)

Garantit qu'un seul worker demarre APScheduler. Les autres restent en standby avec re-election
automatique si le leader est tue (Docker restart, SIGKILL). Resout le probleme de locks
fantomes qui empechaient le scheduler de redemarrer.

```python
from src.infrastructure.scheduler.leader_elector import SchedulerLeaderElector

leader_elector = SchedulerLeaderElector(redis, scheduler, on_elected=callback)
await leader_elector.start()     # Non-blocking: SETNX + background re-election
await leader_elector.shutdown()  # Release lock, stop scheduler
```

> Voir [SchedulerLeaderElector](../../apps/api/src/infrastructure/scheduler/leader_elector.py)

### Fire-and-Forget Pattern

```python
# apps/api/src/infrastructure/async_utils.py

_background_tasks: set[asyncio.Task] = set()

def safe_fire_and_forget(
    coro: Coroutine[Any, Any, Any],
    name: str | None = None
) -> asyncio.Task:
    """
    Launch a coroutine in the background safely.

    Avoids FastAPI garbage collection issue where asyncio.create_task()
    can be GC'd if the HTTP request terminates before task completes.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)  # Keep strong reference

    def _on_task_done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if t.exception():
            logger.error("background_task_failed", error=str(t.exception()))

    task.add_done_callback(_on_task_done)
    logger.debug("background_task_started", task_name=name or "unnamed")

    return task

# Usage in response_node
safe_fire_and_forget(
    extract_memories_background(store, user_id, messages, session_id),
    name="memory_extraction"
)
```

### Memory Extraction (Background)

```python
# apps/api/src/domains/agents/services/memory_extractor.py

async def extract_memories_background(
    store: BaseStore,
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    personality_instruction: str | None = None,
) -> int:
    """
    Background psychoanalytical extraction from conversation.

    OPTIMIZED: Only analyzes the LAST user message.
    """
    if not settings.memory_extraction_enabled:
        return 0

    # Find last human message
    last_human_message = None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_message = messages[i]
            break

    if not last_human_message:
        return 0

    # Semantic search for deduplication
    existing_results = await store.asearch(
        namespace.to_tuple(),
        query=message_content[:500],
        limit=10,
    )

    # Extract using LLM
    extraction_config = LLMAgentConfig(
        model=settings.memory_extraction_llm_model,
        temperature=settings.memory_extraction_llm_temperature,
        max_tokens=settings.memory_extraction_max_tokens,
    )

    llm = get_llm("response", config_override=extraction_config)
    result = await invoke_with_instrumentation(
        llm=llm,
        llm_type="memory_extraction",
        messages=prompt,
    )

    # Parse and persist
    new_memories = _parse_extraction_result(result.content)
    stored_count = 0

    for memory in new_memories:
        memory_key = _generate_memory_key()
        await store.aput(
            namespace.to_tuple(),
            key=memory_key,
            value=memory.model_dump(),
        )
        stored_count += 1

    logger.info(
        "memory_extraction_completed",
        user_id=user_id,
        extracted_count=len(new_memories),
        stored_count=stored_count,
    )

    return stored_count
```

### Job Configuration

```python
# apps/api/src/core/constants.py

# Currency sync schedule
CURRENCY_SYNC_HOUR = 3  # 3:00 AM UTC
CURRENCY_SYNC_MINUTE = 0

# Job IDs
SCHEDULER_JOB_CURRENCY_SYNC = "sync_currency_rates"
SCHEDULER_JOB_MEMORY_CLEANUP = "memory_cleanup"
SCHEDULER_JOB_REMINDER_NOTIFICATION = "reminder_notification"
```

### Job Summary Table

| Job ID | Trigger | Schedule | Description |
|--------|---------|----------|-------------|
| `sync_currency_rates` | Cron | 3:00 AM UTC | Sync USD→EUR exchange rates |
| `memory_cleanup` | Cron | 4:00 AM UTC | Purge old unused memories |
| `reminder_notification` | Interval | Every 1 minute | Process pending reminders |

```python
# apps/api/src/core/config/agents.py

memory_max_age_days: int = Field(
    default=180,
    description="Maximum age before memory eligible for purge",
)
memory_min_usage_count: int = Field(
    default=3,
    description="Minimum usage count for protection",
)
memory_purge_threshold: float = Field(
    default=0.3,
    description="Retention score threshold (0-1)",
)
memory_cleanup_hour: int = Field(
    default=4,
    description="Hour (UTC) for daily cleanup",
)
memory_cleanup_minute: int = Field(
    default=0,
)
memory_emotional_protection_threshold: int = Field(
    default=7,
    description="Absolute emotional weight for protection",
)
```

### Prometheus Metrics

```python
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

# In job functions
background_job_duration_seconds.labels(job_name="currency_sync").observe(duration)
background_job_errors_total.labels(job_name="currency_sync").inc()
```

### Consequences

**Positive**:
- ✅ **Async Native** : AsyncIOScheduler compatible avec FastAPI
- ✅ **Cron Scheduling** : Expressions cron pour jobs récurrents
- ✅ **Interval Scheduling** : Jobs à intervalle fixe (reminders)
- ✅ **Graceful Lifecycle** : Start/shutdown avec lifespan
- ✅ **Fire-and-Forget** : Extraction mémoire non-bloquante
- ✅ **Concurrency-Safe** : FOR UPDATE SKIP LOCKED (reminders)
- ✅ **Metrics** : Observabilité via Prometheus
- ✅ **Retention Algorithm** : Purge intelligente des mémoires
- ✅ **Personalized Notifications** : LLM + personality + memories

**Negative**:
- ⚠️ Single-process seulement (pas distribué)
- ⚠️ Jobs perdus si crash avant exécution
- ⚠️ LLM cost per reminder (~150 tokens)

---

## Validation

**Acceptance Criteria**:
- [x] ✅ APScheduler AsyncIOScheduler configuré
- [x] ✅ Currency sync job @3AM UTC
- [x] ✅ Memory cleanup job @4AM UTC
- [x] ✅ Reminder notification job @every minute
- [x] ✅ FOR UPDATE SKIP LOCKED for concurrency
- [x] ✅ Fire-and-forget pattern GC-safe
- [x] ✅ Prometheus metrics pour jobs
- [x] ✅ Graceful shutdown via lifespan
- [x] ✅ FCM push notification integration
- [x] ✅ LLM personalized message generation

---

## Related Decisions

- [ADR-039: Cost Optimization & Token Management](ADR-039-Cost-Optimization-Token-Management.md) - Token tracking for reminders
- [ADR-045: Memory System](ADR-045-Memory-System.md) - Memory cleanup algorithm
- [ADR-051: Reminder & Notification System](ADR-051-Reminder-Notification-System.md) - Full reminder system details

---

## References

### Source Code
- **Main Lifespan**: `apps/api/src/main.py`
- **Currency Sync**: `apps/api/src/infrastructure/scheduler/currency_sync.py`
- **Memory Cleanup**: `apps/api/src/infrastructure/scheduler/memory_cleanup.py`
- **Reminder Notification**: `apps/api/src/infrastructure/scheduler/reminder_notification.py`
- **Reminder Repository**: `apps/api/src/domains/reminders/repository.py`
- **FCM Service**: `apps/api/src/domains/notifications/service.py`
- **Async Utils**: `apps/api/src/infrastructure/async_utils.py`
- **Memory Extractor**: `apps/api/src/domains/agents/services/memory_extractor.py`
- **Constants**: `apps/api/src/core/constants.py`

### Documentation
- [GUIDE_BACKGROUND_JOBS_APSCHEDULER.md](../guides/GUIDE_BACKGROUND_JOBS_APSCHEDULER.md) - Guide complet APScheduler

---

**Fin de ADR-046** - Background Job Scheduling Decision Record.
