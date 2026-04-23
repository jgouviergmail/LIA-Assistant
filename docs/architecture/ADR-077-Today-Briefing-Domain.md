# ADR-077 — Today Briefing as a Standalone Bounded Context

**Status**: Accepted
**Date**: 2026-04-22
**Related**: ADR-009 (Config Module Split), ADR-070 (ReAct Execution Mode), ADR-076 (Health Metrics Ingestion)

---

## Context

The home page (`/[lng]/dashboard`) was previously a static set of usage statistics (messages / tokens / cost / Google API requests) plus a marketing hero. It had no operational value: nothing the user could *act on* in their morning routine.

We needed to turn the dashboard into a **daily briefing** — a "Today" view aggregating weather, agenda, unread mails, upcoming birthdays, active reminders, and health signals — accompanied by an LLM-generated greeting and a contextual synthesis.

Two architectural choices had to be made:

1. **Where does the orchestration live?** — Should we extend the heartbeat domain (which already aggregates similar sources for proactive notifications), or create a new bounded context?
2. **Should the briefing flow through the LangGraph chain?** — Or call the underlying services directly?

## Decision

We create a **new bounded context** `apps/api/src/domains/briefing/` that:

1. **Bypasses the LangGraph chain entirely** — the briefing is *read*, not *reasoning*. No router, no planner, no orchestrator, no HITL.
2. **Calls the existing services directly** via `asyncio.gather`:
   - `OpenWeatherMapClient.get_current_weather/.get_forecast`
   - `client.list_events()` (multi-provider via `ClientRegistry`)
   - `client.search_emails()` (multi-provider)
   - `GooglePeopleClient.list_connections(fields=["names","birthdays"])`
   - `ReminderService.list_pending_for_user()` (local DB)
   - `HealthMetricsService.build_heartbeat_health_signals()`
3. **Caches each section in Redis with a per-source TTL** (weather 1 h, agenda 10 min, mails 5 min, birthdays 24 h, reminders live, health 15 min).
4. **Two LLM invocations** (greeting + synthesis) on a single dedicated `briefing` slot in `LLM_TYPES_REGISTRY`, with two distinct versioned prompts. Tokens are tracked through the existing `track_proactive_tokens` pipeline (`task_type="briefing"`).
5. **No DB model, no migration, no scheduler job** — pure read orchestration. The pre-compute via the heartbeat scheduler can be added later without breaking the API.

## Rationale

### Why a separate bounded context (not extending heartbeat)

| Concern | Heartbeat | Briefing |
|---|---|---|
| Trigger | Scheduler cron (background) | Synchronous user request |
| Output | Push notification (LLM decision) | UI payload (deterministic shape) |
| Failure mode | Skip notification | Show error CTA per card |
| Cache strategy | None (each cycle is fresh) | Per-section Redis TTL |
| Schema stability | LLM-driven | API-contracted |

The two contexts share *what* they aggregate, but *why* and *how* they orchestrate it diverge enough that coupling them would erode both:
- A heartbeat refactor would risk breaking the dashboard contract.
- A briefing change (new card) would risk altering proactive notification behavior.

DDD bounded contexts exist precisely for this kind of separation.

### Why bypassing LangGraph

The plan-build-orchestrate-respond chain is designed for **complex multi-step reasoning**. The Today briefing is **lecture pure** — no decision, no tool selection, no HITL. Forcing it through the chain would:

- Add 2-5 s of latency from router → planner → orchestrator overhead.
- Cost ~10× more in LLM tokens (planner + orchestrator + response).
- Make caching per-source impossible (the chain operates at request granularity).
- Create false test coupling between the dashboard and the agent pipeline.

Direct service calls are the correct primitive here: < 1 s latency on a cold cache, < 100 ms warm.

### Why a single LLM slot with two prompts

The greeting (1 sentence) and the synthesis (2-3 sentences) share:
- The same model class (lightweight, ~500 tokens output max).
- The same provider preferences.
- The same cost tier (POWER_TIER_LOW).

Splitting them into two slots would force admins to keep two configs in sync without any practical reason. One slot, two versioned prompt files (`briefing_greeting_prompt.txt` + `briefing_synthesis_prompt.txt`), is the right granularity.

### Why per-section TTL (not global)

A single cache TTL would force the most volatile source's TTL on the slowest one — gratuitously hammering OpenWeatherMap (free tier 60 calls/min) while letting Gmail data stale unnecessarily. Per-section TTL respects each source's natural change rate.

## Consequences

### Positive

- **Fast first paint** : < 1 s on warm cache, < 2 s on cold cache.
- **Cheap LLM** : ~4 €/month for 100 active users (gpt-4.1-nano, ~250 in / 60 out tokens × 2 calls).
- **Independently testable** : 6 fetchers + 1 service + 2 LLM helpers = small, mocked unit tests.
- **No regression risk on heartbeat or chat** : zero shared code paths.
- **Future-proof** : a heartbeat-driven pre-compute job can populate the cache in advance without changing the API surface.

### Negative

- **Code duplication light** : the agenda/mails/health fetchers reproduce some logic from `heartbeat/context_aggregator.py`. Mitigated by formatters.py being purely functional and unit-testable, and by the underlying clients being shared.
- **Two contexts to evolve in parallel** when adding a new source (heartbeat + briefing). Acceptable: the feature requirements are usually not symmetric.

### Neutral

- The LLM `briefing` slot adds one entry to the admin LLM config UI — admins can fine-tune model/temperature/max_tokens per the existing pattern.
- Sections backed by `NOT_CONFIGURED` are entirely hidden from the UI (frontend `return null`), so the layout adapts naturally to onboarding state.

## Implementation Notes

- Bounded context: `apps/api/src/domains/briefing/` (constants, exceptions, schemas, formatters, fetchers, llm, service, router).
- Cache: Redis keys `briefing:{user_id}:{section}` with per-section TTL.
- Frontend: `apps/web/src/components/dashboard/` with a generic `<BriefingCard>` driving 6 specific cards via a `renderContent` callback.
- i18n: 16 keys × 6 languages under `dashboard.briefing.*`.
- Prometheus: `briefing_build_duration_seconds`, `briefing_section_status_total`, `briefing_refresh_requests_total`, `briefing_llm_invocations_total`.

## Alternatives Considered

1. **Extend heartbeat domain** — Rejected: muddles two distinct concerns and breaks DDD bounded-context isolation.
2. **Use the LangGraph chain with a "briefing" intent** — Rejected: 5-10× higher cost and latency for zero added value.
3. **Pre-compute via scheduler from day one** — Rejected: lazy fetch < 1 s satisfies the SLO; pre-compute can be added later as an optimization without breaking the API.
4. **Split LLM into two slots** — Rejected: admins would maintain two configs in sync for no practical benefit.

## References

- Plan d'implémentation : `C:\Users\jgouv\.claude\plans\radiant-today-briefing.md`
- Patterns of reuse : `apps/api/src/domains/heartbeat/context_aggregator.py`
- LLM tracking : `apps/api/src/infrastructure/proactive/tracking.py`
