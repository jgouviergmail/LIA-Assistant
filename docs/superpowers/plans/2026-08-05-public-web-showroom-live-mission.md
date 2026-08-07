# Public Demo Live Synthetic Mission Implementation Plan

> **For the implementing agent:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task by task, superpowers:test-driven-development for each change, systematic-debugging for failures, requesting-code-review after each boundary-sensitive tranche, and verification-before-completion before any public beta.

**Goal:** Add a bounded live version of the overloaded-morning mission on top of the proven public-demo boundary, using a unique synthetic User per non-account visitor session, demo-only workspace tools, explicit execution policy, atomic budgets, HITL over synthetic changes, and complete retryable purge.

**Architecture:** The website talks through four exact same-origin Next route/method pairs to the separate public-demo ASGI process. A random cookie resolves to a durable `public_demo_sessions` row and a synthetic User, provisioned through SQLAlchemy Core repositories so the running public process never initializes LIA's global ORM registry. The normal `AgentService`, `MessagesState`, `ExecutionPlan`, graph, nodes, and tool registry remain untouched and unimported; they are settings-coupled. A public-only runtime composes standalone settings, bounded `PublicDemoState`/`PublicDemoPlan`/nodes, `PublicDemoRunKernel`, a dedicated proxy-bound provider client, a versioned price manifest, a fresh restricted agent catalogue, `PublicDemoGraphFactory`, and generation-fenced persistence adapters. A public resolver enforces per-agent tool capabilities immediately before invocation. Durable PostgreSQL ledgers authorize creations and cost; Redis carries rebuildable concurrency leases/wake-ups only. Temporary identity, messages, checkpoints, Store entries, workspace, and usage detail are purged by a public-demo-only worker.

**Tech stack:** FastAPI, LangGraph 1.x, LangChain 1.x, SQLAlchemy 2, PostgreSQL, Redis Lua, Pydantic v2, SSE, Next.js 16 route handlers, React 19, pytest, Vitest, Playwright.

**Program specification:** docs/superpowers/specs/2026-08-05-public-web-showroom-program.md

**Required predecessors:** The P0 evidence gate and every completion gate in docs/superpowers/plans/2026-08-05-public-web-showroom-runtime-boundary.md are green. Technical implementation may proceed in isolation, but no public P2 beta or live website routing is allowed until the installer has produced the E3 clean-install proof defined by docs/superpowers/specs/2026-08-05-self-host-installer-audit-addendum.md. Runtime tests are authorized only in a newly created disposable environment.

## Global invariants

- Never touch, query, inspect, attach to, copy from, or reuse any current DEV or PROD runtime resource.
- Never perform Git actions.
- The Habits worktree was reconciled and released (v1.28.0, `c5955b73`); verify the worktree is clean before touching constants or environment templates. Do not modify `users/models.py`, `agents/api/service.py`, standard agent nodes/state/plan, `post_response_extractions.py`, `account_deletion_service.py`, or `core/config/__init__.py` for this feature.
- The normal app, routes, auth sessions, users, tools, and behavior remain unchanged when runtime profile is standard.
- Public-demo tables, quota ledgers, and fencing functions/triggers live only in a separate Alembic overlay with version table `alembic_version_public_demo`; the standard Alembic environment, model registry, entrypoint, and migration head never import or apply it.
- The public app never imports the current `agents/api/service.py`, standard `models.py`/`orchestration/plan_schemas.py`/graph/nodes, or connector-bearing `ToolDependencies` module, directly or transitively. Every reused utility must pass the executable import-boundary checker.
- The public app never imports `src.core.config`, the standard `settings` singleton, the standard ORM registry/repositories, the ordinary LLM factory/provider adapter/key cache, or any global agent registry. Every public dependency is passed explicitly from one runtime composition root.
- One demo cookie maps to one random synthetic User, one Conversation whose ID equals that User ID, and generation-bearing LangGraph thread/Store namespaces recorded for exact purge.
- A demo cookie is never accepted by normal authentication; a normal session cookie is never accepted by public-demo dependencies.
- Absolute TTL never slides. Expiry denies new runs immediately.
- Normal connectors, MCP, browser, filesystem, network fetch, voice, images, attachments, RAG, skills, telephony, reminders, channels, geolocation, memory, interests, open loops, journals, psyche, habits, recurrence, proactive injection, global learning, product outcomes, Langfuse, and content caches are disabled.
- Normal HITL registries and action executors are disabled. Only decisions tied to demo-only synthetic workspace mutations are accepted.
- Tool authorization is enforced both during manifest discovery and immediately before returning/invoking a callable.
- Hidden reasoning, prompts, raw tool arguments, user messages, cookie tokens, synthetic email, IP, user-agent, secrets, and unrestricted exception strings never enter public traces or logs.
- Provider retention and backup semantics are disclosed separately; local purge is never described as deleting provider-held data.
- A live run accepts only mission ID `overloaded_morning_v1`; no visitor prompt, edit instruction, URL, attachment, or free-form follow-up is sent to the provider in this bounded beta.
- The API has no direct Internet route. The one explicitly injected provider transport can reach only the dedicated egress proxy and its exact allowlisted provider origin.

## Target bounded context

Create under apps/api/src/domains/public_demo:

- enums.py
- tables.py
- schemas.py
- repositories.py
- session_tokens.py
- session_service.py
- dependencies.py
- execution_policy.py
- state.py
- plan.py
- run_kernel.py
- nodes/__init__.py
- nodes/router.py
- nodes/planner.py
- nodes/semantic_validator.py
- nodes/domain_agents.py
- nodes/approval.py
- nodes/response.py
- admission.py
- budget.py
- reconciliation.py
- workspace.py
- tools.py
- tool_registry.py
- agent_catalogue.py
- llm_runtime.py
- pricing.py
- graph_factory.py
- fenced_checkpointer.py
- fenced_store.py
- runtime.py
- run_service.py
- purge_service.py
- cleanup_worker.py
- trace.py
- metrics.py
- purge_manifest.py

Create the demo-only migration/Core persistence surfaces:

- apps/api/src/domains/public_demo/persistence_schema.py
- apps/api/alembic_public_demo/versions/<revision>_public_demo_lifecycle.py
- apps/api/alembic_public_demo/versions/<revision>_public_demo_fencing.py
- migration-overlay tests under apps/api/tests/unit/public_demo

Create versioned, public-only prompts under `apps/api/src/domains/agents/prompts/v1/public_demo_*.txt`; load them through an import-clean path-only loader. If the current loader is not import-clean, extract its pure file-loading core and retain the standard wrapper unchanged.

Create mirrored tests under apps/api/tests/unit/domains/public_demo and integration tests under apps/api/tests/integration/public_demo.

Create Web files:

- apps/web/src/app/api/public-demo/session/route.ts
- apps/web/src/app/api/public-demo/run/route.ts
- apps/web/src/app/api/public-demo/decision/route.ts
- apps/web/src/lib/public-demo-api.ts
- apps/web/src/lib/public-demo-config.ts
- apps/web/src/components/showroom/LiveShowroomMission.tsx
- apps/web/src/components/showroom/useLiveShowroom.ts
- their unit tests and apps/web/e2e/smoke/public-demo-live.spec.ts

Modify only the explicit seams listed per task.

## Task 1: Add the lifecycle schema and SQLAlchemy Core contract through the isolated overlay

**Files:** create `enums.py`, `tables.py`, `repositories.py`, `persistence_schema.py`, one lifecycle revision under `alembic_public_demo/versions`, and Core/overlay tests. Do not create a public ORM registry and do not modify standard `alembic/env.py`, `infrastructure/database/registry.py`, the base versions directory, or the standard startup model-registration point.

1. Write failing schema-contract tests for these overlay-owned tables:
   - `public_demo_sessions`: UUID id; unique `user_id` FK to `users.id` with `ondelete="CASCADE"`; unique fixed-length HMAC-SHA256 token digest; active/draining/purging status; locale and fixture version; validated JSONB workspace; absolute expiry; active run ID, lease deadline, run generation; cleanup attempt count, next retry, bounded last error code; UTC timestamps;
   - `public_demo_creation_reservations`: random nonce digest, nullable rotating client-bucket digest, bucket expiry no later than the current UTC hour boundary, UTC day, unbound/bound/expired state, optional bound session FK using `ON DELETE SET NULL`, and timestamps;
   - `public_demo_runs`: session FK with cascade, unique `(session_id, generation)`, owner epoch/heartbeat, immutable deadline, status enum `reserved | capacity_acquired | running | waiting_decision | completed | cancelled | timed_out | aborted_before_start | failed`, reserved billable tokens and integer microusd, actual usage fields, and timestamps;
   - `public_demo_budget_days`: UTC date primary key plus aggregate creation count, reserved billable tokens, and reserved integer microusd only;
   - `public_demo_approvals`: session/run/generation/action/payload-digest/expiry binding, single-use decision status, and no visitor text.
2. Require explicit indexes, unique constraints, `ondelete` behavior, UTC timezone-aware timestamps, nonnegative counters, coherent lease/run fields, bounded enums, and checks that aggregate values fit signed 64-bit integer storage. Floats are forbidden for money.
3. Implement every table with explicit Alembic operations in the separate overlay. The revision has one overlay head and uses `alembic_version_public_demo`; it must not alter the base head or appear under `apps/api/alembic/versions`.
4. Add a public-only schema-preparation command that uses explicitly supplied public DSN and upstream LangGraph `setup()` routines to create the isolated checkpoint/Store schema after marker verification and base migration but before the overlay. The entrypoint order becomes marker proof → base head → persistence-schema preparation → overlay head → schema fingerprint verification → ASGI. This command imports no LIA settings, ORM model, global saver/store singleton, or runtime app.
5. In the running app, reflect only a code-owned table allowlist with SQLAlchemy Core. Pin names, columns, types, nullability, defaults, keys, and the exact mutable LangGraph persistence table inventory. Startup fails when a required contract drifts or upstream setup creates a new mutable table that is not classified for fencing and purge.
6. `PublicDemoRepositories` receives an `AsyncConnection`/factory and these reflected `Table` objects. It never imports `User`, `Conversation`, `ConversationMessage`, a standard repository, `Base`, or mapper configuration. An executable import test proves that `configure_mappers()` is never called by the public app.
7. Write fresh-database migration tests that apply the base head, run public persistence preparation, apply the overlay, inspect every contract, downgrade only the overlay-owned objects, and prove the base head/version table remains unchanged. Use a subprocess for the base migration so its permitted standard registry import cannot leak into the public runtime process.
8. Extend `check_public_demo_boundary.py` so a public revision in the base directory, any ORM model/registry/repository import in the public closure, overlay invocation from the standard entrypoint, or wrong migration order fails.
9. Run focused Core/migration tests against a fresh disposable test database only. Never point `DATABASE_URL` at an existing database.
10. Suggested owner checkpoint: feat(public-demo): add isolated Core lifecycle overlay

## Task 2: Create durable creation admission, opaque session token, and synthetic identity provisioning

**Files:** create `session_tokens.py`, `session_service.py`, `dependencies.py`, `schemas.py`, and unit/integration tests; extend the Core repositories and lifecycle tables only.

1. Test generation of a 256-bit CSPRNG token and storage of only HMAC-SHA256(token, dedicated key). Raw tokens may exist only in the Set-Cookie response.
2. Cookie contract: distinct name from lia_session; HttpOnly; Secure; SameSite=Lax; Path=/api/public-demo; Max-Age no greater than absolute TTL. Rotation invalidates the previous digest.
3. Public schemas use `ConfigDict(extra="forbid")`. Session creation accepts locale only. Run accepts only `mission_id: Literal["overloaded_morning_v1"]`; the server supplies the versioned synthetic request. Client-supplied message, user ID, session ID, conversation ID, mode, tool, URL, location, attachment, provider, directive, or edit text is 422.
4. Before any User/Conversation/session insert, commit a PostgreSQL creation reservation under transactional advisory/row locks for the rotating trusted client bucket, UTC hour, UTC day, and active-session ceiling. Enforce three creations per bucket/hour, 1,000 global reservations/day, and 100 active or reserved sessions. A failed/unbound attempt still consumes its conservative reservation; database failure denies creation.
5. The client-bucket digest is never copied beyond `public_demo_creation_reservations` and is nulled or the row purged at its hour boundary. The daily table retains only aggregate counts. Tests cover two API workers, boundary rollover, replayed nonce, crash between reservation and identity creation, expiry, and concurrent attempts.
6. In a second transaction, bind one unused reservation while provisioning through Core: one random User with `demo-<random>@example.invalid`, `hashed_password=NULL`, inactive, verified, non-admin, no OAuth/session row; one Conversation whose ID equals the User ID; and one public session. Failure rolls back every identity row but does not refund the prior reservation.
7. The Core insert explicitly supplies false/disabled values for every memory, habits, interests, heartbeat, journal, notification, login-notification, location, media, connector, scheduled-action, and proactive preference required by the reflected schema. A pinned schema-completeness test fails when a new required/relevant User column appears without an explicit public value and purge classification.
8. Bypass `AuthService`, `AccountProvisioningService`, `SessionStore`, standard repositories, welcome email, default notification creation, and provider provisioning. Import and call spies prove zero access; no SQLAlchemy mapper is initialized.
9. Two cookies must produce different User, Conversation, token digest, generation namespaces, and workspace. Replaying an invalidated or expired cookie returns the same bounded not-found response.
10. A public-demo token must fail every normal auth dependency; a normal cookie must fail `get_current_public_demo_session`.
11. Run focused unit tests, then fresh isolated integration tests.
12. Suggested owner checkpoint: feat(public-demo): admit and provision isolated synthetic identities

## Task 3: Define bounded public state, plan, run kernel, and immutable policy

**Files:** create `state.py`, `plan.py`, `run_kernel.py`, `execution_policy.py`, public node modules, and tests. Do not modify any standard agent service/state/plan/node module.

The current `AgentService`, `MessagesState`, `ExecutionPlan`, router/planner/semantic/response nodes, and graph are not safe public imports because their closures read standard settings or broad side-effect domains. The bounded showroom therefore owns smaller contracts and discloses that fact. It may reuse only a utility whose complete runtime/lazy import closure is positive-allowlisted.

1. Define `PublicDemoState` with only the fixed mission version, bounded messages/content deltas, validated public plan, four synthetic result slots, proposal/approval references, receipt fields, run generation/status, and numeric usage. No memory, connector, arbitrary context, URL, attachment, ReAct, or generic tool field exists.
2. Define `PublicDemoPlan` with `ConfigDict(extra="forbid")`, a fixed maximum step count, and only canonical agent names `email_agent`, `event_agent`, `task_agent`, and `weather_agent`. Validate the exact read/prepare dependency shape server-side; model output cannot add an agent, tool, target, retry, or free-form capability.
3. Implement public router/planner/semantic-validator/domain/approval/response nodes over typed injected protocols. They never import standard node wrappers. Reuse a shared model/schema/helper only after a transitive import test proves it does not import standard settings, ORM, registries, caches, or denied domains; otherwise keep the bounded equivalent public.
4. `PublicDemoRunKernel` owns graph invocation, the one SSE stream, durable interrupt wait/signalling, cancellation, Core message/usage writes, and bounded error normalization. All dependencies are constructor fields; no module-level singleton or service locator exists.
5. Define a frozen `DemoExecutionPolicy` with explicit fields, not a generic dictionary. It permits only pipeline mode, the exact public agents/tools, Core conversation/messages, generation-fenced saver/Store, numeric usage, and bounded trace events. Every ordinary side effect is false.
6. Propagate the policy plus run generation through one typed `RunnableConfig` key/accessor that fails closed when missing. Do not infer policy from `is_automated_source`, a visitor field, or environment capability list.
7. Add AST plus runtime/lazy import-graph tests denying `AgentService`, standard state/plan/graph/nodes, auth, connectors, attachments, voice/images, MCP/user MCP, browser, RAG, skills, telephony, channels, schedulers, `src.core.config`, ORM registry/repositories, ordinary LLM factory/provider/key cache, and global agent registry. No transitive waiver is allowed.
8. Spy tests prove no usage-limit lookup, geolocation, OAuth/contact warmup, MCP, proactive context, learning/extraction, product outcome, Langfuse, content cache, attachment, image, voice, browser, or ordinary tool seam executes.
9. Logs contain only profile, bounded phase/status/error code, durations, and aggregate numeric usage. They contain no user/session/run/thread/approval/token identifier; caplog tests also reject message, prompt, synthetic email, cookie, workspace, and raw error fragments.
10. Run focused public tests plus existing agent characterization tests as non-regression evidence; standard source hashes/import snapshots must prove that no standard agent service/state/plan/node file changed.
11. Suggested owner checkpoint: feat(public-demo): add bounded execution contracts

## Task 4: Compose the complete standalone model, graph, persistence, and observability runtime

**Files:** create `llm_runtime.py`, `pricing.py`, `agent_catalogue.py`, `graph_factory.py`, `fenced_checkpointer.py`, `fenced_store.py`, `runtime.py`, public prompt files, the fencing overlay revision, and tests; extend `startup/public_demo.py`, public settings/readiness, the entrypoint, and the import-boundary checker. Extract only narrowly characterized settings/LLM/node protocols from standard modules when required.

1. Define a single `create_public_demo_runtime(PublicDemoRuntimeSettings)` composition root. It receives the standalone settings instance created with `env_file=None`; explicit Core DB/Redis pool factories; the resource verifier; and a `MetricExporterFactory`. It returns typed public dependencies and owns shutdown. No module-level client, saver, Store, graph, registry, cache, metric, or settings singleton is allowed.
2. Implement `PublicDemoModelRuntime` for this exact public-role to current LIA-slot mapping: `router→router`, `planner→planner`, `semantic_validator→semantic_validator`, `email_agent→emails_agent`, `event_agent→calendar_agent`, `task_agent→tasks_agent`, `weather_agent→weather_agent`, and `response→response`. It accepts one code-reviewed provider/model pair from a versioned manifest, receives the dedicated key explicitly, disables environment credential discovery and standard DB overrides/caches, sets explicit connect/read/overall timeouts, sets provider SDK retries to zero, and permits no provider/model fallback. Any code-owned structured-output repair call is declared and counted separately. It constructs a transport with `trust_env=False` plus the exact injected egress-proxy URL. A sentinel standard `.env`, standard provider key, and standard LLM override row must have zero effect.
3. The versioned price/cap manifest binds provider, model, provider origin, public role, legacy-slot evidence mapping, required tools/structured-output/streaming/context capabilities, maximum initial and repair calls, maximum input/output tokens per call, timeouts, and integer `microusd_per_million_input_tokens`/`microusd_per_million_output_tokens`. At boot, enumerate every reachable graph path and calculate each component with conservative ceiling division before summing and applying an integer safety margin. Readiness fails if any role/path/capability/price is absent, a retry/fallback is implicit, a graph path exceeds its declared call count, or the derived envelope exceeds the reviewed run/daily/provider caps. `20,000` tokens and `$0.20` are ceilings to prove, not assumed costs.
4. Create a fresh `PublicDemoAgentCatalogue` and tool registry containing only the four synthetic domain agents and the exact demo-tool set. Build no global/standard registry. Startup fails on a missing or extra role, prompt, agent, manifest, callable, or model mapping.
5. `PublicDemoGraphFactory` compiles a fresh pipeline-only LangGraph over `PublicDemoState` and `PublicDemoPlan` with this exact bounded flow: fixed mission ingest → public router → public planner → public semantic validator → parallel `email_agent`/`event_agent`/`task_agent`/`weather_agent` → deterministic proposal gate → server-bound approval interrupts → approved synthetic mutations/refusals → public response/receipt. Normal state, plan, graph construction, nodes, and ReAct are never imported. Every node receives settings, model resolver, catalogue, tools, clock, and policy explicitly.
6. Use versioned `public_demo_*` prompts and reject prompt fallback to a standard or unversioned name. A startup hash manifest binds the exact prompt files used by the graph so a deployment cannot silently mix prompt versions.
7. Instantiate fresh `AsyncPostgresSaver` and `AsyncPostgresStore(index=None)` objects on dedicated public pools without their normal global factories or embedding configuration. API availability was proven by import on the locked versions during the 2026-08-05 consolidation (langgraph 1.2.4, checkpoint 4.1.1, checkpoint-postgres 3.1.0): `AsyncPostgresSaver.adelete_thread` exists (`aio.py:340`), `store.setup()` applies `VECTOR_MIGRATIONS` only when an index config is supplied, so `index=None` creates no `store_vectors` table or pgvector index. The pinned mutable-table inventory for fencing triggers is exactly `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, and `store` (`checkpoint_migrations`/`store_migrations` hold no run data); the completeness test still guards against upstream additions. The saver uses a public `JsonPlusSerializer` whose exact allowlist contains only the public state/plan/enums needed to round-trip both approval interrupts; an unknown custom type fails a test rather than degrading silently. Wrap every read/write/batch/delete surface in `FencedCheckpointer` and `FencedStore`. Thread IDs use `public-demo:<session_uuid>:g:<generation>`; Store namespace tuples begin `("public-demo", str(session_uuid), f"g-<generation>")`, producing PostgreSQL prefixes beginning `public-demo.<session_uuid>.g-<generation>`. Nonconforming identifiers fail before reaching the delegate.
8. Add overlay functions/triggers to every mutable checkpoint/blob/write/Store table from the pinned persistence-schema inventory. On `INSERT`/`UPDATE`, they parse the code-owned namespace and atomically reject an absent session, wrong generation, expired lease, or purging session in the same database transaction as the write. They do not block exact, purge-owned `DELETE` operations while the session is purging. A completeness test fails if upstream `setup()` adds a mutable persistence table without a trigger. Barrier tests pause a writer, increment/finalize the generation, then prove both adapter and direct-SQL late writes are rejected and leave zero row while exact purge deletion succeeds.
9. Initialize runtime components in this fail-closed order: resource identities → reflected schema/fencing fingerprints → offline provider-cap attestation → price/call envelope → dedicated provider transport → fenced saver/Store → public catalogue/tools → graph → durable budget/reconciliation services → cleanup worker → public metric pipeline from the injected factory. Only then may the live route registry become ready. Shutdown stops admission, drains/cancels bounded runs, fences generations, closes graph/provider/metric reader/exporter/saver/Store, then Redis/DB.
10. Build the public-only metric path as OpenTelemetry SDK `MeterProvider` → `PeriodicExportingMetricReader` → OTLP metric exporter → private collector → collector's internal Prometheus endpoint → isolated Prometheus scrape. Do not import the application's global `prometheus_client` registry or standard metrics modules. Use an in-memory exporter unit test and an isolated fake-collector integration test; no public `/metrics` route, remote write, dynamic label, prompt, session/run/user ID, or content is allowed. Readiness verifies only local exporter/collector pipeline state and never contacts the paid provider.
11. Add proxy transport tests with a fake provider origin: the public client succeeds only through the allowlisted egress proxy; direct sockets, environment proxies, redirects, a second hostname, IP literals, and visitor-controlled destinations fail. Verify the dedicated runtime key fingerprint matches the fresh RFC 8785/Ed25519 cap attestation before constructing the client.
12. Extend the executable boundary checker to reject standard settings/LLM/cache/ORM/registry imports, a direct API outbound network, an unwrapped saver/Store, a missing persistence trigger, mutable prompt/model fallback, or an observability export outside the isolated collector.
13. Run unit/import tests without network, then fake-provider/fake-collector tests only in fresh disposable infrastructure. Suggested owner checkpoint: feat(public-demo): compose isolated live runtime

## Task 5: Enforce a two-layer tool capability boundary

**Files:** create public `workspace.py`, `tools.py`, `tool_registry.py`, and tests. Do not modify/import standard context, registry, resolution, parallel-executor, or ReAct modules.

The exact discoverable P2 tool set is:

~~~text
demo_read_inbox
demo_read_calendar
demo_read_tasks
demo_read_weather
demo_prepare_email_reply
demo_prepare_calendar_change
~~~

`demo_apply_approved_change` is a seventh internal decision-only callable. It has no LangChain tool manifest, is absent from planner/catalogue discovery, and cannot be resolved from a model-produced name.

1. Implement a versioned workspace derived from overloaded-morning-v1. It contains no URL, file path, credential, command, SQL, network target, or real identifier.
2. Each callable accepts only typed IDs/enums and obtains session/workspace from injected `DemoToolDependencies`. It cannot accept arbitrary content destinations.
3. Freeze and enforce this agent matrix at discovery and immediately before invocation: `email_agent` → `demo_read_inbox`, `demo_prepare_email_reply`; `event_agent` → `demo_read_calendar`, `demo_prepare_calendar_change`; `task_agent` → `demo_read_tasks`; `weather_agent` → `demo_read_weather`. No agent receives another agent's callable.
4. Read tools return bounded fixture subsets. Prepare tools create pending synthetic changes. The internal apply callable requires an unconsumed server-issued approval bound to session, run generation, action, payload digest, and expiry plus a non-forgeable decision-worker capability object that no model/node input can construct.
5. `ToolResponse`, `ToolErrorModel`, and `ToolErrorCode` are mandatory only after their import closure passes the public allowlist; otherwise extract an import-clean response core without altering standard behavior. No raw exception or object repr escapes.
6. Discovery tests return exactly six manifests and the per-agent subsets above. They prove `demo_apply_approved_change`, every normal tool, and a canary are absent.
7. Invocation tests use the public strict resolver and recheck both policy and agent matrix immediately before returning a callable. A manifest discovered for one agent but invoked as another is denied before any coroutine executes.
8. Direct public-node tests monkeypatch the catalogue with a forbidden fake and prove denial. Static import tests prove ReAct and every standard registry/resolver remain unreachable and unchanged.
9. The owning decision-wait worker alone receives the internal capability after a valid SQL decision is consumed; direct node/planner calls and forged capability instances fail.
10. Add a static `demo_forbidden_canary` that is never registered; all tests require zero executions. Suggested owner checkpoint: feat(public-demo): enforce demo-only workspace tools

## Task 6: Implement exact public routes and server-bound synthetic HITL

**Files:** extend schemas.py, workspace.py, run_service.py, router.py, trace.py, and tests.

1. Extend the code-owned route manifest and boundary checker with exactly these pairs: `POST /api/public-demo/v1/sessions`, `POST /api/public-demo/v1/runs`, `POST /api/public-demo/v1/decisions`, and `DELETE /api/public-demo/v1/sessions/current`. No other public domain route is mounted.
2. Run accepts only `mission_id="overloaded_morning_v1"`, locale from the session, and pipeline mode fixed server-side. The code-owned synthetic request is at most the configured byte ceiling. The one run response streams a bounded SSE vocabulary: phase, trace_step, content_delta, approval_required, receipt, done, error, plus content-free comment heartbeats while waiting.
3. `trace_step` contains step_id, code-owned i18n key, category, status, and duration only. It contains no hidden reasoning, prompts, visitor text, raw tool arguments, stack trace, or unrestricted error.
4. Approval records are server-owned, single-use, session/run/generation/action/payload-digest-bound, and expire no later than session/run. The bounded live beta accepts only the opaque approval ID plus confirm or cancel; no edit text, run ID, or other visitor free text crosses the public API. P0 may continue to simulate email editing entirely in browser state.
5. Normal HITL registries and draft/action executors are unreachable. `demo_apply_approved_change` is not a discoverable tool: only the owning public run worker may invoke that internal mutation after consuming a valid persisted decision.
6. `POST /runs` reserves once and keeps one bounded SSE response open for the same run/generation. At each durable interrupt, the worker persists `waiting_decision`, releases global execution concurrency, emits `approval_required`, and waits with content-free comment heartbeats. `POST /decisions` atomically consumes the approval, returns `202`, and publishes a content-free signal on the exact session/run Redis channel; authoritative bounded SQL polling makes Pub/Sub loss harmless. The same owning worker reacquires concurrency and performs the only server-owned LangGraph `Command(resume=...)`. It never increments run count or reserves budget again, and every wait/continuation remains under the original immutable deadline.
7. The canonical mission fans out four reads, prepares email/calendar changes, and surfaces separate sequential approvals on the same stream. Confirm email/cancel calendar yields a receipt proving the refusal. Tests cover all four live confirm/cancel combinations; the six-combination email-edit matrix belongs to P0 only.
8. There is no client-visible resume, generic SSE reconnect/replay cursor, detached producer, arbitrary resume payload, or background completion. Browser disconnect or worker loss cancels/fences the owner and moves the run terminal; another worker never resumes it and later decisions are rejected. The UI falls back to P0 and TTL cleanup wins.
9. Multi-worker tests route decisions to a process other than the owner and prove durable SQL observation plus best-effort wake-up, two sequential waits on one stream, lost notification recovery, duplicate/replayed/wrong-session decision rejection, disconnect before/after interrupt commit, worker death, original-deadline enforcement, no second budget charge, invalid SSE type, rejected edit/free-text/run-ID fields, tool denial, exact route manifest, and no external side effect.
10. Suggested owner checkpoint: feat(public-demo): add bounded live mission and synthetic HITL

## Task 7: Add durable admission, concurrency leases, and hard budgets

**Files:** create `admission.py`, `budget.py`, `reconciliation.py`, and tests; extend `run_service.py`, standalone public settings, constants, repositories, and public readiness.

1. Treat PostgreSQL as the authority for creation counts, active sessions, per-session run count, run generations, and daily token/microusd reservations. The Task 2 creation reservation and every run reservation use dedicated rows plus transactional locks; Redis is never allowed to initialize or lower a durable count.
2. At readiness, use Task 4's reachable-path calculation to derive the exact per-run reservation. The reviewed upper ceilings are 20,000 billable tokens, USD 0.20, and 2,048 output tokens; daily ceilings are 2,000,000 reserved tokens and USD 10. If the derived model/call/price envelope exceeds a ceiling, live remains not ready. Configuration may lower ceilings; raising one requires a reviewed specification change and fresh cap attestation.
3. Run admission starts one SQL transaction that locks the session and current UTC budget row; verifies active status, absolute expiry, fewer than three runs, no active SQL run, and sufficient token/microusd capacity; increments the generation; inserts a `reserved` run with immutable deadline/owner epoch; binds `active_run_id`; updates aggregate reserved values; and commits. The full worst-case reservation and run attempt are never refunded from the hard daily/three-run limits. Actual usage is recorded separately.
4. Only after that commit, execute one reviewed Redis Lua operation that atomically acquires the session lease and one of four global concurrency slots for the exact run ID/generation/deadline. On success, conditionally persist `capacity_acquired` then `running` before the first provider call. Missing Redis, reconciliation marker, malformed state, stale epoch, or script failure conditionally persists `aborted_before_start` and clears the session's active run/lease while retaining generation, budget, and run count. A decision continuation reacquires capacity for the same `waiting_decision` run/generation/deadline without another SQL reservation. Redis may release global concurrency on wait/completion but cannot modify budgets or run counts.
5. Persist the same immutable wall-time deadline in SQL and Redis. Heartbeat may refresh liveness only up to that deadline. Workspace, message, approval, checkpoint, and Store writes carry the generation namespace and are protected by Task 4's conditional Core writes/adapters/database triggers.
6. On first boot and after any Redis reset/reconnect, set readiness false, block new creation/run admission, and reconcile exact SQL states: stale `reserved` without a lease becomes `aborted_before_start`; `reserved` with a lease becomes conservatively `capacity_acquired`; `capacity_acquired`/`running` retains a slot until owner heartbeat resolution or immutable deadline; `waiting_decision` retains the per-session run lock but no global slot; terminal states retain neither. Rebuild Redis from that result, and take the more restrictive state on ambiguity. A reconciliation epoch prevents an old Lua result from reopening admission; no worker resumes another worker's graph after process loss.
7. Expiry atomically moves active to draining and denies new admission. Cleanup waits for confirmed cancellation or immutable deadline plus grace, increments/fences the generation, and only then purges. A stale producer is unable to write even through the raw LangGraph delegate.
8. The provider credential is dedicated and provider-side spend is hard-capped outside LIA at no more than USD 10/day and USD 100/month. The deployment gate writes RFC 8785 canonical JSON and a detached Ed25519 signature with bounded `kid`, resource ID, verified database incarnation ID, key fingerprint, account/project, UTC day/month, hard caps, spend-to-date/remaining integer microusd, source, issue time, and expiry no later than 24 hours or the UTC day boundary. The signing private key remains offline; runtime mounts only current/next public keys and an atomically replaceable read-only attestation.
9. Revalidate the attestation at least once per minute with at most 60 seconds clock skew and require local ceilings to fit the attested remaining amounts. Rotation uses current/next overlap then removal; revocation removes the trusted `kid` or replaces the attestation. Readiness makes no provider call and labels `source=operator` as attested, never provider-verified. Missing, revoked, stale, resource/incarnation/key/period-mismatched, over-limit, or invalid evidence leaves P0 active. “Durable” covers process/Redis restart only while one tmpfs PostgreSQL incarnation survives; a recreated empty cluster generates a new non-overridable incarnation and cannot reopen with the previous attestation.
10. Tests cover two-process SQL races, simultaneous Redis acquisition, first boot, Redis restart mid-run, reconciliation mismatch, UTC rollover, expired lease, stale heartbeat, adapter and trigger fence rejection, derived-price overflow, daily cap, every attestation failure/rotation path, and provider failure. A disposable two-cluster test proves recreation changes the database incarnation and rejects the old attestation before admission. No test calls a paid provider.
11. A disposable fake-provider load test proves configured concurrency, conservative rejection, and recovery without weakening a durable reservation.
12. Suggested owner checkpoint: feat(public-demo): enforce durable admission and cost ceilings

## Task 8: Implement retryable complete purge

**Files:** create `purge_manifest.py`, `purge_service.py`, `cleanup_worker.py`, tests; extend public startup composition. Treat the normal `users/user_data_map.py` as audited evidence only; do not change the normal deletion contract for this feature.

Purge order is normative:

1. In one conditional Core transaction, invalidate the token, transition to purging, increment the generation fence, and record the exact known run/thread/Store namespaces. Reject new admission, request cancellation, and wait only until confirmed termination or immutable deadline plus grace.
2. Delete every recorded `public-demo:<session_uuid>:g:<generation>` thread through `FencedCheckpointer.adelete_thread`. Then query the exact checkpoint/blob/write keys and require zero. Any failure is retryable and blocks finalization.
3. Delete every exact Store namespace tuple beginning `("public-demo", str(session_uuid), f"g-<generation>")` through `FencedStore`; verify zero persisted prefixes beginning `public-demo.<session_uuid>.g-<generation>` and confirm that no vector index exists. Never use a broad user prefix or wildcard. Any failure blocks finalization.
4. Delete only Redis keys from the session's code-owned key index, never global globs or approximate UUID matching. Durable aggregate creation/budget ledgers are not reconstructed from Redis.
5. Through Core, delete every temporary relational row classified by the public purge manifest, including conversations/messages, detailed run/approval/usage rows and canary rows in `token_usage_logs`, `message_token_summary`, `user_statistics`, `google_api_usage_logs`, `product_outcomes`, and user-attributed `product_events`. The public path is expected not to create most canaries; the purge still proves defense in depth.
6. Remove exact UUID attachment/RAG directories if they exist, even though public policy forbids their creation.
7. Hard-delete the synthetic User and cascading public session in the final transaction. The daily ledger may retain only UTC date plus aggregate creation count, reserved tokens, and reserved microusd; expired client-bucket digests are nulled/purged and no retained row contains user/session/run/network/content identity.
8. Verify absence across the reflected base/overlay table inventory, checkpoint/Store tables, Redis key index, and exact filesystem paths, and reassert that no vector/embedding index exists, before marking the purge complete. Keep the tombstone only as aggregate metric increments, never as an identifier-bearing row.

Tests:

- batch claim uses FOR UPDATE SKIP LOCKED;
- absolute expiry does not slide;
- two cleanup workers cannot own one session;
- injected crash after every phase resumes idempotently;
- checkpoint/Store deletion errors are never swallowed;
- expiry during run obeys deadline/grace, and deliberately late adapter and direct-SQL checkpoint/Store writes are rejected with zero row left;
- second purge is a no-op success;
- metadata completeness fails if a new user-linked table or upstream persistence table is not classified;
- a full isolated integration run leaves zero local residual data;
- local purge SLO is reported as expiry + max run + grace + cleaner interval + retries, not simply 30 minutes.

A test-only subprocess may import the standard model registry after a fresh base migration to enumerate metadata; compare that inventory plus database foreign keys with the code-owned public purge manifest. The running public app never imports it. Use a public-demo-only asyncio worker in the public lifespan and do not register the normal application scheduler. Suggested owner checkpoint: feat(public-demo): add retryable zero-residual purge

## Task 9: Add the four narrow same-origin Website proxy pairs

**Files:** create the three Next route-handler files listed in the target map (the session handler implements both POST and DELETE), `public-demo-api.ts`, `public-demo-config.ts`, and tests; modify environment examples relevant to Web deployment only.

1. PUBLIC_DEMO_API_URL_SERVER and PUBLIC_DEMO_PROXY_SECRET are server-only. No NEXT_PUBLIC variable contains API origin or secret.
2. Validate the upstream base URL at server startup against a configured exact HTTPS origin; visitor input can never affect host, scheme, port, or path.
3. Route handlers implement only this exact map: `POST /api/public-demo/session` → `POST /api/public-demo/v1/sessions`; `POST /api/public-demo/run` → `POST /api/public-demo/v1/runs` with one bounded SSE response; `POST /api/public-demo/decision` → `POST /api/public-demo/v1/decisions` returning `202`; `DELETE /api/public-demo/session` → `DELETE /api/public-demo/v1/sessions/current`. They enforce bounded body sizes/content types, short connect/header timeouts, the immutable run wall deadline for the stream, no redirects, and no arbitrary header forwarding.
4. Add the proxy secret server-side. Forward only the demo Set-Cookie with rewritten first-party domain/path attributes; never forward upstream cookies or internal headers.
5. Derive a one-hour client bucket as HMAC of a normalized coarse address prefix with a rotating server-only key. Forward only the fixed-format bucket header through the authenticated proxy; never forward or log the raw address. The API rejects a bucket header from any unauthenticated caller.
6. Stream the run SSE with backpressure and abort upstream when the browser disconnects. Do not buffer a complete model response. Forward content-free SSE comments during decision waits; the JSON decision request only receives `202` and never owns execution.
7. Normalize upstream errors to bounded public codes. Do not return connection details.
8. Unit tests inject a fake fetch and cover spoofed forwarding headers, bucket rotation/TTL, SSRF input, redirect, timeout, abort, cookie filtering, oversize body, unexpected content type, and secret non-exposure in client bundles.
9. The guided P0 has no dependency on these routes and remains renderable during every error.
10. Suggested owner checkpoint: feat(showroom): proxy isolated live demo server-side

## Task 10: Add live UI with automatic P0 fallback

**Files:** create LiveShowroomMission.tsx, useLiveShowroom.ts, tests; modify showroom config/page and six locales.

1. Extend the bounded variant to legacy, guided, and live. Missing/invalid remains legacy until the release owner deliberately changes it; live is rejected at build validation unless server-only upstream settings exist.
2. Live UI begins with the same canonical fixture/request and clear labels `Live model`, `Bounded showroom graph (not the full local graph)`, `Synthetic workspace`, `No external action`, and `Expires in N minutes`.
3. It renders bounded trace events through ExecutionTraceDisclosure with reasoning empty and approvals through HitlActionCard.
4. The shared receipt model can render the P0 `edited` simulation state, but a live P2 receipt distinguishes only prepared, approved, refused, and applied to synthetic workspace because P2 accepts no edit text.
5. Any session, readiness, admission, stream, decision, or upstream error exposes one action to continue in the guided P0 immediately. Fallback never loops or hides the disclosure.
6. There is no free-form follow-up or edit instruction in the bounded beta. The only live inputs after session creation are the fixed mission ID and confirm/cancel decisions.
7. Page close and explicit End demo call DELETE best-effort; TTL cleanup remains authoritative.
8. Add this exact predeclared P2 experiment vocabulary to the dedicated credential-less showroom route: `demo_guided_assigned`, `demo_live_assigned`, `demo_guided_started`, `demo_live_started`, `demo_guided_completed`, `demo_live_completed`, `demo_live_fallback`, `demo_guided_source_click`, `demo_live_source_click`, `demo_guided_release_click`, `demo_live_release_click`, `demo_guided_install_click`, and `demo_live_install_click`. Emit attempts with `credentials: "omit"` and no dimensions, content, identifier, or cross-event join; publish raw aggregate counts beside ratios. The browser attempts `demo_live_fallback` at the fallback transition because an unavailable API cannot count its own failure. Only a concurrent randomized allocation may be called uplift; otherwise report pre/post deltas.
9. Implement the program's internal API metric names in `public_demo/metrics.py` with code-owned bounded labels only: run outcome, purge outcome, denial reason, and reconciliation outcome. Unit tests enumerate every allowed label value and reject dynamic/content labels; no fallback counter or public metrics route is mounted. Task 4 owns OTLP collection.
10. Force public-funnel telemetry off in repository defaults, DEV, test, ordinary CI, and preview builds. Because the flag is build-time, add two clean managed-build Task/CI/Playwright paths: telemetry-off proves zero request; the sole telemetry-on hermetic contract build intercepts `/api/v1/product/showroom-events`, asserts enum-only body, no Cookie/Authorization, credentials omitted, and `202 Accepted`. Both contract builds inject `NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0` (the layout-level `TelemetryBootstrap` would otherwise flush credentialed Web Vitals to the ordinary route and blur the oracle). Report bot/internal traffic that cannot be reliably excluded as a measurement limitation.
11. Update all six locales with strict parity and run unit/a11y tests.
12. Suggested owner checkpoint: feat(showroom): add live synthetic mission with static fallback

## Task 11: Complete adversarial and residual-data acceptance

Static/unit gates first:

~~~bash
cd apps/api && .venv/Scripts/pytest tests/unit/domains/public_demo tests/unit/domains/agents -q
task lint:public-demo-boundary
cd apps/api && .venv/Scripts/ruff check src/domains/public_demo src/public_demo_app.py
cd apps/api && .venv/Scripts/mypy src/domains/public_demo src/public_demo_app.py
cd apps/web && pnpm vitest run src/components/showroom src/lib/__tests__/public-demo-api.test.ts
cd apps/web && pnpm type-check
task lint:i18n
~~~

Then, only after explicit owner authorization, use the new disposable public-demo project with a fake provider:

1. Prove the entrypoint order marker → base head → LangGraph persistence schema → separate overlay → schema/fencing fingerprint. Confirm one unchanged base head, one overlay head, distinct version tables, and no ORM/global-settings import in the ASGI process.
2. Exercise the full composition root with standalone sentinel settings. Require the exact role/agent/tool/route manifests, derived price envelope, fresh offline attestation, fenced saver/Store, durable ledgers/reconciliation, private OTLP exporter, and cleanup worker before readiness becomes true.
3. Create two sessions and prove Core-row, token, cookie, workspace, thread-generation, Store-prefix, approval, and run isolation. Exhaust creation quotas before identity insertion and prove no orphan User.
4. Complete all four live confirm/cancel decision paths, forced disconnect, timeout, Redis restart/reconciliation, and a late writer paused across a generation change.
5. Attempt prompt injection, every denied tool family, identity override, cross-session decision, cookie replay, oversize/malformed payload, SSE reconnect, direct API access, proxy bypass, direct provider socket, alternate host, IP literal, and redirect.
6. Validate RFC 8785/Ed25519 attestation success plus bad signature, stale evidence, wrong key fingerprint, revoked/unknown `kid`, current/next rotation, excessive cap, and 60-second skew boundaries without a provider readiness call.
7. Inject failure after every purge phase and prove idempotent recovery. Run the residual-data probe across every reflected base/overlay table, detailed usage row, checkpoint/Store item, Redis key index, and exact file path; also prove no vector/embedding index exists. Only non-identifying daily aggregates may remain.
8. Run concurrency/load at the configured ceiling with the deterministic fake provider, verify SQL budget reservations survive Redis resets, and prove every overload/error path fails closed to guided P0.
9. Send IP, User-Agent, cookie, URL/body, provider payload, and raw-error sentinels through edge/API/egress/provider-SDK paths. Scan combined Caddy, Uvicorn, API, egress, SDK, OTEL, and container stdout/stderr sinks; require zero sentinel retention while bounded error codes and aggregate metrics remain.
10. Capture metrics in the isolated fake collector and assert the exact low-cardinality series/labels, no content identifiers, no public metrics route, and no remote write/shared backend. Separately assert the browser emits `demo_live_fallback` when the API is unavailable.
11. Destroy the disposable Compose project and verify only its explicitly resolved dedicated networks/volumes are gone. Do not inspect or mutate any other Docker project/context.

A paid-provider beta is a separate promotion step. It requires installer E3 clean-install evidence, a dedicated key, provider retention review, fresh signed cap attestation, hard external spend cap, monitoring owner, incident kill switch to guided P0, and documented deletion semantics.

Suggested owner checkpoint: feat(public-demo): complete live synthetic mission acceptance

## Completion definition

P2 is complete only when the exact public route/capability manifest, import-clean kernel boundary, two-layer tool denial, separate migration overlay, synthetic-user isolation, run fencing, atomic budget, refusal receipt, automatic P0 fallback, and zero-residual cleanup all pass in a new disposable environment. Readiness alone is not proof. No public traffic is allowed until adversarial/purge gates and installer E3 pass, and P0 remains the immediate kill-switch throughout beta.
