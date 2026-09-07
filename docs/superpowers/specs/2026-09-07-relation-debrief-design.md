# Relation debrief — design (2026-09-07)

One LLM-written debrief per relationship, built at most once per user local day,
rendered on the relationship card and injected into the chat when the person is
named.

## 1. Problem

The relationship card already shows everything LIA knows about a person, in ten
sections. Nobody reads ten sections. What the reader wants first is the answer
to *"where do I stand with this person, and what should I raise?"* — a synthesis
no aggregate can produce.

The same synthesis is worth having in the chat: naming someone should not make
the assistant announce a lookup for facts the database already holds.

## 2. What already exists (measured, not assumed)

| Piece | Where | What it gives |
|---|---|---|
| DB-local half | `RelationsService.build_detail` | open commitments, calls, memories, relayed messages, peer link, merges — pages **plus exact totals** |
| Provider half | `RelationContextService.build` | contact card, mail, meetings — per-section status, Redis-cached (contact 6 h, mail/events 15 min) |
| Scope | `RelationOverviewScope` | what a "360° point" may read: sections, directions, roles, `max_items` |
| **Evidence assembly** | `get_person_overview_tool` | **all of the above, under the scope, with `unavailable`** |
| Chat injection seam | `_inject_peer_context` → `build_peer_context` | one prompt block, peers only |

The fourth row is the discovery that shapes this design: the assembly a debrief
needs **already exists**, inside an agent tool. Writing a second one would create
two authorities on "what a 360° point reads" — the defect class ADR-185 exists to
prevent.

## 3. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | The evidence assembly is **extracted** from `person_tools.py` into `relations/overview/`, and the tool becomes its first consumer | one implementation of "what a 360° reads"; pinned by the tool's existing 654-line test file |
| D2 | The debrief **obeys `RelationOverviewScope`** | one place where the user says what a point on this person may read; it also bounds provider cost and prompt size |
| D3 | Built **lazily, on card open only** — never by a scheduler, never by a chat turn | `relations_total` is unbounded; a nightly sweep is N users × M relations LLM calls/day |
| D4 | **At most once per user LOCAL day**; language change and scope change are legitimate rebuilds | a debrief written in the wrong language, or under a scope the user has since changed, contradicts the user's own settings |
| D5 | The passive "data moved" flag is **removed**; the digest is compared **only when the evidence is in hand** | a flag reading `false` would state a negative nobody verified (ADR-184) |
| D6 | Chat injection reaches the **response node only**, in the existing `_inject_peer_context` slot | `fetch_response_context` has CC=67; the audit gate forbids growing a hotspot. Zero new branches, and the `gather` stays at six awaitables |
| D7 | The injected block gets **its own versioned template with the opposite directive** to the peer block | the peer block says its facts are EXACT and to answer without looking — true for a live read, a false-claim machine for a dated summary |
| D8 | Per-user toggle `relation_debrief_enabled`, settable **from the Relations page** | the feature costs LLM money and reads relationship data; the user owns that decision |
| D9 | A merge or a split **deletes** the affected debriefs | the key is the canonical identity; a stale row would describe an identity that no longer exists |

## 4. Defect fixed on the way

`get_person_overview_tool` calls `RelationContextService.build()` **unconditionally**,
then drops the provider blocks the scope excluded (`_provider_blocks` filters
after the fetch). A user who unticked `contact`, `emails` and `events` still pays
up to **11 external API calls** (3 mail searches per address × 3 addresses, plus
contact, plus calendar). This is ADR-184's trap pointing at cost: a selection
published but not honoured.

The extraction fixes it — the provider read is skipped entirely when no provider
section is in scope, and narrowed to the requested sections otherwise. This needs
one new `ContextStatus` member, `NOT_REQUESTED`: "I did not look, on purpose" is
a third answer, and folding it into `EMPTY` ("looked, found nothing") or
`NOT_CONFIGURED` ("nothing plugged in") would be a lie.

Second factorization: `person_tools._resolve_provider_client` duplicates
`relations/providers/client.open_category_client`, without its deterministic
close. The duplicate goes.

## 5. Architecture

```
relations/
  overview/                 # NEW — the single 360° evidence assembly
    blocks.py               # pure projections, no I/O
    recall.py               # semantic memory recall
    fallback.py             # by-name last resort (uses open_category_client)
    evidence.py             # build_overview_evidence() + overview_payload()
  debrief/                  # NEW — the artefact
    models.py               # RelationDebrief
    repository.py           # atomic claim / settle
    llm.py                  # prompt render + invoke + token tracking
    service.py              # once-a-day rule, digests, invalidation
    schemas.py              # API contract
```

`person_tools.get_person_overview_tool` shrinks to: validate runtime → scope →
`build_overview_evidence` → `overview_payload` → `_overview_message`.

## 6. Persistence

`relation_debriefs` — one row per `(user_id, name_key)`, the CURRENT debrief, not
a history.

| Column | Note |
|---|---|
| `user_id` | FK `users.id` ON DELETE CASCADE |
| `name_key` | canonical folded identity (`IdentityResolver`) |
| `display_name` | spelling to render |
| `generated_for` | the user's **local** date (`resolve_user_timezone`) |
| `generated_at` | UTC instant |
| `language` | backend-canonical (`zh-CN`, never `zh`) |
| `scope_digest` | sha256 of the scope the debrief was written under |
| `evidence_digest` | sha256 of the evidence — compared only at rebuild |
| `sections_used`, `unavailable` | JSONB — the honesty contract |
| `body` | JSONB, versioned structured payload |
| `state` | `building` / `ready` / `failed` / `empty` |
| `claim_owner`, `claim_expires_at` | lease, so a hard kill cannot wedge a row |

Unique `(user_id, name_key)`; index `(user_id, state)` for the chat directory.

**The claim is one statement**: `INSERT … ON CONFLICT (user_id, name_key) DO UPDATE
SET … WHERE <today's date differs> OR <language differs> OR <scope differs> OR
<lease expired> OR <forced> RETURNING id`. An empty `RETURNING` means someone else
owns the build, or today's is already there. No `SET NX` + unconditional delete.

## 7. Freshness contract

- Automatic build: at most once per user local day, per relationship.
- Legitimate rebuilds (not counted as "the same day"): language changed, scope changed.
- Data moved: **never rebuilds by itself**. The card states `generated_at`; the user may ask.
- Forced rebuild whose `evidence_digest` is unchanged: **the LLM call is skipped**
  and the answer says "re-checked at HH:MM, nothing changed" — exact, because it
  was just verified.
- No evidence at all → `state=empty`, no LLM call, no generic paragraph.
- Merge / split → rows deleted.

## 8. API

| Route | Behaviour |
|---|---|
| `GET /relations/{name}/debrief` | returns the stored debrief or `state: absent`. **Never generates.** |
| `POST /relations/{name}/debrief?force=` | builds today's, or forces a rebuild. Own rate-limit action + per-user daily cap |
| `PATCH /relations/settings` | `{debrief_enabled}` — the per-user toggle |

`GET /relations` carries `debrief_enabled` so the page knows without a second read.
All three declared **before** the `/{name}` catch-all.

The panel issues the `POST` **after** `useRelationContext` resolves — chained, so
the provider caches are warm and the debrief costs no external call.

## 9. Chat injection

`build_peer_context` → `build_relation_context`, same module, same slot.

- Directory = `ready` debriefs no older than `relation_debrief_injection_max_age_days`
  ∪ accepted peers (today's behaviour preserved).
- **Ambiguous match injects nothing** — a false positive leaks the wrong person.
- Debrief present → injected with its age and its `unavailable` list.
- Debrief absent → exactly today's behaviour.
- New template `relation_debrief_context_template.txt` (English, like the rest):
  a **dated summary**, useful for context and what to raise, **never** an authority
  on a date, a count or a status; factual questions go to the tools.

## 10. Frontend

`RelationDebriefSection.tsx`, first block of the left column. States: absent,
building (`aria-busy`, never an unmount), ready, failed, disabled. Footer states
`generated_at`, sections used, sections unavailable. The toggle lives in the
section's toolbar, and when off the section collapses to a single re-enable row —
a feature that vanishes with no way back is a bug.

## 11. Out of scope (YAGNI)

No debrief history, no scheduler, no planner/ReAct injection, no admin surface.

## 12. Test plan

See `docs/superpowers/plans/2026-09-07-relation-debrief-plan.md`.
