# LIA application tools implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task. The user explicitly requires inline execution without subagents. Steps use checkboxes for tracking. Implementation is authorized and in progress on `codex/lia-application-tools`; incomplete lots must not be described as delivered.

**Goal:** Give LIA typed, permission-correct access to the application's information and confirmed business operations, including controlled interactions on the originating device.

**Scope revision — 2026-10-08:** The user explicitly excludes account password, MFA, passkey, recovery and telephone-verification workflows. Do not implement tools or new secure forms for those purposes. Mark the corresponding inventory affordances as excluded by user decision, rather than unfinished coverage. Existing authentication/HITL safeguards required by other in-scope operations remain mandatory. Complete the non-administrator scope first, then pause before administrator implementation.

**Architecture:** Native tools and an explicit operation registry compose existing domain commands/queries. Native application-action drafts reuse current HITL and effect registers. An addressed device protocol delegates local state and secure interactions to existing hooks/stores/native adapters.

**Tech stack:** Current Python/FastAPI/Pydantic/SQLAlchemy/PostgreSQL/Redis/LangGraph and Next.js/React/TypeScript stacks; no new dependency assumed.

**Spec:** [Functional and technical design](../specs/2026-10-06-lia-application-tools-design.md).

**Evidence:** [Full declared-surface inventory](../specs/2026-10-06-lia-application-interface-inventory.md) and [route signatures/source fingerprints](../specs/2026-10-06-lia-application-interface-inventory.json).

**Execution reviews:** [Inline cold-review record](2026-10-06-lia-application-tools-reviews.md).

## Global constraints

Execution order updated by the user: finish the non-administrative tools as one
delivery lot, then pause. Administrative tools form a separate second lot and
must not start before that pause. The platform-capability switch already in the
implementation continues to gate user tools throughout.

- All execution stays inline; preserve concurrent source, test, index and documentation edits. Root CLAUDE.md and apps/web/CLAUDE.md apply; AGENTS.md is generated.
- Reads require no HITL. Reviewed reversible personalization executes directly through the original domain writer and effect ledger. Sensitive consent, creation, resource modification, deletion, external delivery, microphone capture and hard-to-reverse actions retain exact HITL. Mixed patches containing a sensitive field retain HITL. New fields require explicit risk review; administrative reads remain superuser-only.
- Actor identity is injected. Admin role, active account, ownership, capability and any session/step-up requirement are checked at read/preparation and execution/result access.
- No arbitrary HTTP/path/SQL/JavaScript/localStorage/DOM dispatcher; no credentials in model context, draft/checkpoint or chat. Secure interaction remains on the device.
- UI and tools share domain rules and schemas; do not call FastAPI handlers as regular functions or duplicate their writes.
- Current request schemas own field/range/enum vocabulary. Tool patches refuse unknown fields and distinguish omitted/null/reset/clear. Repairable values are shown repaired before HITL.
- All new input/output contracts are typed; Any/casts/ignored diagnostics are not a substitute for modeling the new boundary.
- A turn's frozen runtime is not mutated or treated as current authorization. Persistent approval carries identity/digests, not a cached superuser flag.
- Claims, commits, post-commit work and external completion are distinct. A failure or unknown outcome never renders as success; no automatic non-idempotent replay.
- All platform spend is traced/displayed/attributed under both ceilings; personal-key spend follows cost_bearers. No paid provider probe or production mutation is part of this plan's local tests.
- Future tunable limits use settings/constants and matching schema/manifest publication; relevant env example/demo surfaces follow root rules when settings are introduced.
- File size/complexity/cycles/types/coverage/a11y/hooks/metrics ratchets are shrink-only. Every lot includes its registry and six-language vocabulary wiring.
- Business code starts after this analysis is reviewed. Do not perform Git delivery or deployment without the user's request.

## Review focus

1. **Consent changed inside its own turn:** disabling memory, deleting journals or clearing history must not be undone by finalization or a background task already scheduled. Pinned by T17 in lots 3/5.
2. **Multiple authorities:** `allowed_roles`, current user, target user, resource owner and authenticated device/session must not be confused. Pinned by T02/T03/T20/T23/T38 in lots 1/4/7/8.
3. **An effect followed by a lost acknowledgement:** a saved state or a started session must not be repeated after reconnect or falsely called complete. Pinned by T07/T39/T40/T47 in lots 2/8.
4. **A seemingly shared service has multiple commits/recorders:** reuse must preserve existing propagation and avoid double audit rows, without promising transactionality the service does not have. Pinned by T10/T34/T50 in lots 2/3/6/7.
5. **Tool reachability and schema cost:** adding application tools must not lose domains under cap/panic/frequent mode or flood every unrelated turn. Pinned by T51/T52/T53/T54 in lots 1/10.

The numbered T scenarios refer to the [director test catalogue](../specs/2026-10-06-lia-application-tools-design.md#explicit-scenario-catalogue).

## Shared interfaces and responsibility map

The names in this section are proposed contracts, not names falsely attributed to existing code. Implement them once in the indicated owner; downstream lots consume them. Domain-specific payload types reference the existing request model for that family, with a strict tool boundary.

| Contract | Owner | Required content / use |
|---|---|---|
| `ApplicationOperationSpec` | `agents/application/operation_spec.py` | Stable id/name, finite UI origins, typed request/response classes, authorization, query/command, availability, modes, cost owner, context behavior and adapter. Registry-generated manifests use these same values. |
| `ApplicationActor` | `agents/application/authorization.py` | UUID identity and fresh account/permission facts. Sensitive session proof is injected by host, opaque, operation-bound and never model-visible. |
| `authorize_application_operation(actor_id, operation, target)` | Same | Return authorized actor/target or typed denial; load current authority, never read a model role. |
| `ApplicationReadProjection` | `agents/application/schemas.py` | Saved/effective values, availability/reason, account/device scope, observed-at, resource ids, applied filters and exact paging metadata. No secret fields. |
| `prepare_application_action(operation, intent, actor, origin)` | `agents/application/preparation.py` | Validate concrete typed intent, resolve target, read affected snapshot, compute before/after and expected digest, produce pending native draft; no effect. |
| `ApplicationActionDraftContent` | `agents/application/draft_models.py` | Operation/catalogue/schema version, actor/target ids, expected digest, canonical intent, ordered batch membership if present, device binding, visible consequences. Round-trip through checkpoint exactly. |
| `execute_application_action_draft(content, user_id, deps)` | `agents/application/draft_execution.py` | Existing executor signature; normalize validated content, reauthorize/recheck current state/quota, claim and invoke the adapter, return explicit outcome. No arbitrary function replay. |
| `ApplicationExecutionOutcome` | `agents/application/outcomes.py` | Actual success plus separate committed/waiting/unavailable/conflict/error facts, changed projections and command/job refs. Shared draft engine adapts explicit success; waiting is not completed success. |
| `ApplicationCommand` | `agents/application/command_models.py` | Durable finite execution/handoff record with actor/draft/effect/client identities, digest/version, claim/expiry/phase, encrypted non-secret intent and bounded result. Unique identity and owner-conditioned writes. |
| `application_state_changed` | Existing agents SSE/client type registries | Affected query/resource ids and authoritative revision; no credential or full record dump. Reducer pure; side effects in dedicated handler/hook. |
| `ApplicationDeviceSnapshot` / `ApplicationDeviceCommand` / `ApplicationDeviceAck` | `agents/application/device_schemas.py`, client mirror | Finite typed preferences/commands/results; originating client binding, schema version, observed-at/expiry, command id and actual completion facts. |
| `useApplicationStateSync` | `apps/web/src/hooks/` | Targeted user/query/context invalidation; preserve focused input and current filters. |
| `useApplicationDeviceCommands` | Same | Addressed claim, dispatch through existing hook/store/native owner, ACK/status/expiry; cleanup/abort and no archive replay. |

Keep the registry's adapters in small per-family files under `agents/application/operations/`. Query and command business logic belongs to each existing domain, not to this registry. The registry aggregates declarations; it does not become a second data store. Use the existing program-taxonomy/manifest aggregators instead of expanding frozen main modules. A new settings context belongs in `agents/application/context.py` and must wire every registry/context reader.

## Lot 0 — Characterize the seams before changing them

**Deliverable:** Reproducible source-backed tests for the mandatory-confirmation paths and the two observed source gaps, plus the final per-affordance operation mapping.

**Read/characterize:** `effects/runtime.py`, `effects/gate.py`, `services/draft_executor.py`, `services/draft_executor_types.py`, `services/draft_executor_registry.py`, `drafts/models.py`, `drafts/display.py`, `nodes/post_response_extractions.py`, `context/runtime_context.py`, current pending-HITL changes and their tests, current UI section registry/hooks/routers from the inventory.

**Create tests:**

- `apps/api/tests/unit/domains/agents/services/test_draft_executor_explicit_outcome.py`.
- `apps/api/tests/unit/domains/agents/application/test_existing_mutation_contracts.py`.
- `apps/api/tests/unit/domains/agents/nodes/test_management_turn_extraction_consent.py`.

**Interfaces:** Produce the characteristic behavior and approved operation classification consumed by lot 1. Do not make a schema from a route name or import list alone.

- [ ] Read the final local HITL diff and snapshot relevant source hashes; preserve unrelated changes and distinguish future changes by other sessions.
- [ ] Walk every section component and its imported hooks/child controls, then authenticated page/card/context-menu affordances. Map each business operation to handler, request model, called service, authorization, persistence, invalidation, cost owner and existing tool. Mark telemetry/chunks/callbacks as excluded with reason.
- [ ] Write a red T06 test invoking the actual confirmed-draft dispatcher with an executor returning an explicit failure; assert response outcome, metric and ledger agree. Counter-check that the gate does not already raise/normalize this case.
- [ ] Write red T17 tests on the actual finalization/extraction boundary: a confirmed consent-off/change is committed after run-context creation, and no prohibited extraction write follows. Include already-scheduled task completion and deletion repopulation.
- [ ] Write characterization of ticket/routine/reminder current policy and generic TOOL_CALL native-runtime limitation; show the necessary change without weakening historic assertions.
- [ ] Characterize T58 account registration/verification/demo/native activation/admin activation/deactivation/deletion writers and audit evidence. Verify that inactive alone cannot identify pending initial approval; define the monotonic activation-history projection and reliable-versus-unknown legacy backfill before the administrative slice.
- [ ] Run the new files using `.venv/Scripts/python.exe -m pytest` from `apps/api`, and the existing draft/gate/TCM/pending lifecycle suites. Record expected new failures separately from unrelated baseline failures.
- [ ] Review every mapped operation inline. Complete source-body/schema characterization before its implementation lot; no automatically exposed unknown operation.

**Exit:** The failure oracle is demonstrated and the UI-to-operation inventory has no silently missing management affordance. This is required analysis work inside development, not permission to claim deployed parity from the static appendix alone.

## Lot 1 — Typed operation catalogue and hard authorization

**Deliverable:** Application query/command definitions registered in the existing system, with no unconfirmed effects yet.

**Create:** `agents/application/operation_spec.py`, `schemas.py`, `authorization.py`, `registry.py`, `catalogue_registration.py`, `context.py`, focused `operations/profile.py` and `operations/admin.py` declarations; `tools/application_read_tools.py`.

**Modify:** `core/context.py`, `context/runtime_context.py`/builder only for typed host facts required by this feature, `registry/program_domain_configs.py`, `program_manifests.py`, `tools/tool_registry.py`, `infrastructure/startup/agents.py`, context/type/treatment/display vocabularies as required by the new family. Do not create a new model slot.

**Tests:** `tests/unit/domains/agents/application/test_operation_registry.py`, `test_authorization.py`, `test_read_projection.py`, `test_manifest_parity.py`, `test_per_request_availability.py`; extend `tools/test_tool_registry_smoke.py` fixtures and taxonomy/context completeness tests.

**Interfaces:** Produces registry lookup, authorized typed query projection and manifest generation for lots 2–8. Existing request manifests remain request-scoped.

- [ ] Write red T01/T02/T03/T12/T18/T19/T20/T51/T56 cases: missing policy/schema/cost road/context wiring, duplicate operation id, ordinary/admin reads, inactive/missing actor, unrelated-user cache, untrusted text and planted credentials.
- [ ] Derive personal/admin settings schemas from actual allowed fields; refuse extras at the tool boundary and share field bounds/enums with manifest generation.
- [ ] Implement explicit fresh actor/target authorization. Filter application administration before selection/ranking/panic/binding, and enforce again in the query adapter. Do not trust `allowed_roles` or a state boolean as authority.
- [ ] Preserve operation/sensitivity provenance on application projections; reauthorize pending/status/result reads and filter restricted application context before subsequent prompt assembly. T02 covers an admin downgraded after preview, archived command ids and later-turn context, without rewriting unrelated history.
- [ ] Add `setting`/`administration` through the program aggregator; reuse existing resource domains and serves_domains rather than invent plural taxonomy tables.
- [ ] Register read tools with current metrics/rate-limit preset and explicit read policy. Return no defaults on failed capability/device lookups.
- [ ] Add boot assertions for spec↔tool↔manifest↔schema↔context parity. Unknown/sensitive/internal route mapping fails loudly.
- [ ] Run the application unit files, registry smoke, applicable context/taxonomy guards and `task test:backend:agents`. Inspect real offered schemas, including inherited descriptions and mode/role filtering.

**Exit:** Authorized queries work end to end through deterministic model fixtures; all mutation adapters remain inaccessible without the next lots' draft contract.

## Lot 2 — Native HITL, explicit outcomes, command identity and concurrency

**Deliverable:** A confirmed state-setting slice, with reliable result semantics and no approval/replay bypass.

**Create:** `agents/application/draft_models.py`, `preparation.py`, `draft_execution.py`, `outcomes.py`, `command_models.py`, `command_repository.py`, `command_service.py`, `tools/application_action_tools.py`; migration for the new command record using the then-current single Alembic head.

**Modify:** `drafts/models.py`, `display.py`, `preview_renderer.py`, `summary_renderer.py`, `result_renderer.py`/card specs where required, `services/draft_executor.py`, `draft_executor_types.py`/registry, `services/hitl/action_taxonomy.py`, `core/i18n_drafts.py` and all associated vocabulary/catalogue entries; database model registry, effect gate's explicit per-draft requirement, finite error/metric consumers. Preserve concurrent local HITL work.

**Tests:** `application/test_native_draft.py`, `test_command_lifecycle.py`, `test_strict_claim_policy.py`, `test_explicit_outcomes.py`; `tests/integration/domains/agents/application/test_commands_db.py`, `test_concurrency.py`, `test_hitl_resume.py`; extend draft display/summary/round-trip and pending lifecycle suites.

**Interfaces:** Consumes lot 1 operation registry. Produces preparation/execution/command result APIs, expected-state CAS and changed-projection descriptor consumed by all write slices/device bridge.

- [ ] Write red T04–T12/T26/T45–T49/T54/T56 tests. Confirm/decline/edit/expiry/tamper/schema upgrade, raw coroutine/ainvoke, double-worker confirmation, collection race, no claim/Redis outage, CancelledError and explicit negative result must have observable assertions.
- [ ] Correct the shared confirmed-draft result adaptation using the existing explicit-success predicate; test legacy result shapes and genuine success without changing unrelated result/status vocabularies.
- [ ] Introduce native APPLICATION_ACTION and all display/summary/executor/action mappings. The native tool builds a draft; do not add a duplicate pre-call HITL.
- [ ] Reuse effect claims/approval_ref/draft_digest and enforce a strict authority/durable-claim prerequisite for this family. Do not incidentally change every legacy draft's best-effort branch.
- [ ] Implement durable command identity linked to the existing draft/effect, encrypted bounded intent, expiry and actor-owned outcome access. Unique constraints and owner/fencing settlement are tested against real PostgreSQL.
- [ ] Extract the first domain write boundary so expected fields are compared under the same short transaction as the actual write. Do not hold its lock during model/provider/human work. Persist command identity with create/job side effects where needed.
- [ ] Emit an explicit no-op when desired state already holds; never replay an inverse toggle. Separate committed state and resumable post-commit invalidation from external/waiting completion.
- [ ] Implement batch membership/digest and ordered per-member outcomes; no hidden members, dependent continuation after failure or false rollback claim.
- [ ] Run the new unit/integration files on disposable PostgreSQL/Redis, existing effects/draft/pending suites, migration replay and backend agents. Verify no duplicate ledger row.

**Exit:** One approved command has one verified outcome; cancelled/unapproved/stale commands have no effect. Crash/replay and negative-result behavior are pinned before broad adapters exist.

## Lot 3 — Profile, display, preferences and turn consent

**Deliverable:** Personalization and settings with immediate coherent account/UI/context effects.

**Sections:** language, timezone, location server preferences, theme, font, font-size, display-mode, usage-preferences, briefing-grid, chat-shortcuts, my-shortcuts, own token/debug/TTS/memory opt-ins; device-only portions remain unavailable until lot 8.

**Read/modify:** `users/schemas.py`, `users/service.py`, `users/router.py`, `users/preferences_cache.py`, `auth/router.py` and schemas, `chat/router.py`/shortcuts, `briefing/router.py`/preferences, `shared/settings_shortcuts.py`, scheduler timezone propagation, `nodes/post_response_extractions.py`; touched UI hooks from the source inventory.

**Create focused owners:** `domains/auth/preference_commands.py` for extracted auth preference rules; agent operation files `operations/profile.py`, `display.py`, `shortcuts.py`; client `hooks/useApplicationStateSync.ts` and typed change-event handler.

**Tests:** `application/test_profile_operations.py`, `test_preference_operations.py`, `test_shortcuts_operations.py`, integration `test_ui_tool_preference_parity.py`; frontend `useApplicationStateSync.test.ts`, real theme/grid/shortcut integration tests.

- [ ] Pin T01/T10–T19/T22/T44: omitted/null, strict font-size, actual OLED vocabulary, stale lists, reserved static shortcut ids, locale normalization, timezone/DST propagation and paid geocoding when used.
- [ ] Pin T57 end to end: read saved/current-device size; relative increase uses the UI's actual one-step increment, resolves a concrete target before HITL, respects limits without silent clamping, re-previews conflicts and synchronizes the existing font-context owner after commit.
- [ ] Extract handler-local commands while preserving current API response/error behavior and all side effects. Use UserService for profile/personality/zone; do not assign User columns in a parallel tool implementation.
- [ ] Normalize static shortcut collision authority to one declaration usable by the server/tool and derive/check the frontend registry against it. A frontend-only refusal cannot protect a server tool.
- [ ] Add read+draft action tools/manifest/schema/context per aggregate; version/list CAS is shared with direct UI writes.
- [ ] Define and implement current-turn opt-out/destructive-management finalization gates. Background writes reread consent before committing; declare any checkpointed overlay/reset guard and round-trip/reset it.
- [ ] Add targeted refresh descriptor/handler/hook. Refresh User/current queries without dropping input/focus/filters, and synchronize saved theme/font/locale through current owners.
- [ ] Run targeted API/front tests, backend agents, frontend lint/coverage and extraction/context suites; no Docker/runtime claim from static tests alone.

**Exit:** The same setting saved from UI or tool has the same durable value, schedule/cache effect and next-turn behavior; failures show the correct partial/local outcome.

## Lot 4 — Communication, connectors, security and automation

**Deliverable:** Confirmed server-side communication/account management, with secure-flow handoffs specified for lot 8.

**Sections:** notifications, channels, existing non-secret security status/devices/export, voice-mode, live-mode non-secret preferences, connectors/shared MCP personal opt-out, telephony identity/history without telephone verification, heartbeat, routines/reminders. New password/MFA/passkey/recovery workflows are excluded.

**Domain owners:** notification/channel/auth session-step-up/account-export routers/services; connector service/preferences/provider resolver/bulk OAuth; live connector/preference services; heartbeat schemas/sanitizers; telephony identity/settings; scheduled-actions/reminders. Existing `automation_tools.py`, `reminder_tools.py`, corresponding manifests and native executors are reused and aligned.

**Create agent operation files:** `operations/communication.py`, `connectors.py`, `security.py`, `automation.py`; domain command extractions only where handler-local rules require them.

**Tests:** per-operation unit contract modules; integration `test_communication_parity.py`, `test_session_bound_actions.py`, `test_automation_confirmation.py`, `test_connector_parity.py`; typed secure-flow descriptor frontend tests.

- [ ] Pin T20–T24/T27/T33/T43/T53/T54 with owned/unowned connectors/bindings/sessions, admin-shared servers and personal/global keys.
- [ ] Split non-secret configuration from credential/auth actions. No cookies, keys, QR/OTP material, recovery codes, live credentials or raw push token enter model/draft projections.
- [ ] Implement host-injected, operation-bound session/step-up proof for sensitive flows; “confirmed” without that proof remains awaiting secure interaction. Current session id comes from the transport, never the model.
- [ ] Extract and reuse settings/source sanitizers and existing feature/state checks. Publish saved/effective source availability and refusal reasons.
- [ ] Convert all in-scope reversible automation/reminder entry points to native confirmation without alternate unconfirmed entry or unattended stand-in. Keep autonomous execution's existing read/technical actions intact.
- [ ] Use desired enabled state instead of blind toggle and preserve provider exclusivity/default-container preference rules.
- [ ] Verify platform-accounting ownership and current budgets for provider/test/verification work, with bounded safe retries only.
- [ ] Run targeted unit/integration, existing OAuth/grant/session/automation/HITL and agent suites. Sensitive browser/device completions stay explicitly waiting until lot 8's handler exists.

**Exit:** Server operations cannot bypass secure session/credential participation or current rights, and routine mutation always carries genuine confirmation.

## Lot 5 — Learning, health, relations, peers and workboard

**Deliverable:** Full explicit management of displayed personal knowledge and collaborative work, with current consent and ownership.

**Sections/screens:** personality, psyche, memories, interests, open-loops, habits, journals/portrait, health-metrics, peer-connections, relations and workboard.

**Owners:** Existing domain routers/schemas/services/store/repositories, canonical name folding and peer grants; `workboard_tools.py`, memory/journal/activity/read tools and manifests; post-response/background extraction owners.

**Create:** small agent operation files `learning.py`, `health.py`, `relations.py`, `peer_management.py`. Extend existing workboard native tools rather than register competing alternatives.

**Tests:** `test_learning_management.py`, `test_health_management.py`, `test_peer_management.py`, `test_workboard_confirmation.py`; real DB/store integration parity/deletion/concurrency modules; frontend actual section/card state tests.

- [ ] Pin T17–T19/T25–T28/T33/T48–T50: full CRUD/status/pin/feedback/provenance/export, source opt-in and current resource holder/owner distinction.
- [ ] Build complete typed read projections with exact aggregates and paging; preserve name folding/provenance and separate user's memories from LIA's journal.
- [ ] Reuse services/store interfaces and new-dict JSONB writes. Destructive “all” targets are frozen and presented with exact counts; confirmed deletion updates current/list TCM and turn management guards.
- [ ] Make existing workboard create/update/comment/manual run controls confirmed, with appropriate native executor; deletion reuses its current flow. Preserve follow notifications and single-use carried draft identity.
- [ ] Apply fresh peer shares/connection/block/owner checks before effect. An admin operation cannot pretend to execute as a peer with that peer's tools.
- [ ] Keep ingestion tokens inside secure display; generation/revocation returns status/reference only to the model.
- [ ] Track consolidation/recompute/debrief/summary job spend using the existing named accountant; correct any entry-specific accounting gap measured by tests, not by import inference.
- [ ] Run target unit/integration/store, existing workboard/peer/extraction/provenance suites and relevant frontend coverage.

**Exit:** Explicit management is complete for these UI affordances and neither concurrent extraction nor carried replay undoes consent or performs an unseen mutation.

## Lot 6 — Extensions, spaces, generated/kept assets and media records

**Deliverable:** All supported resource/library/job operations using existing safety, quotas and result lifecycles.

**Owners:** `skills`, `skill_library`, `plugins`, `user_mcp`, `rag_spaces`, `attachments`, `bookmarks`, `email_share`, `meetings`, `radio`, `avatars`, `live` services/schemas; current generated-file tools; shared action_sink and existing egress grant flow.

**Create:** operation files `extensions.py`, `spaces.py`, `assets.py`, `meeting_management.py`, `radio_settings.py`, `media_settings.py`, decomposed further when size/complexity warrants. No speculative provider layer.

**Tests:** per-family typed contract suites; real DB/file/job integration for space movement, import rollback, library pinning, report changes, source validation and recorder parity.

- [ ] Pin T22/T26/T29–T33/T43/T48/T50: existing file ids/ownership, quota/size/MIME, preview commit, per-account/system skill identity, URL redirect/SSRF and partial plugin constituents.
- [ ] Cover read and confirmed mutation/download/share/import/export workflows from every nested UI control. File inputs reference owned uploaded content or a secure picker, never arbitrary local/server paths.
- [ ] Keep library install/update at the previewed revision; reuse provenance/trust, isolated runner and egress constraints. Management must not turn skill Markdown into trusted instructions.
- [ ] Preserve durable sync/index/report jobs and last-good serving generation. Return accepted job reference/status and subsequent verified outcome, not “finished” when queued.
- [ ] Wire existing action-recorder context through sharing/install services so a tool records one effect. Test original direct UI path still records one effect too.
- [ ] Implement radio/live/avatar/meeting saved preferences and server lifecycle status separately from device play/record. Do not expose raw start credentials or simulate playheads/audio chunks.
- [ ] Run targeted unit/integration and existing file/import/job/cancellation/egress tests. Secure picker and player commands get handlers in lot 8.

**Exit:** All server-side resource/job operations in these screens have confirmed parity; third-party content, file safety and ownership retain existing boundaries.

## Lot 7 — Administration in bounded slices

**Deliverable:** Administrative parity with current role enforcement, exact preview and accountable global effects.

**Slice 7A: users, quotas, exports and broadcasts.** Use users admin request models/service, usage-limit service/instance budget, notifications broadcast, consumption export streams. Tests cover T02/T03/T24/T33/T36/T37/T54 and exact audience/count/target fields. No role promotion or arbitrary User patch absent from the UI.

T58 adds a precise latest-pending-registration query and activation flow. Extend the existing User model/schema/service/repository and auth registration/verification/native activation writers with one monotonic activation-history fact; add a reviewed Alembic migration with reliable backfill and explicit unknown legacy provenance. Derive eligibility from verified/inactive/non-deleted/known-never-activated facts; apply the filter before selecting the creation-time latest row. Share this lifecycle projection with admin UI/query paths. Freeze the selected id in the draft, reauthorize/recheck under the command boundary, and preserve the activation service's separate committed-state and email-delivery results. Do not infer initial pending approval from inactive alone, missing audit history or the newest unfiltered row.

**Slice 7B: model configuration, JEV and tariffs.** Use `llm_config`/JEV registry/service, LLM model/pricing sheet services, image/Google pricing and existing cache publication. Tests cover T12/T22/T33–T35/T53. Required derived reasoning/capability validators, masked provider keys, actual runtime slots, two-worker cache invalidation and rollback. Credentials are secure handoffs.

**Slice 7C: personalities, system skills and RAG jobs.** Use system-scope services and existing translation/index job owners. Tests cover T26/T29–T31/T33/T35/T56. Confirm system/cross-account scope and job consequences; keep last-good index.

**Slice 7D: switches, debug, demo link, diagnostics and registers.** Use current feature-switch/system-settings/product/diagnostic/ledger services. Tests cover T02/T03/T19/T22/T34/T37/T51. Reuse named diagnostic query tools; no shell/free query/chain repair. Audited unmasking remains an actual audited action.

**Create:** `operations/admin_users.py`, `admin_limits.py`, `admin_models.py`, `admin_pricing.py`, `admin_content.py`, `admin_system.py`, `admin_registers.py`; small domain command extractions where needed; corresponding unit/integration test modules.

**Shared cycle for each slice:**

- [ ] Write red tests for every displayed read/filter/detail/export and action, including forced invocation by ordinary user, stale-role resume and other-account result access.
- [ ] Reuse the actual API schema/service/guard/cost owner and implement a bounded native read/action pair. Ordinary-user discovery carries no administrative payload/schema values.
- [ ] Present exact scope and dependency effects. Check account/instance budgets just before paid work; admin target identity is not actor identity.
- [ ] Preserve domain commit/rebuild/publish sequence and inspect all writers of the affected cache.
- [ ] Verify secure secret flows stay outside the model; verify no global action is reachable through a personal schema.
- [ ] Run slice unit/integration/parity, relevant pricing/capability/reasoning/export/diagnostic suites and actual two-worker tests; inline review the complete slice diff.

**Exit:** All Administration tokens are mapped and implemented or securely delegated, without privilege escalation, global setting shadow state or unaccounted jobs.

## Lot 8 — Addressed device bridge and secure handoffs

**Deliverable:** Device-only settings, current-view snapshots, navigation/playback/recording and secure interaction completion under a precise origin identity.

**Create backend:** `application/device_schemas.py`, `device_router.py`, `device_service.py`, `device_presence.py`, strict ACK/command lifecycle helpers using lot 2 persistence and existing notification fanout. Register any new Redis runtime families, API routes and metric consumers. Streaming auth uses detached session lookup.

**Create frontend:** `types/application-commands.ts`, `hooks/useApplicationDeviceCommands.ts`, `lib/application-commands/registry.ts`, `dispatch.ts`, finite handlers grouped by settings/media/navigation/security; a bounded secure interaction card in `components/chat/` only where existing cards/forms need a host.

**Reuse:** current theme/haptics/eyes/avatar/dock/debug stores/hooks, geolocation/FCM/native navigation, existing mandatory step-up for included operations, file/share helpers, radio player, live session and meeting recorder owners. No new password/MFA/passkey/recovery/telephone-verification handlers. Do not duplicate these owners or their business logic.

**Tests:** backend `test_device_protocol.py`, integration `test_device_commands.py`/`test_device_reconnect.py`; frontend real dispatch/hooks/card/store tests, finite JSON-schema/type parity and archived-event replay guard; hermetic E2E device-command journeys.

- [ ] Pin T14/T21/T23/T24/T38–T47/T49/T55/T56 before implementing transport: wrong user/tab/session, offline, stale snapshot, unsupported browser API, schema mismatch, forged/duplicate ACK, command takeover and crash after actual local effect.
- [ ] Register an authenticated origin client; snapshot only allowlisted non-secret state requested for the question. Include supported/unknown, local/account scope and observed-at/expiry. Unsaved non-secret form values are marked draft device state, not persisted settings.
- [ ] Claim delivery/execution for the addressed client with a stable command id/version. Other tabs do not execute. Expiry/logout/unmount abort; reconnect reads server status, not archived command messages.
- [ ] Dispatch finite typed commands through the existing owner; re-read values when verifying a set-state result. Non-idempotent start/play/record/share has no automatic replay after unknown completion.
- [ ] Host current step-up/file/OAuth/permission flows in secure UI; return only server-verified operation proof/status. Pending human gesture is represented as waiting; it is not completed success.
- [ ] ACK current completion fact through authenticated api-client; ensure no ACK/session/client data is accepted as role authority. Completion/outcome read is actor/device scoped.
- [ ] Mirror finite protocol types and consumer/producer vocabulary; wire errors and normal fallback in all six locales. Do not route commands through arbitrary notification metadata/URLs without schema validation.
- [ ] Run backend unit/integration, real frontend hook/state-machine tests and hermetic browser paths. Qualify Android/iOS gestures/media on a dedicated account separately; report physical output and provider release limits explicitly.

**Exit:** The originating device can be inspected/controlled within its supported affordances, with truthfully scoped completion and no multi-tab replay/credential leak.

## Lot 9 — End-to-end UX, all execution origins and complete parity guard

**Deliverable:** Read → preview → confirm/edit/cancel → actual result is coherent across application surfaces and execution origins.

**Modify:** current HITL available-action/schema/reducer hooks, typed SSE events/handlers, chat cards/markdown renderer only where needed, affected query hooks/UI error states and locale catalogs. Use existing design primitives and preserve the active concurrent HITL solution.

**Tests:** frontend actual reducer/card/query/secure-handoff integration suites; `apps/web/e2e/smoke/application-settings-hitl.spec.ts`, `application-admin-tools.spec.ts`, `application-device-commands.spec.ts`, `application-management-parity.spec.ts`; backend deterministic graph/voice/channel/workboard flow tests and an inventory-to-operation coverage guard.

- [ ] Pin T02/T04/T05/T08/T09/T16/T19/T27/T28/T37/T42/T44/T45/T48/T50/T55. Build real required API/SSE fixture contracts; no reduced payload that bypasses current dashboard/HITL error boundaries.
- [ ] Test Pipeline and ReAct native draft flow, multiple drafts, classification edits, stale structured acceptance, carried ticket digest and ordinary channel confirmation. Reads do not generate spurious confirmation.
- [ ] Keep Live direct read-only and delegate application actions to the supported chat/HITL flow. No mutation hidden in a read-only voice callback; no administrative tool offered to a normal caller.
- [ ] Test same actual service/query from UI and tool for every operation id. Every section/page entry and meaningful nested affordance maps to operation/handoff/exclusion with reason; unknown added affordance fails the parity guard.
- [ ] Test narrow layouts, long translation/value, keyboard order/focus/return, inline error/announcements, zoom/reflow, reduced motion and light/dark/OLED. Refresh preserves drafts/filters and never blurs the focused control by disabling it.
- [ ] Validate User/query/context synchronization and result links under localized routing/API origin; secure commands never replay from archive or history reset.
- [ ] Run affected Chromium hermetic journeys, then the full hermetic package because shared chat/SSE/fixture infrastructure changed. Extend Firefox/WebKit/native qualification according to current Taskfile commands.

**Exit:** Functional coverage is proven by actual states/results rather than snapshots alone; restored pending confirmations and partially completed commands remain actionable and honest.

## Lot 10 — Token, cost, reliability and release qualification

**Deliverable:** Measured qualification and complete documentation for the exact implemented snapshot.

**Owners:** existing token counter/ReAct schema measure, per-slot window resolver, smart catalogue/semantic selector/cache fingerprint, spend roads/accountants, usage guards/cost bearers, rate limits/provider shaper, decision/treatment/effect registers and Grafana/alerts.

**Tests/artifacts:** `application/test_spend_attribution.py`, `test_quota_paths.py`, `test_selector_reachability.py`, `test_catalogue_budget.py`, `test_cache_identity.py`, fixed labeled routing/operation corpus and before/after assembled prompt reports under `.tmp`/normal measurement artifact location. No paid live probe by default.

- [ ] Pin T33/T34/T46/T47/T51–T54/T56: account+instance quota, personal-key exclusion, paid failure/fallback, near-limit concurrency, unknown/small windows, panic/frequent/occasional selection and schema re-registration.
- [ ] Measure assembled prompts and bound schemas on the same corpus before/after. Record input/output/cache/read/write/schema/result counts, number of calls/retries, latency and estimated cost from the current pricing authority. Label static estimates as estimates.
- [ ] Verify authorized family coverage and all required binding units. Correct schema granularity/reuse or actual redundant work rather than shortening useful history/tools or hiding constraints.
- [ ] Ensure catalogue/embedding/cache fingerprint includes schema/version and authorization/availability wherever cached payload depends on them; no cross-user/admin reuse of projected values.
- [ ] Verify every new spend reader/writer and direct client path's named accountant and decision filer, then verify actual ledger and visible meter values with controlled usage fixtures.
- [ ] Wire new bounded metrics to real panel/rule/alert expressions, including zero-series/no-data behavior; update shrink-only baselines only after measured improvement.
- [ ] Run current gates: `task lint`, `task test:backend:unit:fast`, `task test:backend:unit:coverage`, `task test:markers`, `task test:backend:agents`, disposable integration/migration replay, `task test:frontend`, `task test:frontend:coverage`, and relevant hermetic `task test:e2e`/browser matrix. Before a later authorized push run `task ci:fast`; hooks are not a substitute and are never bypassed.
- [ ] Review every file in each completed slice inline, then all cross-slice contracts, serializers, lifecycle/cache writers and runtime mounts. Report fresh counts/exits/warnings/skipped qualifications separately.
- [ ] Create/update architecture decision and technical/tool/frontend guides where behavior changed, documentation index and six-language living maps for new runtime domains/modules. Regenerate derived facts; do not edit AGENTS.md separately or invent release counts/performance claims.
- [ ] Reconcile every F requirement/T scenario/section/page/operation against a completed test and a implemented path or justified secure handoff. State any actual unsupported device/platform limitation precisely.

**Exit:** Source, runtime tests, traceability, cost ownership, UI parity and device qualification agree. No release/deployment or universal “100% no hidden issue” claim is implied by passing a narrower gate.

## Per-slice TDD execution loop

For every family/operation (including sub-slices of broad lots), use this complete loop rather than one large green integration at the end:

1. Write the failing behavioral test with actual request schema and real entry boundary. Include its highest-risk forbidden/conflict/failure case.
2. Run the selected test and verify its failure is the missing intended behavior, not a fixture/import/environment error.
3. Implement the smallest domain command/query extraction and native adapter satisfying the existing UI and new tool contract.
4. Run the test to green; add the concurrency/round-trip/device integration when that boundary's semantics require it.
5. Register tool/manifest/context/draft/i18n/cost/metric consumers and run completeness, agent and parity guards.
6. Refresh the affected UI state and prove focus/error/mobile behavior where the operation changes a user flow.
7. Perform an inline cold review of every changed file in the slice and run its mandated Taskfile gates. Preserve unrelated working-tree/index changes.
8. Mark the operation closed only when read, action/handoff, permissions, confirmation, actual result, invalidation/accounting and tests are all present. Commit/push remains a separate user-authorized action.

## Plan self-review

- **Spec coverage:** F01–F10 map to lots 1–10; all current section tokens/page groups appear in the design matrices and the per-family lots. Static inventory is explicitly separated from runtime parity.
- **Test coverage:** T01–T58 have named owning lots and assertions; PostgreSQL concurrency, device acknowledgement and model cost each have an appropriate oracle rather than universal mocks. The user's font-size and latest-pending-account examples have explicit end-to-end acceptance contracts.
- **Interface consistency:** Native application actions always use the lot 2 executor/command contract; device operations use the same command identity and separate actual completion facts; domain services remain the business owner.
- **No business implementation in this deliverable:** proposed files/signatures are marked as proposed. This plan supplies schemas, boundaries, concrete test scenarios and ordered TDD steps without writing product code.
- **Remaining qualification:** actual deployment capabilities/prices/models, real-device gestures/media behavior, measured prompt cost and final concurrent-HITL integration are explicitly tested during execution. They are not facts asserted from memory.
