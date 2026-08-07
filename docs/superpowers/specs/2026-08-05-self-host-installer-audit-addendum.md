# Self-Host Installer — Static Audit Addendum

**Date:** 2026-08-05  
**Status:** Binding correction to the validated design; implementation and activation remain unproven  
**Amends:** `docs/superpowers/specs/2026-07-29-self-host-installer-design.md`  
**Execution plan:** `docs/superpowers/plans/2026-08-05-self-host-installer-activation.md`  
**Architecture decision allocation:** ADR-215 (ADR-179 is already occupied)
**Reservation snapshot:** source commit `1c1c5d6655cb4a8aa3d19905d58c8f2f14d8de0f`
(not an exact release tag) plus the inspected 2026-08-05 worktree; ADR-214 was the highest
allocated file and ADR-215 was absent.
**Consolidation re-audit (2026-08-05, HEAD `c5955b73`, v1.28.0):** Habits was committed and
released; the worktree is clean apart from these program documents. ADR-214 remains the highest
allocated file, ADR-215 remains absent, `ADR-179` remains occupied, and the July 29 plan still
contains exactly 70 unchecked boxes. Every blocker's observed fact (B01-B15) was re-verified on
`c5955b73`; line references may drift by a few lines and remain content-accurate. One additional
blocker was found and is recorded as B10-bis inside B10 below.

## Purpose and precedence

This document corrects the July 29 design without deleting or replacing it. The original
document remains the record of the product intent and the choices made during brainstorming.
Where this addendum conflicts with the original design or its July 29 implementation plan,
this addendum governs implementation and release activation.

ADR-215 is a reservation, not permission to overwrite. Immediately before creating the ADR,
the implementer must reconcile the live worktree and both ADR indexes. If ADR-215 exists or is
reserved concurrently, stop before writing, choose the smallest unused number above the live
maximum, and update this addendum, the activation plan, the ADR filename/title, and both index
entries in one coherent patch. Existing ADR-214/index changes must be preserved.

The review was static and non-destructive. It inspected repository files only. It did not
start Docker, an application process, a database, a provider call, a DEV environment, or a
PROD environment. Therefore every runtime property remains unproven until the disposable
qualification gates in this addendum have passed.

## Verdict

The one-command self-host path is **not implemented and is not activation-ready**.
`install.sh`, the `scripts/install/` package, the installer settings validator, the Caddy
template, and the planned Compose overlays are absent.

The July 29 decision to build the API and Web images locally remains the only coherent v1
default. It must remain the default until the exact GHCR API and Web digests have been built
once, qualified together on disposable amd64 and native arm64 hosts, and promoted without a
rebuild. A mutable tag such as `latest`, `1`, `1.27`, or `1.27.14` is never an installer
input.

The target after qualification is a dual-mode installer:

1. `local` — current v1 default; build the checked-out source and retain
   `lia-api:local` / `lia-web:local`.
2. `prebuilt` — locked until qualification; consume a release bundle and the exact
   `repository@sha256:...` references from its manifest, run Compose with `--no-build`,
   and retain `--local-build` as the permanent fallback.

## Evidence conventions

Each blocker below separates three things:

- **Observed fact:** directly visible in the current files.
- **Failure consequence:** the behavior that follows from that fact.
- **Binding amendment:** the implementation and gate required to remove the blocker.

Line references describe the 2026-08-05 static snapshot and may move when implementation
starts. Tests must bind to symbols and structured data rather than preserving these line
numbers.

## Fifteen activation blockers

### B01 — The installer surface does not exist

**Observed fact.** The repository contains neither `install.sh` nor `scripts/install/`.
`apps/api/scripts/validate_settings.py`, `docker-compose.devops.yml`, and
`infrastructure/caddy/Caddyfile.template` are also absent. The July 29 plan has exactly 70
unchecked boxes and zero completed boxes.

**Failure consequence.** There is no command whose behavior, idempotence, secret handling, or
fresh-install result can be tested.

**Binding amendment.** Implement the path in dependency order under TDD. Keep the local-build
mode as the default until Gate G5. The mere presence of files does not remove this blocker;
the hermetic gates and disposable qualification must also pass.

### B02 — Published app images have no release-consumable identity contract

**Observed fact.** `.github/workflows/release.yml:82-103` publishes semver-derived tags but
does not retain the Buildx digest in a release manifest. The release body then tells users to
pull `${{ github.ref_name }}` at lines 170-175, although the metadata step emits normalized
semver tags. The release build does not pass the API provenance arguments supported by
`apps/api/Dockerfile.prod:123-131`. Only a backend lockfile SBOM is attached
(`.github/workflows/release.yml:105-129`).

**Failure consequence.** The installer cannot prove which API and Web artifacts it will run,
cannot prove both architectures belong to the same release, and cannot roll back to an
immutable artifact pair.

**Binding amendment.** Build each app once as a candidate, capture its multi-platform index
digest plus each amd64/arm64 child-manifest and OCI config digest, attach API and Web SBOMs plus
`lia-self-host-manifest.json`, qualify those exact
digests, and promote semver tags from the qualified digests without rebuilding. Pass
`APP_VERSION`, `GIT_COMMIT_SHA`, and `BUILD_DATE` from release context. Release
documentation must display digest pulls, not `github.ref_name`.

### B03 — The current Web release image is host-specific

**Observed fact.** `apps/web/Dockerfile.prod:76-107` bakes `NEXT_PUBLIC_*` values during
the Next.js build and defaults the public API and app URLs to `http://localhost:8000` and
`http://localhost:3000`. `NEXT_PUBLIC_APP_URL` is also consumed by metadata, sitemap,
robots, JSON-LD, and public-page modules, whose fallback is the hosted-project origin.
`apps/web/next.config.ts:96-105` confirms that public values are inlined. The release workflow
supplies none of these build arguments. The same Next.js configuration already defines an
explicit empty string as the same-origin API contract and proxies `/api/v1/*` to the API
service at `apps/web/next.config.ts:214-229`.

**Failure consequence.** One generic GHCR Web digest cannot currently serve arbitrary LAN,
proxy, or Caddy installations.

**Binding amendment.** Build release Web images with `NEXT_PUBLIC_API_URL=""`, remove
`NEXT_PUBLIC_APP_URL`, and obtain the absolute canonical origin at request time from validated
server-only `APP_URL_SERVER`. Metadata, sitemap, robots, JSON-LD, and public routes must use
that runtime origin; browser calls remain same-origin and the server-side rewrite targets
`http://api:8000`. Inventory every remaining public build variable. The generic prebuilt v1
sets telemetry off and Firebase public fields empty, reports push notifications as unavailable,
and retains local build for deployments that need custom public build values. Remove
`NEXT_PUBLIC_GOOGLE_CLIENT_ID` from the mandatory installer contract: it occurs in Docker,
Compose, and documentation but has no Web source consumer in the audited snapshot.
Cross-workstream note: the public-showroom P0 plan introduces two additional public build
variables, `NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT` and `NEXT_PUBLIC_SHOWROOM_PROOF_SHA`; the
public-variable inventory must classify both as hosted-site-only (`legacy`/empty in the generic
prebuilt image). The hosted showroom release that sets `NEXT_PUBLIC_PRODUCT_TELEMETRY=true` is a
distinct build of the hosted site, never the generic GHCR artifact, which stays telemetry-off.

### B04 — Compose has no safe app-image mode switch

**Observed fact.** `docker-compose.prod.yml:129-142` fixes the API image to
`lia-api:local` and includes a build definition. Lines 235-256 do the same for Web. The API
environment independently fixes `SKILLS_SCRIPT_SANDBOX_IMAGE=lia-api:local` at lines
160-168.

**Failure consequence.** Substituting a prebuilt API image can silently leave the script
sandbox on a different image; a normal Compose invocation may also rebuild instead of using
the qualified digest.

**Binding amendment.** Parameterize the app images as
`LIA_API_IMAGE` and `LIA_WEB_IMAGE`, both defaulting to the existing local names.
Derive `SKILLS_SCRIPT_SANDBOX_IMAGE` from `LIA_API_IMAGE`. Local mode runs `build`;
prebuilt mode runs `pull api web` followed by `up --no-build`. Tests must inspect every
generated argv and reject a prebuilt command without `--no-build`.

### B05 — A fresh source tree does not satisfy every host-path contract

**Observed fact.** Production Compose bind-mounts PostgreSQL initialization, seed SQL, system
knowledge, system skills, observability configuration, and
`./apps/api/config:/app/config:ro` (`docker-compose.prod.yml:33-35,173-197` and the
observability services below line 316). `apps/api/config/` is ignored
(`.gitignore:113`) and can be absent in a fresh checkout. The default backup path is outside
the repository at `../lia-data/postgres-backups` (`docker-compose.prod.yml:78-88`).

**Failure consequence.** Prebuilt application images alone are insufficient, and Compose can
create missing bind paths with unsuitable ownership or the wrong file-versus-directory type.

**Binding amendment.** Define and test an allowlisted self-host release bundle containing
every required read-only runtime asset. It also embeds one deterministic
`lia-self-host-source-context.tar.gz` generated from the exact API and Web Docker build contexts at
the release source identity. The manifest records both the embedded archive SHA-256 and its
canonical extracted-tree SHA-256. Before Compose, create `apps/api/config/` and the resolved backup
directory with explicit modes, then validate that every bind source has the expected type. Local
mode in a checkout uses the full source tree; `--local-build` in an official release directory
must verify and extract the embedded source context before any mutation. Prebuilt mode accepts only
the qualified bundle and its manifest. The release verifies the outer archive SHA-256 before
extraction and the installer verifies the canonical host tree; local fallback additionally verifies
the embedded source archive and tree. Both archives exclude secrets, caches, generated outputs, and
Python bytecode; the production host bundle excludes tests, while the source-context inventory
contains only files required by the effective Docker build contexts. `install.sh` rejects
pre-existing installer bytecode and uses Python's no-bytecode mode so verification cannot mutate its
own tree.

### B06 — Third-party services are tag-addressed

**Observed fact.** PostgreSQL, Redis, backup, observability, management, and optional Caddy
images are specified by tags, for example `pgvector/pgvector:pg16`,
`redis:7.4-alpine`, and `grafana/tempo:2.6.1`
(`docker-compose.prod.yml:8-9,58-60,103-106,320-321`).

**Failure consequence.** Pinning only the two LIA images does not make the complete
self-host stack reproducible, and describing it as wholly immutable would be false.

**Binding amendment.** The release manifest records a qualified digest for every Compose
image used by core, observability, skill-sandbox, and Caddy modes. The installer generates an
image-lock override from that manifest. Local mode may continue to resolve the documented
tags, but its report must label dependency resolution as local and non-release-locked.

### B07 — Settings validation is neither canonical nor complete

**Observed fact.** The real settings composition is `Settings` in
`apps/api/src/core/config/__init__.py:93-171`, instantiated globally at lines 394-401 with a
hard-coded `.env` source. The planned `validate_settings.py` is absent. The existing
`apps/api/scripts/validate_config.py` is not an installer validator: it declares Google and
OpenAI mandatory at lines 375-384, rejects the supported production LAN cookie posture at
lines 680-699, and can contact PostgreSQL and Redis at lines 707-749.
`SecuritySettings.fernet_key` is required but has no Fernet-format validator
(`apps/api/src/core/config/security.py:131-150`).

**Failure consequence.** Two validators would drift, LAN installs can be rejected for the
wrong reason, and a malformed encryption key can survive the pre-start check.

**Binding amendment.** Add one pure Settings-validation entry point that starts no service
and formats Pydantic errors deterministically. Make the legacy validator delegate its
Pydantic phase to that entry point. Add a field validator that accepts only a URL-safe
base64-encoded 32-byte Fernet key. Installer validation bypasses the API entrypoint and runs
with `--no-deps`.

### B08 — Reference seeds are opt-in, not automatic

**Observed fact.** The July 29 design says the API entrypoint automatically seeds a fresh
database. Current Compose defaults `APPLY_SEEDS` to false
(`docker-compose.prod.yml:164-168`), and the entrypoint requires both explicit
`APPLY_SEEDS=true` and a confirmed empty personalities table
(`apps/api/docker-entrypoint.sh:21-68`). A static guard deliberately enforces that
fail-closed behavior (`apps/api/tests/unit/test_entrypoint_seed_gate_guard.py:140-184`).

**Failure consequence.** Following the original orchestration can produce a migrated but
unseeded instance.

**Binding amendment.** Fresh-install orchestration explicitly arms seeding for the first API
start and removes that intent immediately after the first `/ready` proves the blocking entrypoint
completed, before provider/admin bootstrap can fail or be interrupted.
Normal boots and reconfiguration remain seed-inert. No row-count heuristic may arm seeding.

### B09 — The five-file seed bundle is not atomic or self-verifying

**Observed fact.** The entrypoint invokes one `psql -f` process per file without
`ON_ERROR_STOP` (`apps/api/docker-entrypoint.sh:56-63`). Several seed files delete before
inserting; `personalities_seed.sql:9-16` is one example. They do not share a transaction,
and count mismatches are warnings rather than failures
(`personalities_seed.sql:367-390`). The directory contains five independent SQL files.

**Failure consequence.** A mid-bundle failure can commit partial data, make personalities
non-empty, and prevent a safe resume while the entrypoint still prints a success message.

**Binding amendment.** Apply all five files through one `psql` process with
`ON_ERROR_STOP=1` and one transaction. A final SQL contract raises exceptions unless all
five domains meet their postconditions, then records the seed-bundle version in the same
transaction. Failure-injection tests must prove rollback to the pre-seed state and a clean
retry. The wrapper recomputes the exact six-file seed-plus-verifier digest before `psql` and
rejects a mismatch. Raw SQL uses the existing SQLAlchemy enum's persisted member-name token
`SELF_HOST_SEED_BUNDLE`; an ORM round-trip test prevents name/value drift.

### B10 — “At least one provider” does not produce the current functional core

**Observed fact.** Current code defaults mix providers: planner and query analysis use Qwen,
router and semantic validation use OpenAI
(`apps/api/src/domains/llm_config/constants.py:574-662`), and response uses Qwen
(`constants.py:872-893`). The adapter resolves DB cache, then environment, then
`NOT_CONFIGURED` (`apps/api/src/infrastructure/llm/providers/adapter.py:92-133`), while
the model and startup cache call the encrypted `provider_api_keys` table the sole source of
truth (`apps/api/src/domains/llm_config/models.py:1-30`;
`apps/api/src/infrastructure/startup/caches.py:116-145`). The one-time migration imports
some environment keys but omits Qwen
(`apps/api/alembic/versions/2026_03_08_0002-migrate_env_keys_to_db.py:28-74`).

**Failure consequence.** One arbitrary provider key can pass the questionnaire while the
first real chat fails in a different provider slot.

**Binding amendment.** The current-core acceptance baseline requires both `openai` and
`deepseek` — the providers of the audited POST-SEED effective core (B10-bis below; the
pre-seed `qwen` assumption of this paragraph's first draft did not survive the mechanical
derivation). Store both through a backend
bootstrap service as encrypted DB rows; do not persist either key in the generated
environment or installer state. An anti-drift test derives the provider set from effective
defaults and fails if the questionnaire contract becomes incomplete. After commit, reuse the
existing cross-worker LLM-cache invalidation contract, then recreate the API without rebuild and
wait for readiness so every worker reloads the committed keys before verification/chat.

**B10-bis — The reference LLM-override seed overwrites the audited core defaults (found by the
2026-08-05 consolidation re-audit).**

**Observed fact.** `infrastructure/database/seeds/llm_config_seed.sql` is a production-database
extraction of the maintainer's admin-configured settings. It inserts 42 rows into
`llm_config_overrides`, of which 27 set `provider='deepseek'` — including the core slots
`planner`, `query_analyzer`, `query_agent`, `react_agent`, `response`, and `semantic_validator` —
plus one `gemini` (`vision_analysis`) and one `elevenlabs` (`voice_tts`). `LLMConfigOverrideCache`
loads these rows at startup before any `get_llm()` call
(`src/infrastructure/startup/caches.py`), so database overrides take precedence over the code
defaults that the original B10 audited.

**Failure consequence.** The activation plan as originally written cannot pass its own gates: it
applies the five seeds (B09), stores OpenAI+Qwen keys (B11), then verifies that every core slot
resolves to OpenAI/Qwen (B12) — but after seeding, the core resolves to DeepSeek with no key, so
the verifier fails and the G3 hermetic chat fails. This is exactly the "first real chat fails in a
different provider slot" class B10 exists to close, reintroduced by the seed itself.

**Binding amendment (owner arbitration, 2026-08-06 — supersedes the earlier reconciliation
proposal).** The seeded overrides are **kept as-is**: they are the proven production
configuration, and a self-hoster can change them later through the Admin UI. No bootstrap
reconciliation runs. Instead, the baseline provider contract is derived from the **post-seed
effective configuration** (DB override when present, else code default) across reachable
default-enabled LLM slots — never from code defaults alone. On the audited seed this makes
DeepSeek a required core provider alongside OpenAI (core slots `planner`, `query_analyzer`,
`query_agent`, `semantic_validator`, `response`, `react_agent` resolve to DeepSeek; `router`,
`context_resolver`, `hitl_classifier`, `briefing` resolve through `NULL` overrides to their
OpenAI code defaults). The mechanical derivation (2026-08-06) proved the set is exactly
`{deepseek, openai}`: the seed overrides EVERY qwen code default, and all sixteen slots absent
from the seed default to OpenAI — so Qwen is an optional Admin-UI provider, never a required
install key. The anti-drift
test derives this set mechanically from code defaults plus the parsed seed, the questionnaire
requires one key per derived required provider, and the installation verifier checks coverage on
the same post-seed effective configuration. The final report names the optional capabilities that
stay degraded without their key: `vision_analysis` (Gemini, seeded), `voice_tts` (ElevenLabs,
seeded), and MCP App widgets (`mcp_app_react_agent`, Anthropic code default; reachable only after
an MCP server with interactive widgets is configured). The hermetic qualification chat therefore
needs base-URL overrides for every required provider, including DeepSeek.
Personalities/translation postconditions stay exact (re-verified: 14 personalities,
84 translations).

This technical baseline is distinct from the public zero-friction promise. Before any
"turnkey", "one key", or "zero-friction" call to action, Gate G6 requires at least one
named mono-provider profile that explicitly remaps and qualifies every enabled core LLM
slot and required capability. A generic OpenAI-compatible endpoint is never assumed to be
capability-compatible. A local Ollama profile is not advertised without an exact
model-and-hardware matrix.

### B11 — Admin bootstrap bypasses the stated password authority and exposes secrets in argv

**Observed fact.** `apps/api/scripts/data/create_admin.py:31-33` defines
`admin@example.com/admin123` defaults. It creates or promotes an account and hashes the
password directly at lines 36-80 without calling
`validate_password_strict` (`apps/api/src/core/security/password_validation.py:85-103`).
The July 29 plan passes the password as a command-line argument.

**Failure consequence.** Backend policy is not authoritative and credentials can be exposed
through process listings, diagnostic argv capture, or logs.

**Binding amendment.** Refactor admin creation into an uncommitted backend operation that
always calls `validate_password_strict`. The combined install bootstrap reads one JSON
payload from stdin, creates/promotes the admin, and upserts the two encrypted provider keys
in one database transaction. No default password and no password/key argv flag remain in
the installer path.

### B12 — `/ready` is necessary but not an installation proof

**Observed fact.** `apps/api/src/api/health.py:18-25` explicitly limits readiness to
PostgreSQL and Redis and says agent/graph startup can fail while it stays green.

**Failure consequence.** Polling `/ready` cannot prove seeds, admin login, provider
configuration, the graph, or a chat response.

**Binding amendment.** Keep `/ready` as the infrastructure gate, then run a non-secret
backend installation verifier for seed marker/postconditions, admin status, decryptable
provider rows, and effective-provider coverage. It requires the one live Alembic revision to equal
the code's single head and the marker to equal the expected seed-bundle SHA-256. The disposable
qualification adds an admin login and one hermetic fake-provider chat through the public HTTP path.

### B13 — Resume cannot recover the secrets that later steps require

**Observed fact.** The July 29 state model deliberately excludes the admin password while
marking questions complete, then bootstrap requires that password
(`docs/superpowers/plans/2026-07-29-self-host-installer.md:725-753,774-788`). Its state
does not carry a schema version, installer identity, artifact digests, generated-file
fingerprints, or the last failure.

**Failure consequence.** A process restart after question collection can skip the only step
that held ephemeral credentials, or resume against changed inputs/artifacts.

**Binding amendment.** State stores only non-secret facts:
`schema_version`, installer/release identity, all sanitized public answers, mode, exact image
digests, seed/bundle identities, completed steps, attempt counters, last non-secret error code,
and SHA-256 fingerprints of generated files.
When bootstrap is incomplete, resume re-prompts only the admin password and provider keys.
Fingerprint or schema mismatch stops with an actionable message; it never silently resumes.

### B14 — Failure handling has no defined rollback boundary

**Observed fact.** The July 29 deploy step runs build, validation, `up -d`, readiness, and
admin creation but has no rollback path. The repository already has tested semantics that
capture prior app images, poll readiness, write a manifest, restore the previous pair, and
recheck readiness (`scripts/deploy/lib/deploy_readiness_gate.sh:36-116`).

**Failure consequence.** A re-run can overwrite `lia-*:local` and leave a previously
working installation unavailable. On a first install there is no prior application image
to restore, so promising a universal rollback would also be false.

**Binding amendment.** Reuse the existing readiness-gate state machine behind a compose-argv
interface. For an existing qualified installation, restore the previous exact image pair
and configuration backup, then recheck. For a first install, stop only installer-created
containers, preserve volumes and generated backups, record the failed step, and provide the
resume command. Database upgrade rollback remains outside v1.

### B15 — The baseline plan contains contradictory wiring and lacks an installability gate

**Observed fact.** ADR-179 already names
`docs/architecture/ADR-179-Structured-Output-Chokepoint-And-Thinking-Budget-Floor.md`;
ADR-214 is the highest allocated file in the audited tree, so the installer allocation is
ADR-215. The July plan proposes a colon-separated `COMPOSE_FILE`, while
`scripts/deploy/lib/deploy_readiness_gate.sh:23-32` passes that value as one `-f`
filename. The plan also proposes removing the Docker socket even though skill scripts are
enabled by default with the container sandbox
(`apps/api/src/core/config/skills.py:179-183,263-281`) and execution calls
`docker run` (`apps/api/src/domains/skills/executor.py:168-238`). CI replays migrations
and builds source images but performs no fresh installer smoke
(`.github/workflows/ci.yml:332-406,524-550`).

**Failure consequence.** The documented overlay command is invalid, default script skills
can break, the ADR index can collide, and a release can be green without proving its
installer or exact published digests.

**Binding amendment.** Use ADR-215. Python commands always carry repeated `-f` argv pairs;
the Bash deploy gate lets Compose interpret `COMPOSE_FILE` instead of wrapping the pair in
one `-f`. Move the socket and `group_add` into a distinct
`docker-compose.skill-sandbox.yml`; generic self-host installs set script skills false
unless that overlay is explicitly selected. Add hermetic installer/config matrix gates to
normal CI and exact-digest disposable smoke gates before release promotion.

## Binding corrections to the July 29 design

| July 29 statement | Corrected contract |
|---|---|
| Status says an implementation plan is pending. | A baseline plan exists but is not executable as written; the activation plan named above governs. |
| Local images are the v1 choice. | Retained. Local remains the default until Gate G5; prebuilt is an inactive mode before then. |
| The entrypoint auto-applies first-run seeds. | False. The installer explicitly arms one atomic, marked seed transaction for a verified fresh database. |
| Any one of seven providers is sufficient. | False for the current core. Baseline acceptance requires OpenAI and Qwen, stored encrypted in DB. A one-provider public promise additionally requires G6. |
| Provider keys land in environment fallbacks. | Rejected. Provider keys are ephemeral installer input and encrypted DB bootstrap data. |
| Admin password is passed to `create_admin --password`. | Rejected. Admin and provider secrets enter the backend bootstrap through stdin only. |
| `/ready` proves the deployment. | Insufficient. It is followed by the installation verifier and disposable login/chat proof. |
| Resume skips completed questions without secrets in state. | Resume re-prompts the minimal secret set whenever bootstrap is incomplete. |
| Seeds can run file by file. | Rejected. The five-file bundle is one error-stopping transaction with blocking postconditions and a marker. |
| Google OAuth feeds a required public Web client ID. | The audited Web source does not consume it; it is removed from the installer contract unless a future source consumer and test establish the need. |
| DevOps and socket mounts can move together. | Split them: maintainer CLI mounts and the optional skill-sandbox socket have different responsibilities. |
| ADR-179 is available. | False. Use ADR-215 and update both indexes. |
| A colon-separated Compose value can be passed through one `-f`. | False. Use repeated `-f` arguments or native `COMPOSE_FILE` interpretation. |
| Re-running includes reinstall-from-scratch behavior. | Destructive reinstall and database upgrade rollback remain outside v1. Fresh install, safe resume, and non-destructive configuration regeneration are distinct commands. |
| GHCR is simply out of scope. | It remains inactive until proven; the activation work may prepare it, but only Gate G5 may change the default. |

## Lifecycle semantics

### Fresh install

A fresh install requires no existing installer state and no existing LIA database marker.
The installer may create configuration, named volumes, the backup directory, and containers.
It must never remove a pre-existing volume. Seed intent exists only for the first API start
and is cleared after the seed marker and postconditions pass.

### Resume

Resume is allowed only when state schema, installer identity, mode, release manifest,
generated-file fingerprints, and existing database marker agree. Non-secret completed work
is reused. Missing ephemeral credentials are re-prompted. A mismatch stops before any
Compose mutation.

### Reconfigure

Reconfiguration may regenerate non-secret routing/exposure values and preserve generated
secrets. It first creates a mode-0600 timestamped backup and validates the candidate
configuration. It does not seed, migrate backward, prompt for or replace provider keys, or remove
data. Provider-key changes remain an authenticated Admin UI operation.

### Upgrade and destructive reinstall

Both remain outside v1. The installer must detect them and direct the operator to the
existing documented deploy/backup path. No installer option removes volumes.

## Required implementation sequence

1. Freeze the local-build default and add the corrected document/ADR contracts.
2. Establish canonical Settings validation, including Fernet format.
3. Make the Web artifact runtime-neutral and prove same-origin/canonical-origin behavior.
4. Parameterize Compose modes; split observability, skill-sandbox, and maintainer overlays.
5. Produce release manifests, dependency locks, both SBOMs, a complete host bundle with its
   deterministic embedded source-build context, and the non-dispatching candidate/promotion workflow contract.
6. Make reference seeding atomic, blocking, marked, and retryable.
7. Add the stdin-only admin/provider bootstrap and the functional verifier.
8. Build the secret-safe questionnaire, environment, Compose, state, logging, and rollback
   orchestration around those backend primitives.
9. Wire hermetic tests and static Compose matrices into normal CI.
10. With explicit authorization, qualify exact digests in disposable amd64 and native arm64
    environments, including injected failures and cleanup.
11. Promote the already-qualified digests and publish the passed manifest next to the unchanged
    bundle; only that official release directory resolves bare `install.sh` to prebuilt. A complete
    source tree or absent/candidate manifest remains local; `--local-build` from the official bundle
    verifies and extracts its manifest-bound source context before building.
12. Keep public copy explicit about the effective seeded baseline (OpenAI and DeepSeek)
    until a separately qualified mono-provider profile passes Gate G6.

No later stage may be implemented by weakening an earlier gate.

## Activation gates

### G0 — Static contract

Pass criteria:

- all referenced installer files exist;
- ADR-215 is indexed and no installer reference claims ADR-179;
- the active plan contains no unresolved placeholder;
- local is the declared fallback when no adjacent passed manifest exists;
- no Python-installer command builder can emit a bare Compose invocation; the existing Bash deploy
  helper may use Compose's native `COMPOSE_FILE` parsing.

This gate runs no service.

### G1 — Hermetic behavior

Pass criteria:

- wizard unit tests cover EN/FR flow, local/prebuilt modes, all exposure modes, optional
  observability and skill-sandbox, invalid inputs, and non-interactive answers;
- config/state/rollback failure-injection tests cover every checkpoint;
- canary secrets are absent from state, logs, rendered reports, exceptions, and recorded
  argv;
- Settings, seed-contract, admin/provider bootstrap, and functional-verifier unit tests pass;
- the matrix `local|prebuilt × lan|proxy|caddy × core|observability ×
  scripts-off|skill-sandbox` renders with `docker compose config --quiet`;
- the same tests pass **against** the allowlisted release bundle: the bundle deliberately excludes
  `scripts/install/tests/**`, so the working tree's test suite is executed with the extracted
  bundle directory as its target root, not from files shipped inside the bundle.
- a required normal-CI Python 3.10 import/compile contract proves the advertised installer minimum.

This gate starts no LIA service.

### G2 — Artifact identity

Pass criteria:

- every app and dependency image exposes one multi-platform index digest plus child-manifest and OCI
  config digests for `linux/amd64` and `linux/arm64`; a missing architecture blocks qualification;
- API provenance matches release version, source SHA, and build date;
- the Web candidate is API-same-origin, obtains canonical origin from runtime server configuration,
  and contains no deployment hostname fallback;
- API and Web SBOMs plus host-bundle and embedded source-context archive/canonical-tree SHA-256 values are attached;
- the manifest contains exact app and third-party image digests;
- the installer rejects tags and a digest/manifest mismatch.

Building and inspecting artifacts occurs only on ephemeral CI runners.

### G3 — Disposable clean-install proof

This gate requires explicit authorization for the dedicated manual-dispatch-only disposable
workflow and a demonstrated required-reviewer environment. No release workflow may call it. It
must never address DEV or PROD.

Pass criteria on both amd64 and native arm64:

- prebuilt rows install from a clean release bundle; local rows invoke `--local-build` from that
  same bundle and use its verified embedded source context at the candidate identity;
- migrate from an empty database;
- atomically apply and verify all five seed domains;
- create the admin and log in through the public API;
- store and decrypt the required provider rows, and prove post-seed effective provider coverage
  (every reachable core slot resolves to a provider whose key was collected — B10-bis owner
  arbitration: seeded overrides are kept, so DeepSeek is part of the required set);
- complete one chat through a hermetic fake OpenAI-compatible provider serving all three
  required provider base URLs (OpenAI, DeepSeek);
- prove each registry index resolves to the recorded platform child/config pair, then prove each
  running container `.Image` equals that platform's OCI config digest;
- tear down only the unique disposable Compose project and its labelled volumes.

Emulated arm64 build success is not a substitute for the native arm64 runtime row.

### G4 — Resume and failure proof

Pass criteria in a disposable project:

- injected failure before generation leaves no partial target file;
- injected failure during seeding rolls back all five domains and permits a clean retry;
- failure after start but before bootstrap re-prompts secrets and resumes;
- a corrupt state fingerprint stops before mutation;
- an existing qualified app pair is restored and rechecked after readiness failure;
- non-destructive reconfiguration preserves generated secrets/seed/provider/image identities and
  restores prior routing after an injected readiness failure;
- first-install failure preserves volumes and backups while stopping only created
  containers;
- every cleanup is scoped by the unique project label.

### G5 — Promotion and manifest-selected default activation

Pass criteria:

- G0-G4 artifacts are attached to the same release source identity;
- semver tags are created from the already-qualified digests without rebuilding;
- the release manifest and release notes use digest references;
- documentation describes the checkout-local and verified release-bundle local fallbacks plus the remaining upgrade limitation;
- candidate and passed manifests are identical except for qualification status;
- publishing the adjacent passed manifest makes the already-qualified release directory resolve
  bare `install.sh` to prebuilt without changing source, bundle, image, dependency, or documentation;
- source checkouts and directories with an absent or candidate manifest still resolve to local;
  `--local-build` always forces local and, outside a complete checkout, fails before mutation unless
  the manifest-bound embedded source context verifies.

If any criterion fails, the release may still ship the existing local-build path, but GHCR
remains non-default and must not be described as qualified.

### G6 — Public one-provider and zero-friction claim

G6 is a separate product-claim gate. It is not required to prove the technically honest
effective seeded baseline (OpenAI, DeepSeek) or to qualify the exact prebuilt artifacts, but it is mandatory before
a public call to action says `turnkey`, `one key`, `one endpoint`, or `zero friction`.

Pass criteria:

- at least one named remote mono-provider profile has an explicit, versioned mapping for
  every enabled core LLM slot and its required tools, structured-output, streaming, context,
  and reasoning capabilities;
- the profile names exact provider and model identifiers; an arbitrary
  OpenAI-compatible endpoint/key pair is rejected unless it matches that profile;
- the complete login/chat and representative tool/structured-output matrix passes on both
  qualified architectures using only that profile;
- failure tests cover a provider that lacks tools, structured output, the required context
  window, or the declared reasoning behavior and prove that it is rejected before chat;
- a local Ollama profile is advertised only after exact model digests, CPU architecture,
  RAM floor, context size, latency ceiling, and tool/structured-output results are published
  for each supported hardware row;
- until these criteria pass, release and installer copy says
  `guided self-host installation; OpenAI and DeepSeek are required for the current core`.

## Explicit non-goals

- No command in this design targets an existing DEV or PROD deployment.
- Documentation and implementation checkpoints perform no Git operation—commit, push, tag,
  merge, or branch action; they only present evidence and suggest a conventional message to the
  operator.
- No database downgrade, volume deletion, or automated upgrade is part of v1.
- No real provider credential is used in CI.
- No mutable image tag is accepted by prebuilt mode.
- No claim of runtime success is based on static inspection alone.
