# Self-Host Installer Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a one-command, resumable Linux self-host installer whose current v1 default builds locally, while preparing a digest-only prebuilt mode that cannot become the default until the same API/Web artifacts pass all disposable qualification gates.

**Architecture:** The installer is a Python 3.10+ stdlib-only orchestration package behind a small POSIX bootstrap. Backend-owned commands validate Settings, apply reference data atomically, bootstrap admin/provider data through stdin, and verify the installed database. Compose retains local build definitions, adds exact image and profile overlays, and prebuilt mode is gated by a release manifest containing immutable app and dependency digests.

**Tech Stack:** Python 3.10+ stdlib for `scripts/install/`, FastAPI/Pydantic/SQLAlchemy backend primitives, POSIX shell, Docker Compose v2.24.4+, Next.js 16, pytest, Vitest, GitHub Actions, GHCR, CycloneDX JSON.

**Governing documents:**

- `docs/superpowers/specs/2026-07-29-self-host-installer-design.md`
- `docs/superpowers/specs/2026-08-05-self-host-installer-audit-addendum.md`

The addendum governs every conflict. The July 29 baseline currently contains exactly 70 unchecked boxes and zero completed boxes; do not execute that baseline plan independently.

## Global Constraints

- With no adjacent validated passed manifest, the default install mode is always `local`. Task 16
  activates the official release-directory default by publishing the passed manifest next to the
  already-qualified bundle; it does not modify or rebuild that bundle.
- `prebuilt` accepts only `repository@sha256:<64 lowercase hex>` references loaded from a validated release manifest. Mutable tags are rejected.
- Public `install.sh` prebuilt invocations require `qualification="passed"`. Only the dedicated
  Task 16 workflow harness may explicitly load a `candidate` manifest, and that path is not exposed
  by the public CLI.
- Keep `--local-build` as a permanent supported fallback after prebuilt activation. It uses the live tree in a complete source checkout; in an official release directory it must use the manifest-bound source-context archive embedded in the verified host bundle. If neither complete context exists, it fails before mutation with exact recovery instructions.
- No implementation or verification command in this plan may start, stop, restart, reconfigure, or inspect a DEV or PROD service.
- Ordinary task verification is limited to unit tests, lint, static file checks, and `docker compose config`; these commands must not contact the Docker daemon or start a service.
- Full-stack commands may run only in the dedicated disposable workflow added in Task 16, after explicit approval through the `installer-disposable-smoke` environment.
- Every disposable Compose command uses a unique `lia-installer-smoke-*` project name and a unique
  working directory on an ephemeral runner. Every row extracts the same release bundle; prebuilt rows
  use its locked images, while local rows force `--local-build` from its embedded, manifest-verified
  source context at the candidate source SHA.
- The disposable cleanup trap may remove only resources labelled with that exact project name. It must never use a broad prune command.
- Wizard code under `scripts/install/` is Python stdlib-only. Backend support scripts may use already-locked backend dependencies.
- Python code has complete type hints, Google-style docstrings, module docstrings, 100-column Black formatting, Ruff-clean imports, and MyPy strict compatibility.
- User-facing wizard strings go through `scripts.install.i18n.tr()` and exist in English and French.
- No provider key, admin password, generated secret, session cookie, or database password may appear in argv, state, logs, reports, exceptions, fixtures, or CI artifacts.
- Provider and admin secrets are sent to the backend bootstrap as one JSON document on stdin. They are never persisted by the installer.
- `.env` is the only generated deployment secret store and is written atomically with mode `0o600`. LLM provider keys are not written to it.
- Existing `.env` and generated overrides are timestamp-backed-up before replacement; failed candidate validation restores the prior files.
- Every Python-installer Compose command is built as an argv list with explicit repeated `-f` pairs;
  a bare installer `docker compose` call is forbidden. The existing Bash deploy readiness helper is
  the sole exception: Task 4 deliberately lets Compose parse its native colon-separated
  `COMPOSE_FILE` environment value.
- Local mode may call `build`; prebuilt mode must call `pull api web` and `up --no-build`, and its tests reject any `build` token.
- Normal boots and reconfiguration use `APPLY_SEEDS=false`. Only the verified fresh-install start may set it true.
- Reference seeding is one `psql` process, `ON_ERROR_STOP=1`, one transaction, five seed files, blocking postconditions, and one marker written in that transaction.
- The current-core baseline provider set is `("deepseek", "openai")` — derived from the post-seed effective configuration (DB override when present, else code default), never from code defaults alone. An anti-drift test binds it to that effective derivation (B10-bis, owner arbitration 2026-08-06).
- The reference `llm_config_seed.sql` is a maintainer-production extraction whose overrides supersede code defaults at startup (B10-bis). Owner arbitration: the seeds are kept as-is (proven configuration; self-hosters may change them in the Admin UI later). No bootstrap reconciliation runs; the questionnaire collects one key per derived required provider and the verifier checks post-seed effective coverage.
- Baseline technical acceptance and public zero-friction positioning are separate. G0-G5 may
  qualify the honest effective seeded baseline (OpenAI, DeepSeek); public `turnkey`,
  `one key`, `one endpoint`, or `zero friction` copy remains forbidden until Gate G6 qualifies a
  named mono-provider profile.
- An arbitrary OpenAI-compatible key/endpoint is never treated as a qualified profile. Ollama is
  advertised only for an exact model-and-hardware row with measured capability and resource gates.
- `/ready` is an infrastructure prerequisite, not the completion criterion. Backend verification and the disposable login/chat proof are mandatory.
- Upgrade, database downgrade, destructive reinstall, and volume removal are outside v1.
- Do not perform any Git operation. At each checkpoint, show the diff and suggest only the message written in the task.
- Existing unrelated worktree changes belong to the user and must not be altered.

---

## File and Responsibility Map

### Governing documentation

- Create `docs/architecture/ADR-215-Self-Host-Installer.md` — accepted architecture, mode boundary, bootstrap and release gates.
- Modify `docs/superpowers/specs/2026-07-29-self-host-installer-design.md` — add a non-destructive amendment banner.
- Modify `docs/superpowers/plans/2026-07-29-self-host-installer.md` — add a historical-plan banner directing execution here.
- Modify `docs/architecture/ADR_INDEX.md`, `docs/INDEX.md` — index ADR-215 and the installer docs.
- Modify `docs/GETTING_STARTED.md`, `README.md` — accurate local-default quick start and qualified prebuilt path.
- Modify `docs/guides/GUIDE_DEPLOYMENT.md` — bootstrap stdin and installer lifecycle contract.

### Backend-owned install primitives

- Create `apps/api/scripts/validate_settings.py` — pure real-Settings validation CLI.
- Modify `apps/api/scripts/validate_config.py` — delegate its Pydantic phase to the canonical validator.
- Modify `apps/api/src/core/config/security.py` — validate Fernet key structure.
- Create `apps/api/scripts/data/apply_reference_seeds.sh` — one atomic seed invocation.
- Create `infrastructure/database/seeds/verify_reference_seeds.sql` — five-domain postconditions and bundle marker.
- Modify the five files under `infrastructure/database/seeds/` — turn count warnings into blocking exceptions.
- Modify `apps/api/docker-entrypoint.sh` — explicit marked seed gate and one seed command.
- Modify `apps/api/src/domains/system_settings/models.py` — add `SELF_HOST_SEED_BUNDLE`.
- Modify `apps/api/scripts/data/create_admin.py` — strict validation and reusable uncommitted admin operation.
- Modify `apps/api/src/domains/llm_config/service.py` — reusable uncommitted encrypted-key upsert.
- Create `apps/api/src/domains/llm_config/install_contract.py` — core provider-set contract.
- Create `apps/api/scripts/data/bootstrap_install.py` — stdin-only atomic admin/provider bootstrap.
- Create `apps/api/scripts/data/verify_installation.py` — non-secret installation postcondition report.

### Web and Compose contracts

- Modify `apps/web/Dockerfile.prod`, `apps/web/next.config.ts` — same-origin generic release artifact.
- Create `apps/web/src/lib/runtime-app-url.ts` and update metadata/SEO routes — runtime canonical
  origin with no baked deployment host.
- Modify `docker-compose.prod.yml` — app image variables and core/observability split.
- Create `docker-compose.skill-sandbox.yml` — explicit Docker-socket capability.
- Create `docker-compose.devops.yml` — maintainer-only Claude CLI mounts.
- Create `infrastructure/caddy/Caddyfile.template` — optional Caddy vhosts.
- Modify `scripts/deploy/lib/deploy_readiness_gate.sh`, `scripts/deploy/prepare-prod.ps1` — valid multi-file Compose handling and overlay shipment.

### Release identity and bundle

- Create `scripts/release/self_host_dependencies.json` — exact service-to-upstream-reference catalogue.
- Create `scripts/release/self_host_manifest.py` — candidate-manifest assembly CLI over the shared installer schema.
- Create `scripts/release/build_self_host_bundle.py` — deterministic allowlisted host bundle.
- Create `scripts/release/build_self_host_source_context.py` — deterministic, secret-free API/Web Docker build context embedded in the host bundle.
- Create `scripts/release/frontend_sbom.py` — convert `pnpm licenses list --prod --json` into CycloneDX.
- Create `scripts/release/tests/` — manifest, SBOM, bundle, and failure tests.
- Modify `.github/workflows/release.yml` — candidate digests, both SBOMs, qualification, promotion without rebuild.
- Create `.github/workflows/installer-disposable-smoke.yml` — approved ephemeral amd64/native-arm64 qualification.

### Wizard

- Create `install.sh` — prerequisite-only POSIX entry point.
- Create `scripts/install/__init__.py`, `__main__.py` — package and CLI.
- Create `scripts/install/manifest.py` — shared stdlib-only manifest schema, digest validation, and image-lock rendering.
- Create `scripts/install/model.py` — enums and immutable data contracts.
- Create `scripts/install/i18n.py` — bilingual message catalogue.
- Create `scripts/install/questions.py`, `answers.py`, `verify.py` — declarative input and optional key checks.
- Create `scripts/install/envgen.py`, `compose.py`, `host_paths.py`, `seed_bundle.py` — generated
  artifacts, canonical seed identity, and static host validation.
- Create `scripts/install/state.py`, `redaction.py`, `log.py` — resumable non-secret state and logs.
- Create `scripts/install/preflight.py`, `deploy.py`, `rollback.py`, `report.py` — orchestration and outcome.
- Create `scripts/install/tests/` — hermetic TDD suite and static Compose matrix.
- Create `scripts/install/tests/runtime/` — disposable-only fake providers and assertions.
- Modify `.gitignore`, `Taskfile.yml`, `.github/workflows/ci.yml` — artifact ignores and mandatory hermetic gates.

---

### Task 1: Rebase the documentation contract and allocate ADR-215

**Blocks:** B01, B15  
**Files:**

- Create: `docs/architecture/ADR-215-Self-Host-Installer.md`
- Modify: `docs/superpowers/specs/2026-07-29-self-host-installer-design.md`
- Modify: `docs/superpowers/plans/2026-07-29-self-host-installer.md`
- Modify: `docs/architecture/ADR_INDEX.md`
- Modify: `docs/INDEX.md`
- Test: `apps/api/tests/unit/test_self_host_installer_document_contract.py`

**Interfaces:**

- Produces the unique architecture identifier `ADR-215`.
- Establishes the addendum and this plan as the active implementation sources.
- Preserves all July 29 content; only banners and indexes change.
- Treats ADR-215 as reserved on source commit `1c1c5d6655cb4a8aa3d19905d58c8f2f14d8de0f`
  plus the inspected worktree, not as an overwrite authorization.

- [ ] **Precondition: reconcile the live ADR namespace before creating a file**

Run these read-only checks:

```powershell
Test-Path docs/architecture/ADR-215-Self-Host-Installer.md
Select-String -LiteralPath docs/architecture/ADR_INDEX.md -Pattern 'ADR-215'
Get-ChildItem docs/architecture -File -Filter 'ADR-*.md' | Select-Object -ExpandProperty Name
```

Expected on the audited snapshot: `False`, no index match, and ADR-214 as the highest number.
Preserve the existing ADR-214 and ADR-index worktree edits. If ADR-215 is present or reserved, stop
before any ADR write, select the smallest unused integer above the live maximum, and update every
installer ADR reference in the addendum, this plan, the new filename/title, and both indexes in
one `apply_patch` operation. Never overwrite or repurpose the colliding ADR.

- [ ] **Step 1: Write the failing static contract test**

```python
"""Static contracts for the self-host installer governing documents."""

import re
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()


def test_baseline_documents_delegate_to_the_august_addendum() -> None:
    spec = (ROOT / "docs/superpowers/specs/2026-07-29-self-host-installer-design.md").read_text()
    plan = (ROOT / "docs/superpowers/plans/2026-07-29-self-host-installer.md").read_text()
    active = "2026-08-05-self-host-installer-audit-addendum.md"
    assert active in spec
    assert active in plan
    assert len(re.findall(r"^- \[ \]", plan, flags=re.MULTILINE)) == 70
    assert re.search(r"^- \[[xX]\]", plan, flags=re.MULTILINE) is None


def test_adr_215_is_unique_and_indexed() -> None:
    adr = ROOT / "docs/architecture/ADR-215-Self-Host-Installer.md"
    assert adr.is_file()
    assert "# ADR-215:" in adr.read_text(encoding="utf-8")
    index = (ROOT / "docs/architecture/ADR_INDEX.md").read_text(encoding="utf-8")
    assert adr.name in index
```

- [ ] **Step 2: Run the test and prove the expected red state**

Run:

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_self_host_installer_document_contract.py -v
```

Expected: failure because ADR-215 and the two banners do not yet exist.

- [ ] **Step 3: Add the exact banners and ADR**

The first paragraph after each July 29 title must be:

```markdown
> **Implementation amendment (2026-08-05):**
> `docs/superpowers/specs/2026-08-05-self-host-installer-audit-addendum.md`
> governs every conflict. The July document remains historical context.
```

ADR-215 records these accepted decisions: local is the current v1 default; prebuilt is digest-only
and locked behind G5; Web is same-origin; fresh seeds are explicit and atomic; bootstrap secrets use
stdin; OpenAI and DeepSeek are the v1 core set (the seed overrides every qwen default, Qwen stays optional); the socket is opt-in; upgrades and destructive reinstall
are excluded; disposable qualification is mandatory.

- [ ] **Step 4: Run the focused test and documentation lint**

```powershell
task lint:docs
cd apps/api
.venv/Scripts/pytest tests/unit/test_self_host_installer_document_contract.py -v
```

Expected: both commands exit 0.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `docs(installer): bind the audited design to ADR-215`.

---

### Task 2: Make Settings validation canonical and validate Fernet structure

**Blocks:** B07  
**Files:**

- Create: `apps/api/scripts/validate_settings.py`
- Modify: `apps/api/scripts/validate_config.py`
- Modify: `apps/api/src/core/config/security.py`
- Test: `apps/api/tests/unit/test_validate_settings_script.py`
- Test: `apps/api/tests/unit/core/config/test_security_settings.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class SettingsIssue:
    location: str
    message: str

def validate_current_settings() -> tuple[Settings | None, tuple[SettingsIssue, ...]]: ...
def format_issues(issues: Sequence[SettingsIssue]) -> str: ...
def main() -> int: ...
```

`validate_current_settings()` imports and constructs the real composed `Settings`; it performs no
socket, database, Redis, Docker, or provider operation. Error text is sorted by `(location, message)`
and contains no setting values.

- [ ] **Step 1: Add red tests**

Test these exact cases:

```python
def test_malformed_fernet_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FERNET_KEY", "not-a-fernet-key")
    settings, issues = validate_current_settings()
    assert settings is None
    assert any(issue.location == "fernet_key" for issue in issues)
    assert "not-a-fernet-key" not in format_issues(issues)


def test_valid_fernet_key_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode("ascii"))
    settings, issues = validate_current_settings()
    assert settings is not None
    assert issues == ()
```

Also assert that `validate_config.validate_pydantic_models()` calls
`validate_current_settings()` through a monkeypatched spy and that no connectivity helper runs.

- [ ] **Step 2: Prove red**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_validate_settings_script.py tests/unit/core/config/test_security_settings.py -v
```

Expected: import failure for `scripts.validate_settings` and acceptance of the malformed key.

- [ ] **Step 3: Implement the minimal canonical path**

In `SecuritySettings`, add a `field_validator("fernet_key")` that:

1. encodes ASCII;
2. requires exactly 44 encoded characters;
3. decodes with `base64.b64decode(value, altchars=b"-_", validate=True)`;
4. requires exactly 32 decoded bytes;
5. raises `ValueError("must be a URL-safe base64-encoded 32-byte Fernet key")`;
6. returns the original string.

`main()` prints only `OK: settings are valid` or the deterministic issue list. Modify the legacy
validator's Pydantic phase to consume this function; retain its other operator checks for its
existing manual use, but the installer never calls them.

- [ ] **Step 4: Prove green and pure behavior**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_validate_settings_script.py tests/unit/core/config/test_security_settings.py -v
.venv/Scripts/python -m ruff check scripts/validate_settings.py src/core/config/security.py
.venv/Scripts/python -m mypy scripts/validate_settings.py
```

Expected: all exit 0. The tests monkeypatch all known connectivity functions to raise if called.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `fix(config): establish pure canonical installer validation`.

---

### Task 3: Make the Web release artifact same-origin and host-neutral

**Blocks:** B03  
**Files:**

- Modify: `apps/web/Dockerfile.prod`
- Modify: `apps/web/next.config.ts`
- Create: `apps/web/src/lib/runtime-app-url.ts`
- Modify: `apps/web/src/lib/app-metadata.ts`
- Modify: `apps/web/src/components/seo/JsonLd.tsx`
- Modify: `apps/web/src/app/robots.ts`
- Modify: `apps/web/src/app/sitemap.ts`
- Modify: `apps/web/src/app/[lng]/layout.tsx`
- Modify: `apps/web/src/app/[lng]/page.tsx`
- Modify: `apps/web/src/app/[lng]/why/page.tsx`
- Modify: `apps/web/src/app/[lng]/terms/page.tsx`
- Modify: `apps/web/src/app/[lng]/demo/page.tsx`
- Modify: `apps/web/src/app/[lng]/more/page.tsx`
- Modify: `apps/web/src/app/[lng]/story/page.tsx`
- Modify: `apps/web/src/app/[lng]/how/page.tsx`
- Modify: `apps/web/src/app/[lng]/faq/page.tsx`
- Modify: `apps/web/src/app/[lng]/privacy/page.tsx`
- Modify: `apps/web/src/app/[lng]/blog/page.tsx`
- Modify: `apps/web/src/app/[lng]/blog/[slug]/page.tsx`
- Modify: `apps/web/src/lib/__tests__/api-base-url-env.test.ts`
- Create: `apps/web/src/lib/__tests__/runtime-app-url.test.ts`
- Modify: `.github/workflows/release.yml`
- Test: `apps/api/tests/unit/test_web_release_image_contract.py`

**Interfaces:**

- Release-build value: `NEXT_PUBLIC_API_URL=""`.
- Local-build value: the explicit installer-generated URL remains accepted.
- Runtime server rewrite: `/api/v1/:path* -> http://api:8000/api/v1/:path*`.
- Runtime canonical-origin value: `APP_URL_SERVER`, validated as an absolute HTTP(S) origin with no
  credentials, query, fragment, or non-root path.
- `NEXT_PUBLIC_APP_URL` is removed from the Dockerfile and all source consumers.
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` is absent from the release-image contract.

```typescript
export function getRuntimeAppUrl(env: NodeJS.ProcessEnv = process.env): URL;
export function buildAbsoluteUrl(base: URL, path: string): string;
```

The generic release build has this complete public-variable policy:

| Variable family | Release value | Consequence |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | explicit empty string | browser API calls are same-origin |
| `NEXT_PUBLIC_APP_NAME` | `Lia` | deployment-independent product name |
| `NEXT_PUBLIC_PRODUCT_TELEMETRY` | `false` | no public telemetry endpoint is baked |
| `NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE` | `0` | no inactive telemetry sampling |
| seven `NEXT_PUBLIC_FIREBASE_*` fields | empty | push notifications are unavailable in generic prebuilt v1; local build remains the opt-in path |
| `NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT` | `legacy` (or absent) | the guided/live public showroom is a hosted-site feature, not part of generic self-host v1 |
| `NEXT_PUBLIC_SHOWROOM_PROOF_SHA` | empty | proof links are supplied only by the hosted showroom release build |
| timeout/log-level public knobs | repository defaults | not installer-configurable in generic prebuilt v1 |

- [ ] **Step 1: Write a failing artifact guard**

```python
def test_web_dockerfile_defaults_to_same_origin() -> None:
    body = WEB_DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG NEXT_PUBLIC_API_URL=" in body
    assert "ARG NEXT_PUBLIC_API_URL=http://localhost:8000" not in body
    assert "NEXT_PUBLIC_APP_URL" not in body
    assert "NEXT_PUBLIC_GOOGLE_CLIENT_ID" not in body


def test_release_web_build_sets_explicit_empty_api_url() -> None:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    dumped = yaml.safe_dump(workflow["jobs"])
    assert "NEXT_PUBLIC_API_URL=" in dumped
```

Extend the Vitest contract so explicit empty string yields relative `/api/v1`, while an explicit
local-build URL remains absolute. Add a source inventory test that finds every
`NEXT_PUBLIC_[A-Z0-9_]+` consumer, classifies it in the table above, and fails on any unreviewed public
variable. Add runtime-origin tests for LAN/proxy/Caddy values and rejection of credentials, query,
fragment, path, non-HTTP schemes, and missing production configuration. Scan the Dockerfile and the
runtime-origin/metadata/SEO route modules listed in this task for `http://localhost:3000`,
`http://localhost:8000`, and `https://lia.jeyswork.com`; none may serve as a production canonical or
API fallback there.

- [ ] **Step 2: Prove red**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_web_release_image_contract.py -v
cd ../web
pnpm test -- src/lib/__tests__/api-base-url-env.test.ts src/lib/__tests__/runtime-app-url.test.ts
```

Expected: the static test fails on localhost API/app defaults, the hosted canonical fallback, and
the Google public argument.

- [ ] **Step 3: Implement the neutral build contract**

Set the API Dockerfile argument to an explicit empty default, remove the app-URL and unused Google
public arguments/environment assignments, and retain the existing `??` logic in `next.config.ts`.
In release metadata, pass the table values explicitly so absence can never re-enable a development
fallback. Do not remove `API_URL_SERVER=http://api:8000`.

Replace every module-scope `NEXT_PUBLIC_APP_URL`/hosted fallback with `getRuntimeAppUrl()`. Pass the
runtime URL into metadata and JSON-LD builders. Make metadata, sitemap, robots, and the listed public
routes request-time server outputs so no canonical origin is evaluated during `next build`; no
client component imports the helper, whose first import is `server-only`. Task 11 sets
`APP_URL_SERVER` at container runtime.

- [ ] **Step 4: Prove green**

```powershell
cd apps/web
pnpm test -- src/lib/__tests__/api-base-url-env.test.ts src/lib/__tests__/runtime-app-url.test.ts
pnpm type-check
cd ../api
.venv/Scripts/pytest tests/unit/test_web_release_image_contract.py -v
```

Expected: all exit 0.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `fix(web): make release images same-origin and host-neutral`.

---

### Task 4: Separate Compose modes, profiles, and privileged overlays

**Blocks:** B04, B15  
**Files:**

- Modify: `docker-compose.prod.yml`
- Create: `docker-compose.skill-sandbox.yml`
- Create: `docker-compose.devops.yml`
- Modify: `.env.prod.example`
- Modify: `.env.min.prod`
- Modify: `scripts/deploy/lib/deploy_readiness_gate.sh`
- Modify: `scripts/deploy/prepare-prod.ps1`
- Create: `scripts/install/tests/fixtures/compose.env`
- Test: `apps/api/tests/unit/test_self_host_compose_contract.py`
- Test: `scripts/deploy/lib/test_deploy_readiness_gate.sh`
- Test: `scripts/deploy/deploy-prod.Tests.ps1`

**Interfaces:**

```text
LIA_API_IMAGE default  = lia-api:local
LIA_WEB_IMAGE default  = lia-web:local
SKILLS_SCRIPT_SANDBOX_IMAGE = ${LIA_API_IMAGE:-lia-api:local}
profile "observability" = all 12 non-core services
base scripts setting    = false
skill overlay           = socket + group_add + scripts setting true
devops overlay          = ~/.claude + maintainer CLAUDE.md only
```

Core services are exactly `postgres`, `postgres-backup`, `redis`, `api`, and `web`. Observability
services are exactly `tempo`, `prometheus`, `alertmanager`, `blackbox-exporter`, `grafana`, `loki`,
`promtail`, `node-exporter`, `cadvisor`, `postgres-exporter`, `redis-exporter`, and `portainer`.

- [ ] **Step 1: Write the red structured tests**

Tests load all YAML files and assert:

- API/Web image variables have the stated local defaults;
- sandbox image uses the same API variable;
- core services have no profile and the 12 listed services have only `["observability"]`;
- the base API has no Docker socket, `group_add`, or Claude mount;
- the skill overlay contains the socket and `group_add`;
- the DevOps overlay contains only the two Claude mounts;
- scripts are false in base and true in the skill overlay;
- `_dc()` does not contain `-f "$COMPOSE_FILE"` and delegates native `COMPOSE_FILE` parsing.

- [ ] **Step 2: Prove red**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_self_host_compose_contract.py -v
cd ../..
task test:deploy
```

Expected: profile, overlay, image-variable, and `_dc` assertions fail.

- [ ] **Step 3: Implement the exact split**

Use these image expressions:

```yaml
services:
  api:
    image: ${LIA_API_IMAGE:-lia-api:local}
    environment:
      - SKILLS_SCRIPTS_ENABLED=${SKILLS_SCRIPTS_ENABLED:-false}
      - SKILLS_SCRIPT_SANDBOX_IMAGE=${LIA_API_IMAGE:-lia-api:local}
  web:
    image: ${LIA_WEB_IMAGE:-lia-web:local}
```

Let Compose interpret a colon-separated `COMPOSE_FILE`:

```bash
_dc() { COMPOSE_FILE="$COMPOSE_FILE" docker compose "$@"; }
```

Ship all three files from `prepare-prod.ps1`. The maintainer deploy value is exactly:

```text
docker-compose.prod.yml:docker-compose.skill-sandbox.yml:docker-compose.devops.yml
```

Add `COMPOSE_PROFILES=observability` to the maintainer template and leave it commented in the
minimal template.

- [ ] **Step 4: Run static Compose and deploy gates**

These are parser-only commands and must not start a service:

```powershell
docker compose --env-file scripts/install/tests/fixtures/compose.env -f docker-compose.prod.yml config --quiet
docker compose --env-file scripts/install/tests/fixtures/compose.env -f docker-compose.prod.yml -f docker-compose.skill-sandbox.yml config --quiet
docker compose --env-file scripts/install/tests/fixtures/compose.env -f docker-compose.prod.yml -f docker-compose.devops.yml config --quiet
task test:deploy
cd apps/api
.venv/Scripts/pytest tests/unit/test_self_host_compose_contract.py -v
```

Expected: all exit 0 without daemon access.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `refactor(compose): separate self-host profiles and privileged overlays`.

---

### Task 5: Define the release manifest, dependency lock, and host bundle

**Blocks:** B02, B05, B06  
**Files:**

- Create: `scripts/install/__init__.py`
- Create: `scripts/install/manifest.py`
- Create: `scripts/release/__init__.py`
- Create: `scripts/release/self_host_dependencies.json`
- Create: `scripts/release/self_host_manifest.py`
- Create: `scripts/release/build_self_host_bundle.py`
- Create: `scripts/release/build_self_host_source_context.py`
- Create: `scripts/release/frontend_sbom.py`
- Create: `scripts/release/tests/__init__.py`
- Create: `scripts/release/tests/test_self_host_manifest.py`
- Create: `scripts/release/tests/test_self_host_bundle.py`
- Create: `scripts/release/tests/test_self_host_source_context.py`
- Create: `scripts/release/tests/test_frontend_sbom.py`
- Create: `scripts/release/tests/fixtures/pnpm-licenses.json`

**Interfaces:**

`scripts/install/manifest.py` owns the shared stdlib-only schema:

```python
DIGEST_PATTERN = re.compile(r"^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

@dataclass(frozen=True)
class PlatformArtifact:
    platform: Literal["linux/amd64", "linux/arm64"]
    manifest_digest: str
    config_digest: str

@dataclass(frozen=True)
class ImageArtifact:
    service: str
    reference: str
    platforms: tuple[PlatformArtifact, ...]

@dataclass(frozen=True)
class SelfHostManifest:
    schema_version: int
    release_version: str
    source_sha: str
    built_at: str
    bundle_archive_sha256: str
    bundle_tree_sha256: str
    source_context_archive_sha256: str
    source_context_tree_sha256: str
    images: tuple[ImageArtifact, ...]
    sboms: Mapping[str, str]
    qualification: Literal["candidate", "passed"]

def load_manifest(
    path: Path,
    *,
    required_qualification: Literal["candidate", "passed"] = "passed",
) -> SelfHostManifest: ...
def validate_manifest(manifest: SelfHostManifest) -> tuple[str, ...]: ...
def render_image_lock(manifest: SelfHostManifest, services: Collection[str]) -> str: ...
def validate_bundle_tree(root: Path, manifest: SelfHostManifest) -> tuple[str, ...]: ...
```

`scripts/release/self_host_manifest.py` imports those types and owns candidate assembly; it must not
redeclare them:

```python
def write_candidate_manifest(
    *,
    release_version: str,
    source_sha: str,
    built_at: str,
    bundle_archive_sha256: str,
    bundle_tree_sha256: str,
    source_context_archive_sha256: str,
    source_context_tree_sha256: str,
    images: Sequence[ImageArtifact],
    sboms: Mapping[str, str],
    output: Path,
) -> SelfHostManifest: ...

def write_passed_manifest(
    *,
    candidate_path: Path,
    qualification_evidence_path: Path,
    output: Path,
) -> SelfHostManifest: ...

@dataclass(frozen=True)
class BundleDigests:
    archive_sha256: str
    tree_sha256: str

def build_source_context(root: Path, output: Path) -> BundleDigests: ...
def build_bundle(root: Path, source_context_archive: Path, output: Path) -> BundleDigests: ...
def licenses_to_cyclonedx(payload: Mapping[str, object]) -> dict[str, object]: ...
```

`self_host_dependencies.json` lists every current third-party service with its exact tag from
Compose, plus the planned Caddy baseline `caddy:2-alpine`: postgres, postgres-backup, redis, tempo,
prometheus, alertmanager,
blackbox-exporter, grafana, loki, promtail, node-exporter, cadvisor, postgres-exporter,
redis-exporter, portainer, and caddy.

- [ ] **Step 1: Write failing schema and bundle tests**

Cover:

- a tag reference is rejected;
- uppercase or short digests are rejected;
- every app and dependency service must declare exactly amd64 and arm64, with one child-manifest
  digest and one OCI config digest per platform; a dependency missing either architecture blocks
  prebuilt qualification rather than being silently omitted;
- every dependency-catalogue service appears once;
- image-lock YAML maps every requested Compose service to its digest, rejects an unknown service,
  and never introduces an optional service absent from the selected Compose layers;
- public/default manifest loading rejects `qualification="candidate"`;
- the workflow-only candidate load requires that status explicitly;
- promotion rejects evidence whose candidate-manifest SHA-256 or four-row matrix does not match;
- candidate and passed manifests have byte-identical canonical fields except `qualification`;
- archive verification rejects a mismatched tarball before extraction, and canonical tree
  verification rejects a missing, added-to-allowlist, changed, or symlinked bundled path before any
  deployment mutation;
- source-context verification rejects a wrong source identity, missing/extra Docker `COPY` input,
  secret/cache/generated member, archive mismatch, tree mismatch, or symlink before local build or
  any deployment mutation;
- the bundle contains every bind source and excludes `.env`, state, logs, caches, and
  `apps/api/config`;
- the bundle contains exactly one generated `lia-self-host-source-context.tar.gz`, and a complete
  checkout build plus an extracted verified-source-context build resolve identical Docker input
  trees for both app images;
- the archive contains no `__pycache__`, `.pyc`, or `.pyo` entry even when those files exist in the
  source workspace;
- the archive excludes `scripts/install/tests/**`, `scripts/install/tests_py310.py`, and
  `scripts/install/tests/runtime/**` from the production bundle;
- two builds from the same fixture have the same SHA-256;
- the frontend SBOM is CycloneDX 1.5, contains only production packages, sorts components, and
  never includes a filesystem path.

Bundle unit tests construct a complete synthetic allowlist under `tmp_path`; they do not require the
later installer files to exist in the live tree. A live-root build must fail closed on any missing
required path until Tasks 10-14 create them. Task 15 is the first checkpoint that must build and
unpack the complete live-tree bundle.

- [ ] **Step 2: Prove red**

```powershell
apps/api/.venv/Scripts/pytest scripts/release/tests -v
```

Expected: imports fail because the release modules do not exist.

- [ ] **Step 3: Implement deterministic artifacts**

The host bundle allowlist is exact:

```text
install.sh
.env.min.prod
docker-compose.prod.yml
docker-compose.skill-sandbox.yml
scripts/install/**
infrastructure/caddy/Caddyfile.template
infrastructure/docker/postgres-init.sql
infrastructure/database/seeds/*.sql
infrastructure/observability/**
data/skills/system/**
docs/knowledge/**
lia-self-host-source-context.tar.gz
LICENSE
```

Build the source-context archive first. Its code-owned inventory contains the effective
`apps/api` Docker build context and the root-level Web Docker build inputs required by every
non-stage `COPY` in `apps/api/Dockerfile.prod` and `apps/web/Dockerfile.prod`. It excludes `.git`,
`.env*` except safe examples explicitly required by a build, credentials, config secrets,
`node_modules`, virtual environments, caches, bytecode, coverage, logs, and generated build output.
Static tests parse both Dockerfiles and effective `.dockerignore` rules: a new build-context `COPY`
source fails until the inventory and fixture are reviewed. The archive records the full source SHA
in a non-executable metadata member, uses the same deterministic tar rules as the host bundle, and
is passed as the generated `lia-self-host-source-context.tar.gz` member above.

Use sorted paths, fixed uid/gid `0`, empty owner/group names, file mode from the source executable
bit, and timestamp `0`. Write gzip with `mtime=0`. Reject symlinks and any resolved path outside the
repository root. Build the bundle before the candidate manifest, then pass the returned bundle
archive/tree SHA-256 values plus the embedded source-context archive/tree SHA-256 values to
`write_candidate_manifest()`. The tree digest hashes, in allowlist
path order, each POSIX path, normalized type/mode, and content SHA-256; it ignores generated paths
outside the allowlist. Cache directories and bytecode are explicit exclusions, never archive
members or tree-digest inputs. The manifest is a sibling release asset and is not embedded
in the bundle, which avoids a manifest/bundle hash cycle. `write_passed_manifest()` accepts only a
candidate plus qualification evidence that records that candidate file's SHA-256, the exact four
architecture/mode rows, and four passing results. It copies every canonical field and changes only
`qualification` from `candidate` to `passed`.

- [ ] **Step 4: Prove green and style**

```powershell
apps/api/.venv/Scripts/pytest scripts/release/tests -v
apps/api/.venv/Scripts/python -m ruff check scripts/release scripts/install/manifest.py
apps/api/.venv/Scripts/python -m mypy --strict scripts/release scripts/install/manifest.py
```

Expected: all exit 0.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `feat(release): define immutable self-host manifest and bundle`.

---

### Task 6: Build candidates once and promote only qualified digests

**Blocks:** B02, B06, B15  
**Files:**

- Modify: `.github/workflows/release.yml`
- Modify: `apps/api/tests/unit/test_release_workflow_gate_guard.py`
- Create: `apps/api/tests/unit/test_self_host_release_workflow_contract.py`

**Interfaces:**

The workflow has two non-overlapping graphs. A tag can build candidates but cannot qualify or
publish them:

```text
require-green-ci
  -> build-candidates
  -> assemble-self-host-release
  -> publish-candidate-summary
```

Only a later manual `workflow_dispatch` with exact candidate and qualification run IDs can execute:

```text
verify-qualified-evidence
  -> finalize-qualified-manifest
  -> promote-images
  -> create-release
```

`build-candidates` uploads one JSON record per app containing repository, index digest, per-platform
child-manifest and config digests, source SHA, and candidate tag. `assemble-self-host-release`
resolves every dependency's index plus amd64/arm64 child-manifest and config digests,
generates both SBOMs, builds the host bundle, computes its archive and canonical-tree SHA-256 values,
and emits a candidate manifest.
`publish-candidate-summary` uploads the candidate assets and prints their hashes; it invokes no
runtime workflow. `verify-qualified-evidence` downloads immutable artifacts from the two explicit
run IDs, validates the source/candidate hashes and four-row evidence, and rejects any workflow name,
conclusion, repository, or source identity mismatch. `finalize-qualified-manifest` then changes only
the manifest qualification field from `candidate` to `passed`.
`promote-images` uses `docker buildx imagetools create` to attach semver tags to those digests; it
does not build.

- [ ] **Step 1: Extend the red release guard**

Assert both job graphs, the manual-only promotion trigger, exact index/child-manifest/config digest
outputs, both platform names, API
provenance build args, explicit
empty Web API build arg, two SBOM paths, bundle archive/tree hashes, hash-bound qualification
evidence, immutable
candidate-to-passed transition, promotion dependency, and absence of
`${{ github.ref_name }}` from pull instructions. Assert `promote-images` has no
`docker/build-push-action` step and includes `imagetools create`. Assert the tag graph cannot reach
promotion and `.github/workflows/release.yml` never calls the disposable workflow. Release notes
must run `sha256sum --check lia-self-host-bundle.tar.gz.sha256` before their first `tar` command.

- [ ] **Step 2: Prove red**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_release_workflow_gate_guard.py tests/unit/test_self_host_release_workflow_contract.py -v
```

Expected: failure because digest aggregation, qualification, Web SBOM, and promotion jobs are absent.

- [ ] **Step 3: Implement candidate and promotion flow**

Use candidate tags only as registry staging handles:

```text
ghcr.io/${{ github.repository }}/api:sha-${{ github.sha }}
ghcr.io/${{ github.repository }}/web:sha-${{ github.sha }}
```

All qualification and manifest inputs use the Buildx `digest` output joined to the repository, never
the candidate tag. Pass `APP_VERSION`, `GIT_COMMIT_SHA=${{ github.sha }}`, and UTC `BUILD_DATE` to
the API build. Attach `sbom-api.cdx.json`, `sbom-web.cdx.json`,
`lia-self-host-manifest.json`, the deterministic bundle, and its archive `.sha256` file to the
release; the canonical tree hash remains inside the manifest.

The promotion dispatch inputs are exactly `candidate_run_id` and `qualification_run_id`, both
positive decimal GitHub Actions run IDs. The verification job resolves artifacts through the GitHub
API and accepts only successful runs in the same repository whose workflow filenames and manifest
hashes match the expected candidate/reviewer-approved qualification pair. User-supplied artifact
URLs, tags, repositories, and digest overrides are forbidden.

- [ ] **Step 4: Prove the workflow contract statically**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_release_workflow_gate_guard.py tests/unit/test_self_host_release_workflow_contract.py -v
cd ../..
task lint:ci-parity
```

Expected: all exit 0. No release workflow is dispatched during this task.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `ci(release): qualify exact image digests before promotion`.

---

### Task 7: Make the five-file reference seed bootstrap atomic and retryable

**Blocks:** B08, B09  
**Files:**

- Create: `apps/api/scripts/data/apply_reference_seeds.sh`
- Create: `infrastructure/database/seeds/verify_reference_seeds.sql`
- Modify: `infrastructure/database/seeds/google_api_pricing_seed.sql`
- Modify: `infrastructure/database/seeds/image_generation_pricing_seed.sql`
- Modify: `infrastructure/database/seeds/llm_config_seed.sql`
- Modify: `infrastructure/database/seeds/llm_pricing_seed.sql`
- Modify: `infrastructure/database/seeds/personalities_seed.sql`
- Modify: `apps/api/docker-entrypoint.sh`
- Modify: `apps/api/src/domains/system_settings/models.py`
- Test: `apps/api/tests/unit/test_reference_seed_bundle_contract.py`
- Test: `apps/api/tests/unit/test_entrypoint_seed_gate_guard.py`

**Interfaces:**

```text
apply_reference_seeds.sh "$SEED_BUNDLE_SHA256"
PSQL_BIN optional test indirection, default "psql"
one invocation:
  "$PSQL_BIN" -X --set ON_ERROR_STOP=1 --single-transaction
       --set "seed_bundle_version=$SEED_BUNDLE_SHA256"
       -f infrastructure/database/seeds/google_api_pricing_seed.sql
       -f infrastructure/database/seeds/image_generation_pricing_seed.sql
       -f infrastructure/database/seeds/llm_config_seed.sql
       -f infrastructure/database/seeds/llm_pricing_seed.sql
       -f infrastructure/database/seeds/personalities_seed.sql
       -f infrastructure/database/seeds/verify_reference_seeds.sql
marker:
  system_settings.key = "SELF_HOST_SEED_BUNDLE"
  system_settings.value = "$SEED_BUNDLE_SHA256"
```

`SEED_BUNDLE_SHA256` is the 64-character lowercase SHA-256 of six ASCII records in the invocation
order above. Each record is `repository-relative POSIX path`, one NUL byte, the lowercase SHA-256 of
that file's raw bytes, and one LF byte.

The Python enum member is
`SystemSettingKey.SELF_HOST_SEED_BUNDLE = "self_host_seed_bundle"`, but the existing SQLAlchemy
`Enum(..., native_enum=False)` persists enum **member names**. Raw SQL therefore writes and queries
the exact database token `SELF_HOST_SEED_BUNDLE`; tests must round-trip that row through the ORM.

- [ ] **Step 1: Write red atomicity guards**

The tests assert one executable `psql` call, all five `-f` arguments, the verification file last,
`ON_ERROR_STOP=1`, `--single-transaction`, and no loop that launches `psql` per file. A PATH-stubbed
fake `psql` records argv and returns an injected non-zero code; the wrapper must propagate it and
must not print success. A focused SQLAlchemy test inserts the enum member, confirms the raw stored
token is `SELF_HOST_SEED_BUNDLE`, and confirms the ORM reads it back without deserialization error.
The wrapper recomputes the six-record digest before invoking `psql`; a wrong argument or one mutated
file exits non-zero without a database call.

Static SQL assertions require:

```sql
RAISE EXCEPTION
```

for bad personalities/translations, Google pricing, image pricing, LLM model pricing, and 41 LLM
configuration rows. The final marker insert follows all checks in the same transaction.

- [ ] **Step 2: Prove red**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_reference_seed_bundle_contract.py tests/unit/test_entrypoint_seed_gate_guard.py -v
```

Expected: failures on per-file execution, warning-only validation, and missing marker.

- [ ] **Step 3: Implement the single transaction**

Add `SystemSettingKey.SELF_HOST_SEED_BUNDLE = "self_host_seed_bundle"`. The entrypoint keeps both
fail-closed gates: explicit `APPLY_SEEDS=true` and confirmed empty personalities. It also refuses a
non-empty marker. When armed, it invokes the wrapper exactly once. Its success log occurs only after
the wrapper exits 0. The wrapper computes the exact six-record digest using the six logical
repository-relative names above (never absolute container paths), compares it exactly to
its 64-lowercase-hex argument, and starts `psql` only on equality.

The installer computes the bundle version with the exact six-record algorithm above. After
successful verification, it regenerates the install override with
`APPLY_SEEDS=false` before any later restart.

- [ ] **Step 4: Prove green hermetically**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_reference_seed_bundle_contract.py tests/unit/test_entrypoint_seed_gate_guard.py -v
```

Expected: all pass. Transaction behavior against PostgreSQL remains reserved for Task 16's
disposable failure-injection row.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `fix(bootstrap): apply reference seeds as one verified transaction`.

---

### Task 8: Add stdin-only atomic admin and provider bootstrap

**Blocks:** B10, B11  
**Files:**

- Create: `apps/api/src/domains/llm_config/install_contract.py`
- Modify: `apps/api/src/domains/llm_config/service.py`
- Modify: `apps/api/src/infrastructure/llm/providers/adapter.py`
- Modify: `apps/api/src/infrastructure/llm/providers/responses_adapter.py`
- Modify: `apps/api/scripts/data/create_admin.py`
- Create: `apps/api/scripts/data/bootstrap_install.py`
- Modify: `Taskfile.yml`
- Modify: `docs/guides/GUIDE_DEPLOYMENT.md`
- Test: `apps/api/tests/unit/domains/llm_config/test_install_contract.py`
- Test: `apps/api/tests/unit/test_create_admin_script.py`
- Test: `apps/api/tests/unit/test_bootstrap_install_script.py`
- Create: `apps/api/tests/unit/infrastructure/llm/providers/test_openai_base_url.py`

**Interfaces:**

```python
CURRENT_CORE_LLM_TYPES: tuple[str, ...] = (
    "router",
    "planner",
    "query_analyzer",
    "query_agent",
    "semantic_validator",
    "response",
    "context_resolver",
    "hitl_classifier",
)
CURRENT_CORE_PROVIDER_IDS: tuple[str, ...] = ("deepseek", "openai")

def required_current_core_provider_ids() -> tuple[str, ...]: ...
    # Derived from the POST-SEED effective configuration: for each reachable
    # default-enabled slot, take the seeded override provider when non-NULL,
    # else the code default. The literal above is the audited result; the
    # anti-drift test recomputes it from constants + the parsed seed file.

async def ensure_admin(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
) -> UUID: ...

async def upsert_provider_key_uncommitted(
    db: AsyncSession,
    *,
    provider: str,
    key: str,
    updated_by: UUID,
) -> None: ...

async def bootstrap(payload: BootstrapPayload, db: AsyncSession) -> BootstrapResult: ...
def main() -> int: ...
```

B10-bis owner arbitration (2026-08-06): the seeded overrides are kept untouched — no
reconciliation function exists. `bootstrap()` stores one encrypted key per provider in
`CURRENT_CORE_PROVIDER_IDS`, and `BootstrapResult` reports the derived required-provider set plus
the optional seeded capabilities left unkeyed (`vision_analysis`/Gemini, `voice_tts`/ElevenLabs).

`main()` reads exactly one JSON object from stdin. It accepts admin email/password/name and provider
keys with exactly the required IDs. Output contains only admin ID/email, provider IDs, and status.

- [ ] **Step 1: Write failing business tests**

Cover:

- the derived current-core provider set is exactly OpenAI/DeepSeek, computed from code
  defaults merged with the parsed `llm_config_seed.sql` overrides (post-seed effective
  configuration);
- changing one core slot (in code default or in the seed) to a provider outside the derived set
  makes the anti-drift test fail;
- invalid admin password raises before a query;
- existing non-admin is promoted idempotently;
- existing admin is unchanged;
- provider rows are encrypted and decrypt to the canary values;
- failure on the second provider rolls back admin and first provider;
- the seeded overrides are never mutated by bootstrap (owner arbitration): a canary read before
  and after `bootstrap()` proves `llm_config_overrides` rows are byte-identical, and
  `BootstrapResult` lists the unkeyed optional capabilities (Gemini vision, ElevenLabs voice);
- successful commit calls the existing `LLMConfigOverrideCache.invalidate_and_reload()` contract;
- invalidation failure returns a stable non-secret error after commit, and an idempotent retry
  republishes it without duplicating the admin or provider rows;
- OpenAI defaults to `https://api.openai.com/v1`, honors an explicit `OPENAI_BASE_URL`, and passes it
  to both Chat Completions and Responses API adapters exactly as Qwen already honors
  `QWEN_BASE_URL`;
- stdout, stderr, exception text, SQL recorder, and argv recorder contain no canary secret;
- EOF or malformed JSON exits non-zero with a non-secret error code;
- the old `admin123` default and `--password` installer path are absent.

- [ ] **Step 2: Prove red**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/domains/llm_config/test_install_contract.py tests/unit/test_create_admin_script.py tests/unit/test_bootstrap_install_script.py tests/unit/infrastructure/llm/providers/test_openai_base_url.py -v
```

Expected: missing modules/functions and the insecure default assertion fails.

- [ ] **Step 3: Implement one transaction and one authority**

`ensure_admin()` calls `validate_password_strict()` before hashing. All reusable helpers flush but
never commit. `bootstrap()` uses `async with db.begin():` around admin and all three provider
writes, so a failure anywhere rolls the whole bootstrap back to the freshly seeded state; the
seeded LLM overrides are read-only for bootstrap (B10-bis owner arbitration).
The API-facing `LLMConfigService.update_provider_key()` delegates to the same upsert helper, then
retains its audit log, commit, and cache invalidation. After the bootstrap transaction commits, the
one-off process calls `LLMConfigOverrideCache.invalidate_and_reload(db)` so Redis notifies live API
workers. If that post-commit step fails, return a stable failure and let resume repeat the idempotent
upserts plus publication; never claim rollback of the already-committed bootstrap.

Keep manual admin creation usable through stdin or an interactive `getpass` prompt; never restore a
default password. Update `db:create-admin` documentation to pipe stdin without echoing or embedding
the value in Task output.

Add OpenAI to `_BASE_URL_DEFAULTS`, route its Chat adapter through `_get_base_url("openai")`, and add
an explicit `base_url` parameter to `create_responses_llm()` so eligible `gpt-4.1+` defaults use the
same override. Verify and, if absent, add the equivalent DeepSeek base-URL override
(`DEEPSEEK_BASE_URL` through the langchain-deepseek adapter's `api_base`) — the seeded core runs on
DeepSeek, so the hermetic qualification chat must be able to point all three required providers at
the fake endpoint. This is required only so disposable qualification can use a hermetic provider.
The installer exposes no arbitrary-endpoint question, and these technical overrides do not satisfy
or weaken G6.

- [ ] **Step 4: Prove green and type safety**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/domains/llm_config/test_install_contract.py tests/unit/test_create_admin_script.py tests/unit/test_bootstrap_install_script.py tests/unit/infrastructure/llm/providers/test_openai_base_url.py -v
.venv/Scripts/python -m ruff check scripts/data/bootstrap_install.py scripts/data/create_admin.py src/domains/llm_config src/infrastructure/llm/providers/adapter.py src/infrastructure/llm/providers/responses_adapter.py
.venv/Scripts/python -m mypy scripts/data/bootstrap_install.py scripts/data/create_admin.py src/domains/llm_config/install_contract.py src/infrastructure/llm/providers/adapter.py src/infrastructure/llm/providers/responses_adapter.py
```

Expected: all exit 0.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `feat(bootstrap): atomically create admin and encrypted provider keys`.

---

### Task 9: Add a backend installation verifier beyond readiness

**Blocks:** B12  
**Files:**

- Create: `apps/api/scripts/data/verify_installation.py`
- Test: `apps/api/tests/unit/test_verify_installation_script.py`

**Interfaces:**

```python
class CheckName(str, Enum):
    MIGRATIONS = "migrations"
    SEED_MARKER = "seed_marker"
    REFERENCE_DATA = "reference_data"
    ADMIN = "admin"
    PROVIDER_KEYS = "provider_keys"
    PROVIDER_COVERAGE = "provider_coverage"

@dataclass(frozen=True)
class CheckResult:
    name: CheckName
    passed: bool
    code: str
    detail: str

async def verify_installation(
    db: AsyncSession,
    *,
    admin_email: str,
    expected_alembic_head: str,
    expected_seed_bundle_sha256: str,
) -> tuple[CheckResult, ...]: ...
def load_single_alembic_head(config_path: Path) -> str: ...
def render_json(results: Sequence[CheckResult]) -> str: ...
def main() -> int: ...
```

- [ ] **Step 1: Write red verifier tests**

Use a fake AsyncSession or the existing async DB fixtures to cover each independent failure. Exact
success requirements are:

- the code's Alembic script directory has exactly one head and `alembic_version` has exactly one row
  equal to that head;
- the ORM-readable `SystemSettingKey.SELF_HOST_SEED_BUNDLE` marker equals the expected 64-lowercase-
  hex digest computed by the installer, not merely a non-empty value;
- personalities = 14, translations = 84, Google pricing >= 9, image pricing >= 27,
  LLM models >= 96, and LLM config overrides >= 41 (the seed is kept verbatim — B10-bis owner
  arbitration);
- the requested user is active, verified, and superuser;
- OpenAI and DeepSeek rows exist and decrypt successfully;
- every entry in `CURRENT_CORE_LLM_TYPES` resolves to a provider in `CURRENT_CORE_PROVIDER_IDS`,
  evaluated on the post-seed effective configuration (DB override if present, else code default)
  — never on code defaults alone; OpenAI and DeepSeek rows both exist and decrypt.

Assert no decrypted key appears in JSON.

`main()` requires `--admin-email` and `--seed-bundle-sha256`, loads the current code head from
`alembic.ini`, and rejects malformed expected hashes before opening a database session.

- [ ] **Step 2: Prove red**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_verify_installation_script.py -v
```

Expected: missing verifier module.

- [ ] **Step 3: Implement read-only checks**

Run all checks even after one fails so the operator receives one complete report. Use parameterized
SQL and stable non-secret codes. Exit 0 only when every result passes. Do not modify `/ready`; the
installer calls this verifier after `/ready`.

- [ ] **Step 4: Prove green**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_verify_installation_script.py -v
.venv/Scripts/python -m ruff check scripts/data/verify_installation.py
.venv/Scripts/python -m mypy scripts/data/verify_installation.py
```

Expected: all exit 0.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `feat(bootstrap): verify functional installation postconditions`.

---

### Task 10: Build the declarative questionnaire and ephemeral secret flow

**Blocks:** B10, B13  
**Files:**

- Create: `scripts/install/model.py`
- Create: `scripts/install/i18n.py`
- Create: `scripts/install/questions.py`
- Create: `scripts/install/answers.py`
- Create: `scripts/install/verify.py`
- Create: `scripts/install/tests/__init__.py`
- Create: `scripts/install/tests/conftest.py`
- Create: `scripts/install/tests/test_i18n.py`
- Create: `scripts/install/tests/test_questions.py`
- Create: `scripts/install/tests/test_answers.py`
- Create: `scripts/install/tests/test_verify.py`
- Create: `scripts/install/tests/test_stdlib_only.py`

**Interfaces:**

```python
class InstallMode(str, Enum):
    LOCAL = "local"
    PREBUILT = "prebuilt"

class Exposure(str, Enum):
    LAN = "lan"
    PROXY = "proxy"
    CADDY = "caddy"

@dataclass(frozen=True)
class PublicAnswers:
    language: Literal["en", "fr"]
    mode: InstallMode
    exposure: Exposure
    admin_email: str
    admin_name: str
    default_language: Literal["fr", "en", "es", "de", "it", "zh-CN"]
    observability: bool
    skill_sandbox: bool
    server_host: str | None
    web_domain: str | None
    api_domain: str | None
    caddy_email: str | None
    manifest_path: Path | None

@dataclass(frozen=True)
class SecretAnswers:
    admin_password: str
    provider_keys: Mapping[str, str]

@dataclass
class IOAdapter:
    input_fn: Callable[[str], str]
    getpass_fn: Callable[[str], str]
    print_fn: Callable[[str], None]

def collect_answers(
    questions: Sequence[Question],
    *,
    io: IOAdapter,
    non_interactive: bool,
    answers_path: Path | None,
) -> tuple[PublicAnswers, SecretAnswers]: ...
def load_answers_file(path: Path) -> Mapping[str, str]: ...
def verify_provider_key(provider: str, key: str, opener: UrlOpener) -> VerifyOutcome: ...
```

- [ ] **Step 1: Write red flow tests**

Cover all exposure branches, both modes, six application languages, optional observability and skill
sandbox, invalid email/domain/password, non-interactive missing secret failure, and fake OpenAI/DeepSeek
verification responses. Assert:

- local is the default when no adjacent validated passed manifest exists;
- prebuilt requires a manifest path;
- OpenAI and DeepSeek secrets are required for the current-core baseline (post-seed effective set, B10-bis — the seed overrides every qwen default, so Qwen is optional);
- secret prompts use `getpass_fn`;
- `PublicAnswers` cannot contain password/key fields;
- provider keys are not environment-key questions;
- every message ID exists in both languages;
- AST imports under `scripts/install/` belong to the stdlib or `scripts.install`.
- installer enums use `class Name(str, Enum)` and never `enum.StrEnum`, preserving Python 3.10.

- [ ] **Step 2: Prove red**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests/test_i18n.py scripts/install/tests/test_questions.py scripts/install/tests/test_answers.py scripts/install/tests/test_verify.py scripts/install/tests/test_stdlib_only.py -v
```

Expected: module import failures.

- [ ] **Step 3: Implement declarative questions**

The optional key verification uses injected `urllib` openers and never blocks installation on a
network error. HTTP 401/403 means invalid; 200 means valid; timeout/URL error means unverified. Never
place a Gemini key in a query string because Gemini is not in the current-core baseline set.

An answers file may contain secrets, but the loader requires mode `0o600` on POSIX and rejects a
group/world-readable file. It is read once and never copied.

- [ ] **Step 4: Prove green**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests/test_i18n.py scripts/install/tests/test_questions.py scripts/install/tests/test_answers.py scripts/install/tests/test_verify.py scripts/install/tests/test_stdlib_only.py -v
```

Expected: all pass without network.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `feat(installer): add audited questionnaire and ephemeral secrets`.

---

### Task 11: Generate environment, image lock, exposure override, and host paths

**Blocks:** B03, B04, B05, B06  
**Files:**

- Create: `scripts/install/envgen.py`
- Create: `scripts/install/compose.py`
- Create: `scripts/install/host_paths.py`
- Create: `scripts/install/seed_bundle.py`
- Create: `infrastructure/caddy/Caddyfile.template`
- Create: `scripts/install/tests/test_envgen.py`
- Create: `scripts/install/tests/test_compose.py`
- Create: `scripts/install/tests/test_host_paths.py`
- Create: `scripts/install/tests/test_seed_bundle.py`
- Create: `scripts/install/tests/render_compose_matrix.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ComposeInvocation:
    files: tuple[Path, ...]
    profiles: tuple[str, ...]
    mode: InstallMode

    def prefix(self) -> list[str]: ...

def generate_secrets() -> Mapping[str, str]: ...
def load_existing_generated_secrets(path: Path, required_keys: Collection[str]) -> Mapping[str, str]: ...
def derive_environment(public: PublicAnswers, generated: Mapping[str, str]) -> Mapping[str, str]: ...
def render_env(base: str, values: Mapping[str, str]) -> str: ...
def write_atomic_private(path: Path, content: str) -> Path | None: ...
def compute_seed_bundle_sha256(root: Path) -> str: ...
def render_install_override(
    public: PublicAnswers,
    *,
    seed_intent: bool,
    seed_bundle_sha256: str,
) -> str: ...
def required_host_paths(invocation: ComposeInvocation) -> tuple[HostPathRequirement, ...]: ...
def prepare_host_paths(requirements: Sequence[HostPathRequirement]) -> None: ...
```

Import `SelfHostManifest` and `render_image_lock()` from `scripts.install.manifest`; do not define a
second manifest model or renderer. Pass the exact service names already defined by the selected
base/install/skill layers so the lock cannot introduce Caddy into a LAN/proxy scenario. The API
override also sets `SKILLS_SCRIPT_SANDBOX_IMAGE` to the locked API digest when the sandbox is enabled.

For the base plus generated install overlay, `ComposeInvocation.prefix()` returns exactly
`["docker", "compose", "-f", "docker-compose.prod.yml", "-f",
"docker-compose.install.yml"]`; it never uses a joined filename.

- [ ] **Step 1: Write red artifact tests**

Cover:

- Fernet is 44-character URL-safe base64 decoding to 32 bytes;
- reconfiguration loads every required generated secret from the existing mode-0600 `.env`, rejects
  missing/placeholder/duplicate values, and generates no replacement;
- no provider key is rendered to `.env`;
- LAN renders `APP_URL_SERVER=http://{validated_server_host}:3000` and non-secure cookies;
- proxy/Caddy render `APP_URL_SERVER=https://{validated_web_domain}` and secure cookies;
- all modes retain `API_URL_SERVER=http://api:8000`; no runtime value tries to rewrite baked
  `NEXT_PUBLIC_*` values;
- local Compose uses local image defaults and allows build;
- prebuilt renders app/dependency digests and rejects tags;
- prebuilt command suffixes always include `--no-build`;
- Python seed-bundle hashing matches the Task 7 six-record golden vector and changes when any of the
  six files changes;
- the generated override always carries the computed non-secret seed-bundle SHA-256, while only the
  fresh-start candidate carries `APPLY_SEEDS=true`;
- LAN port lists use Compose `!override`;
- Caddy template produces Web/API vhosts and ACME email;
- only Caddy exposure adds a `caddy` service with ports `80:80` and `443:443`, the generated
  read-only Caddyfile, and named `caddy_data`/`caddy_config` volumes;
- local Caddy uses `${LIA_CADDY_IMAGE:-caddy:2-alpine}` while prebuilt Caddy is overridden by the
  exact catalogue digest;
- observability and skill overlays are included only when selected;
- every `-f` is a distinct argv element;
- `apps/api/config` and the resolved backup directory are created with expected modes;
- an expected file path that is a directory, or vice versa, fails before Compose;
- existing `.env` is backed up and a failed write leaves it intact.

- [ ] **Step 2: Prove red**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests/test_envgen.py scripts/install/tests/test_compose.py scripts/install/tests/test_host_paths.py scripts/install/tests/test_seed_bundle.py -v
```

Expected: missing modules.

- [ ] **Step 3: Implement exact mode behavior**

Prebuilt mode requires a `qualification="passed"` manifest and writes:

```text
docker-compose.install.yml
docker-compose.images.yml
infrastructure/caddy/Caddyfile   only for Caddy
```

Local mode never writes an image lock. Both modes validate all bind sources. The backup directory
must resolve outside the release bundle by default and be created as `0o700`; `apps/api/config` is
`0o700`. Generated Compose files are `0o600`. For `Exposure.CADDY`,
`docker-compose.install.yml` owns the optional `caddy` service and its two named volumes; neither
LAN nor proxy output contains that service.

- [ ] **Step 4: Prove green and render the static matrix**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests/test_envgen.py scripts/install/tests/test_compose.py scripts/install/tests/test_host_paths.py scripts/install/tests/test_seed_bundle.py -v
apps/api/.venv/Scripts/python scripts/install/tests/render_compose_matrix.py
```

Expected: all pass; the matrix script renders every scenario into a temporary directory and runs
`docker compose config --quiet` only. Task 15 later delegates its named Task target to this script.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `feat(installer): generate private config and exact Compose layers`.

---

### Task 12: Implement versioned state, redacted logs, and safe resume

**Blocks:** B13  
**Files:**

- Create: `scripts/install/state.py`
- Create: `scripts/install/redaction.py`
- Create: `scripts/install/log.py`
- Create: `scripts/install/tests/test_state.py`
- Create: `scripts/install/tests/test_redaction.py`
- Create: `scripts/install/tests/test_log.py`

**Interfaces:**

```python
STATE_SCHEMA_VERSION = 1

class Step(str, Enum):
    PREFLIGHT = "preflight"
    QUESTIONS = "questions"
    GENERATE = "generate"
    ACQUIRE = "acquire"
    VALIDATE = "validate"
    START = "start"
    BOOTSTRAP = "bootstrap"
    VERIFY = "verify"
    REPORT = "report"

@dataclass(frozen=True)
class InstallState:
    schema_version: int
    installer_version: str
    mode: InstallMode
    public_answers: PublicAnswers
    release_id: str | None
    bundle_tree_sha256: str | None
    source_context_tree_sha256: str | None
    image_digests: Mapping[str, str]
    seed_bundle_sha256: str
    completed: tuple[Step, ...]
    attempts: Mapping[Step, int]
    last_error_code: str | None
    generated_sha256: Mapping[str, str]
    bootstrap_complete: bool
    project_name: str

class ResumeDecision(str, Enum):
    CONTINUE = "continue"
    REPROMPT_SECRETS = "reprompt_secrets"
    STOP_MISMATCH = "stop_mismatch"

def load_state(path: Path) -> InstallState | None: ...
def save_state(path: Path, state: InstallState) -> None: ...
def decide_resume(state: InstallState, observed: ResumeInputs) -> ResumeDecision: ...
def redact(text: str, secrets: Iterable[str]) -> str: ...
```

- [ ] **Step 1: Write red state and canary tests**

Test atomic state replacement, schema rejection, round-trip of every `PublicAnswers` field,
manifest/host-tree/source-context-tree/image-digest/seed-bundle mismatch, generated-file hash mismatch, per-step attempt increments,
non-secret error codes, and the exact secret re-prompt rule: bootstrap incomplete returns
`REPROMPT_SECRETS`; bootstrap complete never does. Assert serialized state can reconstruct exposure,
profiles, host/domain values, admin email/name, language, and manifest path, but its schema cannot
contain `SecretAnswers`, password, or provider-key fields.

Use canaries containing regex punctuation, URL encoding, JSON escaping, and base64. Assert none
appear in state JSON, log output, translated exceptions, report input, or a recorded runner argv.

- [ ] **Step 2: Prove red**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests/test_state.py scripts/install/tests/test_redaction.py scripts/install/tests/test_log.py -v
```

Expected: missing modules.

- [ ] **Step 3: Implement fail-closed resume**

State and logs are mode `0o600`. State writes use a sibling temporary file, flush, `os.fsync`, and
`os.replace`. Redaction replaces longest secrets first and also covers URL-encoded and JSON-escaped
forms. A state parse error, unknown schema, release mismatch, or fingerprint mismatch returns a
stable stop code and performs no repair or Compose action.

- [ ] **Step 4: Prove green and scan artifacts**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests/test_state.py scripts/install/tests/test_redaction.py scripts/install/tests/test_log.py -v
```

Expected: all pass and every canary scan is empty.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `feat(installer): add fail-closed resume and secret redaction`.

---

### Task 13: Add deploy orchestration and bounded rollback semantics

**Blocks:** B08, B12, B14  
**Files:**

- Create: `scripts/install/deploy.py`
- Create: `scripts/install/rollback.py`
- Create: `scripts/install/tests/test_deploy.py`
- Create: `scripts/install/tests/test_rollback.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

class Runner(Protocol):
    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult: ...

@dataclass(frozen=True)
class RollbackPoint:
    previous_images: Mapping[str, str]
    rollback_aliases: Mapping[str, str]
    config_backups: Mapping[Path, Path]
    first_install: bool

def acquire(invocation: ComposeInvocation, runner: Runner) -> None: ...
def validate_settings(invocation: ComposeInvocation, runner: Runner) -> None: ...
def start(invocation: ComposeInvocation, runner: Runner, *, seed_intent: bool) -> None: ...
def wait_ready(url: str, opener: UrlOpener, clock: Clock, timeout_s: int = 300) -> None: ...
def run_bootstrap(
    invocation: ComposeInvocation,
    public: PublicAnswers,
    secrets: SecretAnswers,
    runner: Runner,
) -> None: ...
def restart_api_without_build(invocation: ComposeInvocation, runner: Runner) -> None: ...
def run_verifier(
    invocation: ComposeInvocation,
    *,
    admin_email: str,
    seed_bundle_sha256: str,
    runner: Runner,
) -> None: ...
def capture_rollback_point(
    invocation: ComposeInvocation,
    state: InstallState | None,
    runner: Runner,
) -> RollbackPoint: ...
def restore_or_quiesce(point: RollbackPoint, invocation: ComposeInvocation, runner: Runner) -> None: ...
def reconfigure_existing(
    *,
    current: InstallState,
    candidate_public: PublicAnswers,
    candidate_files: Mapping[Path, Path],
    invocation: ComposeInvocation,
    runner: Runner,
) -> None: ...
```

Append these exact suffixes to `ComposeInvocation.prefix()`:

```text
Settings:
  run --rm --no-deps --entrypoint "" api python -m scripts.validate_settings
Bootstrap, with the single JSON document supplied as runner stdin:
  run --rm --no-deps -T --entrypoint "" api python -m scripts.data.bootstrap_install
Verifier prefix:
  run --rm --no-deps -T --entrypoint "" api python -m scripts.data.verify_installation
```

The verifier then appends exactly
`["--admin-email", public.admin_email, "--seed-bundle-sha256",
state.seed_bundle_sha256]`. Email/name and the content digest are non-secret; passwords and keys
remain stdin-only.

- [ ] **Step 1: Write red argv and failure-injection tests**

The recording runner proves:

- local acquire calls `build api web`;
- prebuilt acquire calls `pull api web` and never contains `build`;
- Settings validation uses `run --rm --no-deps --entrypoint "" api python -m scripts.validate_settings`;
- fresh start sets seed intent true only for the first start;
- bootstrap argv contains no password or provider key and sends one JSON stdin payload containing
  public admin email/name plus the ephemeral admin password and provider keys;
- after bootstrap, API recreation uses `up -d --no-deps --force-recreate --no-build api`, then a
  second readiness wait; this guarantees every API worker starts from the committed provider rows;
- the generated override is rewritten with seed intent false immediately after the first `/ready`,
  before bootstrap can fail or an operator can interrupt;
- verifier runs after `/ready` and bootstrap;
- success writes the exact deployed image pair and file hashes;
- an existing local installation resolves both running image IDs and creates project-scoped
  rollback aliases before either local tag can be overwritten by `build`;
- a prebuilt rollback point retains its prior immutable manifest digests without retagging;
- existing-install failure restores prior exact images/config then rechecks readiness;
- first-install failure stops only services in its project, never adds `--volumes`, and preserves
  generated backups;
- every raised `StepFailed` contains a stable code and `./install.sh --resume`, never raw secrets.
- reconfiguration rejects mode/release/admin identity changes, preserves existing generated secrets,
  never arms seeds or invokes bootstrap, validates candidate files before replacement, recreates
  only the recorded project with `--no-build`, and restores files/readiness on failure.

- [ ] **Step 2: Prove red**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests/test_deploy.py scripts/install/tests/test_rollback.py -v
```

Expected: missing modules.

- [ ] **Step 3: Implement the ordered state machine**

The execution order is exact:

```text
capture rollback -> acquire -> validate Settings -> start with fresh seed intent
-> /ready -> clear seed intent -> stdin bootstrap -> recreate API with --no-build
-> second /ready -> backend verifier
-> record manifest -> report
```

The first `/ready` proves that the entrypoint completed its blocking seed wrapper and launched the
API; only then may the installer atomically replace the generated override with
`APPLY_SEEDS=false`. If that replacement fails, stop before bootstrap and quiesce or restore. This
prevents a resume after a later bootstrap/verifier failure from re-entering the seed gate with a
non-empty marker.

The post-bootstrap invalidation publication is retained for the normal hot-update contract, but it
is not treated as a worker barrier. The forced API recreation after seed intent is false is the
installer's barrier: all workers execute startup cache loading against the committed rows before the
second `/ready`. Failure to recreate or reach readiness enters the same bounded rollback path.

The separate reconfiguration path is exact:

```text
verify matching state/project -> collect allowed non-secret fields -> render temporary candidates
-> static Compose + Settings validation -> back up mode 0600 -> atomically replace candidates
-> up -d --no-build --remove-orphans for the recorded project -> /ready -> backend verifier
-> atomically update public_answers/file fingerprints -> report
```

Allowed changes are exposure, server host, Web/API domains, Caddy email, observability, and skill
sandbox. Mode, release/manifest, image digests, seed identity, admin email/name, database identity,
and every generated secret are immutable. Provider-key replacement remains an Admin UI operation.

On any failure after capture, call `restore_or_quiesce()`. For an existing local installation,
capture the running API/Web image IDs and alias each before acquisition as
`lia-installer-rollback-{project_name}-{service}:{attempt}`; the rollback overlay references those
aliases, not the mutable `lia-*:local` names. Remove only those two aliases after final success or a
successful restore. Prebuilt rollback uses the prior manifest's exact digests and creates no alias.
A first install may stop only the unique
project's containers; it leaves volumes, `.env`, backups, state, and logs for resume. An existing
installation restores the saved app pair and configuration, recreates with `--no-build`, and must
pass `/ready` before reporting rollback success.

- [ ] **Step 4: Prove green**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests/test_deploy.py scripts/install/tests/test_rollback.py -v
task test:deploy
```

Expected: all pass without Docker daemon or network.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `feat(installer): orchestrate verified start with bounded rollback`.

---

### Task 14: Wire the CLI, preflight, report, and non-destructive lifecycle

**Blocks:** B01, B05, B12, B13  
**Files:**

- Create: `scripts/install/preflight.py`
- Create: `scripts/install/report.py`
- Create: `scripts/install/__main__.py`
- Create: `install.sh`
- Modify: `.gitignore`
- Modify: `docs/GETTING_STARTED.md`
- Modify: `README.md`
- Modify: `docs/guides/GUIDE_DEPLOYMENT.md`
- Create: `scripts/install/tests/test_preflight.py`
- Create: `scripts/install/tests/test_report.py`
- Create: `scripts/install/tests/test_main_flow.py`
- Create: `scripts/install/tests/test_install_sh.py`

**Interfaces:**

```text
./install.sh                                      # local without adjacent passed manifest
./install.sh                                      # prebuilt with adjacent passed manifest
./install.sh --local-build
./install.sh --prebuilt --manifest lia-self-host-manifest.json
./install.sh --resume
./install.sh --reconfigure
./install.sh --non-interactive --answers /protected/answers.env
./install.sh --dry-run
./install.sh --check-only
```

`--dry-run` stops after validated artifact generation and starts no service. `--check-only` performs
prerequisite checks only.

```python
def resolve_install_mode(
    *,
    requested: InstallMode | None,
    bundle_root: Path,
) -> tuple[InstallMode, Path | None]: ...
```

An explicit `--local-build` always wins. Explicit prebuilt requires a passed manifest. With no mode
flag, the resolver loads only `bundle_root / "lia-self-host-manifest.json"`: absent or candidate means
local, while a valid passed manifest means prebuilt. It never searches parent directories, follows a
manifest symlink, or selects a mutable image reference.

- [ ] **Step 1: Write red end-to-end hermetic tests**

With injected runner, filesystem root, opener, and clock, cover:

- a fresh all-default local dry run;
- an explicit local dry run from a complete source checkout;
- an explicit `--local-build` dry run from an official release directory verifies and selects its
  embedded source context;
- an adjacent valid passed manifest makes the no-flag dry run prebuilt;
- an absent or candidate adjacent manifest keeps the no-flag dry run local;
- an explicit prebuilt dry run with a valid passed manifest;
- a manifest paired with the wrong extracted tree fails before directory creation, backup, Docker,
  or generated-file writes;
- a release-directory local fallback with a missing, wrong-hash, wrong-source, incomplete, or
  symlinked embedded source context fails before directory creation, backup, Docker, or generated-file writes;
- rejection of candidate manifest and mutable image reference;
- preflight rejects Compose 2.24.3 and accepts 2.24.4 because LAN output uses `!override`;
- resume before bootstrap re-prompts exactly three secrets: admin password, OpenAI key, DeepSeek key;
- resume after bootstrap asks no secret;
- reconfigure offers only the seven allowed non-secret fields, preserves every generated secret,
  performs no seed/bootstrap command, and updates state only after readiness/verifier success;
- existing `.env` with no matching state aborts as an unsupported takeover; reconfiguration always
  requires the matching state, project label, database marker, mode, and release identity;
- `--check-only` never calls Docker daemon checks that mutate state;
- final report contains URLs, mode, release/digest summary, backup path, and limitations, but no
  password, key, Fernet value, database password, or internal token;
- every prebuilt report states that Firebase push is unavailable in generic v1 and that a local
  build is required for custom public Firebase/build-time values;
- Ctrl-C records an interrupted non-secret code and prints the exact resume command;
- install shell rejects any pre-existing `scripts/install/**/__pycache__`, `.pyc`, or `.pyo` before
  Python import and delegates with `PYTHONDONTWRITEBYTECODE=1 python3 -B -m scripts.install`.

- [ ] **Step 2: Prove red**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests/test_preflight.py scripts/install/tests/test_report.py scripts/install/tests/test_main_flow.py scripts/install/tests/test_install_sh.py -v
```

Expected: missing modules/scripts.

- [ ] **Step 3: Implement exact lifecycle guards**

`install.sh` checks Linux, Python >= 3.10, Docker CLI, Compose >= 2.24.4, supported
`x86_64|aarch64`, and minimum 10 GiB free. The Python preflight checks daemon reachability and
scenario ports only during a real install, never during `--dry-run`.

The POSIX cache scan runs before the first Python command and is read-only/fail-closed. The release
bundle never ships bytecode, and `-B` prevents the integrity check itself from mutating the canonical
tree on first run or resume.

For every official release directory, `validate_bundle_tree()` is the first Python-side gate after
argument parsing. It must pass before preflight creates a path or any generated artifact is backed
up or written. The release quick start separately compares the downloaded archive to
`bundle_archive_sha256` before extraction; the installer then compares the extracted allowlisted
tree to `bundle_tree_sha256`. If `--local-build` runs outside a complete source checkout, the next
gate verifies the embedded source archive against `source_context_archive_sha256`, extracts it to a
new private temporary directory, verifies `source_context_tree_sha256` plus the recorded full source
SHA, and uses only that directory for both Docker build contexts. Failure leaves no target or state;
the temporary directory is removed after build. There is no network or mutable-source fallback.

Add these ignores:

```text
.install-state.json
install.log
docker-compose.install.yml
docker-compose.images.yml
infrastructure/caddy/Caddyfile
.env.backup.*
```

No reinstall-from-scratch or volume-removal option exists.

`--reconfigure` is mutually exclusive with install/resume/mode/answers flags. It uses the matching
state's public answers as defaults, reads existing generated secrets without printing them, and
delegates to `reconfigure_existing()`. Changing provider keys remains an authenticated Admin UI
operation; changing mode/release or database schema remains the documented upgrade path.

Update the three operator documents with the same conditional rule: a complete source checkout
defaults local; an official release directory defaults prebuilt only when its adjacent manifest is
passed; `./install.sh --local-build` in that directory uses the verified embedded source context.
If neither a complete checkout nor a valid embedded context exists, it fails before mutation and
prints the exact qualified release asset required. This wording is true before and after G5, so
activation never requires a post-qualification documentation change.

- [ ] **Step 4: Prove green**

```powershell
apps/api/.venv/Scripts/pytest scripts/install/tests -v
apps/api/.venv/Scripts/python -m ruff check scripts/install
apps/api/.venv/Scripts/python -m mypy --strict scripts/install --exclude scripts/install/tests
```

Expected: all exit 0.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `feat(installer): expose the audited resumable CLI`.

---

### Task 15: Make hermetic installer proof a mandatory normal-CI gate

**Blocks:** B01, B15  
**Files:**

- Modify: `Taskfile.yml`
- Modify: `.github/workflows/ci.yml`
- Create: `scripts/install/tests_py310.py`
- Create: `apps/api/tests/unit/test_installer_ci_contract.py`

**Interfaces:**

```text
task test:install
task lint:install
task test:install:compose-matrix
task test:release:self-host
task test:install:hermetic
```

`test:install:hermetic` delegates to the four preceding tasks and the focused backend tests from
Tasks 2, 7, 8, and 9.

- [ ] **Step 1: Write a red CI parity test**

Assert each Task target exists, uses platform-correct venv paths, and is reachable from a dedicated
CI step whose `run:` is exactly `task test:install:hermetic`. Assert the release-bundle tests unpack
a newly built allowlisted bundle into a temporary directory and rerun dry-run plus Compose matrix
from that directory. Assert a separate normal-CI job uses `actions/setup-python` with exact version
`3.10`, then runs `python -B scripts/install/tests_py310.py`; no `continue-on-error` is allowed.

- [ ] **Step 2: Prove red**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_installer_ci_contract.py -v
```

Expected: missing task targets and workflow step.

- [ ] **Step 3: Add exact task delegation**

The commands are:

```yaml
test:install:
  cmds:
    - apps/api/.venv/Scripts/pytest scripts/install/tests -q
test:release:self-host:
  cmds:
    - apps/api/.venv/Scripts/pytest scripts/release/tests -q
test:install:compose-matrix:
  cmds:
    - apps/api/.venv/Scripts/python scripts/install/tests/render_compose_matrix.py
lint:install:
  cmds:
    - apps/api/.venv/Scripts/python -m ruff check scripts/install scripts/release
    - apps/api/.venv/Scripts/python -m mypy --strict scripts/install scripts/release --exclude "scripts/(install|release)/tests"
```

Add Linux equivalents with `.venv/bin/`. The matrix script invokes only
`docker compose config --quiet`. Do not add any `up`, `run`, `exec`, `pull`, `build`, or provider
request to normal CI.

`tests_py310.py` uses `unittest`, `ast`, in-memory `compile()`, and imports only the production installer
modules. It verifies the stdlib-only import allowlist, imports with
`PYTHONDONTWRITEBYTECODE=1`, exercises enum construction and manifest parsing, and fails on syntax or
runtime APIs unavailable in Python 3.10. The dedicated CI job is required by the same branch gate as
the main hermetic job.

- [ ] **Step 4: Run the complete no-service gate**

```powershell
task test:install:hermetic
task lint:ci-parity
task lint:docs
```

Expected: all exit 0 and no service is started.

- [ ] **Step 5: Checkpoint**

Present the diff and suggest: `ci(installer): require hermetic installability proof`.

---

### Task 16: Qualify disposable runtime, promote digests, then activate the manifest-selected default

**Blocks:** B02, B09, B12, B14, B15  
**Files:**

- Create: `.github/workflows/installer-disposable-smoke.yml`
- Create: `scripts/install/tests/runtime/docker-compose.disposable.yml`
- Create: `scripts/install/tests/runtime/fake_provider.py`
- Create: `scripts/install/tests/runtime/assert_install.py`
- Create: `scripts/install/tests/runtime/inject_seed_failure.py`
- Create: `apps/api/tests/unit/test_installer_disposable_workflow_contract.py`
- Create: `apps/api/tests/unit/test_self_host_marketing_claim_guard.py`

**Interfaces:**

```text
workflow trigger: workflow_dispatch only
approval environment: installer-disposable-smoke
runner rows:
  linux/amd64 -> ubuntu-24.04
  linux/arm64 -> ubuntu-24.04-arm
mode rows: local, prebuilt
project prefix: lia-installer-smoke-
OPENAI_BASE_URL: http://fake-provider:18080/v1
QWEN_BASE_URL: http://fake-provider:18080/v1
DEEPSEEK_BASE_URL: http://fake-provider:18080/v1
```

The fake provider implements `GET /v1/models`, `POST /v1/chat/completions`, and
`POST /v1/responses`, including the streaming event shapes and terminal events consumed by the
current OpenAI/Qwen adapters. It rejects any request whose test key is not the fixed non-secret
fixture value and records only method/path/schema metadata, never prompts or authorization headers.

- [ ] **Step 1: Write the red workflow guard**

The static test asserts:

- both native architectures and both modes exist;
- no `push`, `pull_request`, `schedule`, `workflow_run`, or `workflow_call` trigger exists;
- every runtime job declares `environment: installer-disposable-smoke`;
- the workflow refuses a project name outside `^lia-installer-smoke-[a-zA-Z0-9-]+$`;
- cleanup selects the exact project and contains no prune or unscoped resource removal;
- no `docker-compose.dev.yml`, production hostname, PROD credential, or real provider secret occurs;
- prebuilt rows extract the allowlisted bundle and consume manifest digests, not candidate tags;
- local rows invoke `--local-build` from the same extracted host bundle, verify its embedded source
  archive/tree/source identity, and build only from that extracted context;
- the public CLI rejects a candidate manifest while the workflow harness explicitly requires one;
- login posts to `/api/v1/auth/login`;
- chat posts to `/api/v1/agents/chat/stream` and requires a terminal SSE event;
- each running app/dependency container `.Image` config ID is compared with that service manifest's
  config digest for the row's platform; it is never compared directly with a multi-platform index
  digest;
- seed failure injection is followed by zero partial-domain counts and a successful retry.
- README, GETTING_STARTED, release Quick Start, and installer report copy contain no public
  `turnkey`, `one key`, `one endpoint`, or `zero friction` claim while no qualified
  mono-provider-profile evidence file exists.

- [ ] **Step 2: Prove red without dispatching anything**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_installer_disposable_workflow_contract.py tests/unit/test_self_host_marketing_claim_guard.py -v
```

Expected: missing workflow and fixtures.

- [ ] **Step 3: Implement the approved disposable workflow**

The workflow creates a unique temporary working directory and project name, installs from an empty
database, and registers an unconditional cleanup trap before its first Compose call. Every row
extracts the same deterministic host bundle. Prebuilt rows consume its locked image manifest; local
rows invoke `--local-build`, verify and extract its embedded source context, and never use the
workflow checkout as a Docker build context. Its four rows prove:

1. exact host-bundle extraction plus either locked prebuilt identity or exact embedded local source-context identity, according to the mode row;
2. clean migration replay;
3. all five seed postconditions and marker;
4. admin bootstrap and public login;
5. encrypted OpenAI/DeepSeek rows plus post-seed effective provider coverage (B10-bis: the
   seeded overrides are kept and every reachable core slot resolves to a collected key);
6. one fake-provider SSE chat (the seeded pipeline core runs on DeepSeek through the fake);
7. registry index-to-child-to-config mappings plus exact running config digests for every selected
   app/dependency service in prebuilt rows;
8. local app image identities in local rows;
9. page metadata, sitemap, robots, and JSON-LD use the configured runtime Web origin and contain
   neither localhost nor the hosted-project fallback;
10. resume after pre-bootstrap interruption;
11. atomic rollback and retry after injected seed failure;
12. existing-image rollback after injected readiness failure;
13. non-destructive LAN-to-proxy reconfiguration preserves secret fingerprints, seed marker,
    provider rows, and image identity; an injected reconfigure failure restores prior routing;
14. first-install quiesce without volume removal.

The harness imports `load_manifest(candidate_path, required_qualification="candidate")` directly and passes the
result to the same runner used by the CLI; `install.sh` has no candidate-acceptance flag. The workflow
emits `qualification-evidence.json` containing the candidate file SHA-256, the four exact matrix row
IDs, each result, source identity, and workflow run ID. It never rewrites the candidate manifest.

The workflow uploads redacted test results and cleanup evidence. It does not upload `.env`, answers,
state, database dumps, container logs containing request bodies, or bootstrap stdin.

- [ ] **Step 4: Prove the static workflow contract**

```powershell
cd apps/api
.venv/Scripts/pytest tests/unit/test_installer_disposable_workflow_contract.py -v
cd ../..
task lint:ci-parity
```

Expected: exit 0. This step does not dispatch the workflow.

- [ ] **Step 5: Request explicit authorization and run G3/G4**

This is the only full-stack execution checkpoint. Present the candidate manifest, source identity,
four-row matrix, cleanup scope, and absence of real credentials. Before dispatch, verify read-only
that the repository environment exists and has the documented required-reviewer protection; if that
protection cannot be demonstrated, stop and leave G3/G4 unpassed. After explicit human approval,
manually dispatch the dedicated workflow with the candidate run ID. No release workflow can invoke
it. Pass requires all four rows and cleanup jobs green for the same candidate manifest, with the
uploaded evidence SHA-256 matching the candidate file consumed by every row.

If any row fails, publish neither a passed manifest nor semver tags; without that adjacent passed
manifest, `./install.sh` continues to resolve its default to local. Return to the failing task with
the captured non-secret evidence.

- [ ] **Step 6: Verify G2 artifact identity from the approved run**

Require the attached evidence to show:

```text
API index: exact sha256 + amd64/arm64 child-manifest and config sha256 values
Web index: exact sha256 + amd64/arm64 child-manifest and config sha256 values
API provenance: release version + source SHA + UTC build date
Web public API contract: same-origin
SBOMs: API + Web
Host bundle: exact archive SHA-256 + extracted canonical-tree SHA-256
Embedded source context: exact archive SHA-256 + extracted canonical-tree SHA-256 + full source SHA
Dependencies: exact digest per manifest service
```

No rebuild is permitted between this evidence and promotion.

- [ ] **Step 7: Finalize, promote, and activate without changing the qualified bundle**

Only after Steps 5-6 pass for the same source identity:

Manually dispatch the release promotion graph with the exact candidate and qualification run IDs.
It validates the qualification evidence, creates a passed manifest whose canonical fields are
identical to the candidate except for `qualification`, promotes semver tags with
`imagetools create` from those
same qualified digests, and publishes the unchanged bundle plus its passed manifest. The release quick
start downloads both assets into one directory and verifies the bundle checksum before extraction;
the adjacent passed manifest then makes bare `./install.sh` choose prebuilt. A complete source
checkout or a directory with no passed manifest remains local. In the official release directory,
`./install.sh --local-build` verifies and uses the embedded source context; it never assumes that the
runtime-only host files are a build tree.
No source, installer, documentation, bundle, app image, or dependency digest changes between the
approved run and publication. Until G6 passes, the public requirement sentence is exact:

```text
Guided self-host installation; OpenAI and DeepSeek are required for the current core.
```

- [ ] **Step 8: Run final no-service regression gates**

```powershell
task test:install:hermetic
task lint
task test:backend:unit:fast
task test:frontend
task lint:docs
```

Expected: all exit 0. These commands do not target DEV or PROD.

- [ ] **Step 9: Checkpoint**

Present the G0-G5 evidence, state that G6 remains unpassed unless separate mono-provider evidence
exists, and suggest: `feat(installer): activate qualified digest-based self-host installs`.

---

## Gate-to-Task Traceability

| Gate | Tasks that establish it | Required evidence |
|---|---|---|
| G0 Static contract | 1, 3, 4, 6, 15 | active docs, ADR-215, conditional local fallback, valid command construction |
| G1 Hermetic behavior | 2-15 | unit, lint, Python 3.10, canary redaction, Compose matrix, clean bundle |
| G2 Artifact identity | 3, 5, 6, 16 | index/child/config and dependency digests, archive/tree hashes, provenance, two SBOMs |
| G3 Disposable clean install | 7-11, 13-14, 16 | migrations, five seed domains, login, encrypted providers, fake chat |
| G4 Resume and failure | 7, 12-14, 16 | atomic seed retry, secret re-prompt, fingerprint stop, reconfigure/rollback |
| G5 Promotion/default | 6, 16 | same qualified digests promoted without rebuild; passed-manifest publication activates release-directory prebuilt default |
| G6 Public one-provider claim | 1, 16 guard plus separate profile qualification | named complete profile, capability matrix, both architectures, honest copy |

## Blocker-to-Task Traceability

| Blocker | Removing tasks |
|---|---|
| B01 | 1, 10-15 |
| B02 | 3, 5, 6, 16 |
| B03 | 3, 11 |
| B04 | 4, 11, 13 |
| B05 | 5, 11, 14 |
| B06 | 5, 6, 11, 16 |
| B07 | 2 |
| B08 | 7, 13 |
| B09 | 7, 16 |
| B10 (incl. B10-bis) | 8, 9, 10, 16 |
| B11 | 8 |
| B12 | 9, 13, 16 |
| B13 | 10, 12-14, 16 |
| B14 | 13, 16 |
| B15 | 1, 4, 6, 15, 16 |

## Gate G6: Separate mono-provider product qualification

G6 is intentionally not satisfied by the OpenAI+DeepSeek baseline in this plan. The marketing-claim
guard added in Task 16 is the executable outcome here: it keeps public copy honest until a separate
profile change supplies all of this evidence:

1. a named, versioned remote profile maps every enabled core LLM slot to exact provider/model IDs;
2. provider capability checks cover tools, structured output, streaming, required context, and
   declared reasoning behavior, with fail-fast negative fixtures;
3. one credential for that named profile passes login, chat, representative tool, and structured
   output flows on qualified amd64 and native arm64 artifacts;
4. no arbitrary OpenAI-compatible endpoint is accepted merely because its HTTP schema resembles
   OpenAI;
5. any local Ollama profile names exact model digests and publishes CPU architecture, RAM floor,
   context size, latency ceiling, tool support, and structured-output results per hardware row.

G6 is mandatory before a public zero-friction call to action. It is not required to prove or ship
the technically explicit two-provider baseline.

## Execution Boundaries

The plan has three deliberately separate proof classes:

1. **Static/hermetic:** Tasks 1-15. Unit processes, linters, document checks, and Compose parsing only.
2. **Disposable runtime:** Task 16 after explicit authorization. Unique ephemeral runners and project
   labels only.
3. **Activation:** passed-manifest publication and registry-tag promotion only after the disposable
   evidence matches the candidate manifest; qualified source/bundle bytes do not change.

A green class never substitutes for a later class. In particular, source-image build success does
not prove installability, `/ready` does not prove chat, emulated arm64 does not prove native arm64,
and a mutable tag does not prove artifact identity.

## Self-Review Performed While Writing

- **Spec coverage:** every corrected design statement and all fifteen blockers map to at least one
  task and one gate in the two traceability tables.
- **Placeholder scan:** every file, interface, command, decision rule, provider set, service set,
  architecture row, lifecycle outcome, and checkpoint message is explicit.
- **Type consistency:** `InstallMode`, `PublicAnswers`, `SecretAnswers`, `ComposeInvocation`,
  `InstallState`, `Runner`, `RollbackPoint`, and `SelfHostManifest` are defined once and consumed
  under the same names.
- **Safety:** no task contains a Git command, no ordinary verification starts a LIA service, no task
  addresses DEV or PROD, and full-stack execution is isolated behind the explicitly approved
  disposable workflow.
- **Activation boundary:** local remains the fallback through Tasks 1-15 and every failed Task 16
  branch; only publication of the passed manifest in Task 16 Step 7 makes an official release
  directory resolve its default to prebuilt, without changing any qualified artifact.
