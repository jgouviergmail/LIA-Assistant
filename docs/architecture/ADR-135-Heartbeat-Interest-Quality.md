# ADR-135: Heartbeat Interest Quality — varied sampling, unified ledger, content-level anti-repetition, concrete enrichment

**Status**: ✅ IMPLEMENTED (2026-07-19)
**Deciders**: JGO
**Technical Story**: User report — proactive notifications kept mentioning the same interests, and the mentions were vague ("jette un œil à une sortie récente A24" without ever naming a film).
**Related Documentation**: `docs/architecture/ADR-131-Interest-Subject-Variety.md` (subject machinery reused), `docs/technical/HEARTBEAT_AUTONOME.md`, `docs/technical/INTERESTS.md` §2.5.2d

---

## Context and Problem Statement

ADR-131 fixed variety in the **interest content flow**. The **heartbeat flow** — the LLM-driven contextual notifier — kept anchoring on the same interests: over 45 days of production, **~14 of 20 interest-flavored heartbeats centered on A24/SF-horror**, near-daily, and **not one named an actual film**. A secondary motif ("une 1664 bien fraîche") repeated 4+ times from a different channel entirely.

Three structural causes were identified in code and confirmed on production data:

1. **Fixed interest sample** — `_fetch_interests` requested the top 30% by weight, hardcoded, ignoring ADR-131 subjects: the same ~6 topics were shown to the decision LLM at every tick, and evening rules (`prefer interests`) made it re-anchor daily.
2. **Anti-repetition blind to what was said** — the window held 5 notifications (< 2 days at 3/day) and exposed only `sources_used` + `decision_reason`, never the message content. The model could not know it had proposed A24 ten evenings running.
3. **No facts, by construction** — the context injected topic *names* only. With no material, "have a look at a recent release" is the best a model can produce.

A fourth channel (memories fetched by a **fixed embedding query**, surfacing the same "1664" memory every tick) explains the non-interest repetitions and is addressed indirectly (see Consequences).

## Evidence (benches on the production container, 2026-07-18)

- **Extended decision schema** (`interest_topic` + `Literal` source labels) on deepseek-v4-flash: **8/8 valid**, topic copied exactly from the injected sample, zero inventions → the structured-output risk was retired before implementation.
- **Content-window variant**: exposing recent *contents* unlocked pivots (2 notifies / 4 runs vs 0 / 7 without) **but** the pivot landed on "1664" — a motif absent from a 5-item window. Hence: **10 items / 7 days** and a rule that operates on topics/products/activities, not sources.
- **Enrichment chain**: Perplexity on the real A24 interest returned "The Backrooms (Kane Parsons), the studio's highest-grossing film" + 8 citations; the message LLM with a FACTS block produced a concrete notification **2/2**, preserving the contextual weave ("Vendredi soir, 24°C à Joinville-le-Pont — et si tu lançais *The Backrooms*…").
- **Query-site census**: 19 `InterestNotification` query sites across 7 files + the runner's today-count → the eligibility/selection boundary table below.

## Decision

1. **Subject-aware varied sample** (`pick_varied_sample` in `domains/interests/selection.py`, reusing ADR-131 subjects): one interest per subject, subjects ordered least-recently-served first (never-served lead), least-served member within a subject. Sample size in `.env`. The decision LLM can only mention what it is shown — the rotation is mechanical, not rhetorical.
2. **Unified mention ledger**: an interest-centered heartbeat writes an `InterestNotification(source="heartbeat")` row (with content embedding), so **both** flows see the subject as served. Boundary:

| Query site | Counts `source='heartbeat'` rows? |
|---|---|
| Interest daily quota / global cooldown / runner pacing | **No** — `notification_filter` |
| Heartbeat cross-type burst check on InterestNotification | **No** — `cross_type_filters` (own artifacts must not self-block) |
| Interest selection: rarity, subject cooldown (`get_recent_for_user`) | **Yes** — variety is global |
| Content dedup (`get_recent_for_interest`), heartbeat sample serving counts | **Yes** |
| GDPR erasure | **Yes** — everything is purged |

3. **Content-level anti-repetition**: the window becomes 10 notifications / 7 days and renders **content excerpts**; the decision prompt gains a two-level rule (source level + topic/product/activity level, explicitly cross-source).
4. **On-demand enrichment**: when the decision sets `interest_topic`, the heartbeat fetches real content through the existing `InterestContentGenerator` (Perplexity → Brave → Wikipedia) under a hard timeout, injects it as a VERIFIED FACTS block with a "name 1-2 concrete items, never invent" contract, and appends deterministic source links (`build_sources_block`, ADR-131). Fetches reuse the interest's recent-notification embeddings so enrichment is deduplicated exactly like the interest flow.
5. **Canonical source labels** (`HeartbeatSourceLabel` Literal): free-text labels had drifted in production ("USER_MEMORIES" vs "USER MEMORIES"), making per-source statistics approximate.
6. **Observability**: `heartbeat_enrichment_total{outcome}` (success | empty | error | disabled) makes the fail-open rate measurable in production, matching ADR-131's metric parity. The canonical `Literal` is deliberately confined to the LLM structured output — the history API keeps `list[str]` so rows predating this ADR still serialize (pinned by a regression test).
7. **Bonus fix**: `_map_source` learned `"brave"` — 141 Brave-served notifications over 60 days were stored as `"custom"`, silently corrupting the source audit trail.

## Consequences

**Positive**: the dominant interest can no longer monopolize the sample; a mention in either flow counts for both; the model sees what it already said (bench-proven to unlock pivots); interest-centered notifications name real, fresh items and link their sources; source statistics become exact.

**Negative / accepted**: ~13 enrichment fetches per month (measured rate) plus one embedding each — negligible; enrichment adds latency to an interest-centered heartbeat (background job, hard timeout, fail-open); the LLM's obedience to the topic-level rule is probabilistic — the mechanical sample rotation is the primary lever, the prompt is the belt over the braces.

**Out of scope, documented**: the memories source still uses a **fixed embedding query** ("important upcoming events preferences routines"), so the same high-relevance memories resurface every tick. The content-level anti-repetition window mitigates the symptom; rotating that query is a separate change.

## Alternatives Considered

- **Embedding-cosine "semantic cooldown" on topics** — rejected: ADR-131 measured the topic-embedding space as compressed (a false pair outscored a true one); only ≥ 0.95 is reliable.
- **Delegating all interest content to the interest flow** — rejected: it would lose the contextual weave (heat + evening + film) that is the heartbeat's whole value.
- **Prompt-only fix** (rules without mechanical rotation) — rejected as a sole measure: the model cannot rotate away from a fixed sample, and the bench showed it skips rather than pivots when the window hides contents.

## Verification

- Unit: varied sample (7 tests, seeded RNG), extended schema (3), content window (3 + updated contract test), eligibility filters (7, both directions + defaults-unchanged), unified ledger (4, incl. embedding symmetry), enrichment (5, incl. fail-open and dedup symmetry), brave mapping (1).
- Full touched suites green (heartbeat + interests + proactive infrastructure).
- Runtime: dev Docker boot, varied-sample rotation observed, one full interest-centered cycle (decision → enrichment → message → ledger row).
