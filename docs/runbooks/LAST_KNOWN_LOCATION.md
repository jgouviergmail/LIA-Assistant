# Runbook — Last-Known Location (Phase 3 Proactive Weather)

**Scope**: Operations and troubleshooting for the Phase 3 feature that persists a user's browser geolocation (opt-in, encrypted, non-historized) so the heartbeat proactive weather job can use it when the user is traveling.

**Related**: [ADR-073](../architecture/ADR-073-Last-Known-Location-Persistence.md).

## Key identifiers

- Feature flag (per-user): `users.weather_use_last_known_location` (default `false`).
- Encrypted payload column: `users.last_known_location_encrypted` — Fernet JSON `{lat, lon, accuracy}`.
- Freshness watermark: `users.last_known_location_updated_at` — UTC.
- Migration: `last_known_loc_001` (Alembic).
- Service: `src/domains/auth/user_location_service.py`.
- Reverse geocoding: `src/domains/heartbeat/geocoding.py` — cache key `heartbeat:geocode:{lat:.3f}:{lon:.3f}`, TTL 30 days.

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Range | Role |
|---|---|---|---|
| `LAST_KNOWN_LOCATION_TTL_HOURS` | 24 | [1, 168] | Above this age, last-known is ignored → fallback home |
| `LAST_KNOWN_LOCATION_MIN_DISTANCE_KM` | 50.0 | [1.0, 500.0] | Below this distance from home, last-known is ignored → fallback home |

Hardcoded (in `src/core/constants.py`):

- `LAST_KNOWN_LOCATION_UPDATE_THROTTLE_MINUTES = 30` — server-side write throttle.
- `LAST_KNOWN_LOCATION_GEOCODE_CACHE_TTL_SECONDS = 2592000` (30 d) — Redis reverse-geocode cache.

## Monitoring

Prometheus metrics (`metrics_heartbeat.py`):

- `heartbeat_weather_location_source_total{source="home|last_known"}` — expected: `home` dominates, `last_known` grows with mobile users.
- `user_location_put_total{result="accepted|throttled|forbidden"}` — `forbidden` should be near-zero after frontend has been updated; `throttled` is normal (30-min window).
- `user_location_geocode_total{result="cache_hit|api_hit|api_error|redis_down"}` — expect `cache_hit` >> others after warm-up.

To count opted-in users at a point in time, query the database directly:
`SELECT COUNT(*) FROM users WHERE weather_use_last_known_location = true;`

Structured logs (via structlog):

- `last_known_location_updated`, `last_known_location_throttled`, `last_known_location_update_forbidden`, `last_known_location_wiped`, `proactive_location_last_known_used`, `proactive_location_home_preferred_close`, `geocode_api_failed`, `geocode_cache_read_failed`, `last_known_location_background_update_failed`.

**Coordinates are never logged in clear**. Observability uses `distance_bucket` (`<10km`, `10-50km`, `50-100km`, `100-500km`, `500-1000km`, `>=1000km`).

## Common operations

### Manually wipe one user's last-known location

SQL (run carefully, prod):

```sql
UPDATE users
SET last_known_location_encrypted = NULL,
    last_known_location_updated_at = NULL
WHERE id = '<user_uuid>';
```

Or call the service in a shell:

```python
from src.domains.auth.user_location_service import UserLocationService
from src.infrastructure.database import get_db_context
from src.domains.auth.models import User

async with get_db_context() as db:
    user = await db.get(User, user_id)
    await UserLocationService(db).wipe_last_known_location(user)
```

### Force opt-out for a user

```sql
UPDATE users
SET weather_use_last_known_location = false,
    last_known_location_encrypted = NULL,
    last_known_location_updated_at = NULL
WHERE id = '<user_uuid>';
```

Recommended: use the PATCH endpoint when possible — it goes through the service's wipe path and emits the right log/metric events.

### Clear the reverse-geocoding cache (Redis)

```bash
# From a redis-cli connected to the same DB as the app:
SCAN 0 MATCH "heartbeat:geocode:*" COUNT 1000
# then DEL the returned keys, or:
redis-cli --scan --pattern "heartbeat:geocode:*" | xargs redis-cli DEL
```

Impact: next heartbeat with a stored last-known will make a fresh API call to OpenWeatherMap reverse. Safe; only cost is one extra API call per unique bucket.

## Troubleshooting

### Users report notifications are still for their home while they opted in and are traveling

Check, in order:

1. `SELECT weather_use_last_known_location, last_known_location_updated_at FROM users WHERE id = '<user>';`
   - `false` → user has not actually opted in, or it was reset.
   - `NULL` timestamp → the frontend has not pushed a location. Verify the user allowed browser geolocation and is opening the app.
2. Age vs TTL: if `now - last_known_location_updated_at > LAST_KNOWN_LOCATION_TTL_HOURS`, the cascade skips last-known. User is seeing stale fallback.
3. Distance check: decrypt stored last-known and home; if `haversine(last_known, home) < LAST_KNOWN_LOCATION_MIN_DISTANCE_KM`, the cascade prefers home by design.
4. Log `proactive_location_home_preferred_close` with this user's id → distance bucket shown in the log.
5. Check `heartbeat_weather_location_source_total{source="last_known"}` rate — if zero globally, the cascade integration is broken (not a per-user issue).

### PUT /me/last-location returns 403 unexpectedly

Root cause: user has `weather_use_last_known_location = false`. Either:

- Frontend pushed before the PATCH preference settled — benign, retries after toggle.
- Backend state was wiped (e.g., auto-wipe on home deletion). The service is consistent — user should re-opt-in.

### Fernet decryption failures

Logged as `last_known_location_decrypt_failed` / `home_location_decrypt_failed`. Most likely cause: Fernet key was rotated without data migration. Per ADR-073, silent reset is acceptable for last-known (ephemeral by design):

```sql
UPDATE users
SET last_known_location_encrypted = NULL,
    last_known_location_updated_at = NULL
WHERE last_known_location_encrypted IS NOT NULL;
```

Home must be migrated separately — it's user-critical config.

### Reverse-geocoding failing

Logs: `geocode_api_failed`, metric `user_location_geocode_total{result="api_error"}`.

Causes:

- OpenWeatherMap API down or rate-limited (60 req/min on free tier).
- User's API key revoked — notifications still fire, but without city name.

Impact: low. Notifications degrade gracefully — the prompt omits the city suffix but weather detection is unaffected.

### Migration rollback

```bash
task db:migrate:down
# or manually:
alembic downgrade -1
```

Drops the three columns — data is lost (acceptable, ephemeral + opt-in).

## Privacy incident playbook

If a privacy incident requires wiping all last-known locations (e.g., suspicion of Fernet key compromise):

```sql
UPDATE users
SET last_known_location_encrypted = NULL,
    last_known_location_updated_at = NULL;
```

Then rotate the Fernet key (separate procedure). User-visible impact: nobody's last-known is served for the next push cycle — cascade falls back to home silently.
