# Heartbeat Autonome LLM — Technical Documentation

## Overview

The Heartbeat Autonome (Feature F5 from evolution_INTEGRATION_ROADMAP) enables the LLM to proactively contact users with relevant information — without waiting for a user request. It aggregates multiple context sources (calendar, weather, tasks, interests, memories) and lets the LLM decide whether there's something genuinely useful to communicate.

**User-facing name**: "Proactive notifications" (in UI and push notifications).

## Architecture

```
APScheduler (30 min, configurable)
      |
      v (for each opt-in user)
+----------------------------+
| EligibilityChecker         |  <-- Existing infrastructure (reused)
| (heartbeat_enabled,        |
|  dedicated time window,    |
|  quota, cooldown, activity)|
+------------+---------------+
             v (if eligible)
+----------------------------+
| HeartbeatProactiveTask     |  <-- New: implements ProactiveTask Protocol
|  select_target() ->        |
|    1. ContextAggregator    |  <-- Parallel fetch (asyncio.gather)
|       [Calendar, Weather,  |
|        Tasks, Interests,   |
|        Memories, Activity, |
|        Time]               |
|    2. LLM Decision         |  <-- Structured output (gpt-4.1-mini)
|       -> skip | notify     |
|  generate_content() ->     |
|    LLM Message             |  <-- Personality + message_draft input
+------------+---------------+
             v (if action="notify")
+----------------------------+
| NotificationDispatcher     |  <-- Existing (+ conditional push)
| Archive + SSE (always)     |
| FCM + Telegram             |  <-- Only if heartbeat_push_enabled
+----------------------------+
```

## Feature Flag

- **Global**: `HEARTBEAT_ENABLED=true` in `.env` (default: `false`)
- **Per-user**: `heartbeat_enabled` field on User model (opt-in, default: `false`)
- Scheduler job only registers if global flag is enabled
- Router only registers if global flag is enabled

## Configuration (.env)

| Setting | Default | Description |
|---------|---------|-------------|
| `HEARTBEAT_ENABLED` | `false` | Global feature flag |
| `HEARTBEAT_NOTIFICATION_INTERVAL_MINUTES` | `30` | Scheduler interval (10-120) |
| `HEARTBEAT_NOTIFICATION_BATCH_SIZE` | `50` | Users per batch |
| `HEARTBEAT_GLOBAL_COOLDOWN_HOURS` | `2` | Min hours between notifications |
| `HEARTBEAT_ACTIVITY_COOLDOWN_MINUTES` | `15` | Skip if user active recently |
| `HEARTBEAT_DECISION_LLM_PROVIDER` | `openai` | LLM provider for decision |
| `HEARTBEAT_DECISION_LLM_MODEL` | `gpt-4.1-mini` | LLM model for decision |
| `HEARTBEAT_MESSAGE_LLM_PROVIDER` | `openai` | LLM provider for message |
| `HEARTBEAT_MESSAGE_LLM_MODEL` | `gpt-4.1-mini` | LLM model for message |
| `HEARTBEAT_CONTEXT_CALENDAR_HOURS` | `6` | Hours ahead for calendar |
| `HEARTBEAT_CONTEXT_MEMORY_LIMIT` | `5` | Max memories to fetch |
| `HEARTBEAT_CONTEXT_TASKS_DAYS` | `2` | Days ahead for pending tasks (1-7) |
| `HEARTBEAT_WEATHER_RAIN_THRESHOLD_HIGH` | `0.6` | pop above = rain likely |
| `HEARTBEAT_WEATHER_RAIN_THRESHOLD_LOW` | `0.3` | pop below = clearing |
| `HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD` | `5.0` | Degrees C change to flag |
| `HEARTBEAT_WEATHER_WIND_THRESHOLD` | `14.0` | m/s for wind alert |
| `HEARTBEAT_INACTIVE_SKIP_DAYS` | `7` | Skip if user inactive > N days |

## User Settings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `heartbeat_enabled` | bool | `false` | Enable proactive notifications |
| `heartbeat_max_per_day` | int | `3` | Max notifications per day (1-8) |
| `heartbeat_push_enabled` | bool | `true` | Enable FCM/Telegram push (if false, silent archive only) |
| `heartbeat_notify_start_hour` | int | `9` | Start hour (0-23) for notification window |
| `heartbeat_notify_end_hour` | int | `22` | End hour (0-23) for notification window |

## Context Sources

The `ContextAggregator` fetches all sources in parallel via `asyncio.gather(return_exceptions=True)`:

| Source | Method | Dependency | Fallback |
|--------|--------|------------|----------|
| Calendar | Google Calendar API | Active connector | None |
| Weather + Changes | OpenWeatherMap API | Connector + home_location | None |
| Tasks | Google Tasks API | Active connector | None |
| Interests | InterestRepository | Active interests | None |
| Memories | LangGraph Store | memory_enabled | None |
| Activity | Last message query | Always available | None |
| Recent heartbeats | HeartbeatNotification table | Always available | [] |
| Recent interest notifications | InterestNotification JOIN | Always available | [] |
| Time | Computed from timezone | Always available | Always OK |

### Weather Change Detection

Compares current weather (`weather[0].main`) with forecast entries (`pop` values) to detect:
- **rain_start**: Not raining + pop > threshold
- **rain_end**: Raining + pop < threshold
- **temp_drop**: Temperature dropping > threshold degrees
- **wind_alert**: Wind speed > threshold m/s

Each change type is detected at most once (dedup via `detected_types` set).

## Two-Phase LLM Approach

### Phase 1: Decision (structured output)
- Model: `gpt-4.1-mini` (cheap, fast)
- Temperature: 0.3 (deterministic)
- Output: `HeartbeatDecision` (action, reason, message_draft, priority, sources_used)
- Includes recent heartbeats + interest notifications for anti-redundancy

### Phase 2: Message Generation (if action="notify")
- Model: `gpt-4.1-mini`
- Temperature: 0.7 (creative)
- Rewrites `message_draft` with user's personality and language
- Output: 2-4 sentences, natural tone

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/heartbeat/settings` | Get settings + available_sources |
| PATCH | `/api/v1/heartbeat/settings` | Partial update settings |
| GET | `/api/v1/heartbeat/history` | Paginated notification history |
| PATCH | `/api/v1/heartbeat/notifications/{id}/feedback` | Submit thumbs_up/thumbs_down |

## Database

### User columns (added)
- `heartbeat_enabled` (boolean, default false)
- `heartbeat_max_per_day` (integer, default 3)
- `heartbeat_push_enabled` (boolean, default true)
- `heartbeat_notify_start_hour` (integer, default 9) — Start hour (0-23) for notification window
- `heartbeat_notify_end_hour` (integer, default 22) — End hour (0-23) for notification window

### heartbeat_notifications table
- `id` (UUID, PK)
- `created_at` (timestamp)
- `user_id` (FK -> users.id)
- `run_id` (string, unique run identifier)
- `content` (text, message sent)
- `content_hash` (string, SHA256 for dedup)
- `sources_used` (JSON string)
- `decision_reason` (text, nullable)
- `priority` (string: low/medium/high)
- `user_feedback` (string, nullable: thumbs_up/thumbs_down)
- `tokens_in`, `tokens_out` (integer)
- `model_name` (string, nullable)

Index: `ix_heartbeat_notifications_user_created` on (user_id, created_at)

## Infrastructure Modifications

### ProactiveTaskRunner
- `_extract_user_settings()`: Added heartbeat fields
- `_process_user()`: Uses `self.eligibility_checker.interval_minutes` (was hardcoded)
- `_dispatch_notification()`: Added `push_enabled` parameter (generic convention: `getattr(user, f"{task_type}_push_enabled", True)`)

### NotificationDispatcher
- `dispatch()`: Added `push_enabled: bool = True` parameter
- When `push_enabled=False`: skips FCM and channel push, only archives + SSE

### EligibilityChecker
- Added `interval_minutes: int = 15` parameter (backward-compatible)
- Added cross-type cooldown: `cross_type_models` + `cross_type_cooldown_minutes` params
- New `_check_cross_type_cooldown()` method queries other notification types
- Symmetric: heartbeat checks `InterestNotification`, interest checks `HeartbeatNotification`
- Configurable via `PROACTIVE_CROSS_TYPE_COOLDOWN_MINUTES` (default 30)
- New `EligibilityReason.CROSS_TYPE_COOLDOWN` enum value

### Token Tracking
- Decision phase tokens captured via `_TokenCaptureHandler` (LangChain callback)
- Skip decisions tracked via `_track_skip_tokens()` (calls `track_proactive_tokens()` directly)
- Prevents silent token cost leakage when LLM decides not to notify
- **Per-bubble token display**: `ProactiveTaskRunner` pre-generates `run_id` via `generate_proactive_run_id()` and injects `run_id`, `tokens_in`, `tokens_out`, `tokens_cache`, `cost_eur`, `model_name` into `result.metadata` before dispatch. This ensures:
  - The archived message's `message_metadata` contains `run_id` for the LEFT JOIN in `get_messages_with_token_summaries()` (history load)
  - The SSE payload includes token data for real-time display
  - All proactive types (interest, heartbeat, future) get token display automatically (centralized in runner, DRY)

### ContentSource enum
- Added `HEARTBEAT = "heartbeat"`

## File Inventory

### New files
| File | Description |
|------|-------------|
| `domains/heartbeat/__init__.py` | Package init |
| `domains/heartbeat/models.py` | HeartbeatNotification model |
| `domains/heartbeat/schemas.py` | All schemas (Decision, Context, Target, API) |
| `domains/heartbeat/repository.py` | Repository CRUD + queries |
| `domains/heartbeat/router.py` | API endpoints |
| `domains/heartbeat/context_aggregator.py` | Multi-source parallel aggregator |
| `domains/heartbeat/prompts.py` | LLM prompts (decision + message) |
| `domains/heartbeat/proactive_task.py` | ProactiveTask implementation |
| `infrastructure/scheduler/heartbeat_notification.py` | Scheduler job |
| `alembic/versions/2026_03_03_0002-add_heartbeat_autonome.py` | Migration: user columns + notifications table |
| `alembic/versions/2026_03_03_0003-add_heartbeat_time_window.py` | Migration: dedicated time window columns |

### Modified files
| File | Change |
|------|--------|
| `auth/models.py` | +5 user columns (enabled, max_per_day, push_enabled, notify_start_hour, notify_end_hour) |
| `core/constants.py` | +1 scheduler constant |
| `core/config/agents.py` | +heartbeat settings |
| `infrastructure/proactive/base.py` | +HEARTBEAT ContentSource |
| `infrastructure/proactive/eligibility.py` | +interval_minutes param |
| `infrastructure/proactive/runner.py` | +heartbeat fields, generic push_enabled |
| `infrastructure/proactive/notification.py` | +push_enabled, +heartbeat titles |
| `infrastructure/scheduler/interest_notification.py` | +explicit interval_minutes |
| `api/v1/routes.py` | +conditional heartbeat router |
| `main.py` | +conditional scheduler job |

### Frontend
| File | Change |
|------|--------|
| `hooks/useHeartbeatSettings.ts` | New hook |
| `components/settings/HeartbeatSettings.tsx` | New component |
| `app/[lng]/dashboard/settings/page.tsx` | +HeartbeatSettings in features tab |
| `locales/{fr,en,es,de,it,zh}/translation.json` | +heartbeat i18n keys |

### Tests
| File | Tests |
|------|-------|
| `tests/unit/domains/heartbeat/test_schemas.py` | 38 tests |
| `tests/unit/domains/heartbeat/test_context_aggregator.py` | 25 tests |
| `tests/unit/domains/heartbeat/test_proactive_task.py` | 17 tests |
| `tests/unit/infrastructure/proactive/test_eligibility.py` | 7 tests |

## Reused Infrastructure

| Component | Usage |
|-----------|-------|
| ProactiveTask Protocol | HeartbeatProactiveTask implements it |
| EligibilityChecker | Generic checker with heartbeat fields + cross-type cooldown |
| ProactiveTaskRunner | Batch user processing (no structural changes) |
| execute_proactive_task() | Convenience function in scheduler job |
| NotificationDispatcher | Multi-channel dispatch |
| SchedulerLock | Distributed Redis locking |
| get_structured_output() | LLM structured output for decision |
| PersonalityService | Personality instruction for message |
| get_db_context() | Background DB session |
| TokenAccumulator pattern | Multi-phase token tracking |
