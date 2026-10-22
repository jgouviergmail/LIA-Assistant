# ADR-360 — Bounded discussion research and accounted abstention

**Status:** Accepted — implemented on the native application contracts; qualification boundaries below.
**Date:** 2026-10-20
**Deciders:** Product owner, with inline engineering analysis.
**Scope:** Context research, prompt limits, actual usage and discretionary admission.

## Context and problem statement

Natural contextual understanding may need older or future evidence. An unrestricted
agent loop would make personal initiative unpredictable in cost, data access and
latency. Limiting emitted messages alone does not limit the expense of decisions,
empty searches, rejected generations, embeddings or context maintenance.

The current platform model-key authority is deployment-level; personal LLM BYOK
must not be assumed. Existing pricing, usage limits, model capability resolution
and provider accounting remain authoritative. This optional feature needs a
strict admission budget without weakening the behavior of interactive work.

## Decision drivers

- Bound the entire run, including physical provider attempts and interpretation.
- Never spend or open a refused source before eligibility and fresh authority.
- Keep all known usage on skip, error, cancellation and discarded output.
- Avoid transactions spanning provider or model waits.
- Treat insufficient context or financial authority as a reason to defer.

## Considered options

| Option | Assessment |
|---|---|
| Daily message cap as a spending cap | Counts successful openings but misses rejected work and research; rejected. |
| Unrestricted ReAct research | Flexible, with excessive execution surface and unpredictable subcalls; rejected. |
| Fixed recent snapshot without enrichment | Predictable but cannot resolve contextual gaps; rejected as the only path. |
| Typed bounded research, reserved discretionary budget and native settlement | Extra admission and recovery logic, with explicit cost and authority; selected. |

## Decision outcome

Use three separately configurable native slots: `discussion_context`,
`discussion_decision` and `discussion_message`. Context interpretation returns
ready evidence, a bounded typed research request, or insufficient context.
Requests name an allowed source, operation and bounded interval or reference;
they cannot grant permission, expand their own budget or write business data.

Adopt the finite staged envelope from the
[approved design](../superpowers/specs/2026-10-19-proactive-discussions-design.md),
including its bounded research waves and context passes. The executable envelopes live in the [LLM contracts](../../apps/api/src/domains/proactive_discussions/llm_contracts.py) and [configuration module](../../apps/api/src/core/config/proactive_discussions.py). Publish
effective limits to the request producer and derive input/output allowances
from the configured slot, verified model capabilities, schema overhead,
reasoning profile and reserved margin. Full procedural rules, style and admitted
portrait count inside the prompt budget. Do not clip a decisive fact into a
misleading proof to fit the envelope.

Reserve a bounded discretionary allowance per owner and per instance before
paid work, under existing platform and provider limits. Context maintenance,
research, embeddings, decisions and wording share that allowance, including
attempts that emit no message. Resolve actual prices and cost bearers through
native services; do not double-charge a personally funded connector or freeze
a deployment's model name in a test. Missing financial limits or unavailable
reservation authority keep this voluntary producer closed.

Settle known actual usage through native tracking on every exit: skip, defer,
empty result, malformed decision, generation refusal, timeout, cancellation,
permission withdrawal and discarded publication. Expired reservations need an
owner-fenced crash recovery path; a completed-spend counter alone is not a
reservation. Provider usage remains the billing authority, with margin for
estimation differences and concurrent calls already in flight.

Charge physical attempts at transport boundaries, before opening a call. Hidden
pages, refresh requests and library retries must be audited, counted and bounded;
a semantic `search` invocation is not necessarily one physical request. Retain
debt even if a response is malformed or a later policy check discards it. Disable
automatic model retries in this envelope. Provider backpressure defers work with
bounded scheduling and jitter, instead of a hidden retry loop.

The [read-budget scope](../../apps/api/src/core/read_budget.py) and
[source gateway](../../apps/api/src/domains/proactive_discussions/source_gateway.py)
provide owner-bound admission, cancellation and a usage sink. Native connector
transport boundaries consume that scope before each admitted physical attempt;
the [spend permit](../../apps/api/src/domains/proactive_discussions/finance_permit.py)
and reservation repository persist known settlement and unresolved liabilities.
An adapter without bounded transport support cannot enter the installed source set.

Use short native read transactions and independent sessions for parallel
sources. Release them before any provider or model wait, as required by
[ADR-304](ADR-304-No-Transaction-Across-A-Network-Call.md). Apply fresh source and
global authority to reused context too; a discussion-policy revision alone does
not prove that a source is still accessible. Revalidate authority, generation,
attention and the current clock before archive/publication.

Use semantic deltas and bounded cache/single-flight coordination to avoid paying
again for unchanged interpretation. A changed opportunity can warrant later
reevaluation even if source text did not change. Invalidation and explicit purge
take precedence over cache reuse. External data stays marked as untrusted, and
admitted sources alone define the context; ambient assistant builders must not
reintroduce a refused profile, address or source implicitly.

## Consequences

Contextual intelligence has an explicit cost envelope and abstention preserves
financial integrity. The trade-off is additional reservation, transport and
recovery machinery, plus possible deferral when the system cannot prove
authority or afford enough context. No numerical euro estimate is trustworthy
without effective slots and current prices. No external graph or new model
provider is required by this decision; JEV remains optional future work.

## Implementation state and verification

The three dedicated native slots, versioned prompts and [full-prompt admission](../../apps/api/src/domains/proactive_discussions/llm_contracts.py) are installed. Effective model capabilities and native reasoning configuration remain authoritative. Complete schema/framing overhead is counted before calls; over-budget material is refused whole. Read-rule compilation shares the context-call allowance and reduces the remaining interpretation/research passes on a cache miss.

[Financial reservations](../../apps/api/src/domains/proactive_discussions/finance_repository.py) bind owner, instance and run budgets before paid work. Missing operator limits close generation. The [spend permit](../../apps/api/src/domains/proactive_discussions/finance_permit.py) retains actual known usage and unknown liabilities across abstention, cancellation and discarded output. Native accounting remains the only billed-usage path; prompts do not embed a deployment's model name or fixed tariff.

Physical provider calls are admitted at native transport boundaries and accumulated across sources. A provider's Retry-After becomes a durable defer rather than an immediate retry. Delivery authority cannot open another provider call. Body-free interpretation/readiness checkpoints avoid redundant context calls without treating stale or insufficient knowledge as fresh evidence.

[Reservation races](../../apps/api/tests/integration/domains/proactive_discussions/test_spend_reservations.py), [native LLM tests](../../apps/api/tests/unit/domains/proactive_discussions/test_discussion_llm.py), [prompt budgets](../../apps/api/tests/unit/domains/proactive_discussions/test_llm_prompt_budget.py), [physical debt](../../apps/api/tests/unit/domains/proactive_discussions/test_source_call_debt.py) and [provider backoff](../../apps/api/tests/unit/domains/proactive_discussions/test_backoff.py) qualify the deterministic envelope. Real-provider latency, paid cost measurements and relational naturalness have not been inferred from stubs. No production or demo deployment is authorized by this record.

## Operator configuration

The native LLM administration metadata exposes `discussion_context`,
`discussion_decision` and `discussion_message` independently. Use the existing
model/reasoning configuration interface for each slot; no provider or model is
hard-coded by this feature.

Before enabling paid generation, configure `DISCUSSION_OWNER_DAILY_BUDGET_USD`,
`DISCUSSION_INSTANCE_DAILY_BUDGET_USD` and `DISCUSSION_RUN_BUDGET_USD` on the target
development instance. Their absence deliberately leaves generation closed and
the settings interface explains that state. `PROACTIVE_DISCUSSIONS_ENABLED` is
the operator ceiling; personal opt-in, source consent, sensitive-topic consent,
activity hours and the native capability switch must also permit the run.
Configuration and validation live in the [settings module](../../apps/api/src/core/config/proactive_discussions.py).

These are dedicated operator spending limits in USD: the first applies to each
owner's daily discussion work, the second to the instance's combined daily work,
and the third to one admitted run. They are separate from the personal daily
opening count and the platform's existing usage limits. Interpretation and
discarded work consume the same allowance even when no discussion is emitted.
No monetary default is silently selected.

The personal settings section is `proactive-discussions`, including context and
history management. Its native deep link is
`/fr/dashboard/settings?section=proactive-discussions`. Reading settings or context
does not start a model call or a provider consultation. A request to rebuild
retains exclusions and runs only when the producer's own admission permits it.
This also applies to the first construction of an empty context. The rebuild
endpoint records a request rather than running a model synchronously. The
context view distinguishes that saved request from execution: missing spending
configuration, a stopped producer, disabled personal discussions or no allowed
source are shown explicitly instead of an unconditional reconstruction message.

An explicit rebuild wakes a retained native context-only background task after
the request commits, both from settings and an approved internal tool. It does
not wait for the periodic scheduler, conversation activity hours, message quotas
or attention cooldowns: those govern unsolicited openings. Personal opt-in,
source/topic permissions, directives, financial admission and owner/epoch/lease
fences still apply. Only context interpretation runs; decision, wording, archive
and notification publication are excluded. A remaining durable refresh request
is retried as context-only work by the periodic recovery path after a worker loss.

## Amendment 2026-10-21 — published bounds, repaired windows, no paid duplicate

- **The research a pass may still buy is published** in the payload's research
  block (waves remaining, history and future bounds) and the prompt states no
  count of its own (ADR-184, ADR-284). A window past the bounds is narrowed
  ([policy](../../apps/api/src/domains/proactive_discussions/policy.py)) rather than raised
  after the context call was paid for.
- **An opening already made stops before its wording is paid**: the fingerprint
  the unique constraint guarantees is checked once the decision is known
  ([runner](../../apps/api/src/infrastructure/proactive/discussion_runner.py)); the constraint
  stays the guarantee against a race.
- **A reservation that refuses to release funds is an abstention**: when the hold no
  longer authorises a call (claim lost, UTC day over, room spent), the run stops as
  `skipped` with its known spend settled, never as `failed`
  ([run setup](../../apps/api/src/infrastructure/proactive/discussion_run_setup.py)).

## Amendment 2026-10-21 b — a reservation sized to the day's room

Production, 2026-10-21: every run reserved its whole ceiling, and with the three
ceilings at the same value a day served one run; the next was refused while €0.0085
of €4.46 had been spent, and the settings said « today's ceiling is reached ».

- **A run reserves its ceiling or what is left of the day, whichever is smaller**,
  and starts only with room for its first call ([repository](../../apps/api/src/domains/proactive_discussions/finance_repository.py)):
  a context call on the person's rules alone, priced on the configured context slot
  and its tariff exactly as the permit will admit it
  ([`first_call_bound`](../../apps/api/src/infrastructure/proactive/discussion_run_setup.py)).
  A model the pricing cache cannot price gives no bound: the run starts and its first
  admission refuses as `tariff_unavailable`, rather than passing for a day without
  room. A day without room settles the run `skipped` with `budget_exhausted` and a
  retry at the end of the UTC day.
- **A finished call commits its bill, never its bound** ([permit](../../apps/api/src/domains/proactive_discussions/finance_permit.py)):
  each admission checks that what the run really committed plus the next call's
  bound fits the reservation, and issues it durably with that commitment; a billed
  request that is not a model call stays held at its bound until its receipt. Before,
  every admitted bound stayed committed, so three context calls needed three bounds.
- **What the settings show is the reservation's own predicate**: the day's room, what
  the next run would reserve and what its first call needs, in euros at the pricing
  cache's rate; a room smaller than that need is stated with both amounts.
- **A run ceiling below one call's bound is named, never read as a day without
  room**: no day can fix it, so the reservation refuses it first
  (`run_ceiling_too_low`) and the settings state both amounts. It happens when a
  slot's output budget is raised without its run ceiling (measured: a context slot
  configured at 100,000 output tokens bounds a first call at about $1.27).
- **Every refusal names its cause** (`tariff_unavailable`, `allowance_exhausted`,
  `phase_exhausted`, `day_over`, `reservation_refused`) and becomes the run's reason
  (ADR-358 amendment b). A run ceiling above a day ceiling, or a ceiling finer than
  the ledger's eight decimals, refuses the boot.

> **Display superseded the same day** by [ADR-359 amendment d](ADR-359-Longitudinal-Discussion-Context-And-User-Control.md):
> the settings no longer show any amount — neither the day's room, nor what a run
> would reserve, nor what its first call needs. They name, in one sentence, the first
> ceiling that stops a run (`BudgetState.reached`) and the day it renews. The
> reservation's predicate described above is unchanged; only booleans leave it
> (`BudgetAvailability`).

## References

- [How a run works, and what its context keeps](../technical/PROACTIVE_DISCUSSIONS.md)
- [Approved budgets and quota analysis](../superpowers/specs/2026-10-19-proactive-discussions-design.md)
- [TDD slots, accounting and runner lots](../superpowers/plans/2026-10-19-proactive-discussions.md)
- [Independent initiative and native delivery](ADR-358-Independent-Proactive-Discussions-And-Native-Delivery.md)
- [Longitudinal context and user control](ADR-359-Longitudinal-Discussion-Context-And-User-Control.md)
