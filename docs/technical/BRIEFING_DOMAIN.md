# Today Briefing — Technical Documentation

> **Bounded context** : `apps/api/src/domains/briefing/`
> **Endpoints** : `GET /api/v1/briefing/today`, `POST /api/v1/briefing/refresh`
> **Frontend** : `apps/web/src/components/dashboard/`
> **ADR** : [ADR-077 — Today Briefing as a Standalone Bounded Context](../architecture/ADR-077-Today-Briefing-Domain.md)

---

## Overview

The Today briefing turns the dashboard home page into a **daily ritual**: an LLM-generated greeting + contextual synthesis above a 6-card grid (weather, agenda, unread mails, upcoming birthdays, active reminders, health metrics).

Architecture in one line: **lecture pure, asyncio.gather parallel, per-section Redis cache, two lightweight LLM calls** (greeting + synthesis), no LangGraph, no DB model, no scheduler.

---

## Backend layout

```
apps/api/src/domains/briefing/
├── __init__.py          Exposes only the router for FastAPI wiring
├── constants.py         TTLs, item limits, error codes, prompt names
├── exceptions.py        ConnectorNotConfiguredError, ConnectorAccessError
├── schemas.py           Pydantic v2 models (CardStatus, *Data, BriefingResponse)
├── formatters.py        Pure functions: raw API/DB → UI strings
├── fetchers.py          One async fetcher per source (testable in isolation)
├── llm.py               generate_greeting() + generate_synthesis() + token tracking
├── service.py           BriefingService — orchestrator
└── router.py            GET /briefing/today + POST /briefing/refresh
```

### Per-section TTL strategy

| Section     | TTL    | Justification                                     |
|-------------|--------|---------------------------------------------------|
| Weather     | 1 h    | Slow variations, free-tier API friendly           |
| Agenda      | 10 min | Occasional event edits                            |
| Mails       | 5 min  | Important but Gmail-quota friendly                |
| Birthdays   | 24 h   | Quasi-static                                      |
| Reminders   | 0 (live) | Local DB lookup, < 10 ms                       |
| Health      | 15 min | Aligned with iPhone Shortcuts ingest cadence      |

Cache keys: `briefing:{user_id}:{section}`. Defensive: any Redis error degrades gracefully to a live fetch.

### Status mapping

Each section yields a `CardSection` with one of four statuses:

| Status            | Trigger                                              | Frontend rendering                  |
|-------------------|------------------------------------------------------|-------------------------------------|
| `ok`              | Fetcher returned a non-empty payload                 | Normal display                      |
| `empty`           | Fetcher returned an empty list                       | Positive empty state ("Inbox propre 🎉") |
| `error`           | `ConnectorAccessError` or unexpected exception       | Message + CTA mapped from `error_code` |
| `not_configured`  | `ConnectorNotConfiguredError`                        | Card entirely hidden (`return null`)|

`error_code` is a stable identifier (see `constants.py`) used by the frontend to choose the correct localized CTA — `connector_oauth_expired` → "Reconnect", `connector_network` → "Retry", etc.

### LLM tracking

Both LLM calls go through `track_proactive_tokens(task_type="briefing", ...)`. Tokens land in the existing `message_token_summary` and `user_statistics` tables, so the briefing's cost is visible in the same dashboards as heartbeat / interest tokens. Cached input tokens are subtracted from `input_tokens` before tracking — aligned with `TokenAccumulator.add_from_usage_metadata` — so the cost calculation does not double-charge cached tokens.

In addition to the analytics persistence, `_invoke_and_track` returns a `(text, LLMUsage | None)` tuple. `LLMUsage` carries `tokens_in`, `tokens_out`, `tokens_cache`, `cost_eur` (computed via the in-memory pricing cache), and `model_name`. Both `generate_greeting` and `generate_synthesis` propagate this object up to the service, which attaches it to `TextSection.usage` so the frontend can surface real consumption next to the timestamp (see `<LLMUsageBadge>`).

The synthesis is **skipped** (returns `(None, None)`) when fewer than `BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA` (=2) cards have OK data — avoids forcing the LLM to write meaningful content from a near-empty dashboard.

### Greeting fallback

`generate_greeting` always returns a `(text, usage)` tuple where `text` is non-empty. If the LLM call fails for any reason, a static localized greeting is returned (`Bonjour Jean.`, `Good morning, Jean.`, etc.) with `usage=None` (no LLM call was made), so the page always renders without a misleading token / cost badge.

---

## API contract

### `GET /api/v1/briefing/today`

Returns the user's Today briefing. Uses the cache when fresh (per-section TTL). Greeting + synthesis are always regenerated.

**Response (200)** — `BriefingResponse`:

```json
{
  "greeting": {
    "text": "Bonjour Jean — prêt pour ce lundi pluvieux ?",
    "generated_at": "2026-04-22T08:14:00Z",
    "usage": {
      "tokens_in": 142,
      "tokens_out": 18,
      "tokens_cache": 0,
      "cost_eur": 0.0000412,
      "model_name": "gpt-4.1-nano"
    }
  },
  "synthesis": {
    "text": "Journée dense : 3 rdv dont Marc à 14h. Pluie vers 16h, parapluie. Pauline 🎂 vendredi.",
    "generated_at": "2026-04-22T08:14:00Z",
    "usage": {
      "tokens_in": 487,
      "tokens_out": 64,
      "tokens_cache": 64,
      "cost_eur": 0.0001824,
      "model_name": "gpt-4.1-nano"
    }
  },
  "cards": {
    "weather":   { "status": "ok", "data": {...}, "generated_at": "...", "error_code": null, "error_message": null },
    "agenda":    { "status": "ok", "data": {...}, ... },
    "mails":     { "status": "empty", "data": null, ... },
    "birthdays": { "status": "ok", "data": {...}, ... },
    "reminders": { "status": "empty", "data": null, ... },
    "health":    { "status": "not_configured", "data": null, "error_code": "connector_not_configured", ... }
  }
}
```

The `usage` field is `null` when no LLM call was made (fallback greeting, skipped synthesis). The frontend only renders the inline `<LLMUsageBadge>` when `usage` is present.

> **Note on `DailyForecastItem`** — the `weekday_short` field shipped before 1.18.0 has been removed. The frontend now derives the localized weekday label from `date_iso` via `Intl.DateTimeFormat` (locale-aware), avoiding the C-locale label that the backend produced.

### `POST /api/v1/briefing/refresh`

Force-refresh selected sections (bypasses cache). Greeting + synthesis are always regenerated for consistency.

**Request body** — `RefreshRequest`:

```json
{ "sections": ["weather"] }
```

Or `["all"]` to bypass every cache.

**Response (200)** — same `BriefingResponse` shape.

---

## Frontend layout

```
apps/web/src/
├── components/dashboard/
│   ├── TodayBriefing.tsx      Orchestrator — greeting + synthesis + hero + 6-card grid
│   ├── BriefingGreeting.tsx   Top-of-page greeting
│   ├── BriefingSynthesis.tsx  AI synthesis banner with sparkles avatar
│   ├── BriefingCard.tsx       Generic 4-state card (status + refresh + skeleton overlay)
│   ├── BriefingSkeleton.tsx   Initial load skeleton mirroring final layout
│   ├── BriefingError.tsx      Page-level fallback (full payload error)
│   ├── HeroLiaCard.tsx        Marketing hero (preserved from old dashboard)
│   ├── QuickAccessCompact.tsx Help + Settings, 2 compact cards
│   ├── UsageStatistics.tsx    Stats block (preserved verbatim)
│   ├── RefreshAllButton.tsx   "Tout rafraîchir" header button
│   ├── UpdatedAtBadge.tsx     Relative timestamp + "updated ✨" badge
│   └── cards/
│       ├── WeatherCard.tsx
│       ├── AgendaCard.tsx
│       ├── MailsCard.tsx
│       ├── BirthdaysCard.tsx
│       ├── RemindersCard.tsx
│       └── HealthCard.tsx
├── hooks/useBriefing.ts        Initial GET + per-section refresh + refreshing state
├── types/briefing.ts           Mirror of Pydantic schemas
└── lib/briefing-utils.ts       computeTimeAgo, resolveErrorCtaKey, parseBirthdayIso
```

### UX behaviour

- **Initial load**: `<BriefingSkeleton>` shown immediately, replaced by content with `animate-in fade-in 300 ms` + 50 ms stagger between cards.
- **Card refresh**: clicking 🔄 on a card calls `POST /briefing/refresh` with that section only. Backend re-fetches that section, regenerates greeting + synthesis (always for consistency), returns the full payload. Frontend swaps `data` — only the targeted card visually changes (others rerender identically).
- **"Updated ✨" badge**: `<BriefingSynthesis>` watches `generated_at` and flashes the badge for 1.5 s when it changes.
- **`prefers-reduced-motion`**: all animations are wrapped in `motion-safe:` so users who disable motion get instant transitions.
- **Dark mode parity**: every color token is OKLCH-based via the LIA design system — no `dark:` overrides needed.

### Card grid (validated order)

```
Météo (0)         Anniversaires (1)   Rappels (2)
Santé (3)         Agenda (4)          Mails (5)
```

Read row-by-row: 3 cols on desktop (`lg:`), 2 cols on tablet (`sm:`), 1 col on mobile.

---

## LLM configuration

The briefing uses a single LLM slot in `LLM_TYPES_REGISTRY`:

```python
"briefing": LLMTypeMetadata(
    llm_type="briefing",
    display_name="Briefing (Greeting + Synthesis)",
    category=CATEGORY_BRIEFING,
    required_capabilities=[],
    power_tier=POWER_TIER_LOW,
)
```

Default config: `openai/gpt-4.1-nano`, `temperature=0.7`, `max_tokens=500`, `timeout_seconds=20.0`. Admin can override via the existing LLM config UI.

Prompts live in `apps/api/src/domains/agents/prompts/v1/`:
- `briefing_greeting_prompt.txt` — single sentence, max 20 words
- `briefing_synthesis_prompt.txt` — 2-3 sentences, max 60 words

Both prompts receive the same template variables: `{user_name}`, `{time_of_day}`, `{day_of_week}`, `{language}`, `{personality_brief}`, `{active_sections}` (compact JSON of the cards data).

---

## Observability

### Prometheus metrics (`metrics_briefing.py`)

| Metric                                    | Labels                                | Use                                |
|-------------------------------------------|---------------------------------------|------------------------------------|
| `briefing_build_duration_seconds`         | `cache_state` (cold/warm/partial)     | E2E latency histogram              |
| `briefing_section_status_total`           | `section`, `status`, `origin`         | Per-source health & cache hit rate |
| `briefing_refresh_requests_total`         | `scope` (single/all)                  | User-initiated refresh activity    |
| `briefing_llm_invocations_total`          | `kind` (greeting/synthesis), `outcome`| LLM reliability                    |

LLM tokens are tracked via `track_proactive_tokens(task_type="briefing")` and surface in the existing `message_token_summary` table.

### Logging

Every build emits a single structured log line:

```
briefing_built  user_id=…  duration_ms=412  cache_state=warm
                synthesis_included=True  sections_status={...}
```

Section failures emit `briefing_section_failed` with the source name and error type. ConnectorAccessErrors emit `briefing_section_access_error` at INFO level (expected, recoverable).

---

## Testing

Unit tests in `apps/api/tests/unit/domains/briefing/`:

- `test_formatters.py` — pure-function coverage of weather/event/email/reminder/birthday/health formatters
- `test_service.py` — `_has_content` truth table, `_section` exception → status mapping, end-to-end `build_today` orchestration with mocked fetchers + LLM

Frontend tests can be added under `apps/web/src/components/dashboard/__tests__/` following the project's vitest pattern.

---

## Adding a new source / card

Adding a new card (e.g. "tasks") follows a 5-step recipe:

1. **Add the section name** to `briefing/constants.py` (`SECTION_TASKS`, TTL constant).
2. **Add the data schema** to `briefing/schemas.py` (`TasksData`, ensure it's part of the `SectionPayload` union and `CardsBundle`).
3. **Add a fetcher** to `briefing/fetchers.py` following the existing pattern (raise `ConnectorNotConfiguredError` / `ConnectorAccessError`).
4. **Wire it in** `BriefingService.build_today()` — add the `_section` call to the `asyncio.gather` block.
5. **Add a frontend card** under `components/dashboard/cards/TasksCard.tsx` and include it in `<TodayBriefing>` with a `staggerIndex`.

i18n: add new keys to `dashboard.briefing.cards.tasks.*` in the 6 locale files.

Tests + docs.

---

## Cost & performance characteristics

- **Latency target** : < 1 s P95 on warm cache, < 2 s P95 on cold cache.
- **LLM cost** : ~ 250 input + 60 output tokens per call, 2 calls per build, gpt-4.1-nano pricing → ~ 0.005 cent per build. At 100 active users × 5 builds/day = 500 builds/day → < 1 €/month total. Negligible.
- **Cache footprint** : ~ 10 KB per section × 6 sections × N users. For 1000 users: ~ 60 MB Redis.

If latency creeps up at scale, the existing heartbeat scheduler can pre-compute the cache for active users without breaking the API surface.
