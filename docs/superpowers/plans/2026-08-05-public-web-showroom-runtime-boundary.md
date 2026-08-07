# Public Demo Runtime Boundary Implementation Plan

> **For the implementing agent:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task by task, superpowers:test-driven-development for each change, systematic-debugging for any unexpected startup behavior, and verification-before-completion before claiming isolation.

**Goal:** Create a fail-closed public-demo process and deployment boundary that can later reuse selected LIA agent-core components without importing or exposing the normal application surface or any existing DEV/PROD resource.

**Architecture:** A separate ASGI entrypoint, standalone Compose project, dedicated PostgreSQL and Redis, resource-identity preflight, minimal middleware, exact route manifest, and reciprocal runtime-profile guards. The normal app remains the default and refuses the public_demo profile. The public app refuses the standard profile. No behavior is selected by a permissive DEMO_MODE branch.

**Tech stack:** FastAPI, Pydantic Settings v2, SQLAlchemy/psycopg, redis-py, Docker Compose, Caddy or the repository's release-edge equivalent, pytest, Ruff, MyPy.

**Program specification:** docs/superpowers/specs/2026-08-05-public-web-showroom-program.md

**Precondition:** P0 has crossed its quantitative go/no-go gate. This plan creates the boundary only; it does not admit agent runs or create synthetic users. The former Habits conflict is resolved (released in v1.28.0, `c5955b73`; `apps/api/src/core/config/__init__.py` is no longer carrying uncommitted changes) — still execute on a verified-clean worktree.

## Non-negotiable constraints

- Do not start, stop, inspect, query, or attach to current DEV or PROD containers, services, databases, Redis, networks, volumes, secrets, or providers.
- Static/unit checks may run locally. Runtime acceptance is deferred to a newly provisioned disposable host/project explicitly authorized for P2; it must not share a Docker daemon context, Compose project, network, volume, hostname, credential, backup target, or provider key with DEV/PROD.
- Perform no Git action. Checkpoints below are owner suggestions only.
- The standard app remains src.main:app and standard remains the default profile.
- The public app must never import src.main, src.api.v1.routes, normal auth routers, admin, connectors, channels, MCP, user MCP, browser, voice, attachments, RAG, skills, telephony, schedulers, or normal startup aggregators.
- Neither database nor Redis has a host-published port. Only the dedicated edge is internet-facing.
- Fail closed before migrations, scheduler registration, graph compilation, or request acceptance when any profile, resource marker, proxy credential, budget dependency, or route-manifest check fails.
- Logs use structlog with bounded error codes. Never log URLs with credentials, marker secrets, proxy secrets, request bodies, cookies, prompts, or messages.

## Target file map

Create:

- apps/api/src/core/runtime_profile.py
- apps/api/src/public_demo_app.py
- apps/api/src/domains/public_demo/__init__.py
- apps/api/src/domains/public_demo/settings.py
- apps/api/src/domains/public_demo/resource_identity.py
- apps/api/src/domains/public_demo/provider_cap_attestation.py
- apps/api/src/domains/public_demo/middleware.py
- apps/api/src/domains/public_demo/health.py
- apps/api/src/domains/public_demo/router.py
- apps/api/src/infrastructure/startup/public_demo.py
- apps/api/public-demo-entrypoint.sh
- apps/api/alembic-public-demo.ini
- apps/api/alembic_public_demo/env.py
- apps/api/alembic_public_demo/script.py.mako
- apps/api/alembic_public_demo/versions/.gitkeep
- apps/api/tests/unit/core/test_runtime_profile.py
- apps/api/tests/unit/public_demo/test_resource_identity.py
- apps/api/tests/unit/public_demo/test_provider_cap_attestation.py
- apps/api/tests/unit/public_demo/test_public_app_boundary.py
- apps/api/tests/unit/public_demo/test_public_demo_middleware.py
- scripts/audit/check_public_demo_boundary.py
- scripts/audit/tests/test_check_public_demo_boundary.py
- infrastructure/public-demo/postgres/init-resource.sh
- infrastructure/public-demo/redis/init-resource.sh
- infrastructure/public-demo/Caddyfile
- infrastructure/public-demo/squid.conf
- infrastructure/public-demo/otel-collector.yaml
- infrastructure/public-demo/prometheus.yml
- docker-compose.public-demo.yml
- .env.public-demo.example
- docs/technical/PUBLIC_DEMO_RUNTIME.md

Modify after reconciling overlapping edits:

- apps/api/src/core/constants.py
- apps/api/src/main.py
- Taskfile.yml
- .github/workflows/ci.yml
- docs/INDEX.md

Do not modify docker-compose.dev.yml, docker-compose.prod.yml, current deploy scripts, normal route aggregation, existing entrypoint, or any runtime environment file.

## Task 1: Define reciprocal pre-import runtime profiles

**Files:** create `runtime_profile.py` and `test_runtime_profile.py`; modify constants and `src/main.py`. Do not add the public settings class to the standard Settings MRO.

1. Write failing tests for a RuntimeProfile StrEnum with standard and public_demo only.
2. Implement a pure environment-only `validate_standard_entrypoint_environment(environ)` that imports neither `src.core.config` nor any application module: standard/missing passes; public_demo or an unknown value raises `RuntimeError` with a bounded code.
3. Implement the reciprocal pure `validate_public_demo_entrypoint_environment(environ)`: only `public_demo` plus `PUBLIC_DEMO_ENABLED=true` passes. Full settings validation occurs later through the standalone public class.
4. Test that importing `src.main` invokes the standard guard before importing `src.core.config`, API routers, logging configuration, schedulers, FastAPI app construction, or any external-resource module. Use isolated module loading and import spies; never open network clients.
5. Test that missing LIA_RUNTIME_PROFILE defaults to standard, preserving current behavior.
6. Run:

~~~bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/test_runtime_profile.py -q
~~~

Expected: missing-module/test failures.

7. Move ordinary imports in `src.main` below the pure guard. Do not instantiate `settings`, configure logging, construct the scheduler/FastAPI object, or import routes before it.
8. Do not add `public_demo` branches to the normal Settings MRO, lifespan, or routes. Standard `.env` loading and effective settings remain byte-for-byte unchanged after the guard passes.
9. Add a static import-order test and rerun the unit test, Ruff, and focused MyPy.
10. Suggested owner checkpoint: feat(runtime): enforce reciprocal application profiles

## Task 2: Specify standalone environment-only public-demo settings

**Files:** create `domains/public_demo/settings.py` and its unit tests; modify constants and the public environment example only.

1. Define constants centrally for absolute TTL, run timeout ceiling, cancellation grace, cleanup batch, retry backoff bounds, maximum server-owned mission bytes, maximum runs per session, maximum concurrent runs, daily reserved-token budget, Redis key prefix, required database name, and exact route paths. The bounded beta has no visitor-prompt byte allowance.
2. Define a standalone `PublicDemoRuntimeSettings(BaseSettings)` with `SettingsConfigDict(env_file=None, extra="ignore")`, `Field` descriptions, strict positive/bounded validators, and `SecretStr` credentials. It imports constants and `runtime_profile` only; importing it must not execute `src.core.config.__init__`.
3. Add tests with a sentinel standard `.env` containing a standard database DSN/provider secret: public settings must ignore the file and read only the explicit injected environment. The standard Settings class remains independently byte-for-byte equivalent with every public variable absent.
4. Add public-profile model/entrypoint invariants:
   - TTL is greater than run timeout plus cancellation grace;
   - the cookie is Secure, HttpOnly, SameSite=Lax, and scoped to /api/public-demo;
   - pipeline is the only orchestration mode;
   - normal session-cookie name and demo-cookie name differ;
   - public proxy secret, token HMAC key, resource ID, provider key, and attestation trust material are distinct; the database incarnation ID is generated only by fresh PostgreSQL initialization and is not an environment setting;
   - database name is exactly lia_public_demo;
   - Redis key prefix begins lia-public-demo and cannot equal any standard prefix;
   - debug, docs, OpenAPI, Langfuse, background feature flags, and content caches are disabled;
   - provider budgets are finite and non-zero.
5. Define and test RFC 8785 canonical JSON plus detached Ed25519 provider-cap attestation bound to `kid`, public resource ID, the fresh database incarnation ID read from the verified PostgreSQL marker, dedicated key fingerprint, provider account/project, UTC budget day/month, hard daily/monthly limits, provider spend-to-date and remaining integer microusd, evidence source `provider_api | operator`, issue time, and expiry no later than both 24 hours and the UTC day boundary. The offline signing private key is never a runtime setting; runtime accepts only current/next public verification keys. Operator-source evidence is labeled attested, not machine-verified.
6. Write a table-driven failure test for every invariant and attestation field, including stale, mismatched-key, over-limit, bad-signature, and unknown-source cases.
7. Add `.env.public-demo.example` containing names and safe non-secret defaults but no generated secret. Compose may pass it explicitly; neither standard nor public Pydantic settings loads it implicitly.
8. Add a static test proving `.env.example` and `.env.prod.example` do not enable `public_demo`.
9. Run focused tests and expect all to pass after minimal implementation.
10. Suggested owner checkpoint: feat(public-demo): add fail-closed bounded settings

## Task 3: Prove resource identity before migrations

**Files:** create resource_identity.py, the empty public-demo Alembic overlay, their tests, and the two init scripts.

The isolated provisioning process generates one high-entropy `PUBLIC_DEMO_RESOURCE_ID`. On every initialization of an empty tmpfs cluster, the Postgres init script generates its own fresh 256-bit database incarnation ID from the container CSPRNG, creates database `lia_public_demo`, and sets its database COMMENT to `lia-public-demo:<resource-id>:<incarnation-id>`. No environment variable, CLI flag, restored file, or operator value may supply the incarnation ID. The Redis init script writes `lia-public-demo:resource-marker` with the resource ID and no expiry. These markers identify a public-demo resource/incarnation; they are not authentication secrets. A code-owned operator command may write the verified IDs to a bounded attestation-request file, but neither init nor application logs print them.

1. Unit-test pure marker construction and validation. Empty, malformed, inconsistent, standard-looking, or wrong-resource markers fail with bounded codes.
2. Test async `verify_database_identity(connection, expected_id)` using a fake connection. It must query `current_database()` and the database comment, require the exact database name/resource marker, validate and return the database-generated incarnation ID, and redact the DSN from errors.
3. Test async verify_redis_identity(client, expected_id) using a fake Redis. It requires the exact sentinel key/value and configured key prefix.
4. Test verify_public_demo_resources runs both checks and aggregates no raw exception text.
5. Create an empty public-demo Alembic overlay with version table `alembic_version_public_demo`. Test the foundation entrypoint order statically: wait for dedicated hosts; verify both markers; apply the existing base Alembic head to the isolated database; apply `alembic-public-demo.ini` to that same database; then exec uvicorn src.public_demo_app:app. Any migration text before marker verification fails. The separately gated live plan later inserts one import-clean LangGraph persistence-schema preparation step after the base head and before the now-nonempty overlay, followed by an exact schema/fencing fingerprint; the checker must recognize only that code-owned module and order.
6. Add static guards proving the overlay version location is absent from standard `alembic.ini` and `alembic/env.py`, the standard entrypoint never references it, and future public-demo revisions cannot live in the base versions directory.
7. The entrypoint refuses database or Redis hostnames other than public-demo-postgres and public-demo-redis in the Compose profile. It never invokes the normal docker-entrypoint.sh.
8. Init scripts use strict shell mode, accept only the resource ID through environment/stdin-safe expansion, validate its format, generate the incarnation from the CSPRNG, and never print either value. Static guards reject a `PUBLIC_DEMO_INCARNATION_ID` setting or override path.
9. A fresh-initialization test creates two disposable empty clusters and proves distinct incarnation IDs; the attestation issued for the first is rejected against the second before readiness or admission. This is the mandatory database-recreation oracle.
10. Run tests plus shellcheck if available. Missing shellcheck is reported as not verified, not silently clean.
11. Suggested owner checkpoint: feat(public-demo): verify isolated data resources before migration

## Task 4: Build a minimal ASGI application factory

**Files:** create public_demo_app.py, health.py, router.py, middleware.py, startup/public_demo.py, and their unit tests.

1. Write tests against `create_public_demo_app(runtime)`: exact public routes are `GET /health`, `GET /ready`, and the empty `APIRouter` prefix `/api/public-demo/v1` reserved for the next plan. Docs, redoc, OpenAPI, metrics, normal `/api/v1`, auth, admin, chat, connectors, MCP, and WebSockets must be absent. Construction accepts a standalone `PublicDemoRuntimeSettings` instance and cannot import standard Settings.
2. Test health is liveness-only. Readiness uses a code-owned required-component registry. The boundary foundation requires runtime profile, resource identity, proxy configuration, isolated Redis, and a fresh valid provider-cap attestation. The live plan later adds schema/fencing verification, fenced checkpointer/Store, public state/plan/run kernel, agent catalogue and model resolver, graph, durable admission/reconciliation, cleanup, and OTLP components before any live route can report ready.
3. Test lifespan call order with injected fakes. The boundary foundation initializes only bounded logging, isolated DB/Redis handles, resource checks, offline attestation validation, validated private-collector configuration, and the readiness registry. It does not create the metric pipeline, compile a graph, initialize pricing/provider clients, a checkpointer, tools, ORM mappers, normal caches, or a scheduler; the live plan adds those through public-only factories after the import-clean seams exist.
4. Test shutdown closes the boundary DB/Redis handles in order. The live plan extends shutdown to drain admitted runs before closing checkpointer/DB/Redis. A failed shutdown step logs a bounded component name, not connection details.
5. Build a public-only middleware stack: proxy-secret verification, trusted host, request ID, body-size ceiling, strict content type, security headers, and bounded error normalization. Do not reuse setup_middleware unless an audited pure subset is first extracted and proven not to add auth/session/CORS behavior.
6. Verify proxy-secret comparison uses secrets.compare_digest; absent/wrong secrets return the same 404-shaped response; health may be separately limited to the edge network.
7. Configure FastAPI with `docs_url`, `redoc_url`, and `openapi_url` all `None`, disable Uvicorn access logs in the entrypoint, and install a bounded third-party logger policy. Do not expose internal exception strings.
8. Run:

~~~bash
cd apps/api && .venv/Scripts/pytest tests/unit/public_demo/test_public_app_boundary.py tests/unit/public_demo/test_public_demo_middleware.py -q
~~~

Expected: all focused tests pass without DB, Redis, LLM, or network access.

9. Suggested owner checkpoint: feat(public-demo): add isolated ASGI application factory

## Task 5: Add an executable import and route boundary guard

**Files:** create check_public_demo_boundary.py and its tests; modify Taskfile and CI.

1. The checker parses the complete transitive import graph from `public_demo_app.py`, `domains/public_demo`, and `startup/public_demo`. Use an explicit positive allowlist and an explicit denied-prefix registry; lazy imports and `importlib` targets are included.
2. Deny direct or transitive imports of `src.main`, `src.api.v1.routes`, the `src.core.config` package/standard `settings` singleton, the standard ORM registry, ordinary LLM factory/key cache, domains.auth/router, connectors, channels, user_mcp, mcp, browser, voice, attachments, rag_spaces, skills, telephony, normal startup aggregators, and standard scheduler composition.
   The later live plan must satisfy this by extracting import-clean execution/settings/LLM/provider seams; importing the current AgentService or normal graph and waiving their transitive closure is not acceptable.
3. Build the public app with dependency fakes and compare its normalized route/method set to a code-owned manifest. Any unexpected method/path fails.
4. Parse runtime/profile settings and require reciprocal guard calls in both entrypoints.
5. Parse Compose and require no references to external DEV/PROD networks, named DEV/PROD volumes, normal env files, standard container names, or host ports for PostgreSQL/Redis.
6. Parse both Alembic configurations and entrypoints. Reject any public-demo version path/import in the standard configuration/registry/entrypoint and any overlay command before resource-marker verification. Reject ORM model/repository imports from the running public app; the base Alembic subprocess is the only public workflow allowed to import the standard model registry, after marker proof and before ASGI startup.
7. Include self-tests proving each forbidden import, route, profile omission, migration leakage, and Compose sharing mutation is detected.
8. Add task lint:public-demo-boundary and delegate to it from CI through the repository parity pattern; do not inline duplicate CI logic.
9. Run checker self-tests and the task. Expected: green on the exact boundary.
10. Suggested owner checkpoint: test(public-demo): enforce import route and resource boundary

## Task 6: Create the standalone disposable deployment definition

**Files:** create docker-compose.public-demo.yml, Caddyfile, .env.public-demo.example; extend checker tests.

1. Set the Compose top-level name to `lia-public-demo`. Define only `public-demo-edge`, `public-demo-api`, `public-demo-egress`, `public-demo-otel`, `public-demo-prometheus`, `public-demo-postgres`, `public-demo-redis`, `postgres-marker-init`, and `redis-marker-init`.
2. Build the API from the same source/image recipe but override entrypoint to public-demo-entrypoint.sh and command to src.public_demo_app:app. Never use src.main:app.
3. PostgreSQL data uses tmpfs for the bounded beta and no backup mount. Redis runs with appendonly no and save disabled. Neither publishes a host port.
4. Use data, app, observability, ingress, and outbound networks unique to this file. Edge joins ingress plus the internal app network; API joins internal app/data/observability only; egress joins internal app plus outbound and is the sole outbound member; PostgreSQL/Redis join data only; OTEL/Prometheus join observability only. The API has no direct Internet route or published port and exports OTLP only to the collector.
5. Edge accepts only the server-side website proxy path over TLS. The API still validates PUBLIC_DEMO_PROXY_SECRET. No browser receives that secret.
6. Give the API no Docker socket, host filesystem, GPU device, SSH material, OAuth secret, connector credential, normal `.env` file, or shared volume. Use read-only rootfs, tmpfs `/tmp`, `cap_drop: ALL`, no-new-privileges, explicit memory/CPU/PID limits, and a non-root user.
7. Configure the egress proxy with default deny, exact code-reviewed provider hostname and port 443 only, no IP literal/wildcard/visitor-controlled destination, DNS rebinding protection, and access logs disabled. The public provider client receives this proxy explicitly; a disposable test proves the provider fake is reachable only through it and a forbidden canary host is unreachable.
8. Use a separate hard-capped provider credential dedicated to public demo. Never mount standard provider-key storage. Mount its signed, time-bounded cap attestation and public verification key read-only; the offline signing private key is absent from every container and env file.
9. Disable Caddy, Uvicorn, egress, and SDK access/request logs or route them through bounded redaction. No combined container log may retain sentinels for IP, UA, cookie, request URL/body, provider payload, or raw exception.
10. The API's public-only OpenTelemetry SDK exporter pushes OTLP to the dedicated collector; the collector exposes a Prometheus endpoint only on the internal observability network, and the isolated Prometheus service scrapes it. Neither collector nor Prometheus publishes a host port or remote-writes to an existing backend; the public ASGI app exposes no metrics route.
11. Add health checks that prove only local component state. No check calls an external provider during Compose startup. Readiness describes an operator-source attestation as attested, not provider-verified.
12. Statically render Compose with an isolated generated test env only after all variables are supplied; `docker compose config` is allowed because it does not contact the daemon. Do not run `up`, `pull`, `ps`, `inspect`, or `down`.
13. Require the boundary checker to reject any shared/published resource, direct API egress, broad proxy ACL, observability remote-write, or access-log enablement mutation.
14. Suggested owner checkpoint: feat(public-demo): define disposable isolated deployment

## Task 7: Document operator ceremony and a no-contact acceptance gate

**Files:** create PUBLIC_DEMO_RUNTIME.md; modify docs/INDEX.md.

Document an exact ceremony:

1. Verify the P0 evidence gate and record the approval.
2. Provision a new host or isolated CI runner with no DEV/PROD Docker context.
3. Generate a fresh resource ID and four distinct secrets locally; store them in the new environment only.
4. Create the isolated resources. PostgreSQL generates the non-overridable incarnation ID; verify both markers before migration, produce the bounded attestation request, and require a new same-day provider attestation that binds that incarnation and includes cumulative external spend. Every tmpfs PostgreSQL recreation repeats this sequence and invalidates the prior attestation automatically.
5. Apply the dedicated Compose file only on that host.
6. Verify route manifest, readiness components, caps, and absence of shared resources.
7. Destroy the entire disposable project after tests; no backup is taken.
8. Record only bounded results and digests, never secrets or user content.
9. Enable website proxy routing only after the live-mission plan is green.
10. Roll back website routing to P0 before stopping the disposable API.

Add explicit forbidden commands/targets: any current DEV/PROD Compose file, context, project, volume, network, host, secret manager path, or provider key. State that this plan itself authorizes none of these runtime actions.

Run `task lint:docs` plus the repository's formatting/whitespace gate on the new documentation. Suggested owner checkpoint: docs(public-demo): document isolated runtime ceremony

## Task 8: Boundary completion gate

On a reconciled worktree, run only static and unit checks first:

~~~bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/test_runtime_profile.py tests/unit/public_demo scripts/audit/tests/test_check_public_demo_boundary.py -q
task lint:public-demo-boundary
cd apps/api && .venv/Scripts/ruff check src/public_demo_app.py src/domains/public_demo src/infrastructure/startup/public_demo.py tests/unit/public_demo
cd apps/api && .venv/Scripts/mypy src/public_demo_app.py src/domains/public_demo src/infrastructure/startup/public_demo.py
docker compose --env-file .env.public-demo.test -f docker-compose.public-demo.yml config --quiet
~~~

The test env is generated in a disposable test directory and removed recoverably; it is never derived from an existing environment. Compose config must not contact Docker.

Runtime acceptance remains blocked until the owner explicitly authorizes a new disposable environment. There, prove marker mismatch before any migration, exact route set, no unexpected egress, resource ceilings, read-only filesystem, no host ports except edge, and destruction without residual volume/network. Never use a current instance as a convenient smoke target.

Suggested owner checkpoint: feat(public-demo): complete isolated runtime boundary

## Completion definition

The boundary is complete only when static import/route/Compose guards and unit tests prove that selecting public_demo cannot start the normal application, selecting standard cannot start the public application, and a marker mismatch prevents migrations. No live agent route exists yet. Passing this plan does not authorize user/session creation, LLM calls, website routing, or public traffic; those belong to the separately gated live-mission plan.
