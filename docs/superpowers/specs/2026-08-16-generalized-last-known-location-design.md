# Generalized Last-Known Location + PWA Geolocation Lifecycle — Design

**Date**: 2026-08-16 · **Status**: Approved (owner arbitrations recorded below) · **Supersedes in part**: ADR-073 (weather-scoped last-known location)

## Problem (evidence)

When the user travels, the PWA (Android/iOS) loses browser geolocation after a period of inactivity, and every feature silently falls back to the home address stored via the Google Places connector. Three verified root causes:

1. **The tool-side resolution chokepoint ignores the persisted last-known location.** `resolve_location` (`apps/api/src/domains/agents/tools/runtime_helpers.py`) cascades browser → home (implicit) and browser-only (current/query). `last_known_location` is only consumed by the *proactive* cascade (`UserLocationService.get_effective_location_for_proactive`), used by heartbeat ×2, briefing, and interests. Scheduled actions carry **no** browser context at all → always home.
2. **`useGeolocation` has no PWA lifecycle handling.** Position is requested only on mount (localStorage cache valid 5 min, 2 auto-retries). No `visibilitychange`/`pageshow` listener: a frozen-then-resumed PWA never refreshes, so chat requests ship `geolocation: null`. On iOS standalone, the permission can also drop back to `prompt`.
3. **Re-activation prompts are reactive only.** `GeolocationPrompt` and the `useChat` toast fire only when the typed message contains a location phrase — hence "a few messages" before the user sees anything.

Aggravating: the periodic push to `PUT /auth/me/last-location` lives in `WeatherLocationBlock`, mounted only on the proactive-notifications settings page, so in real mobility only chat messages feed the store — and only while browser geolocation is alive.

## Owner arbitrations (2026-08-16)

1. **Full rename**: `users.weather_use_last_known_location` → `users.use_last_known_location`; `PATCH /auth/me/weather-location-preference` → `PATCH /auth/me/location-preference`. Frontend and backend deploy together; no compatibility shim.
2. **Dated position for current/query intents**: when browser geolocation is unavailable, "where am I" / "near me" use the fresh last-known location **with its age exposed to the model** (honesty rule: never present a dated position as current).
3. **The weather settings block is removed without trace** from proactive-notifications settings (no hint, no link). The single control lives on the Google Places connector.
4. **Proactive re-activation banner: chat only**, once per session, dismissable, shown on chat open before any typed phrase.

Defaults decided by the implementer (challengeable): no 50 km distance threshold in the chat cascade (it remains proactive-only, where it stabilizes notifications); single freshness TTL (`LAST_KNOWN_LOCATION_TTL_HOURS`, default 24 h) shared by both cascades; opt-in remains default-off (privacy by design).

## Design

### Backend

- **Rename** (Alembic `op.alter_column(new_column_name=...)` + all readers): `models.py`, `user_location_service.py` (×3), `auth/router.py` (endpoint path, handler, log events, docstrings), `auth/schemas.py` (`LocationPreferenceRequest/Response`), `shared/schemas.py` (user payload field + validator), `user_data_map.py` (GDPR export key), `i18n_api_messages.py` (`location_preference_updated`, generic wording ×6 languages).
- **`ResolvedLocation`** gains `as_of: datetime | None = None` (None for browser/home/explicit). `source` gains the `"last_known"` value.
- **New helper** `get_last_known_location(runtime)` in `runtime_helpers.py`: reads `user_id` from config, loads the user, returns a `ResolvedLocation(source="last_known", as_of=updated_at)` only when opted in AND fresh (reuses `UserLocationService.get_last_known_location`, which already enforces TTL via `stale`). Errors degrade to `None` (same doctrine as the sibling helpers).
- **Cascade change in `resolve_location`** (single chokepoint — skills, places, weather, routes, scheduled actions all inherit):
  - `NONE` (implicit): browser → **last_known (fresh)** → home → silent None.
  - `CURRENT`/`QUERY`: browser → **last_known (fresh, `as_of` carried)** → fallback message.
  - `HOME`: unchanged (home → browser → fallback) — a dated position is *not* a valid answer to "chez moi".
- **Age surfaced to the model**: `skill_location_context.resolve_user_location_for_prompt` appends a language-free age marker when `source == "last_known"` (e.g. `lat,lon (as of 2026-08-16T09:12Z)`); prompt rule text lives in the versioned prompt file. Tools that echo a position include `location_source` and `location_as_of` in their data payload.
- **Proactive cascade**: functionally unchanged (flag rename only).

### Frontend

- **`useGeolocation` lifecycle**: `visibilitychange` + `pageshow` listeners. On return-to-visible with `isEnabled`: re-check permission; `granted` → silent `getCurrentPosition` refresh (no prompt); `prompt` → expose `needsReactivation: true`. Refresh is skipped when cached coords are still fresh.
- **Global push hook** `useLastKnownLocationSync` mounted in the authenticated app shell: when `user.use_last_known_location` && geolocation enabled && coordinates → `PUT /auth/me/last-location`, throttled client-side 30 min (localStorage key `lia_last_location_push_ms`) on top of the existing server throttle; also fires on return-to-visible. The push logic leaves `WeatherLocationBlock` (deleted). Old key `smart_weather_last_push_ms` is added to the logout purge registry and removed.
- **Proactive banner**: `GeolocationPrompt` gains a proactive mode — rendered on chat open (empty composer) when `needsReactivation` OR (enabled + granted + no coords after retries), once per session, dismissable; button = user gesture → native permission prompt. Phrase-triggered mode stays as the safety net.
- **Settings**: the opt-in toggle + transparency view (stored coords, updated-at, staleness, wipe) move into `LocationSettings` (Google Places connector) with generalized copy ("used by chat, scheduled actions, proactive notifications, briefing"). `WeatherLocationBlock` and its i18n keys are deleted; `HeartbeatSettings` loses the block entirely.
- **i18n ×6** for all new/updated keys; strict parity.

### Docs

New ADR (generalization; partial supersede of ADR-073), runbook `LAST_KNOWN_LOCATION.md` updated (flag name, chat cascade, global push), `docs/INDEX.md` + `ADR_INDEX.md`.

## Lots (TDD, in order)

1. Backend rename (migration + all readers + API messages) — tests adapted, `task db:migrate:replay-check`.
2. Cascade: `get_last_known_location` helper + `resolve_location` integration + `as_of` (unit tests: fresh/stale/opt-out/error ×each intent).
3. `useGeolocation` lifecycle (+ `needsReactivation`) — jsdom visibility/permission simulation.
4. `useLastKnownLocationSync` global hook + mount + purge-registry entry.
5. Proactive banner (chat) + i18n.
6. Settings move (LocationSettings block in, WeatherLocationBlock out) + i18n cleanup ×6.
7. Docs + full gates (`task lint`, backend unit fast + coverage, frontend coverage, ratchets if improved).

## Non-goals

- No background geolocation (no service-worker tracking, no `watchPosition` battery drain).
- No native prompt without user gesture (platform-impossible; the banner is the ceiling).
- No change to the proactive 50 km / TTL semantics.
- No location history (single encrypted point, unchanged).
