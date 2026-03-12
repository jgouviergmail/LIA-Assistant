# Reminder & Notification System

## Overview

Le système de rappels permet aux utilisateurs de créer des rappels vocaux ou textuels qui seront envoyés sous forme de notifications push (FCM) à l'heure programmée. Les messages sont personnalisés via LLM en utilisant la personnalité de l'utilisateur et ses mémoires pertinentes.

**ADR associé**: [ADR-051-Reminder-Notification-System](../architecture/ADR-051-Reminder-Notification-System.md)

---

## Quick Start

### Exemples d'utilisation

```
User: "Rappelle-moi d'appeler le médecin dans 2 heures"
Bot: "🔔 Rappel créé pour samedi 28 décembre 2025 à 16:30"

User: "Mes rappels"
Bot: "🔔 Tes rappels en attente :
      1. appeler le médecin - 28/12 à 16:30"

User: "Annule le prochain rappel"
Bot: "🔔 Rappel annulé : appeler le médecin"
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           REMINDER SYSTEM                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     USER INTERACTION LAYER                        │  │
│  │                                                                   │  │
│  │  User ──► reminder_agent ──► reminder_tools ──► ReminderService  │  │
│  │                                                       │          │  │
│  │                                                       ▼          │  │
│  │                                              ┌───────────────┐   │  │
│  │                                              │  PostgreSQL   │   │  │
│  │                                              │   reminders   │   │  │
│  │                                              │   table       │   │  │
│  │                                              └───────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                   BACKGROUND PROCESSING LAYER                     │  │
│  │                                                                   │  │
│  │  APScheduler (@minute) ──► reminder_notification.py               │  │
│  │                                    │                              │  │
│  │                    ┌───────────────┼───────────────┐              │  │
│  │                    ▼               ▼               ▼              │  │
│  │            ┌───────────┐   ┌────────────┐   ┌───────────┐        │  │
│  │            │   User    │   │ Personality│   │  Memories │        │  │
│  │            │  Context  │   │   Context  │   │  (Vector) │        │  │
│  │            └─────┬─────┘   └─────┬──────┘   └─────┬─────┘        │  │
│  │                  └───────────────┼───────────────┘              │  │
│  │                                  ▼                              │  │
│  │                         ┌───────────────┐                       │  │
│  │                         │  LLM Message  │                       │  │
│  │                         │  Generation   │                       │  │
│  │                         └───────┬───────┘                       │  │
│  │                                 │                               │  │
│  │                    ┌────────────┼────────────┐                  │  │
│  │                    ▼            ▼            ▼                  │  │
│  │             ┌───────────┐ ┌──────────┐ ┌───────────┐           │  │
│  │             │    FCM    │ │  Redis   │ │Conversation│          │  │
│  │             │   Push    │ │  Pub/Sub │ │  Archive   │          │  │
│  │             └─────┬─────┘ └────┬─────┘ └───────────┘           │  │
│  │                   ▼            ▼                               │  │
│  │             ┌───────────┐ ┌──────────┐                         │  │
│  │             │  Mobile   │ │   SSE    │                         │  │
│  │             │   Apps    │ │  Stream  │                         │  │
│  │             └───────────┘ └──────────┘                         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Components

### Domain Layer

| Component | Path | Description |
|-----------|------|-------------|
| **Models** | `src/domains/reminders/models.py` | Reminder, ReminderStatus |
| **Schemas** | `src/domains/reminders/schemas.py` | Pydantic schemas |
| **Service** | `src/domains/reminders/service.py` | Business logic + timezone conversion |
| **Repository** | `src/domains/reminders/repository.py` | DB operations + FOR UPDATE SKIP LOCKED |

### Agent Layer

| Component | Path | Description |
|-----------|------|-------------|
| **Tools** | `src/domains/agents/tools/reminder_tools.py` | 3 tools: create/list/cancel |
| **Manifests** | `src/domains/agents/reminders/catalogue_manifests.py` | Agent + tool manifests |
| **Domain Config** | `src/domains/agents/registry/domain_taxonomy.py` | Domain "reminder" definition |

### Infrastructure Layer

| Component | Path | Description |
|-----------|------|-------------|
| **Scheduler Job** | `src/infrastructure/scheduler/reminder_notification.py` | Background processing |
| **FCM Service** | `src/domains/notifications/service.py` | Push notification sending |
| **FCM Models** | `src/domains/notifications/models.py` | UserFCMToken model |

---

## Data Model

### Reminder Table

```sql
CREATE TABLE reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,             -- "appeler le médecin"
    original_message TEXT NOT NULL,    -- "rappelle-moi d'appeler..."
    trigger_at TIMESTAMPTZ NOT NULL,   -- ALWAYS UTC
    user_timezone VARCHAR(50) NOT NULL DEFAULT 'Europe/Paris',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/processing/cancelled
    retry_count INTEGER NOT NULL DEFAULT 0,
    notification_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for scheduler performance
CREATE INDEX ix_reminders_user_id ON reminders(user_id);
CREATE INDEX ix_reminders_trigger_at ON reminders(trigger_at);
CREATE INDEX ix_reminders_status ON reminders(status);
```

### UserFCMToken Table

```sql
CREATE TABLE user_fcm_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,        -- FCM token (very long)
    device_type VARCHAR(20) NOT NULL,  -- 'android', 'ios', 'web'
    device_name VARCHAR(100),          -- "iPhone de Jean"
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_used_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_user_fcm_tokens_user_id ON user_fcm_tokens(user_id);
```

---

## Tools Reference

### create_reminder_tool

Crée un rappel pour l'utilisateur.

**Parameters**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `content` | string | ✅ | Ce dont l'utilisateur veut être rappelé (résumé concis) |
| `trigger_datetime` | string | ✅ | Date/heure ISO en heure LOCALE (ex: 2025-12-29T10:00:00) |
| `original_message` | string | ✅ | Message original complet de l'utilisateur |

**Output**:
```json
{
    "success": true,
    "reminder_id": "550e8400-e29b-41d4-a716-446655440000",
    "message": "🔔 Rappel créé pour dimanche 29 décembre 2025 à 10:00",
    "content": "appeler le médecin",
    "trigger_at_formatted": "dimanche 29 décembre 2025 à 10:00"
}
```

**Rate Limit**: 5 calls/minute per user

---

### list_reminders_tool

Liste les rappels en attente de l'utilisateur.

**Parameters**: None (user_id from runtime context)

**Output**:
```json
{
    "success": true,
    "reminders": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "content": "appeler le médecin",
            "trigger_at": "2025-12-29T09:00:00Z",
            "trigger_at_formatted": "29/12 à 10:00"
        }
    ],
    "total": 1,
    "message": "🔔 Tes rappels en attente :\n  1. appeler le médecin - 29/12 à 10:00"
}
```

**Rate Limit**: 20 calls/minute per user

---

### cancel_reminder_tool

Annule un rappel en attente.

**Parameters**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `reminder_identifier` | string | ✅ | UUID ou référence naturelle |

**Supported identifiers**:
- UUID direct: `"550e8400-e29b-41d4-a716-446655440000"`
- Natural references: `"next"`, `"le prochain"`, `"prochain"`, `"first"`, `"premier"`
- Last reminder: `"last"`, `"le dernier"`
- Numeric index: `"1"`, `"2"`, `"3"` (from list)
- Content match: `"médecin"` → matches "appeler le médecin"

**Output**:
```json
{
    "success": true,
    "reminder_id": "550e8400-e29b-41d4-a716-446655440000",
    "content": "appeler le médecin",
    "message": "🔔 Rappel annulé : appeler le médecin"
}
```

**Rate Limit**: 5 calls/minute per user

---

## Background Job

### Configuration

```python
# apps/api/src/core/constants.py
SCHEDULER_JOB_REMINDER_NOTIFICATION = "reminder_notification"

# apps/api/src/main.py
scheduler.add_job(
    process_pending_reminders,
    trigger="interval",
    minutes=1,  # Every minute
    id=SCHEDULER_JOB_REMINDER_NOTIFICATION,
    name="Process pending reminders and send notifications",
    replace_existing=True,
)
```

### Processing Flow

```
1. SELECT reminders WHERE status='pending' AND trigger_at <= NOW()
   FOR UPDATE SKIP LOCKED  -- Concurrency safety

2. For each reminder:
   a. Set status = 'processing' (atomic)
   b. Load user context (timezone, language)
   c. Load personality (optional)
   d. Search relevant memories (semantic, top 5 with score >= 0.6)
   e. Generate personalized message via LLM
   f. Send FCM push notification to all user devices
   g. Archive message in conversation history
   h. Publish to Redis for SSE real-time
   i. DELETE reminder (one-shot behavior)

3. On failure:
   - retry_count++
   - If retry_count >= 3: DELETE + log error
   - Else: status = 'pending' (retry next minute)
```

---

## LLM Message Generation

### Input Context

```python
# Context provided to LLM for message generation:
{
    "persona_prompt": "Tu es un assistant amical...",  # From personality
    "original_message": "rappelle-moi d'appeler le médecin demain",
    "reminder_content": "appeler le médecin",
    "elapsed_text": "il y a 2 heures",  # Since creation
    "created_at_text": "le 27/12 à 15:30",
    "trigger_text": "17:30",  # Current time in user timezone
    "memory_section": "MÉMOIRES PERTINENTES:\n- Préfère les rappels courts...",
    "user_language": "fr",
}
```

### Token Tracking

```python
# Token usage is tracked per reminder:
run_id = f"reminder_{reminder.id}_{uuid.uuid4().hex[:8]}"

await chat_repo.create_or_update_token_summary(
    run_id=run_id,
    summary_data={
        FIELD_TOKENS_IN: result.tokens_in,    # ~200-300 tokens
        FIELD_TOKENS_OUT: result.tokens_out,  # ~50-100 tokens
        FIELD_TOKENS_CACHE: result.tokens_cache,
        FIELD_COST_EUR: cost_eur,
    },
)
```

### Fallback

If LLM generation fails:
```python
# French fallback
message = f"C'est l'heure ! Rappel ({created_at_text}) : {content}"

# English fallback
message = f"It's time! Reminder ({created_at_text}): {content}"
```

---

## FCM Integration

### Requirements

1. **Firebase Project**: Create project at https://console.firebase.google.com/
2. **Service Account**: Download credentials JSON
3. **Environment Variable**:
   ```bash
   FIREBASE_CREDENTIALS_PATH=/path/to/firebase-credentials.json
   ```

### Token Registration (Client)

```javascript
// Flutter/React Native example
const token = await messaging.getToken();
await api.post('/users/me/fcm-tokens', {
    token: token,
    device_type: 'android',  // 'ios', 'web'
    device_name: 'Pixel 8 Pro'
});
```

### Platform-Specific Configuration

```python
# Android
android=messaging.AndroidConfig(
    priority="high",
    notification=messaging.AndroidNotification(
        click_action="OPEN_CHAT",
        channel_id="reminders",
    ),
),

# iOS (APNs)
apns=messaging.APNSConfig(
    payload=messaging.APNSPayload(
        aps=messaging.Aps(
            alert=messaging.ApsAlert(title=title, body=body),
            sound="default",
            badge=1,
        ),
    ),
),

# Web Push
webpush=messaging.WebpushConfig(
    notification=messaging.WebpushNotification(
        title=title,
        body=body,
        icon="/icon-192x192.png",
        require_interaction=True,
    ),
),
```

---

## Real-time Updates (SSE)

### Redis Pub/Sub

```python
# On notification send
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

### Client Subscription

```javascript
// SSE client example
const eventSource = new EventSource('/api/v1/events/stream');
eventSource.addEventListener('notification', (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'reminder') {
        showNotification(data.title, data.content);
    }
});
```

---

## Timezone Handling

### Conversion Logic

```
USER INPUT (local time)
    ↓
convert_to_utc(local_dt, user_timezone)
    ↓
STORAGE (UTC)
    ↓
trigger_at <= NOW(UTC)
    ↓
DISPLAY (convert back to user timezone)
```

### Example

```python
# User in Paris (UTC+1) says: "rappelle-moi à 10h"
# Current time: 9:00 local (08:00 UTC)

# Input: 2025-12-28T10:00:00 (local, naive)
# Stored: 2025-12-28T09:00:00+00:00 (UTC)
# Displayed: "10:00" (converted to Europe/Paris)
```

---

## Prometheus Metrics

```python
# Job duration
background_job_duration_seconds.labels(job_name="reminder_notification").observe(duration)

# Job errors
background_job_errors_total.labels(job_name="reminder_notification").inc()

# Reminder-specific metrics (recommended additions)
# reminder_notifications_sent_total{status="success"|"failed"}
# reminder_generation_latency_seconds
# reminder_fcm_delivery_total{status="success"|"failed"|"no_tokens"}
```

---

## Error Handling

### Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| `ResourceNotFoundError` | Reminder not found or wrong user | Return user-friendly message |
| `ResourceConflictError` | Reminder not in pending state | Cannot cancel non-pending |
| `FCM InvalidToken` | Token expired or invalid | Deactivate token, retry on other devices |
| `LLM Timeout` | LLM generation failed | Use fallback message |

### Retry Policy

- **MAX_RETRIES**: 3
- **Retry on**: FCM errors, LLM errors, DB errors
- **No retry on**: User errors, validation errors
- **After max retries**: DELETE reminder + log error

---

## Testing

### Unit Tests

```python
# tests/domains/reminders/test_reminder_service.py

async def test_create_reminder_converts_timezone():
    """Test that local time is converted to UTC."""
    service = ReminderService(db)

    reminder = await service.create_reminder(
        user_id=user_id,
        data=ReminderCreate(
            content="test",
            trigger_at=datetime(2025, 12, 28, 10, 0),  # 10:00 local
            original_message="test message",
        ),
        user_timezone="Europe/Paris",
    )

    # Paris is UTC+1, so 10:00 Paris = 09:00 UTC
    assert reminder.trigger_at.hour == 9
    assert reminder.trigger_at.tzinfo is not None


async def test_cancel_by_natural_reference():
    """Test canceling with 'next' reference."""
    service = ReminderService(db)

    # Create two reminders
    r1 = await service.create_reminder(...)  # trigger_at: now + 1h
    r2 = await service.create_reminder(...)  # trigger_at: now + 2h

    # Cancel "next" should cancel r1
    cancelled = await service.resolve_and_cancel(user_id, "next")
    assert cancelled.id == r1.id
```

### Integration Tests

```python
# tests/integration/test_reminder_notification.py

async def test_reminder_notification_flow():
    """Test full reminder notification flow."""
    # 1. Create reminder
    reminder = await create_reminder(trigger_at=now - timedelta(minutes=1))

    # 2. Run scheduler job
    stats = await process_pending_reminders()

    # 3. Verify results
    assert stats["processed"] == 1
    assert stats["notified"] == 1

    # 4. Verify reminder deleted
    deleted = await reminder_repo.get_by_id(reminder.id)
    assert deleted is None

    # 5. Verify archived in conversation
    messages = await conv_service.get_messages(user_id)
    assert any("🔔" in m.content for m in messages)
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FIREBASE_CREDENTIALS_PATH` | - | Path to Firebase service account JSON |
| `MEMORY_ENABLED` | `true` | Enable memory search for personalization |
| `MEMORY_MIN_SCORE` | `0.6` | Minimum score for relevant memories |

### Constants

```python
# apps/api/src/core/constants.py
SCHEDULER_JOB_REMINDER_NOTIFICATION = "reminder_notification"

# apps/api/src/infrastructure/scheduler/reminder_notification.py
MAX_RETRIES = 3
```

---

## Troubleshooting

### Reminders not triggering

1. Check scheduler is running:
   ```bash
   docker logs api 2>&1 | grep "reminder_notification_job_scheduled"
   ```

2. Check for pending reminders:
   ```sql
   SELECT * FROM reminders
   WHERE status = 'pending' AND trigger_at <= NOW()
   ORDER BY trigger_at;
   ```

3. Check job errors:
   ```bash
   docker logs api 2>&1 | grep "reminder_notification_failed"
   ```

### No FCM notifications

1. Check Firebase credentials:
   ```bash
   ls -la $FIREBASE_CREDENTIALS_PATH
   ```

2. Check user has active tokens:
   ```sql
   SELECT * FROM user_fcm_tokens
   WHERE user_id = 'xxx' AND is_active = true;
   ```

3. Check FCM logs:
   ```bash
   docker logs api 2>&1 | grep "fcm_"
   ```

### Message not personalized

1. Check memory enabled:
   ```bash
   echo $MEMORY_ENABLED
   ```

2. Check memories exist:
   ```python
   store = await get_tool_context_store()
   results = await store.asearch((user_id, "memories"), query=content)
   ```

3. Check LLM logs:
   ```bash
   docker logs api 2>&1 | grep "reminder_message_generation"
   ```

---

## Distinction : Reminders vs Scheduled Actions vs Heartbeat

LIA possede 3 systemes de notifications qui servent des cas d'usage differents :

| Critere | Reminders | Scheduled Actions | Heartbeat Autonome |
|---------|-----------|-------------------|-------------------|
| **Declencheur** | Utilisateur (ex: "rappelle-moi...") | Utilisateur (action planifiee recurrente) | LLM (decision autonome) |
| **Frequence** | Ponctuel (one-shot) | Recurrent (cron-like) | Periodique (scheduler) |
| **Contenu** | Message LLM personnalise | Resultat d'execution d'action | Message LLM contextuel |
| **Suppression apres envoi** | Oui (DELETE) | Non (recurrent) | Non (audit trail) |
| **Intelligence** | LLM pour message uniquement | Execution d'action LangGraph | LLM pour decision ET message |
| **Sources de contexte** | Memoires + personnalite | Parametres de l'action | Calendar + Weather + Tasks + Interests + Memories + Activity |
| **Feature flag** | Aucun (toujours actif) | `SCHEDULED_ACTIONS_ENABLED` | `HEARTBEAT_ENABLED` |
| **Canaux de delivery** | FCM + SSE | FCM + SSE + Telegram | FCM + SSE + Telegram |

### Quand utiliser quoi ?

- **Reminders** : L'utilisateur veut etre rappele d'une chose precise a un moment precis
  - "Rappelle-moi d'appeler Marie demain a 9h"
  - One-shot, supprime apres envoi

- **Scheduled Actions** : L'utilisateur veut automatiser une action recurrente
  - "Envoie-moi un resume de mes emails chaque lundi a 8h"
  - Recurrent, execute une action complete du pipeline agent

- **Heartbeat Autonome** : LIA prend l'initiative de notifier quand c'est pertinent
  - "Il va pleuvoir dans 2h, pense a prendre ton parapluie"
  - Autonome, base sur l'agregation multi-sources

---

## Related Documentation

- [ADR-051: Reminder & Notification System](../architecture/ADR-051-Reminder-Notification-System.md)
- [ADR-046: Background Job Scheduling](../architecture/ADR-046-Background-Job-Scheduling.md)
- [ADR-019: Agent Manifest Catalogue System](../architecture/ADR-019-Agent-Manifest-Catalogue-System.md)
- [ADR-037: Semantic Memory Store](../architecture/ADR-037-Semantic-Memory-Store.md)
- [SCHEDULED_ACTIONS.md](../technical/SCHEDULED_ACTIONS.md) — Documentation technique Actions Planifiees
- [HEARTBEAT_AUTONOME.md](../technical/HEARTBEAT_AUTONOME.md) — Documentation technique Heartbeat Autonome
- [GUIDE_SCHEDULED_ACTIONS.md](../guides/GUIDE_SCHEDULED_ACTIONS.md) — Guide pratique Actions Planifiees
- [GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md](../guides/GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md) — Guide pratique Heartbeat
