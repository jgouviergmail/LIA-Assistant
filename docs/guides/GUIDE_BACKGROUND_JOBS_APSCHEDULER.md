# Guide Background Jobs avec APScheduler

> Guide pratique pour créer et gérer des jobs background avec APScheduler dans LIA

**Version**: 1.0
**Date**: 2025-12-28
**ADR**: [ADR-046: Background Job Scheduling](../architecture/ADR-046-Background-Job-Scheduling.md)

---

## 📋 Table des Matières

- [Introduction](#introduction)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Types de Jobs](#types-de-jobs)
- [Créer un Job](#créer-un-job)
- [Concurrency Safety](#concurrency-safety)
- [Fire-and-Forget Pattern](#fire-and-forget-pattern)
- [Observabilité](#observabilité)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Introduction

### Qu'est-ce qu'APScheduler ?

**APScheduler** (Advanced Python Scheduler) est une bibliothèque Python pour planifier l'exécution de tâches de fond. LIA utilise `AsyncIOScheduler` pour compatibilité native avec FastAPI async.

### Jobs Actifs dans LIA

| Job ID | Trigger | Schedule | Description |
|--------|---------|----------|-------------|
| `sync_currency_rates` | Cron | 3:00 AM UTC | Sync taux USD→EUR | Toujours |
| `memory_cleanup` | Cron | 4:00 AM UTC | Purge memoires obsoletes | Toujours |
| `reminder_notification` | Interval | Toutes les minutes | Traitement rappels dus | Toujours |
| `scheduled_action_executor` | Interval | Toutes les 60s | Execution actions planifiees utilisateur | `SCHEDULED_ACTIONS_ENABLED` |
| `heartbeat_proactive` | Interval | Configurable (30-120 min) | Notifications proactives LLM-driven | `HEARTBEAT_ENABLED` |
| `interest_proactive` | Interval | Configurable | Notifications centres d'interet | Toujours |
| `oauth_health_check` | Interval | 5 min | Surveillance connecteurs OAuth | `OAUTH_HEALTH_CHECK_ENABLED` |

### Dépendances

```toml
# pyproject.toml
[project.dependencies]
apscheduler = "3.10.4"
```

---

## 🏗️ Architecture

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
        │ APScheduler  │              (graceful)
        │  (start)     │
        └──────┬───────┘
               │
    ┌──────────┼──────────────────────┬───────────────────────┐
    │          │                      │                       │
    ▼          ▼                      ▼                       ▼
┌─────────┐ ┌──────────────┐ ┌─────────────────────┐ ┌───────────────────┐
│ Job 1   │ │ Job 2        │ │ Job 3               │ │ Job 4             │
│ USD→EUR │ │ Memory       │ │ Reminder            │ │ Scheduled Actions │
│ @3AM    │ │ Cleanup @4AM │ │ Notification @1min  │ │ Executor @60s     │
└─────────┘ └──────────────┘ └─────────────────────┘ └───────────────────┘
```

### Intégration FastAPI Lifespan

```python
# apps/api/src/main.py
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""

    # === STARTUP ===
    scheduler = AsyncIOScheduler()

    # Register jobs
    register_all_jobs(scheduler)

    # Start scheduler
    scheduler.start()
    logger.info("scheduler_started")

    yield  # APPLICATION RUNNING

    # === SHUTDOWN ===
    scheduler.shutdown(wait=True)
    logger.info("scheduler_stopped")

app = FastAPI(lifespan=lifespan)
```

---

## ⚙️ Configuration

### Variables d'Environnement

```python
# apps/api/src/core/config/agents.py
from pydantic_settings import BaseSettings

class AgentsSettings(BaseSettings):
    # Memory cleanup schedule
    memory_cleanup_hour: int = Field(default=4, description="Hour (UTC) for cleanup")
    memory_cleanup_minute: int = Field(default=0)
    memory_max_age_days: int = Field(default=180, description="Max memory age")

    # Currency sync schedule
    currency_sync_enabled: bool = Field(default=True)
```

### Constantes

```python
# apps/api/src/core/constants.py

# Job IDs (unique identifiers)
SCHEDULER_JOB_CURRENCY_SYNC = "sync_currency_rates"
SCHEDULER_JOB_MEMORY_CLEANUP = "memory_cleanup"
SCHEDULER_JOB_REMINDER_NOTIFICATION = "reminder_notification"
SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR = "scheduled_action_executor"

# Currency sync schedule
CURRENCY_SYNC_HOUR = 3  # 3:00 AM UTC
CURRENCY_SYNC_MINUTE = 0

# Scheduled actions
SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS = 60
SCHEDULED_ACTIONS_MAX_PER_USER = 20
SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS = 300
SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES = 10
SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES = 5
```

---

## 📅 Types de Jobs

### 1. Cron Job (Planifié)

Exécution à heure fixe (comme `crontab` Unix).

```python
from apscheduler.triggers.cron import CronTrigger

scheduler.add_job(
    my_job_function,
    trigger=CronTrigger(hour=3, minute=0),  # 3:00 AM
    id="my_cron_job",
    name="Description du job",
    replace_existing=True,
)
```

**Cas d'usage** :
- Synchronisation quotidienne (currency_sync @3AM)
- Nettoyage nocturne (memory_cleanup @4AM)
- Rapports hebdomadaires

### 2. Interval Job (Récurrent)

Exécution à intervalles réguliers.

```python
from apscheduler.triggers.interval import IntervalTrigger

scheduler.add_job(
    process_pending_reminders,
    trigger=IntervalTrigger(minutes=1),  # Toutes les minutes
    id="reminder_notification",
    name="Process pending reminders",
    replace_existing=True,
)
```

**Cas d'usage** :
- Polling de rappels (reminder_notification @1min)
- Health checks
- Queue processing

### 3. Date Job (One-Shot)

Exécution unique à une date précise.

```python
from datetime import datetime, timedelta

scheduler.add_job(
    send_scheduled_email,
    trigger="date",
    run_date=datetime.now() + timedelta(hours=2),
    id=f"email_{email_id}",
)
```

**Cas d'usage** :
- Notifications différées
- Actions programmées uniques

---

## 🔧 Créer un Job

### Étape 1: Définir la Fonction Async

```python
# apps/api/src/infrastructure/scheduler/my_job.py
import structlog
from src.infrastructure.observability.metrics_agents import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger()

async def my_background_job() -> dict:
    """
    Description du job.

    Returns:
        dict: Statistiques d'exécution
    """
    import time
    start_time = time.perf_counter()
    job_name = "my_job"

    stats = {"processed": 0, "errors": 0}

    try:
        # === LOGIQUE MÉTIER ===
        # ... votre code ici ...
        stats["processed"] = 42

    except Exception as e:
        stats["errors"] += 1
        background_job_errors_total.labels(job_name=job_name).inc()
        logger.exception("job_failed", job_name=job_name, error=str(e))

    finally:
        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)
        logger.info("job_completed", job_name=job_name, **stats, duration=duration)

    return stats
```

### Étape 2: Enregistrer dans Lifespan

```python
# apps/api/src/main.py
from src.infrastructure.scheduler.my_job import my_background_job

def register_all_jobs(scheduler: AsyncIOScheduler):
    """Register all background jobs."""

    # Existing jobs...

    # Add your new job
    scheduler.add_job(
        my_background_job,
        trigger="cron",
        hour=5,
        minute=30,
        id="my_job",
        name="My custom background job",
        replace_existing=True,
    )
    logger.info("my_job_scheduled", schedule="5:30 AM UTC")
```

### Étape 3: Ajouter Métriques Prometheus

```python
# apps/api/src/infrastructure/observability/metrics_agents.py
from prometheus_client import Counter, Histogram

background_job_duration_seconds = Histogram(
    "background_job_duration_seconds",
    "Duration of background job execution",
    labelnames=["job_name"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

background_job_errors_total = Counter(
    "background_job_errors_total",
    "Total number of background job errors",
    labelnames=["job_name"],
)
```

---

## 🔒 Concurrency Safety

### Problème : Multi-Worker Deployments

Avec plusieurs workers (uvicorn --workers N), chaque worker démarre son propre scheduler → **exécutions dupliquées**.

### Solutions par Type de Job

| Type de Job | Protection Recommandée | Exemple |
|-------------|------------------------|---------|
| Queue processing | `FOR UPDATE SKIP LOCKED` | `reminder_notification` |
| User batch processing | `max_instances=1` + cooldowns | `interest_notification` |
| Simple cron | `replace_existing=True` | `currency_sync` |

### Solution 1 : FOR UPDATE SKIP LOCKED (Queue Processing)

Pour les jobs qui traitent une **queue d'items** (reminders, emails à envoyer), utiliser le locking PostgreSQL.

```python
# apps/api/src/domains/reminders/repository.py
from sqlalchemy import select

async def get_and_lock_pending_items(self, limit: int = 100) -> list[Model]:
    """
    Get pending items AND lock them atomically.

    Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing:
    - Locks selected rows
    - Skips rows already locked by another transaction
    - Prevents duplicate processing in multi-worker deployments
    """
    stmt = (
        select(MyModel)
        .where(MyModel.status == "pending")
        .where(MyModel.due_at <= datetime.now(UTC))
        .order_by(MyModel.due_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)  # CRITICAL!
    )

    result = await self.db.execute(stmt)
    items = list(result.scalars().all())

    # Immediately transition to PROCESSING
    for item in items:
        item.status = "processing"

    await self.db.flush()
    return items
```

### Pattern Complet dans le Job

```python
async def process_pending_items():
    """Process items with concurrency safety."""

    async with get_db_context() as db:
        repo = MyRepository(db)

        # Atomic lock + fetch
        items = await repo.get_and_lock_pending_items(limit=100)

        for item in items:
            try:
                await process_item(item)
                await repo.delete(item)  # Or mark completed
            except Exception:
                item.retry_count += 1
                if item.retry_count >= MAX_RETRIES:
                    await repo.delete(item)
                else:
                    item.status = "pending"  # Retry next cycle

        await db.commit()
```

### Solution 2 : max_instances + Cooldowns (User Batch Processing)

Pour les jobs qui **traitent des utilisateurs** avec des notifications (proactive tasks), le locking row-level peut causer des **deadlocks** si le traitement est long (10+ secondes) et fait des sous-transactions.

**Alternative recommandée** :

```python
# Configuration APScheduler
scheduler.add_job(
    interest_notification_job,
    trigger=IntervalTrigger(minutes=5),
    id="interest_notification",
    max_instances=1,  # Un seul job à la fois
    replace_existing=True,
)
```

**Protection contre doublons** :
- `max_instances=1` : APScheduler n'exécute qu'une instance
- Cooldowns métier : 2h global + 24h par topic

**Avantages** :
- Pas de deadlock (chaque composant gère sa propre transaction)
- Code plus simple et modulaire
- Chaque sous-composant est indépendant et testable

**Exemple** : `ProactiveTaskRunner` dans `src/infrastructure/proactive/runner.py`

```python
# Query SANS FOR UPDATE - cooldowns protègent contre doublons
query = (
    select(User)
    .where(User.is_verified == True)
    .limit(self.batch_size)
)
```

---

## 🔥 Fire-and-Forget Pattern

Pour les tâches non-bloquantes (extraction mémoire après réponse).

### Implémentation Thread-Safe

```python
# apps/api/src/infrastructure/async_utils.py
import asyncio
import structlog

logger = structlog.get_logger()

# Set to hold references (prevents GC)
_background_tasks: set[asyncio.Task] = set()

def safe_fire_and_forget(
    coro,
    name: str = "background_task",
) -> asyncio.Task | None:
    """
    Fire-and-forget a coroutine safely.

    - Prevents garbage collection of the task
    - Logs exceptions without crashing
    - Auto-cleanup on completion
    """
    try:
        task = asyncio.create_task(coro, name=name)
        _background_tasks.add(task)

        def cleanup(t):
            _background_tasks.discard(t)
            if t.exception():
                logger.exception(
                    "background_task_failed",
                    task_name=name,
                    error=str(t.exception()),
                )

        task.add_done_callback(cleanup)
        return task

    except RuntimeError:
        # No event loop running
        logger.warning("no_event_loop", task_name=name)
        return None
```

### Utilisation

```python
from src.infrastructure.async_utils import safe_fire_and_forget

# Dans Response Node, après envoi de la réponse
safe_fire_and_forget(
    extract_memories_background(user_id, conversation),
    name=f"memory_extraction_{user_id}",
)
```

---

## 📊 Observabilité

### Métriques Prometheus

```python
# Définies dans metrics_agents.py

# Duration histogram
background_job_duration_seconds.labels(job_name="my_job").observe(duration)

# Error counter
background_job_errors_total.labels(job_name="my_job").inc()

# Custom metrics pour votre job
my_job_processed_total = Counter(
    "my_job_processed_total",
    "Total items processed by my_job",
)
```

### Dashboard Grafana

Ajouter panel dans dashboard "Background Jobs":

```promql
# Job duration P95
histogram_quantile(0.95,
  rate(background_job_duration_seconds_bucket{job_name="my_job"}[5m])
)

# Error rate
rate(background_job_errors_total{job_name="my_job"}[5m])
```

### Logging Structuré

```python
logger.info(
    "job_completed",
    job_name="my_job",
    processed=42,
    errors=0,
    duration=1.234,
)
```

---

## 🧪 Testing

### Test Unitaire

```python
# tests/unit/infrastructure/scheduler/test_my_job.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_my_background_job_success():
    """Test job processes items correctly."""

    with patch("src.infrastructure.scheduler.my_job.get_db_context") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session

        result = await my_background_job()

        assert result["processed"] > 0
        assert result["errors"] == 0

@pytest.mark.asyncio
async def test_my_background_job_handles_errors():
    """Test job handles errors gracefully."""

    with patch("src.infrastructure.scheduler.my_job.process_item") as mock_process:
        mock_process.side_effect = Exception("Test error")

        result = await my_background_job()

        assert result["errors"] > 0
```

### Test d'Intégration

```python
# tests/integration/scheduler/test_my_job_integration.py
import pytest
from src.infrastructure.scheduler.my_job import my_background_job

@pytest.mark.asyncio
@pytest.mark.integration
async def test_my_job_with_real_db(test_db_session):
    """Test job with real database."""

    # Setup: create test data
    await create_test_items(test_db_session, count=5)

    # Execute
    result = await my_background_job()

    # Verify
    assert result["processed"] == 5

    # Cleanup happens automatically via test_db_session fixture
```

### Test Concurrency

```python
# tests/integration/scheduler/test_concurrency.py
import asyncio
import pytest

@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_job_execution():
    """Test FOR UPDATE SKIP LOCKED prevents duplicates."""

    # Create 10 pending items
    await create_test_items(count=10)

    # Run 3 workers concurrently
    results = await asyncio.gather(
        my_background_job(),
        my_background_job(),
        my_background_job(),
    )

    # Total processed should be exactly 10 (no duplicates)
    total_processed = sum(r["processed"] for r in results)
    assert total_processed == 10
```

---

## 🔧 Troubleshooting

### Job ne s'exécute pas

1. **Vérifier que le scheduler est démarré** :
   ```python
   logger.info("scheduler_started")  # Doit apparaître au démarrage
   ```

2. **Vérifier l'ID du job** (doit être unique) :
   ```python
   scheduler.get_job("my_job")  # Returns None if not found
   ```

3. **Vérifier le timezone** :
   - APScheduler utilise le timezone local par défaut
   - Forcer UTC si nécessaire :
     ```python
     from apscheduler.schedulers.asyncio import AsyncIOScheduler
     scheduler = AsyncIOScheduler(timezone="UTC")
     ```

### Job s'exécute en double

1. **Multi-workers** : Utiliser `FOR UPDATE SKIP LOCKED`
2. **replace_existing=True** : S'assurer qu'il est défini
3. **ID unique** : Vérifier que l'ID n'est pas dupliqué

### Job échoue silencieusement

1. **Capturer les exceptions** :
   ```python
   try:
       await my_job()
   except Exception as e:
       logger.exception("job_failed", error=str(e))
       raise  # Re-raise pour que APScheduler le capture
   ```

2. **Vérifier les logs** :
   ```bash
   docker logs lia-api-1 2>&1 | grep "my_job"
   ```

### Performance dégradée

1. **Limiter le batch size** :
   ```python
   items = await repo.get_pending(limit=100)  # Pas 10000
   ```

2. **Utiliser des transactions courtes** :
   ```python
   # Process in batches, commit after each
   for batch in chunks(items, size=50):
       await process_batch(batch)
       await db.commit()
   ```

---

## 📚 Ressources

### Documentation

- [APScheduler Documentation](https://apscheduler.readthedocs.io/)
- [ADR-046: Background Job Scheduling](../architecture/ADR-046-Background-Job-Scheduling.md)
- [ADR-051: Reminder & Notification System](../architecture/ADR-051-Reminder-Notification-System.md)

### Code Source

- **Main Lifespan**: `apps/api/src/main.py`
- **Currency Sync**: `apps/api/src/infrastructure/scheduler/currency_sync.py`
- **Memory Cleanup**: `apps/api/src/infrastructure/scheduler/memory_cleanup.py`
- **Reminder Notification**: `apps/api/src/infrastructure/scheduler/reminder_notification.py`
- **Async Utils**: `apps/api/src/infrastructure/async_utils.py`
- **Constants**: `apps/api/src/core/constants.py`

---

**Fin du guide** - Background Jobs avec APScheduler dans LIA
