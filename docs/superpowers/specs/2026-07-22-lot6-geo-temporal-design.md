# Lot 6 — Geo-temporal Grounding: Smart Departure (P6) + Local Interests (P9) + Skill Nudges (P13)

**Program**: [Interdomain Intelligence Program](2026-07-21-interdomain-intelligence-program.md) · **Status**: SPEC (2026-07-22) → implementation
**No ADR** (composition of existing mechanisms; recorded here + tracker).

## P6 — Smart departure advice (calendar × route × weather)

- **Second-pass consumer, not a new provider fetch**: the aggregator already
  fetched calendar events WITH `location` in the first pass. After the
  gather, when `HEARTBEAT_DEPARTURE_ENABLED` and the FIRST located event
  starts within `HEARTBEAT_DEPARTURE_LOOKAHEAD_HOURS`: resolve the user's
  effective origin (`get_effective_location_for_proactive`), call
  `GoogleRoutesClient.compute_route(origin, destination=event.location,
  arrival_time=event start, TRAFFIC_AWARE)`, derive `leave_by` = start − ETA.
  Redis cache `heartbeat:departure:{user}:{event-hash}` TTL 15 min (budget:
  ≤1 Routes call / cycle / event). Silent-None everywhere (bonus source).
- `HeartbeatContext.departure_advice` {event_title, event_start_local,
  eta_minutes, leave_by_local, destination} + prompt section `DEPARTURE
  ADVICE` + label `DEPARTURE_ADVICE` + decision rule 20 (HIGH value when
  leave_by is near; combine with rain per rule 13; never repeat for the
  same event — anti-redundancy window carries it).
- Settings module additions (agents.py heartbeat block): flag default False,
  lookahead (3 h), cache TTL (900 s). `.env` ×2.
- Client key: same acquisition path as `routes_tools` (verified at impl).

## P9 — Local anchoring of interests

- `ContentGenerationContext` gains `locality: str | None` (city). When
  `INTERESTS_LOCAL_ANCHOR_ENABLED` and the interest flow resolves a city
  (effective location → `resolve_city_name`, best-effort, OWM key), the
  Brave/Perplexity query templates append a localized "near {city} this
  week" suffix — content becomes locally actionable ("expo à Lyon samedi").
  Existing embedding dedup already prevents repetition. Flag default False.
- City resolution lives in the interest proactive task (one lookup per
  cycle, cached by the location service semantics), never in the sources.

## P13 — Contextual skill nudges (prompt-driven v1, detached from Lot 3)

Verified: skills only activate via QueryAnalyzer match. v1 is deliberately
prompt-only (zero new plumbing): heartbeat decision rule 21 — when an
upcoming calendar event within 2 h looks like a substantial meeting, the
notification MAY end by offering "veux-tu que je te prépare cette réunion ?"
(the user's yes routes through the normal pipeline → preparation-reunion
skill matches). Guarded by the prompt-presence test file. Deeper integration
(initiative-node coaching nudge) deferred with the J+14 measurements.

## Tests
P6: second-pass gating matrix (flag off / no located event / too far /
cache hit / Routes failure → None), leave_by arithmetic (tz-aware), schema
render + label, rule 20 presence. P9: context carries locality; query
builders append the suffix only when locality present + flag on; city
resolution failure → no suffix. P13: rule 21 presence guard.

## Gates
Backend fast suite + lint/mypy + ratchets + runtime smoke. No frontend.
