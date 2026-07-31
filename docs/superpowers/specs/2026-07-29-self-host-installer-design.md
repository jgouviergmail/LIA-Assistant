# Self-Host Installer — Design

**Date**: 2026-07-29
**Status**: Validated (brainstorming session), pending implementation plan
**Related**: GETTING_STARTED.md, `.env.min.prod`, `scripts/deploy/generate-secrets.sh`, `docker-compose.prod.yml`, future ADR-179

## Problem

Installing a production LIA instance today is a manual journey: read GETTING_STARTED.md,
copy a `.env` template (~740 settings in `.env.prod.example`), generate secrets by hand,
build, migrate, seed, create the admin. Self-hosters cloning the open-source repo need a
guided path that asks only the indispensable questions and ends with a fully functional
instance.

## Decisions (validated with the user)

| Decision | Choice |
|---|---|
| Primary audience | Self-hosters deploying **production** on their own Linux server (VPS, Raspberry Pi) |
| Form | **Interactive CLI wizard** run from the cloned repo |
| Scope | Core (URLs, admin, exposure, ≥1 LLM key) **plus optional skippable integration sections** |
| Docker images | **Built locally from source** (no registry pipeline in v1) |
| HTTPS exposure | **Guided choice**: LAN/no-TLS trial, bring-your-own reverse proxy/tunnel, or provisioned Caddy with automatic TLS |
| Implementation | **Python stdlib-only wizard** (`scripts/install/`) + minimal `install.sh` bootstrap |

## Architecture

### Entry point

`install.sh` at the repo root (~60 lines, POSIX). Verifies prerequisites only — docker +
compose plugin v2, python3 ≥ 3.10, git, RAM/disk/architecture sanity — then executes
`python3 -m scripts.install`. No business logic in bash.

### Wizard package: `scripts/install/`

Python **stdlib only** (no `pip install` on the target server): `input`/`getpass`,
`secrets`, `subprocess`, `json`, `urllib`. MyPy strict, pytest-covered like the rest of
the repo.

| Module | Responsibility |
|---|---|
| `__main__.py` | Entry point; args: `--lang fr\|en`, `--non-interactive --answers <file>`, `--resume` |
| `preflight.py` | System checks (docker/compose versions, free ports, disk space) |
| `questions.py` | **Declarative** definition of sections/questions: env key, i18n prompt, validation, default, secret flag, condition |
| `answers.py` | Interactive collection (`input`/`getpass`) or answers-file mode |
| `envgen.py` | `.env` generation: `.env.min.prod` base + answers + auto-generated secrets (`secrets.token_urlsafe`; Fernet key = urlsafe base64 of 32 random bytes — pure stdlib) |
| `compose.py` | Generated compose override (Caddy service if chosen, port bindings per exposure scenario, host-specific mounts) |
| `deploy.py` | build → settings validation → up → wait `/ready` → `create_admin` (migrations + first-run seeds run in the API entrypoint) |
| `report.py` | Final summary: URLs, one-time display of generated credentials, post-install checklist |
| `i18n.py` | Wizard strings in EN + FR (server-side tool — deliberately outside the 6-locale frontend `lint:i18n` scope) |

### Structuring principles

1. **No duplicated source of truth.** Fine-grained `.env` validation is delegated to the
   real Pydantic `Settings`, executed inside the freshly built API image via a new
   `apps/api/scripts/validate_settings.py` (`docker compose run --rm --no-deps --entrypoint "" api python -m
   scripts.validate_settings`) after build, before `up` — `--no-deps` because Settings
   validation is pure Pydantic and must not start postgres/redis prematurely, and
   `--entrypoint ""` because the image entrypoint waits for PostgreSQL and runs alembic
   (`docker-entrypoint.sh:10-18`), which would hang forever without the database. The wizard validates only input
   shape at prompt time (email format, URL format, non-empty).
2. **Reuse the existing machinery.** `docker-compose.prod.yml` stays the single reference
   compose (the installer layers an override, never a competing file); alembic migrations
   keep running in the API entrypoint (see `docker-compose.prod.yml` healthcheck
   comment, confirmed in `docker-entrypoint.sh:18`); the 5 SQL seeds in
   `infrastructure/database/seeds/` are auto-applied by that same entrypoint on first
   boot (`docker-entrypoint.sh:21-39`); `scripts/data/create_admin.py` (idempotent,
   `--email/--password`) is invoked as-is.

### Resume state

`.install-state.json` (repo root, gitignored, **never contains secrets**) records the
last completed step. `./install.sh --resume` continues an interrupted run (long build,
network failure) without re-asking questions. `install.log` captures step output,
secrets redacted.

## Questionnaire

Four mandatory blocks, then optional skippable sections. Defaults in brackets; secret
input via `getpass` (no echo).

### Mandatory

1. **Wizard language**: fr / en — asked first; everything after renders in that language.
2. **Exposure** (guided choice):
   - *LAN/local trial* — access `http://<IP>:3000`, no TLS, `SESSION_COOKIE_SECURE=false`, CORS set to the LAN origin;
   - *Bring-your-own reverse proxy / tunnel* — asks web domain + API domain; LIA binds loopback-only exactly like the current production; final report prints the two vhosts to configure;
   - *Provision Caddy* — asks domains + Let's Encrypt email; Caddy service added via the generated override with automatic TLS.
3. **Admin account**: email, password, default instance language (all 6 LIA locales).
   The prompt-time strength check mirrors the `validate_password_strict` rules as a UX
   convenience only — the wizard is stdlib-only and cannot import the backend; final
   authority remains the backend itself when `create_admin` runs in the container.
4. **LLM provider** (at least one required): OpenAI / Anthropic / Gemini / DeepSeek /
   Qwen / Perplexity / Ollama; API key entry; **optional immediate key verification**
   ("verify now? [Y/n]" — one lightweight stdlib `urllib` call) so an invalid key is not
   discovered after a 20-minute build. Keys land in the env-fallback names resolved by
   `providers/adapter.py::_ENV_FALLBACK` (DB via the admin UI stays primary).
   **Turnkey nuance**: the seeded LLM slots (`llm_config_seed.sql`) target OpenAI models,
   so OpenAI is the out-of-the-box provider; choosing only a non-OpenAI provider prints
   an explicit warning and the final report includes the post-install step (Admin UI >
   LLM Configuration) required before chat works.

### Optional sections (each "Configure X? [y/N]", all recoverable post-install)

- **Google OAuth** (Gmail/Calendar/Drive connectors) — client ID + secret (also feeds
  `NEXT_PUBLIC_GOOGLE_CLIENT_ID`, baked into the web image at build time); final report
  reminds the redirect URIs to declare in Google Cloud Console;
- **Microsoft OAuth** (Graph);
- **Telegram** — bot token;
- *Not in the wizard, by evidence*: **voice** (Edge TTS is free with zero configuration;
  the ElevenLabs key is a per-user connector, not an env var — `.env.prod.example:1096`,
  `:1700`) and **image generation** (admin-catalogue keys, no install-time env var).
  Both get a pointer in the final report instead of questions;
- **Observability** — "full stack (Grafana, Prometheus, Loki, Tempo…) or core only?".
  Implementation: add `profiles: ["observability"]` to the monitoring/management
  services in `docker-compose.prod.yml` (exact list — including whether portainer joins
  the profile — fixed in the implementation plan); choosing "full" writes
  `COMPOSE_PROFILES=observability` into the generated `.env`. The existing production
  `.env` adds that same line to keep behaving identically (single-point change, called
  out in the release notes).

### Never asked, always generated

`SECRET_KEY`, `FERNET_KEY`, PostgreSQL/Redis/Grafana passwords, internal tokens.
Displayed exactly once in the final report; stored only in `.env` (`chmod 600`).

## Orchestration

Sequence after the questionnaire (each step recorded in `.install-state.json` +
`install.log`):

1. **Generate** — write `.env` (timestamped backup first if one exists; never a silent
   overwrite) and the compose override (Caddy/ports/host-specific mounts).
2. **Build** — `docker compose -f docker-compose.prod.yml [-f override] build` with
   provenance args (`APP_VERSION`, `GIT_COMMIT_SHA`, `BUILD_DATE`) derived from the local
   git checkout, matching the current deploy. Honest "this takes 10-30 min" message
   before starting.
3. **Validate** — `docker compose run --rm --no-deps --entrypoint "" api python -m
   scripts.validate_settings`: the real `Settings` boots or fails with clear messages,
   before any service starts (entrypoint bypassed — see Architecture, principle 1).
4. **Start** — `up -d`; wait for postgres/redis health, then the API `/ready` endpoint
   (`apps/api/src/api/health.py:119`). Migrations **and first-run SQL seeds** are both
   handled by the entrypoint (`docker-entrypoint.sh:16-39` — seeds auto-apply when the
   `personalities` table is empty, guarded for re-runs, `APPLY_SEEDS=true` to force) —
   nothing to orchestrate.
5. **Bootstrap** — `create_admin --email … --password …` only (idempotent by design:
   it checks for the existing user first). The wizard does **not** apply seeds itself —
   that would duplicate the entrypoint's mechanism.
6. **Report** — access URLs, one-time credentials, post-install checklist (Google
   redirect URIs, DNS records, backup expectations).

## Idempotence & re-run

Re-running `./install.sh` on an installed instance is never destructive. Menu:

- **Resume** an interrupted installation (from state file);
- **Reconfigure a section** — replays that question block, regenerates `.env`
  **preserving existing secrets**, restarts affected services;
- **Reinstall from scratch** — explicit confirmation; data volumes are **never** removed
  without a second, dedicated confirmation.

## Security posture

- No secret ever lands in `install.log` or `.install-state.json`; `.env` is the single
  secret store, written `chmod 600`.
- Sensitive prompts use `getpass`.
- `--non-interactive --answers <file>` reads an env-format answers file (user-protected;
  intended for reproducible reinstalls and tests).
- Host-specific mounts of the current production (`/var/run/docker.sock` for the DevOps
  Claude CLI, `~/.claude`) move from `docker-compose.prod.yml` into the generated
  override: a generic self-hoster does not mount a Docker socket into the API by
  default — hardening for the general case, opt-in for this repo's own production.

## Error handling

Every failure message states: the step that failed, the probable cause, and the exact
resume command (`./install.sh --resume`). Raw stacktraces are never the only output.

## Testing

- **Unit suite** `scripts/install/tests/` run by a new `task test:install`, wired into
  `ci:fast` (precedent: `task test:deploy` for the deploy scripts). Covers: questionnaire
  flow with injected answers (zero interactivity in tests), `.env` generation vs golden
  files, resume state machine, secret preservation on re-run, no-silent-overwrite.
- `validate_settings` gets its own unit tests under `apps/api/tests/unit/`.
- **Anti-drift guard #1**: every env key the questionnaire writes must exist in
  `.env.prod.example` — no orphan questions, no stale template.
- **Anti-drift guard #2**: the `.env` generated from all-default answers must boot the
  real `Settings` — `integration`-marked test in the service-backed CI job.

## Documentation

- "One-command install" section at the top of `GETTING_STARTED.md` (the manual path
  remains the detailed reference);
- README quickstart;
- **ADR-179** — self-host installer: audience/form/scope/local-build decisions, compose
  profiles change, DevOps-mount extraction;
- `docs/INDEX.md` + `docs/architecture/ADR_INDEX.md` cross-references.

## Release maintenance (anti-rot contract)

The installer is a new surface that will rot unless every release keeps it in sync.
Split enforcement:

- **Enforced by CI (automatic)** — a new mandatory setting without a default breaks
  anti-drift guard #2 (default-answers `.env` must boot `Settings`); an orphan
  questionnaire key breaks guard #1; wizard regressions break `task test:install` in
  `ci:fast`. These cannot ship unnoticed.
- **Editorial (release checklist)** — what no guard can decide: whether a new optional
  integration deserves a questionnaire section, whether a new compose service belongs to
  the core or the `observability` profile, whether a new seed or boot-path change
  (migrations, `/ready`) affects `deploy.py`, and whether the GETTING_STARTED install
  section still tells the truth. ADR-179 and the release checklist gain a standing
  directive covering exactly these five points, so the release driver (human or LLM)
  re-derives nothing from memory.

## Out of scope (v1 — stated in the ADR)

- Upgrading an existing instance (`git pull` + existing deploy flow remains the channel);
- Windows/macOS as the target server;
- Prebuilt registry images (ghcr.io) — revisit if install-time feedback demands it;
- First-boot web setup wizard.
