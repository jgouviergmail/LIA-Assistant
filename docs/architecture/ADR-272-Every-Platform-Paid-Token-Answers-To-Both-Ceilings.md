# ADR-272 — Every platform-paid token answers to both ceilings

**Status:** Accepted — 2026-09-07
**Amends:** ADR-270 (spend roads, cost bearers, register authorship), ADR-248
(one predicate, never two copies), ADR-085 (a registry gets a completeness
assert)

---

## Context

ADR-270 settled **where** each module's model spend is recorded. It did not
settle **whether anything bounds it**, and the two are not the same question:
a euro can be perfectly accounted and still be spent past a ceiling nobody
asked.

The rule this ADR applies is a product one: *every token cost borne by the
platform is subject to the quotas — the per-account one and the global one.
Only what a person pays with their OWN connector key is outside them.*

`cost_bearers` already says which is which. The `llm` family bears
`CostBearer.INSTANCE`: model calls run on the keys in `provider_api_keys`, a
table with no `user_id`. **The deployment pays for every model call**, so every
model call is in scope. Perplexity, Brave, the weather connector and telephony
are not — those run on the person's own credential.

`LLM_SPEND_ROADS` names all 46 modules that obtain a model. Measured against
the guarded doors on 2026-09-07:

| | |
|---|---|
| Declared spend sites | **46** |
| Passing through a guarded door | 17 |
| Bounded upstream, at a turn's entrance (`TURN` road) | 21 |
| Bounded by a named accountant (`CALLER` road) | 7 |
| **Bounded by nothing at all** | **5** |

The five: `evaluation_pipeline` spent for the operator with no ceiling;
`open_loop_extractor`, `briefing/llm`, `user_mcp/description_generation` and
`reminder_notification` spent against a real account without asking it.

Three structural defects produced them.

### 1. The registry named a wrapper, not the door

`LLM_CHOKEPOINTS` declared `get_structured_output_with_retry`. That function is
a retry wrapper: it delegates to **`get_structured_output`**, which is public,
unguarded, and called directly by nine modules. One of two sibling functions in
the same file was guarded, and the guard's own completeness test could not see
it — it only checks that *declared* doors ask.

### 2. The shared gate returned before asking

`enforce_usage_limit` had two early returns:

- on `usage_limits_enabled` being false — which switched off the **instance**
  ceiling too, although `check_user_allowed` deliberately keeps that ceiling
  *outside* the flag ("bounding what ONE account consumes and bounding what the
  INSTANCE spends are two different protections"). An operator who set a daily
  budget while leaving per-user limits off got enforcement at the chat router
  and none at the chokepoints;
- on the call having no owner — true for the per-account ceiling, and beside
  the point: the deployment's key still paid.

### 3. One refusal, two answers

The chat router answered an instance pause with a stable error code and a
computable `Retry-After`; the shared gate answered with neither. A caller
blocked at a chokepoint could not tell "the deployment is paused until
tomorrow" from "you are over your own limit", and had nothing to wait on.

---

## Decision

**One verdict, asked at the real door, answered the same way everywhere.**

### 1. The chokepoint is the innermost door

`LLM_CHOKEPOINTS` now names `get_structured_output`. The retry wrapper keeps
its `user_id` parameter and threads it down — it is a *bounded caller*, not a
door. Moving the declaration closed two of the five holes on its own, because
`evaluation_pipeline` and `open_loop_extractor` were already calling the real
door.

### 2. The gate asks both ceilings, always

`enforce_usage_limit` no longer returns early. With an owner it asks
`check_user_allowed`, which asks the instance ceiling first and the account's
after. Without an owner it asks the instance ceiling directly. The feature flag
keeps governing exactly what it is named for — the per-account bound — inside
the one implementation that owns it.

### 3. One raiser — `usage_limits/enforcement.py`

`raise_for_blocked_verdict` counts the enforcement metric and raises, adding
the instance error code and the seconds until the UTC day rolls over when the
deployment is paused. The chat router and the shared gate both call it.

### 4. Two shapes to receive a refusal, never two ways to compute it

How a caller receives the verdict follows its **transport**, not its opinion of
the rule:

- a request path **raises** — `enforce_usage_limit`;
- a background path **degrades** — `spend_blocked`, the non-raising sibling of
  the existing `is_instance_spend_blocked`, so a reminder still fires with its
  written sentence, a dashboard still renders with its written greeting, and an
  MCP server can still be registered with its deterministic description.

And it says **skipped**, not failed. Logging a quota refusal as a generation
failure describes something the code did not do.

### 5. A refusal is never a measurement

Making `get_structured_output` a chokepoint put a ceiling in front of the
retrieval-evaluation harness — which already carried a written exemption
(`INSTANCE_GATE_EXEMPT`) arguing that *"an evaluator must produce a measurement
or fail; skipping the call would hand back a fabricated score an operator would
then read as real"*. Its `except Exception` returns `score=0.5`, so the ceiling
arriving **through** the gate produced exactly the harm the exemption was
written to prevent by keeping it **around** the gate.

Both principles hold at once: the evaluators now let `UsageLimitExceededError`
propagate instead of scoring it. Bounded, and honest — the harness stops rather
than inventing a number.

### 6. The CALLER road is FOLLOWED, never assumed

`CALLER_ROAD_ACCOUNTANTS` names the module that **accounts** for a caller's
spend. That says nothing about whether it **bounds** it, and the first version
of the completeness test exempted the whole road on that assumption: measured,
two of the seven accountants asked no ceiling at all. The test now follows the
edge — a `CALLER` module is bounded if it asks itself, or if the accountant it
names does.

Measured after the change, every one of the 46 sites is bounded by something
nameable: **25 by a turn entrance, 21 by a door they call directly**. None
relies on the accountant fallback today; it exists for the next one that does.

### 7. What the layers below decide, they keep deciding

`spend_blocked` wraps nothing in a rescue of its own, and that is deliberate.
The per-account check fails **open** — a database outage must not lock everyone
out of their assistant. The instance budget fails **closed**, with its own
written argument: a deployment that cannot tell whether it is over its daily
bound must not keep spending. A fail-open swallow in the shared helper would
quietly overturn the second, which is why a test pins it.

### 8. A completeness test over the existing registry

`test_every_spend_site_is_bounded` walks `LLM_SPEND_ROADS` and requires each
module to reach a ceiling — through a declared chokepoint, by asking one
itself, or by running inside a turn whose **entrance** asks (the entrances are
named, and asserted to ask). A new spend site that skips this fails the build,
which is what ADR-270's own registry was built to make possible.

---

## Consequences

- The five unbounded sites are closed, and the shape that produced them cannot
  return silently.
- An instance with a daily budget is now bounded at every door, not only at the
  chat router — including with per-user limits switched off.
- A blocked account keeps a working product: the reminder fires, the dashboard
  renders, the server registers. What the quota bounds is what LIA may
  **compose**, never whether the person is served.
- The refusal reads the same whichever door said no.

---

## What this does NOT solve

- **A ceiling is asked before the call, not during it.** A single very long
  generation can carry the instance past its budget; the next call is refused,
  that one is not. Bounding mid-stream would mean cancelling a partial answer,
  which costs the tokens anyway.
- **The `TURN` road is bounded once per turn, at the entrance.** A turn that
  runs many nodes is checked once. That is deliberate — a check per node would
  be a database round trip per node — and it is why the entrances are named and
  asserted rather than assumed.
- **Nothing here bounds a connector the person pays for themselves.** By the
  rule's own terms; `cost_bearers` is where that line is drawn, and it stays.

---

## Verification

- `tests/unit/infrastructure/llm/test_every_spend_site_is_bounded.py` — all 46
  declared sites, the CALLER road followed edge by edge, the wrapper's
  obligation to thread the owner it is trusted for, and the turn entrances
  asking **unconditionally**: a ceiling nested inside a branch bounds only the
  turns that take it, and matching the NAME alone would have read as guarded
  (the trap this codebase already paid for with `require_superuser`).
- `tests/unit/infrastructure/llm/test_usage_guard_at_every_chokepoint.py` —
  both ceilings at the gate, the flag governing only the account's, and an
  instance pause saying so and saying when it lifts.
- `tests/unit/domains/usage_limits/test_enforcement_shapes.py` — the two shapes
  agree on the verdict, and the three background surfaces really do skip the
  model rather than merely call the gate.
