# Google API Ecosystem Enrichment — Design Spec

> **Date**: 2026-08-21 · **Status**: awaiting user review · **Scope**: backend + frontend + seeds + GCP console
>
> Opportunity study validated against the codebase (static evidence) and against the live
> Google APIs (dynamic probes with the platform key, all within free tiers). All arbitrations
> below were settled with the user on 2026-08-21.

---

## 1. Context and goals

LIA already integrates two Google API families:

- **Workspace APIs (per-user OAuth)**: Gmail, Calendar, Drive, People, Tasks — free, quota-bound.
- **Maps Platform (platform `GOOGLE_API_KEY`)**: Places, Routes, Geocoding, Static Maps — paid,
  tracked per call by the ContextVar tracker
  (`src/domains/connectors/clients/google_api_tracker.py`) against the `google_api_pricing`
  table seeded by `infrastructure/database/seeds/google_api_pricing_seed.sql`.

This program enriches both families. Adding a paid SKU = a client + a seed line; the
billing/tracking infrastructure requires no change.

### Settled arbitrations (user, 2026-08-21)

1. **Weather topology**: new functional category `weather`; Google Weather (platform key,
   rebilled) is the default provider; OpenWeatherMap kept as per-user-key alternative.
2. **Re-consent is acceptable** (beta): the Gmail Settings lot is retained.
3. **Street View is promoted** into the plan: thumbnail on address search and as a Place
   photo fallback.
4. **Pollen is retained** (user enabled the API; probe returned 200 — the account has no
   Pro-SKU restriction).
5. **Gmail push is retained**: end users do nothing; the one-time Pub/Sub setup is a
   platform-admin action (steps provided at lot H time). If that setup is refused at lot H
   time, only lot H phase 2 is dropped.
6. **Costs are always displayed as if paid** even under free thresholds — this is already the
   tracker's behavior (`cost = sku_price × calls`, no free-tier deduction); it is preserved.
7. **Execution order**: P0 → A → C → D → B → SV → G → E → F → I → H.

## 2. Verified evidence (what the plan stands on)

### Static (code)

| Fact | Evidence |
|---|---|
| `conferenceData` is read (card, manifest, allowlist) but never written | `display/components/event_card.py:184`, `calendar/catalogue_manifests.py:195`, `core/constants.py:399`; `google_calendar_client.create_event` body builds no `conferenceData` |
| No freeBusy endpoint; availability is a projection over `list_events` | `domains/telephony/availability.py:11` (deliberate minimization-by-capability: only start/end fetched) |
| Heartbeat polls email (`is:unread after:`), 30-min default cadence | `heartbeat/context_aggregator.py:774`, `startup/schedulers.py:417-434` |
| No occurrence of gmail.settings / Sheets / Docs / Drive Activity / Safe Browsing / contactGroups / otherContacts / watch / pubsub | repo-wide greps, 2026-08-21 |
| `contacts.other.readonly` scope is requested but the endpoint is never called | `core/constants.py:2208`, `connectors/schemas.py:196` |
| Sheets and Docs APIs accept the already-granted `auth/drive` scope → no re-consent needed | Google OAuth scope documentation; Drive connector scopes at `core/constants.py:2226-2231` |
| OAuth flow forces full-scope `prompt=consent` (no incremental auth) → any scope addition functionally disconnects users until reconnect | `connectors/service.py:414-415` |
| Inbound verified-webhook precedent exists | `domains/telephony/webhook_handler.py`, channels router |
| Places field masks include `reviews` + `editorialSummary` on all three operations | `google_places_client.py:367-385` (searchText), `:488-506` (nearby), `:576-628` (details) |
| The place card reads `data.get("features")` but nothing ever produces a `features` key; `parkingOptions` has no card section | `place_card.py:373`; repo-wide grep: only consumer, no producer |
| `businessStatus`, `priceRange`, `primaryTypeDisplayName`, `shortFormattedAddress`, `timeZone` are never fetched | field masks above |
| `timezonefinder` is not a dependency; no code resolves TZ from coordinates | repo-wide grep |

### Dynamic (live probes, 2026-08-21, platform key, project <gcp-project-number>)

- Weather, Air Quality, Pollen, Street View metadata, Web Risk: **all 200 OK** after the user
  enabled the APIs and extended the key's API allowlist. Before enablement the probes returned
  `API_KEY_SERVICE_BLOCKED` — the key has an API allowlist (good practice, kept). A positive
  control on Geocoding passed throughout.
- Web Risk correctly flags `testsafebrowsing.appspot.com/s/malware.html` as MALWARE and
  returns `{}` for a clean URL.
- The Weather response natively carries `timeZone.id` and supports `languageCode`.
- Pollen (Pro SKU) answering 200 proves the billing account has no SKU-tier restriction.

### External (pricing, verified on Google's official pricing pages, 2026-08)

| SKU | Price /1000 | Free /month |
|---|---|---|
| Text Search / Nearby Search **Enterprise + Atmosphere** (what our masks actually trigger) | $40.00 | 1,000 |
| Place Details **Enterprise + Atmosphere** | $25.00 | 1,000 |
| Weather API (Essentials) | $0.15 | 10,000 |
| Air Quality API (Essentials) | $5.00 | 10,000 |
| Pollen API (Pro) | $10.00 | 5,000 |
| Street View Static (Essentials) | $2.00 | 10,000 (metadata endpoint: free) |
| Web Risk `uris.search` | $0.50 | 100,000 |

The current seed bills Text Search/Nearby at $32 (Pro) and Details at $17 (Pro): **the
platform under-bills by ~20-25% and the real free threshold is 5× smaller than documented.**

## 3. Cross-cutting contracts (apply to every lot)

- **Three response formats**: every data enrichment updates or creates the matching display
  card AND is exercised in cards / enriched-HTML / markup modes.
- **Tools**: `@track_tool_metrics` + `@rate_limit` (settings-driven), catalogue manifest with
  published bounds, registry completeness asserts, `ToolResponse`/`ToolErrorModel`.
- **HITL** on every write (Meet creation rides the existing calendar draft flow; Sheets/Docs
  writes and Gmail Settings writes get classified in `hitl_classifier.py`).
- **i18n**: 6 languages, backend strings through `core.i18n_*`, frontend locale parity.
- **Provider parity** (CLAUDE.md): every Google capability states its Microsoft/Apple
  behavior — implemented equivalent or explicit graceful degradation. Never Google-only silently.
- **Paid SKUs**: seed line + `track_google_api_call()` + `GOOGLE_API.md` row. Seeds are
  updated **and injected in dev and prod** (reference-seed procedure: remove-before-insert,
  `deploy:prod` before re-injection, `verify_reference_seeds.sql` check).
- **Settings**: every tunable is a Settings field + `.env.example` entries; feature flags for
  optional subsystems (`WEB_RISK_ENABLED`, `GOOGLE_WEATHER_ENABLED`, push flags).
- **Tests**: mocked providers, unconditional (no env-gated skips), round-trip tests for any
  serialized state, guards' conventions respected (UTC datetimes, JSONB new-dict, no empty
  except).

## 4. Lots

### Lot P0 — Places: billing exactness & full data exploitation

*The user's intuition ("we don't process all Places data") confirmed and sharpened: we pay
Enterprise+Atmosphere, display a subset, and mis-bill at Pro prices.*

- Fix seed prices: Text Search $40, Nearby $40, Details $25 (SKU names updated accordingly);
  inject dev + prod; realign `GOOGLE_API.md` (prices AND real free thresholds).
- Fetch the missing Pro-tier fields (zero marginal cost at E+A): `businessStatus`,
  `priceRange`, `primaryTypeDisplayName`, `shortFormattedAddress`.
- Card: handle `CLOSED_PERMANENTLY`/`CLOSED_TEMPORARILY` (a permanently closed place must
  never render as a normal one), render `priceRange`, use `primaryTypeDisplayName` instead of
  the hand-rolled type mapping where available.
- Wire the dead branch: normalize the ~20 atmosphere booleans into the `features` key the
  card already renders; add the missing parking section.
- Optional planner-facing "lite search" mode (Pro-only mask, $32/5,000 free) for queries that
  need no atmosphere data; the full mask remains the default.
- Edge cases: absent fields per place type (masks are maximal, responses are sparse — every
  card section stays conditional); registry payload variants (string vs object `displayName`).

### Lot A — Calendar: Meet link at event creation

- `create_event`/`update_event`: optional `add_conference` parameter → body
  `conferenceData.createRequest` + query `conferenceDataVersion=1`.
- Tool + manifest parameter (published, HITL draft shows "with video link").
- Parity: Microsoft → `onlineMeeting` (Teams) on the Graph client; Apple → graceful absence
  (draft states no video support).
- Edge case: accounts where Meet creation fails → event is still created without conference,
  never a creation failure; response states the degradation.
- Validation point (residual risk): behavior on consumer accounts proven by integration test
  at lot start.

### Lot C — People: otherContacts + contactGroups (scopes already granted)

- Client methods `list_other_contacts`, `search_other_contacts`, `list_contact_groups`,
  `get_contact_group` (+ membership resolution).
- Feed `relations`/entity resolution (other-contacts as candidate identities) and contact
  targeting ("send to the family group").
- contact_card: group chips. Parity: Microsoft categories/contact folders read where cheap;
  Apple → none (documented).
- Edge cases: pagination (otherContacts can be large), sync tokens not used (stateless reads),
  group membership caps.

### Lot D — Web Risk URL screening

- Chokepoint: `url_validator` used by web_fetch/browser tools — after SSRF checks, before
  fetch; also applied to outbound link rendering where cards surface external URLs.
- Redis verdict cache honoring the response `expireTime`; `WEB_RISK_ENABLED` flag; separate
  metric counters (checked / flagged / errors).
- **Fail-open**: Web Risk unavailability logs and proceeds (availability must not gate
  browsing); a flagged URL blocks with a localized message (6 languages).
- SKU line (`web_risk`, `/v1/uris:search`, $0.50) + tracking. 100k/month free ≫ expected volume.

### Lot B — Calendar freeBusy + common-slot tool

- Client `query_freebusy(calendars, time_min, time_max)`; tool "find availability / common
  slot" over multi-calendars.
- Migrate `telephony/availability.py` to freeBusy for Google (strictly less data exposure —
  aligned with its minimization doctrine); **keep the list_events projection as the Apple
  fallback and as the generic fallback** (never delete it).
- Parity: Microsoft → `getSchedule`.
- Edge cases: >50 calendars per query (API cap), `errors[]` per calendar in the response
  (a calendar that fails yields the unavailable line, never a crash), all-day events, TZ.

### Lot SV — Street View Static thumbnails

- Client (platform key family): metadata endpoint (free) checked first — imagery exists →
  render thumbnail; otherwise no section at all (no broken images).
- Surfaces: location_card (address search) and place_card (hero fallback when Places returns
  no photo — Street View $2/1000 vs Place Photos $7/1000).
- SKU lines: `street_view` `/streetview` $2.00 (billed) and `/streetview/metadata` $0.00
  (tracked for observability, zero cost); proxy endpoint like the existing static-map one.

### Lot G — Gmail history.list delta sync (heartbeat)

- Store per-user `historyId` (Redis); heartbeat email fetch becomes
  `history.list(startHistoryId)` with fallback to the current query when the id is expired
  (404 → full resync) or absent.
- Cheaper, exact "new since last tick"; **prerequisite for lot H phase 2** (push only carries
  a historyId).
- Providers without history semantics (Apple/Microsoft) keep the current query path.

### Lot E — Google Weather + Air Quality + Pollen

- New functional category `weather` in `CONNECTOR_FUNCTIONAL_CATEGORIES`:
  `GOOGLE_WEATHER` (platform key, default) + `OPENWEATHERMAP` (per-user key, kept). Provider
  resolver drives `weather_tools`; response normalization keeps one internal weather shape.
- **Regression surface (measured 2026-08-21): 19 files reference OPENWEATHERMAP** — among
  them `agents/graphs/weather_agent_builder.py` (dedicated agent graph),
  `interests/proactive_task.py` (proactive weather), `heartbeat/context_aggregator.py`,
  `briefing/fetchers.py`/`formatters.py`, and `connectors/geocoding.py` (OWM geocoding
  coupling). Design rule to keep this lot safe: **normalize at the client boundary and keep
  the internal weather data shape stable** so the 19 call sites are untouched; only the
  resolver + client change. The OWM geocoding path is out of scope (Google Geocoding already
  exists) and must not regress.
- Frontend surface: the connectors settings page gains the `weather` category with the
  provider choice (Google Weather platform-side, no credentials, vs OWM personal key),
  following the existing category UI pattern; 6-locale strings.
- Google Weather client: current conditions, hourly/daily forecast up to 10 days, history
  24 h; `languageCode` from user language (chokepoint `normalize_language`); native
  `timeZone.id` used for display formatting.
- Air Quality (current + hourly forecast; `uaqi` + local index) and Pollen (5-day forecast)
  as platform services surfaced in weather answers, the briefing (health-adjacent card), and
  proactive signals (pollution/pollen peaks for sensitive users — heartbeat interest quality
  rules apply).
- Cards: weather_card upgraded (10-day, condition icons from `iconBaseUri`); new or extended
  section for AQ/pollen; briefing `fetch_weather` extended with per-section cache TTLs.
- SKU lines: `weather` $0.15, `air_quality` $5.00, `pollen` $10.00 + tracking on every call.
- Edge cases: regional unavailability (AQ/pollen coverage varies → conditional sections),
  unit handling, provider switch mid-conversation (resolver is per-call).

### Lot F — Sheets + Docs (reading first, then HITL writes)

- Rides the **existing Drive connector token** (`auth/drive` covers both APIs — no new scope,
  no re-consent). Enabled APIs verified at lot start with a user token (residual risk: proven
  then).
- Phase 1 (read): `read_spreadsheet` (values + basic structure), `read_document` (structured
  text) tools — "read this sheet and answer", cross-domain combination.
- Phase 2 (write, HITL): create/update spreadsheet values, create/append document content;
  optional `document_generation` bridge ("export as a living Sheet/Doc" alongside the static
  xlsx/docx).
- Cards: new sheet/doc cards (file_item base + content preview) in all three formats.
- Edge cases: Sheets quota 60 req/min/user under settings-driven rate limits; A1-notation
  bounds published in manifests; huge sheets (range caps, never full-sheet dumps into the
  LLM); Docs structural edits limited to append/replace patterns (no arbitrary styling in v1).

### Lot I — Gmail Settings (single re-consent wave)

- Adds `gmail.settings.basic` to the Gmail connector scopes — **the only scope-adding lot**;
  acceptable in beta (user decision). Existing Gmail users must reconnect; the connectors UI
  already surfaces the needs-reconnect state.
- Capabilities: vacation responder (proposed proactively when calendar absence detected —
  HITL confirm), filter creation ("route newsletters to label X" as a persistent filter),
  sendAs read.
- Parity: Microsoft automatic replies (`mailboxSettings`) where cheap; Apple → none.
- All writes HITL-classified; every user-visible string i18n'd.

### Lot H — Push (phase 1: Calendar + Drive watch; phase 2: Gmail + Pub/Sub)

- Phase 1 (no Pub/Sub): `events.watch` / `changes.watch` channels pushing directly to a new
  verified webhook endpoint (channel token + resource validation, following the telephony
  webhook precedent); channel registry (DB) with expiry; leader-elected renewal scheduler job;
  invalidation of the matching caches + heartbeat freshness on notification.
- **Phase 1 admin prerequisite (added by self-audit)**: Google requires the push endpoint's
  domain to be **ownership-verified** (Search Console) and registered under the GCP project's
  allowed push domains before `watch` calls are accepted. One-time platform-admin action on
  the production domain, guided step-by-step at lot start — same nature as API enablement,
  no end-user action.
- Phase 2 (Gmail): platform-admin one-time GCP setup (topic, publish grant to
  `gmail-api-push@system.gserviceaccount.com`, OIDC push subscription — exact `gcloud` script
  provided then); `users.watch` per user with existing scopes (no user action, no re-consent);
  7-day watch renewal job; `history.list` delta (lot G) on notification; dedup by historyId.
- Feature flags per phase; polling remains the fallback whenever push is disabled or stale.
- Edge cases: duplicate/out-of-order notifications (idempotent by resource version),
  channel expiry during downtime (resync on boot), Cloudflare tunnel availability, notification
  storms (debounce per user), multi-instance safety (leader election, single consumer).

## 5. Rejected / deferred (decided)

- **Rejected**: Time Zone API (no code-level need; Weather even returns `timeZone`), Drive
  Activity API (needs a new scope; `changes.list` covers the need with existing scopes),
  Elevation / Roads / Solar / Aerial View, YouTube Data (quota-unmanageable multi-user),
  Custom Search (Brave/Perplexity cover), Keep (Workspace-only), Fit REST (shut down 2025),
  Photos Library (scopes withdrawn 2025; Picker UI cost ≫ value), Meet REST / Chat /
  Classroom / Admin SDK (Workspace pivot).
- **Deferred**: Address Validation (Pro, 5k free — waiting for a real need, e.g. contact
  address hygiene), "Drive activity" briefing card via `changes.list` (can join lot H phase 1).

## 6. Residual risks (accepted, with validation points)

1. Meet `conferenceData` on consumer accounts → integration test at lot A start.
2. Sheets/Docs API enablement + drive-scope ride-along → probe with a real user token at
   lot F start.
3. Push end-to-end through the Cloudflare tunnel → staging validation at lot H.
4. AQ/pollen regional coverage variability → conditional rendering by design.

## 7. Deployment prerequisites — status

- Done (user, 2026-08-21): Weather, Air Quality, Pollen, Street View Static, Web Risk, Sheets,
  Docs APIs enabled on project <gcp-project-number>; key allowlist extended (Weather, AQ, Pollen*,
  Street View, Web Risk). All probes green.
- Remaining: Pub/Sub setup (lot H phase 2 only, guided); seed injection dev+prod at each
  SKU-touching lot (P0, D, SV, E).

*Pollen was added to the allowlist together with its enablement.
