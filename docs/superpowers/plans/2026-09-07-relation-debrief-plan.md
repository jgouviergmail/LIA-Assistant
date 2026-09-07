# Relation debrief — implementation plan (2026-09-07)

Design: `docs/superpowers/specs/2026-09-07-relation-debrief-design.md`.
TDD throughout: the failing test first, then the code that makes it pass.

## Lots

| # | Lot | Done when |
|---|---|---|
| 1 | **Evidence extraction** — `relations/overview/` + `ContextStatus.NOT_REQUESTED` + skip the provider read out of scope + drop the `_resolve_provider_client` duplicate | `get_person_overview_tool`'s payload is unchanged on a scope matrix; zero provider call when no provider section is in scope |
| 2 | **Persistence** — `RelationDebrief`, `relation_debrief_enabled` column, one migration, repository with the atomic claim, data-lifecycle wiring | claim is exclusive under two real PostgreSQL sessions; purge + export + registries green |
| 3 | **LLM** — type `relation_debrief`, defaults, seed, admin i18n ×6, versioned prompt, `debrief/llm.py` | a build produces a structured body and one `track_proactive_tokens` call |
| 4 | **Service** — once-a-day, digests, states, merge/split invalidation | the day boundary is the user's local one; a second call the same day makes no LLM call |
| 5 | **API** — GET / POST / PATCH, schemas, rate limit, router order | routes answer before `/{name}`; the limiter is its own action |
| 6 | **Chat injection** — `build_relation_context`, directory, single-match rule, new template, flag | ambiguous match injects nothing; no debrief → today's behaviour byte-identical |
| 7 | **Frontend** — hook, section, toggle, 6 locales, responsive, a11y | five states, `aria-busy` on rebuild, accessible names en+fr, parity |
| 8 | **Observability** — metrics + Grafana panels | metric ratchet green without a baseline entry |
| 9 | **Docs** — ADR-269, INDEX, ADR_INDEX, CLAUDE.md, `docs:sync-agents`, `.env` examples | `task lint:docs` green |
| 10 | **Gates + ratchets + adversarial review** | `task ci:fast` green; ratchets lowered where measurement improved |

## Test plan, as it ended up (enriched during implementation)

Everything below exists and is green. The lines marked **[found]** were added
because the test found a defect, not because the plan predicted one.

### Anti-regression oracle — the extraction
- `golden_overview_payloads.json`, captured from the PRE-extraction tool: 18
  scope cases, payload AND message compared through JSON. 42 assertions.
- The tool's own 654-line suite, assertions untouched (only its patch targets
  moved with the seam). 37 tests.
- **[found]** provider reads follow the scope — the pre-extraction tool charged
  one read for every case, including the two that want none.

### Evidence assembly (real provider service, stubbed fetchers)
- no section wanted → nothing fetched at all;
- contact only → mail and calendar never touched;
- mail only → the CARD is still read (it holds the addresses) but reported
  `NOT_REQUESTED`;
- an excluded section is never reported as a missing address;
- omitting the argument keeps the historical behaviour byte for byte.

### Persistence — real PostgreSQL, 27 tests
Second claimant refused while the lease holds · today's settled debrief not
rebuilt · a dead builder's lease expires and releases the row · day, language
and scope each make a rebuild legitimate · a forced rebuild ignores all three ·
a failure waits out its cooldown · an empty relationship is not retried the same
day · a stale writer writes NOTHING (fencing) · an unchanged rebuild carries the
day without moving `generated_at` · the chat directory lists only `ready` rows
within the age · a build in flight is never injected · merge/split delete by key.
- **[found]** a failed refresh KEEPS the previous body and its date; an emptied
  relationship DOES clear it; `carry_forward` never promotes an empty row to
  `ready`.

### Service — real PostgreSQL, 13 tests
The second build of the day calls no model · a read never builds · the LOCAL
date decides (Pacific/Auckland at 23:30 UTC files under tomorrow) · a language
change and a scope change each write a new debrief · a forced rebuild over
identical evidence calls NO model and keeps the date the words were written on ·
changed evidence does call it · no evidence settles `empty` without a call · a
model failure settles `failed` and never a half body · an unreadable
relationship settles `failed` · the previous debrief survives a failed refresh ·
both switches (account, instance) build nothing and say so.
- **[found]** the "nothing changed" shortcut must NOT apply when the language or
  the scope changed — the evidence is identical, so a language change was
  claimed and then skipped, and the debrief stayed in the old language for good.

### Judgement calls — 27 unit tests
What counts as evidence · digest stability · which sections are reported · a
body this version cannot read · a failed row still shows what stands · the
rebuild control is only offered when it would work.
- **[found]** the prompts actually RENDER with exactly what the builder passes,
  hostile braces in the evidence included, and every section header names a real
  body field.
- **[found]** the model's answer is REPAIRED, not refused: an over-long list is
  trimmed, an over-long sentence is cut within its bound, blank items are
  dropped — and the schema the model sees carries no length or item-count
  keyword at all (not universally accepted in strict mode), while staying
  strict-compatible. Its description is not an essay, because Pydantic sends the
  docstring to the model.

### Injection — 18 unit tests
The one person named brings their debrief · the block states when it was
written · an empty field renders no heading · nobody named injects nothing ·
**two matching people inject nothing** · whole-word matching only · a failing
read, an unreadable body and the flag off each inject nothing · no PII at INFO.
- The template is tested for its WORDING: it never says EXACT, it names date,
  count, status and "still open" as things to verify, it sends them to the
  tools, it says it is not a live reading, it forbids reading absence as
  nothing — and the peer block still says the opposite about its own facts.
- With no debrief, the combined block is byte-identical to today's.

### Frontend — 33 tests
Hook: reads without building · builds once, after the provider half settled ·
never twice for the same person · never retries a FAILED debrief · nothing while
the account has it off · forces a rebuild · a failed build leaves the current
answer standing · reports someone else's build as in flight · stages the first
read only.
- **[found]** it never decides on the PREVIOUS person's answer while the next
  one loads.
Component: the synthesis field by field · states when it was written · names
what could not be read · no heading for an empty field · a refresh announces
itself and keeps the text · a failed refresh keeps the body · empty vs absent ·
the rebuild control works by click AND keyboard and stays focusable while
refused · the switch collapses to a row that turns it back on · every string
comes from the locale.
Overview: the switch reads ON when the API says nothing, adopts what the server
STORED, and rolls back when it refuses.

### Cross-cutting
No French literal in the new backend modules · six-locale parity · the demo
instance's public surface declares the three new routes · the two rate-limit
budgets are separate actions · every literal route is declared before the
catch-all.

## Gates

`task lint`, `task test:backend:unit:fast`, `task test:frontend`,
`task test:frontend:coverage`, `task lint:i18n`, `task lint:docs`,
`task db:migrate:replay-check`, then `task ci:fast`.
