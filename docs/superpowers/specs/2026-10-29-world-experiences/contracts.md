# Verified contracts, reuse and required adaptations

[Master plan](README.md) · [Decisions](decisions.md) · [Handoff](handoff.md)

**Evidence status:** static inspection of the current local working tree on
2026-10-29. “Verified” means the cited implementation or decision was read;
it does not mean a runtime, vendor or production behavior was tested here.
Symbols are preferred over line numbers because this tree contains concurrent
changes. Existing automated tests are anchors for future work, not tests run by
this framing exercise.

## F01 — World is an entry surface with server authority

**Verified.** [ADR-365](../../../architecture/ADR-365-Private-Native-LIA-In-An-Authoritative-Isometric-World.md)
separates browser rendering, native private panels and Redis authority.
[World router](../../../../apps/api/src/domains/world/router.py),
[game commands](../../../../apps/api/src/domains/world/game_commands.py) and
[game rounds](../../../../apps/api/src/domains/world/game_rounds.py) carry
admission/controller, round, revision and deadline contracts.
[Activity entry](../../../../apps/web/src/features/world/activity-entry.ts)
maps destinations to native interfaces; it is not a business executor.
[WorldAccountGuard / WorldPrivateActivity](../../../../apps/web/src/features/world/WorldAccountGuard.tsx)
hide private content and pause nested effects when account identity is unconfirmed.

**Reuse.** Existing catalogue, accessible DOM panels, scene entry, owner guard,
capability availability and server admission. Use game transitions as a concurrency
reference, not as the business model for projects.

**Adapt.** Introduce explicit entries for the selected experiences; keep goals,
transcripts, feedback, ticket details and bills out of shared snapshots and
nameplates. A participant's durable user identity must never be an ephemeral
World actor ID. Room presence alone grants neither membership nor access.

## F02 — “Experience” already has a narrower meaning

**Verified.** [experience.py](../../../../apps/api/src/domains/world/experience.py)
defines versioned, revision-checked route, season and hemisphere presentation
preferences. It is not a learning or focus session service.

**Adapt.** Choose distinct domain names. A new session's owner, purpose, state and
retention must not be bolted into this cosmetic document. Keep authored scene
data independent from session storage.

## F03 — Platform spend and personal-key spend are different contracts

**Verified.**
[cost_bearers.py](../../../../apps/api/src/domains/usage_limits/cost_bearers.py)
classifies cost families. Model calls through platform provider keys are
instance-paid and attributable to the benefiting account; personal connectors
such as Live are user-paid. The personal-key families are excluded from LIA's
platform-spend quota. [ADR-270](../../../architecture/ADR-270-Spend-Roads-And-Register-Authorship.md)
and [ADR-272](../../../architecture/ADR-272-Every-Platform-Paid-Token-Answers-To-Both-Ceilings.md)
explain both sides of that boundary.

[Live closing](../../../../apps/api/src/domains/live/session_end.py) fetches
the personal vendor bill for display after closing, explicitly without persisting
it as platform expenditure. A Live session may nevertheless cause separate
platform-paid synthesis or delegated turns.

**Reuse.** Native token/usage DTOs, pricing and existing ledger. Preserve payer,
credential family and provider-supplied usage provenance.

**Adapt.** Attribute every platform-paid attempt to an authenticated payer and
native run. Distinguish the exercise/session identifier from the run and individual
attempt identifiers. Display personal vendor usage separately, with the native
estimated/exact/unavailable meaning. Do not add it to LIA quota, invent a zero for
unknown usage, or introduce a second personal-spend ledger.

## F04 — Every model caller must declare its accounting road

**Verified.**
[spend_roads.py](../../../../apps/api/src/infrastructure/llm/spend_roads.py)
declares TURN, ACCOUNTED, CALLER and justified INSTANCE routes. Ambient
`TrackingContext` can account calls whose immediate caller does not mention a
tracker. A user's World exercise is not ownerless instance work.

[World translation](../../../../apps/api/src/domains/world/translation.py) provides
a small native example: `get_llm`, explicit usage guard, tracking callback,
bounded input/output and isolated prompt. Its
[register adapter](../../../../apps/api/src/domains/world/translation_register.py)
files a content-free decision under the payer's run.

**Adapt.** Use an ACCOUNTED path for isolated out-of-chat paid work, or an explicitly
named existing accountant; ordinary real work can remain on TURN. Every new model
caller must join the completeness registry. A debrief is a paid act too. Grouping
several calls in one run requires a clear bounded-act definition and finalizer;
a room's lifetime must not become one unbounded billed turn.

## F05 — Quota, request rate, concurrency and duration are separate

**Verified.**
[usage_guard.py](../../../../apps/api/src/infrastructure/llm/usage_guard.py)
resolves ownership and asks `UsageLimitService` for the instance and account
verdicts. [Usage-limit service](../../../../apps/api/src/domains/usage_limits/service.py)
and [enforcement](../../../../apps/api/src/domains/usage_limits/enforcement.py)
own the decision and refusal; disabling per-account limits does not disable the
instance ceiling. The account check falls back from Redis to the database and
allows on an unavailable account check; the configured instance-budget check
returns a blocking unavailable verdict when its spend cannot be read
([instance_budget.py](../../../../apps/api/src/domains/usage_limits/instance_budget.py)).
Preserve these distinct semantics rather than adding a caller-specific policy.

[RedisRateLimiter](../../../../apps/api/src/infrastructure/rate_limiting/redis_limiter.py)
provides distributed atomic sliding-window checks; the native
[create_user_rate_limiter](../../../../apps/api/src/domains/auth/dependencies.py)
is a reusable route dependency with its own fail-open contract. Reuse those
primitives and explicitly select the paid operation's failure behavior; an
admission throttle is not a guaranteed spending fence.

World socket admission and command limits do not authorize or budget a paid
model request. Live's session lease is a further, distinct concurrency control.

**Adapt.** Each new paid operation must have a native pre-dispatch quota check,
rate policy, bounded input/output/work and idempotency. A long-lived rehearsal
cannot treat its admission check as permission for unlimited later calls.
Re-check current permissions and spend eligibility at new paid boundaries.
Publish effective bounds from server configuration.

**Limit of evidence.** The existing checks do not establish an atomic reservation
of all future spend across simultaneous runs. Never promise an exact monetary
ceiling on that basis. [D09](decisions.md#d09--limits-and-concurrent-spend) decides
whether a shared reservation extension is required.

## F06 — Decisions, effects and consultations answer different questions

**Verified.**
[decision_filers.py](../../../../apps/api/src/domains/agents/effects/decision_filers.py)
names who files each accounted act. The native `run_id` joins decisions,
usage, effects and consultations.
[consultation_surfaces.py](../../../../apps/api/src/domains/shared/consultation_surfaces.py)
declares direct personal-data reads that do not pass through a tool;
[consultation_sink.py](../../../../apps/api/src/domains/shared/consultation_sink.py)
is the shared recording seam.
[user_data_readers.py](../../../../apps/api/src/domains/agents/effects/user_data_readers.py)
and [direct_client_callers.py](../../../../apps/api/src/domains/agents/effects/direct_client_callers.py)
enumerate direct-read accounting obligations outside tool execution.

[ADR-263](../../../architecture/ADR-263-Execution-Authority-Chain-And-Effect-Register.md)
explicitly excludes arbitrary database writes from the capability effect register.

**Adapt.** Accounted coaching, acting and debriefs get native decision records with
real outcome; external actions get effects; reading a selected document or ticket
must use the appropriate existing consultation path. Do not fabricate a source
consultation for reading an already captured scenario or a timer tick. Declare
direct readers and client callers where the existing guards require them.
World is a surface, not a new authorship category: use the actual user/scheduled
source semantics. Public progress never exposes another account's register.

## F07 — Real actions retain server-enforced authority and HITL

**Verified.** ADR-263 defines `mutation_policy`, gates registered native tools and
draft executors, and gates MCP adapters at their actual execution door. Effects
are claimed before execution and settled from explicit outcomes. A missing error
is not delivery proof. A HITL flag and a mutation policy are different contracts.

**Adapt.** Roleplay has no real action tools, ordinary chat delegation or automatic
post-session relay. Saying “send the message” while acting remains fictional.
An explicit “use this in real life” action creates an editable native draft and
returns to the existing approval/execution flow. It neither confirms nor executes
the draft. Server permissions must survive direct API calls and stale UI state.

A deterministic session edit still requires ownership and concurrency validation;
it does not need a fabricated model decision or an extra confirmation dialog
unless its actual effect requires one.

## F08 — Live transports are reusable; ordinary Live semantics are not rehearsal

**Verified.**
[LiveSessionStartRequest](../../../../apps/api/src/domains/live/schemas.py)
currently carries the ordinary `delegated | direct` selection and audio
transport; it has no first-class training scenario contract.
[MandateInputs](../../../../apps/api/src/domains/live/mandate.py)
renders the ordinary LIA instruction with personal context.
[VoiceSession](../../../../apps/api/src/domains/voice_sessions/session.py)
and [ADR-301](../../../architecture/ADR-301-Voice-Sessions-One-Policy-Per-Mode.md)
share policy between browser and telephone carriers.

[session_store.py](../../../../apps/api/src/domains/live/session_store.py) uses
a per-account Redis claim, owner token and bounded record lifetime.
[LiveSessionController](../../../../apps/web/src/lib/live/session-controller.ts)
owns the browser session lifecycle.

**Reuse.** Provider adapters, personal credential handling, transport lifecycle,
audio arbitration, stop controls and the existing per-account exclusivity seam.

**Adapt.** Add a server-owned training purpose and explicitly constrained context,
allowed operations, transcript destination and closing policy. Whether this is
represented by a purpose field or another typed policy must be decided after
checking all carriers and serializers. It must not repurpose “direct” to mean
“simulation,” nor change ordinary telephone/browser behavior accidentally.
Training shares the existing Live exclusivity boundary; a new lock cannot
silently permit simultaneous ordinary and training voice sessions.

Written/Live are experience modalities; delegated/direct are existing voice
execution semantics. These are different axes.

## F09 — Closing, standby and learning are a critical isolation boundary

**Verified.**
[session_end.py](../../../../apps/api/src/domains/live/session_end.py) calls
[close_voice_session](../../../../apps/api/src/infrastructure/scheduler/voice_session_closing.py).
The delegated closing archives voice-only exchanges and schedules learning;
`_learn` checks the memory flag for memory extraction but also invokes interest
extraction. The direct closing synthesizes and relays speech as a real user turn.
[voice_relay.py](../../../../apps/api/src/infrastructure/scheduler/voice_relay.py)
and [voice_delegation.py](../../../../apps/api/src/infrastructure/scheduler/voice_delegation.py)
are additional paths to inspect when adapting this policy.
[ADR-329](../../../architecture/ADR-329-Live-Standby-And-Multilingual-Wake-Word.md)
adds standby/resume lifetimes.

**Adapt.** Training must exclude fictional speech from ordinary conversation
archive, relay, memory, interests, journal/profile/open-loop learning and source
inference. Verify the entire path, including standby, cancellation, timeout,
delegation and crash recovery. A prompt saying “this is fictional,” a different
chat label, or `memory_enabled=False` alone is insufficient.
Saved pedagogical progress is explicit feature data, not automatic personal memory.

**Unverified.** No provider session was started in this assessment. Prompt
constraints, transcript fidelity, interruption and resumability require actual
provider/device evidence; provider features are not assumed interchangeable.

## F10 — Workboard is the real-work authority, not a project ACL system

**Verified.**
[ADR-276](../../../architecture/ADR-276-Workboard.md),
[models](../../../../apps/api/src/domains/workboard/models.py),
[board_queries.visible_predicate](../../../../apps/api/src/domains/workboard/board_queries.py)
and [repository](../../../../apps/api/src/domains/workboard/repository.py)
define native tickets, one-level child tickets, lifecycle and ownership/assignment.
Visibility is owner OR assignee, not “member of the same project.”
[workboard_runner.py](../../../../apps/api/src/infrastructure/scheduler/workboard_runner.py)
is the existing execution integration.

**Reuse.** Ticket IDs, statuses, assignments, result evidence, native run lifecycle,
approval and retry behavior. Use existing UI entries and native create/update
commands.

**Adapt.** A camp supplies an outcome and references, not copied tickets or a
parallel completion state. Do not model arbitrary nested milestones as unsupported
nested Workboard tickets. Group membership must not widen the ticket predicate.
Do not delegate another person's assistant through a project role. Closing a focus
interval or a parent project never proves a ticket's work complete.

## F11 — Models, prompts and capabilities have central authorities

**Verified.**
[LLM_TYPES_REGISTRY / LLM_DEFAULTS](../../../../apps/api/src/domains/llm_config/constants.py),
[llm_config_helper](../../../../apps/api/src/core/llm_config_helper.py) and
[factory](../../../../apps/api/src/infrastructure/llm/factory.py) resolve configured
slots. [ADR-244](../../../architecture/ADR-244-LLM-Catalogue-Truth.md),
[output_cap.py](../../../../apps/api/src/infrastructure/llm/output_cap.py) and
[ADR-245](../../../architecture/ADR-245-Reasoning-Unification.md) govern capability
provenance, output bounds and provider-independent reasoning intent.
[core prompt_store](../../../../apps/api/src/core/prompt_store.py) reads versioned
prompt files without creating a domain-to-agents import cycle.

[PlatformCapability / CAPABILITY_SPECS](../../../../apps/api/src/domains/feature_switches/registry.py)
and [capabilities service](../../../../apps/api/src/domains/capabilities/service.py)
implement [ADR-280](../../../architecture/ADR-280-Complete-Capability-Control.md):
operator switches stay inside deployment ceilings; disabling a capability must
not remove access to legitimate archives.

**Adapt.** Declare only justified new role/feedback slots with supported
capabilities, spend roads and prompts. Share training configuration across theatre
and language where requirements match; do not bind a provider/model to a building.
Read effective configuration, not a default assumed to be deployed.
Publish feature and modality availability from the same server policy used to
enforce them. Live personal credentials remain distinct from platform LLM slots.

## F12 — Persistence, deletion and concurrency must be explicit

**Verified.**
[Redis key families](../../../../apps/api/src/infrastructure/cache/key_families.py)
and [ADR-260](../../../architecture/ADR-260-Redis-Key-Families-Scope-And-Reset-Purge.md)
separate reset, cache, learning and runtime scopes.
[World lifecycle](../../../../apps/api/src/domains/world/lifecycle.py) selectively
removes one account from mixed-account state.
[Database registry](../../../../apps/api/src/infrastructure/database/registry.py)
is the model registration point.
[CLAUDE.md](../../../../CLAUDE.md) requires declared serializable graph state,
correct turn resets, owned async lifetimes and separate database sessions for
parallel operations.

**Adapt.** State a source of truth, retention, export and erasure behavior for
every new resource. Durable records must not depend on a socket or background
task living forever. Use transactional claims/revisions and native leases as
appropriate; recover by reading authoritative state, not replaying a paid act.
Account deletion must cancel/fence late writes and preserve other people's data.
Conversation reset must not accidentally delete a project or retained training
record. Do not add a second application-wide concurrency manager.

## F13 — Uncertain paid attempts do not automatically replay

**Verified.**
[Provider retry policy](../../../../apps/api/src/infrastructure/llm/providers/retry_policy.py)
and [client retry decisions](../../../../apps/api/src/infrastructure/llm/client_retries.py)
in the inspected local tree prohibit automatic re-generation after a possibly
sent timeout/lost connection and after streaming begins. They permit bounded
known-safe retry cases at the owning layer. World translation is stricter, with
one transport attempt. These current local changes are not proof of deployment.

**Adapt.** Separate “re-read result” from “start another paid attempt.”
A user-visible retry creates a new bounded attempt only after explaining an
uncertain earlier result. Never perform a Live-to-written paid replay automatically.
An uncertain external side effect must likewise retain the native execution
policy; do not infer failure and repeat it.

## Reuse map by workstream

| Component | Focus | Theatre | Language | Base camps |
|---|---|---|---|---|
| Native World entries and private panels | Reuse | Reuse | Reuse | Reuse |
| Session identity, revision, termination conventions | First concrete use | Reuse conventions, distinct training state | Reuse qualified training state | Links only; project has longer lifetime |
| Platform accounting and register seams | Optional coaching | Actor and feedback | Actor, corrections and feedback | Planning/review calls and native ticket runs |
| Native Live | Not required for proposed first slice | Adapt isolation, then qualify | Reuse training policy; qualify pedagogy | Ordinary explicit real-work Live remains native |
| Scenario and feedback contract | Not needed | First implementation | Extend content and rubric | Optional rehearsal references |
| Workboard | Optional selected ticket | Optional explicit draft export | Optional learning-goal reference | Primary authority for work |
| Memory/learning | Explicit user-selected data only | Fiction excluded | Explicit pedagogical data | Native real-work policy, permission-scoped sources |

## Existing test anchors to extend

- [Accounting completeness](../../../../apps/api/tests/unit/infrastructure/llm/test_llm_spend_road_completeness.py).
- [Cost-bearer declaration](../../../../apps/api/tests/unit/domains/usage_limits/test_cost_bearer_declaration.py),
  [usage-guard coverage](../../../../apps/api/tests/unit/infrastructure/llm/test_usage_guard_at_every_chokepoint.py),
  [decision filers](../../../../apps/api/tests/unit/domains/agents/effects/test_decision_filers_guard.py)
  and [consultation surfaces](../../../../apps/api/tests/unit/domains/shared/test_consultation_surfaces.py).
- [World translation](../../../../apps/api/tests/unit/domains/world/test_translation.py)
  and [public accounting](../../../../apps/api/tests/unit/domains/world/test_public_accounting.py).
- [Workboard real-database lifecycle](../../../../apps/api/tests/integration/domains/workboard/test_run_lifecycle_db.py)
  and [peer lifecycle](../../../../apps/api/tests/integration/domains/workboard/test_peer_lifecycle_db.py).
- [Native World isolation](../../../../apps/web/e2e/native/world-proof-isolation.spec.ts)
  and [concurrent arcade](../../../../apps/web/e2e/native/world-arcade-concurrent.spec.ts).
- Live browser smoke fixtures for
  [Gemini/default](../../../../apps/web/e2e/smoke/chat-live-session.spec.ts),
  [OpenAI](../../../../apps/web/e2e/smoke/chat-live-session-openai.spec.ts) and
  [ElevenLabs](../../../../apps/web/e2e/smoke/chat-live-session-elevenlabs.spec.ts).

These anchors do not cover the new features yet. New tests must exercise real
observable contracts, not merely reproduce their implementation.
