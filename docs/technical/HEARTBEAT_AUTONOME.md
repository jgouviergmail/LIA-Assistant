# Heartbeat Autonome LLM — Technical Documentation

## Overview

The Heartbeat Autonome (Feature F5 from evolution_INTEGRATION_ROADMAP) enables the LLM to proactively contact users with relevant information — without waiting for a user request. It aggregates multiple context sources (calendar, weather, tasks, emails, interests, memories, personal journals) and lets the LLM decide whether there's something genuinely useful to communicate.

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
|        Tasks, Emails,      |
|        Interests, Memories, |
|        Activity, Time]     |
|    2. LLM Decision         |  <-- Structured output (gpt-4.1-mini)
|       -> skip | notify     |
|  generate_content() ->     |
|    LLM Message             |  <-- Personality + message_draft input
+------------+---------------+
             v (if action="notify")
+----------------------------+
| NotificationDispatcher     |  <-- Existing (+ conditional push)
| Archive + SSE (always)     |
| FCM + Telegram             |  <-- Follows the global opt-in (v1.27.11)
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
| `HEARTBEAT_INTEREST_SAMPLE_SIZE` | `5` | Varied interests injected into the context (ADR-135) |
| `HEARTBEAT_RECENT_WINDOW_COUNT` | `10` | Anti-redundancy window size (notifications) |
| `HEARTBEAT_RECENT_WINDOW_DAYS` | `7` | Anti-redundancy window age limit |
| `HEARTBEAT_INTEREST_ENRICHMENT_ENABLED` | `true` | Fetch real facts for interest-centered heartbeats |
| `HEARTBEAT_ENRICHMENT_TIMEOUT_SECONDS` | `45` | Enrichment hard timeout (fail-open) |
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
| `LAST_KNOWN_LOCATION_TTL_HOURS` | `24` | TTL for persisted browser geoloc before fallback to home |
| `LAST_KNOWN_LOCATION_MIN_DISTANCE_KM` | `50.0` | Min distance from home to prefer last-known over home |
| `HEARTBEAT_INACTIVE_SKIP_DAYS` | `7` | Skip if user inactive > N days |

## User Settings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `heartbeat_enabled` | bool | `false` | Enable proactive notifications |
| `heartbeat_max_per_day` | int | `3` | Max notifications per day (1-8) |
| `heartbeat_push_enabled` | bool | `true` | Ignored since v1.27.11 (kept for compatibility) — push follows the global opt-in |
| `heartbeat_notify_start_hour` | int | `9` | Start hour (0-23) for notification window |
| `heartbeat_notify_end_hour` | int | `22` | End hour (0-23) for notification window |
| `weather_use_last_known_location` | bool | `false` | Opt-in: use persisted browser geoloc (Phase 3) when traveling (>50 km from home, <24 h old) |
| `heartbeat_disabled_sources` | JSONB | `NULL` | Sources the user refuses to be INTERRUPTED from (ADR-197). `NULL` = every source allowed. |

## Context Sources

The `ContextAggregator` fetches all sources in parallel via `asyncio.gather(return_exceptions=True)`:

| Source | Method | Dependency | Fallback |
|--------|--------|------------|----------|
| Calendar | Google/Apple/Microsoft Calendar API | Active connector | None |
| Weather + Changes | OpenWeatherMap API | Connector + home_location | None |
| Tasks | Google Tasks / Microsoft To Do API | Active connector | None |
| Emails | Gmail / Apple Email / Microsoft Outlook | Active connector | None |
| Interests | InterestRepository + `pick_varied_sample` (ADR-135: one per subject, least-recently-served first) | Active interests | None |
| Memories | LangGraph Store (semantic search, second-pass dynamic query — P8, symmetric with journals) | memory_enabled | None |
| Journals | JournalEntryRepository (semantic search, second-pass dynamic query) | journals_enabled | None |
| User-model portrait | `build_journal_user_model_block(format='brief')` (compiled portrait, ADR-079) | journals_enabled | "" |
| Health signals | `heartbeat/health_context.fetch_health_signals` → `health_metrics/heartbeat_signals.build_heartbeat_health_signals` (summary + baseline deltas + variations, ONE per-day rollup per kind — ADR-148) | health_metrics_enabled + per-user opt-in | None |
| Birthdays | `connectors.birthdays.fetch_upcoming_birthdays` via `context_sources.fetch_birthdays_context` (Redis cache to local midnight, horizon `HEARTBEAT_CONTEXT_BIRTHDAYS_DAYS`) — P7 | Google Contacts connector | None |
| Departure advice | `context_sources.fetch_departure_advice` (2nd pass over fetched calendar events: Routes traffic-aware ETA + leave-by, Redis cache per (user, event), ≤1 call/cycle) — P6, rule 20 | `HEARTBEAT_DEPARTURE_ENABLED` + Google API key | None |
| Open loops | `context_sources.fetch_open_loops_context` (lazy expiry + nudge-worthiness filter + per-loop cooldown; post-notify bump in `proactive_task` when `OPEN_LOOPS` was used) — P5, ADR-139 | `OPEN_LOOPS_ENABLED` | None |
| Activity | Last message query | Always available | None |
| Recent heartbeats | HeartbeatNotification table (10 items / 7 days, CONTENT excerpts — ADR-135) | Always available | [] |
| Recent interest notifications | InterestNotification JOIN | Always available | [] |
| Recent other proactive messages | Archived `proactive_reminder`/`proactive_phone_call` conversation messages + `ScheduledAction.last_executed_at` (extended anti-redundancy window — P10, prompt rule 10c) | Always available | [] |
| Time | Computed from timezone | Always available | Always OK |

Both second-pass sources (journals AND memories) run after the parallel gather
with a dynamic query built from the aggregated context (`_build_second_pass_query`).
The standalone fetchers and the pure weather-transition rules live in
`src/domains/heartbeat/context_sources.py` (extracted — file-size ratchet);
`ContextAggregator` keeps thin delegate methods.

### Per-source permission (ADR-197)

Being **connected** to a service and being **interrupted** by it are two
decisions. Until v1.27.8 they were one: the only documented way to stop
mail-driven nudges was to disconnect the mail connector — which also removes
the tool the user asks with.

`domains/heartbeat/source_policy.py` owns the vocabulary:

- `HEARTBEAT_SOURCE_KEYS` — the eleven sources a notification can be *about*.
  `activity` and the three anti-redundancy windows are deliberately absent:
  they say what was already sent, so gating them would make the assistant
  repeat itself rather than interrupt less.
- `HEARTBEAT_SOURCE_ORDER` — the display order, published by the API so the
  frontend never re-declares a vocabulary it does not enforce (ADR-184).
- `assert_source_registry_complete()` — called at import, checks the two
  declarations **in both directions** (ADR-085 doctrine).

The preference stores the **refusal set**, never the allowlist: `NULL` means
"never expressed", so existing accounts keep their exact behaviour and a source
added later is ON until someone refuses it.

Gating happens in `ContextAggregator.aggregate` **before** the fetch, so a
refused source also stops costing an API call — a side benefit, not the reason.

**Dependencies are declared and published.** `fetch_departure_advice` opens
with `if not calendar_events: return None`: refusing `calendar` leaves the
`departure` switch ON and permanently silent. `HEARTBEAT_SOURCE_DEPENDENCIES`
declares that edge, the boot assert checks both sides of it, and the settings
response carries it as `source_dependencies` so the panel can say "requires
Calendar" instead of leaving a live control that yields nothing. `journals` and
`memories` are deliberately absent from that table: they also consume the first
pass, but through a query that falls back to a generic one — they degrade
rather than go silent.

### Weather Change Detection

Compares current weather (`weather[0].main`) with forecast entries (`pop` values) to detect:
- **rain_start**: Not raining + pop > threshold
- **rain_end**: Raining + pop < threshold
- **temp_drop** / **temp_rise**: Daily average (today vs tomorrow, bucketed by local date) differs by more than `HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD`. Uses 48 h forecast (`cnt=16`) so the comparison is well-defined regardless of the trigger time — and filters out the noisy day/night cycle that plagued the earlier now-vs-forecast-entry algorithm.
- **wind_alert**: Wind speed > threshold m/s

Each change type is detected at most once (dedup via `detected_types` set).

### Location cascade (Phase 3 — ADR-073)

Before fetching weather, `ContextAggregator` resolves the effective location via `UserLocationService.get_effective_location_for_proactive(user)`:

```
last_known (opt-in + fresh + > LAST_KNOWN_LOCATION_MIN_DISTANCE_KM from home) > home
```

If the cascade returns `"last_known"`, the subsequent `get_current_weather` / `get_forecast` / reverse-geocoding all use the traveling user's coordinates. `HeartbeatContext` exposes `weather_location_source` and `weather_location_city` so the decision prompt can mention the city (prompt rule 16). Prometheus counter `heartbeat_weather_location_source_total{source="home|last_known"}` tracks the split.

Privacy: the persisted coordinates are encrypted (Fernet), non-historized (overwritten on each update), auto-wiped on opt-out or home deletion. See `docs/runbooks/LAST_KNOWN_LOCATION.md`.

## Two-Phase LLM Approach

### Phase 1: Decision (structured output)
- Model: `gpt-4.1-mini` (cheap, fast)
- Temperature: 0.3 (deterministic)
- Output: `HeartbeatDecision` (action, reason, message_draft, priority, sources_used, `interest_topic`)
- `sources_used` uses the canonical `HeartbeatSourceLabel` enum (ADR-135: free-text labels had drifted, e.g. "USER_MEMORIES" vs "USER MEMORIES")
- `interest_topic` must be copied verbatim from the injected interest sample; anything else is dropped by a runtime guard (fail-open to `None`)
- Includes recent heartbeats (with CONTENT excerpts) + interest notifications for two-level anti-redundancy (source level AND topic/product/activity level, explicitly cross-source)

### Phase 1b: Interest enrichment (ADR-135, only when `interest_topic` is set)
- Fetches real, fresh content through `InterestContentGenerator` (Perplexity → Brave → Wikipedia) under `HEARTBEAT_ENRICHMENT_TIMEOUT_SECONDS`
- Reuses the interest's recent-notification embeddings for content dedup (symmetry with the interest flow)
- Fail-open: disabled flag, timeout, failure or empty result → the message is generated from the plain draft

### Phase 2: Message Generation (if action="notify")
- Model: `gpt-4.1-mini`
- Temperature: 0.7 (creative)
- Rewrites `message_draft` with user's personality and language
- When facts were fetched, a VERIFIED FACTS block is appended to the system prompt with a strict contract: center the message on 1-2 **named** items, never invent, never paste raw URLs
- Source links are appended deterministically afterwards (`build_sources_block`, ADR-131)
- Output: 2-4 sentences, natural tone

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/heartbeat/settings` | Get settings + available_sources |
| PATCH | `/api/v1/heartbeat/settings` | Partial update settings |
| GET | `/api/v1/heartbeat/history` | Paginated notification history |
| PATCH | `/api/v1/heartbeat/notifications/{id}/feedback` | Submit thumbs_up/thumbs_down |

> **Frontend wiring (v1.25.29).** Until then the endpoint had no caller: only
> `proactive_interest` cards rendered feedback buttons, so 914 production
> notifications carried `feedback_enabled: true` with no way to answer them.
> `ProactiveFeedbackButtons` now serves both contracts — two verdicts here (the
> heartbeat schema has no `block`), three for interests — and the route marks the
> archived message via `mark_proactive_feedback_submitted`.
>
> **Presentation (v1.25.31).** The chips are in-flow siblings of the copy chip
> in the bubble's action row, like the thumbs of an ordinary answer — they used
> to sit inside the bubble under an introductory sentence, which made the same
> gesture look like two features. A recorded verdict no longer removes them:
> `mark_proactive_feedback_submitted` persists `feedback_value` alongside
> `feedback_submitted`, and the frontend reads it to show the chosen chip
> **pressed and disabled**. Disabled rather than merely unchanged: a proactive
> verdict is final server-side (a `block` really blocks the subject), unlike a
> response verdict which the user may change at will (ADR-138).

## Database

### User columns (added)
- `heartbeat_enabled` (boolean, default false)
- `heartbeat_max_per_day` (integer, default 3)
- `heartbeat_push_enabled` (boolean, default true — ignored since v1.27.11, kept for compatibility)
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

### EligibilityChecker (v1.7.1)
- Added `default_start_hour`, `default_end_hour`, `default_min_per_day`, `default_max_per_day` constructor parameters to support task-specific fallback values instead of hardcoded heartbeat defaults
- All `getattr(user, field, HARDCODED)` calls now use `self.default_*` attributes
- `heartbeat_notification.py` and `interest_notification.py` pass the correct constants from `constants.py`

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
| `users/models.py` | +5 user columns (enabled, max_per_day, push_enabled, notify_start_hour, notify_end_hour) |
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
| `tests/unit/domains/heartbeat/test_context_aggregator.py` | 52 tests |
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
