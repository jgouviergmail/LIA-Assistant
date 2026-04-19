# ADR-073: Last-Known Location Persistence for Proactive Weather

**Date**: 2026-04-19
**Status**: Accepted
**Context**: Make proactive weather notifications relevant when the user is away from home by persisting the browser geolocation (encrypted, non-historized, opt-in), while preserving behavioral consistency with the conversational weather tool.

## Context

The heartbeat proactive weather system uses a single location source: `user.home_location_encrypted`. Notifications tell the user it will rain *at home* regardless of where the user actually is. Users traveling for a few days receive alerts for the wrong place, eroding trust in the entire proactive notification system.

The conversational path already handles this elegantly. `resolve_location()` in `runtime_helpers.py` applies a cascade for the implicit case (no "at home" / "nearby" phrase in the message):

```
browser > home > None
```

The browser geolocation is captured in-session via `BrowserContext.geolocation` on every chat message. It is never persisted: at the end of the session, the signal disappears. That's fine for the chat path, because the chat only runs while the session is active.

The heartbeat scheduler runs out-of-session. It has no access to runtime browser geolocation. Without a persistence mechanism, it can only see what's in the database — i.e., `home_location_encrypted`.

## Decision

Persist the browser geolocation server-side, optionally and opt-in, so the heartbeat can apply the same cascade logic as the chat path when the user is actually traveling. The proactive cascade becomes:

```
last_known (opt-in + fresh + far enough from home) > home
```

Symmetric with the conversational cascade, with a persisted source instead of a runtime one. The user-facing model is consistent: "LIA uses your current position when it can, your home when it can't."

### Data model

Three columns added to `users`:

- `last_known_location_encrypted` (Text, nullable): Fernet-encrypted JSON `{lat, lon, accuracy}`. Same key as `home_location_encrypted`.
- `last_known_location_updated_at` (TIMESTAMPTZ, nullable): UTC timestamp of the last write. Drives TTL and throttling.
- `weather_use_last_known_location` (Boolean, NOT NULL, default False): Opt-in flag.

No separate `user_locations` table: only one persisted coordinate pair exists at a time per user, and there's no need for a travel-mode or multi-home dimension at this stage.

### Cascade (proactive jobs)

`UserLocationService.get_effective_location_for_proactive(user, settings)` implements:

1. If `home_location_encrypted` is missing → raise `NoLocationAvailableError` (job skipped).
2. If `weather_use_last_known_location = False` → return home.
3. If `last_known_*` is missing or stale (age > `LAST_KNOWN_LOCATION_TTL_HOURS`) → return home.
4. If haversine distance between `last_known` and `home` < `LAST_KNOWN_LOCATION_MIN_DISTANCE_KM` → return home. (Avoids switching for intra-city noise.)
5. Otherwise → return last-known.

The returned `source` label (`"home"` or `"last_known"`) is propagated into `HeartbeatContext.weather_location_source` and exposed in the decision prompt so the generated notification can mention the city ("Tomorrow in Paris, …") for transparency.

### Capture

`stream_chat_response` launches a fire-and-forget `asyncio.create_task(update_user_location_fire_and_forget(...))` when `browser_context.geolocation` is present. Opt-in and a 30-minute throttle are enforced server-side inside the service. Any exception is logged and swallowed — the chat UX never fails because of a location-persistence issue.

### Privacy by design

- **Encryption at rest**: same Fernet key as `home_location_encrypted`.
- **Non-historized**: each update overwrites the previous row. No trail.
- **Opt-in**: default is `False`. User must explicitly enable it in Settings.
- **Auto-wipe**:
  - on opt-out (`PATCH /weather-location-preference` with `enabled=False`)
  - on home deletion (DELETE `/me/home-location`) — without home the cascade is meaningless
- **Transparency**: `GET /me/last-location` returns the decrypted stored position + `stale` flag. Settings UI displays it so the user sees exactly what's stored.
- **403 on PUT when opt-out**: explicit, not silent, so the frontend can stop pushing.
- **Logs**: raw coordinates never logged. Observability uses coarse distance buckets (`<10km`, `10-50km`, etc.).

### Configuration

Two settings in `.env` (via Pydantic in `agents.py`):

- `LAST_KNOWN_LOCATION_TTL_HOURS` — default 24, range [1, 168]
- `LAST_KNOWN_LOCATION_MIN_DISTANCE_KM` — default 50, range [1, 500]

The 30-minute write-throttle is hardcoded (`LAST_KNOWN_LOCATION_UPDATE_THROTTLE_MINUTES` in `constants.py`) — it is a safety rail against write amplification, not a business setting.

### Reverse geocoding

`resolve_city_name(lat, lon, api_key)` in `heartbeat/geocoding.py` calls OpenWeatherMap's reverse endpoint with a Redis cache keyed on 3-decimal (≈100m) coordinate buckets, TTL 30 days. The bucketing is safe to share between users because it operates on public coordinates only, and the TTL is long because a city label for a given bucket is effectively stationary. Failures are swallowed and return `None`.

### Observability

Three metrics in `metrics_heartbeat.py`, registered at startup via the top-level
import in `user_location_service.py` (itself imported by `auth/router.py`):

- `heartbeat_weather_location_source_total{source="home|last_known"}` — which source served each proactive notification
- `user_location_put_total{result="accepted|throttled|forbidden"}` — outcomes of the PUT endpoint
- `user_location_geocode_total{result="cache_hit|api_hit|api_error|redis_down"}` — reverse-geocoding observability

Opt-in count is intentionally not exposed as a gauge: it would require either a
scheduled updater (complexity without payoff) or a DB query on `/metrics` scrape
(unbounded cost). Operators query the DB directly when needed.

## Consequences

### Positive

- Notifications become relevant when the user is traveling — directly addresses the "LIA keeps telling me about home weather" issue.
- Consistent model with the chat's implicit cascade — one behavior for the user to understand.
- No new table — additive migration with clean downgrade.
- Privacy-by-design: encryption, non-historization, opt-in, auto-wipe, transparency — audit-friendly.
- Low surface area: one service, three endpoints, one hook, one cascade integration.

### Negative / Trade-offs

- **One-tick staleness**: if the user arrives at a new location just after a heartbeat fires, the next heartbeat (up to ~30 min later) will still be based on the old location. Accepted — the alternative (triggering a heartbeat on position change) is significantly more complex and not worth it for a marginal gain.
- **Single location**: no support for multi-home, work location, or explicit travel mode. If needs evolve, a future ADR will introduce a `user_locations` table.
- **Distance threshold is coarse**: 50 km default is arbitrary. Might need tuning based on usage.
- **OpenWeatherMap reverse dependency**: if OWM is down, city names are missing from notifications (but notifications still fire with fallback text).

### Not handled here

- **Fernet key rotation**: treated as a global concern; when rotation is introduced, a silent reset of `last_known_location_encrypted` is acceptable (data is ephemeral by design).
- **Other proactive jobs** (interests, reminders): they don't exist in a form that uses geolocation today. When/if they do, they'll use the same `UserLocationService.get_effective_location_for_proactive`.
- **Calendar-aware location**: considered and abandoned (free-text `event.location` too noisy).
- **Manual travel mode**: considered and abandoned (redundant with the geoloc-based flow).

## Related

- Phase 1 (shipped 2026-04-18): fix temperature drop detection to use avg today vs avg tomorrow — `context_aggregator.py::_detect_weather_changes`. This ADR is Phase 3 of the same initiative.
- Plan file: `C:\Users\jgouv\.claude\plans\drifting-weather-compass.md` (private — implementation breakdown).
- Existing cascade in conversational path: `apps/api/src/domains/agents/tools/runtime_helpers.py::resolve_location` (`LocationType.NONE` branch).
