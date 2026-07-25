# Skills Integration Guide

## Overview

LIA implements the [agentskills.io](https://agentskills.io/) open standard for Skills — specialized instructions that extend the assistant's capabilities. Skills are SKILL.md files on disk (YAML frontmatter + markdown body), loaded into an in-memory cache at startup. No database required.

**Feature flag**: `SKILLS_ENABLED=true` (default: `false`)

## Standard Compliance

| Level | Standard | Conformity |
|-------|----------|------------|
| agentskills.io (30+ products) | name, description, license, compatibility, metadata, allowed-tools, progressive disclosure, scripts/, references/, assets/ | 100% |
| Claude Code extensions | context, $ARGUMENTS, disable-model-invocation, user-invocable, model, agent, hooks, argument-hint | Parse lenient (stored, not implemented) |
| Anthropic API | container, /v1/skills, beta headers, VM execution | N/A (own API) |

Skills from marketplaces (skillsmp.com, GitHub) are **100% compatible** — they follow Level 1.

## Architecture

```
data/skills/
├── system/                    # Admin skills (git-tracked, shipped with app)
│   ├── briefing-quotidien/
│   │   └── SKILL.md
│   ├── redaction-professionnelle/
│   │   └── SKILL.md
│   └── ...
└── users/{user_id}/           # User-imported skills
    └── my-skill/
        ├── SKILL.md
        ├── scripts/           # Optional: executable Python scripts
        ├── references/        # Optional: documentation loaded on demand
        └── assets/            # Optional: templates, icons
```

```
Startup → SkillLoader.scan() → SkillsCache (in-memory)
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
    SkillBypassStrategy     QueryAnalyzer Prompt     Always-loaded
    (deterministic          ({available_skills})     (L2 passive,
     plan_template)                │                  additive)
                                   ▼
                         detected_skill_name
                         in QueryIntelligence
                                   │
                         ┌─────────┴────────┐
                         ▼                  ▼
                    Planner route     Response route
                    (plan.metadata     (query_intelligence
                     → skill_name)     → detected_skill_name)
                         │                  │
                         └────────┬─────────┘
                                  ▼
                     Response Node (unified activation)
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼              ▼
              Has scripts?   Resources only?   Neither?
                    │             │              │
                    ▼             ▼              ▼
                 Runner       Python load     L2 passive
                 (ReAct)      + L2 passive      only
                    │
              activate_skill_tool
              read_skill_resource
              run_skill_script
```

## Progressive Disclosure (3 Tiers)

| Tier | When loaded | Token cost | Content |
|------|------------|------------|---------|
| L1 Catalogue | Session start | ~50-100/skill | name + description + location |
| L2 Instructions | Skill activated | <5000 tokens | SKILL.md body + resources listing |
| L3 Resources | On demand | Variable | scripts/, references/, assets/ |

## SKILL.md Format

### Required Fields

| Field | Description |
|-------|-------------|
| `name` | Max 64 chars, `[a-z0-9-]`, no consecutive hyphens |
| `description` | Max 1024 chars, 3rd person ("Generates..." not "Generate...") |

### Standard Optional Fields

| Field | Description |
|-------|-------------|
| `license` | License name or file |
| `compatibility` | Max 500 chars, environment requirements |
| `metadata` | Key-value map |
| `allowed-tools` | Pre-approved tool list (experimental) |

### LIA Extensions

| Field | Default | Description |
|-------|---------|-------------|
| `category` | null | UI category for organization |
| `priority` | 50 | Sort priority (higher = first) |
| `always_loaded` | false | L2 always injected into response prompt |
| `plan_template` | null | Deterministic plan (bypass LLM planner) |
| `dialogue` | false | Multi-turn dialogue skill (ADR-118) — surfaced as a `/` slash command |
| `outputs` | null | Declared output channels, subset of `[text, frame, image]` (v1.25.16) — shown in the gallery detail sheet; validated tolerantly by the loader (invalid ⇒ warn + null) and strictly by the generator's `validate_skill.py` (`VALID_OUTPUTS` parity is CI-pinned) |

### Example

```yaml
---
name: briefing-quotidien
description: >
  Generates a comprehensive morning briefing combining calendar events,
  priority tasks, and weather forecast. Use when the user asks for a
  daily briefing, morning summary, or "what's on my schedule today".
category: quotidien
priority: 70
plan_template:
  deterministic: true
  steps:
    - step_id: get_events
      agent_name: event_agent
      tool_name: get_events_tool
      parameters: {days_ahead: 1, include_today: true}
      depends_on: []
---

# Briefing Quotidien

## Instructions
1. Retrieve today's and tomorrow's events
2. List priority and overdue tasks
3. Get local weather (today + 3-day trend)
4. Format: Agenda → Tasks → Weather → Notes
```

## Activation Model

### 1. QueryAnalyzer Detection (Unified)

The `QueryAnalyzer` sees the skills catalogue (`{available_skills}`) in its prompt and sets `skill_name` in the analysis output. This works for both planner and response routes — the `response_node` reads `detected_skill_name` from state.

**MCP-domain guard** (`services/analysis/skill_suppression.py`): the LLM fills `skill_name` and `domains` in one output with no coherence guarantee, and the routing decider gives the skill absolute priority. When the **primary** domain is an MCP domain (`mcp_*`), the detection is suppressed at the chokepoint — before routing AND before storage on `QueryIntelligence` — so a diagram request reaches `mcp_excalidraw_task` instead of being hijacked by a semantically-poor skill match. The ADR-118 dialogue exemption is preserved (a conversational answer mid-dialogue keeps its `dialogue: true` skill); every suppression is logged and counted (`skill_detection_suppressed_total{reason}`).

### 2. Planner Pre-activation (Complementary)

The LLM planner also sees the L1 catalogue and can include `"skill_name": "<name>"` in its JSON output. The `response_node` treats this identically to the QueryAnalyzer-detected skill.

### 3. Unified Activation in Response Node

Both routes converge in the `response_node` which activates the skill based on its nature:

- **Scripts present** → `ReactSubAgentRunner` (same pattern as MCP/browser agents) with 4 skill tools (`activate_skill_tool`, `read_skill_resource`, `run_skill_script`, `import_user_skill`). Runs in isolation (no streaming impact). If plan_executor collected data, it is injected in the task. Uses `llm_type="mcp_react_agent"` and `skill_react_agent_prompt`, whose `<Context>` carries `UserLocation` — the position resolved through the `resolve_location()` chokepoint (browser geolocation first, then home address, `"unknown"` otherwise) by `services/skill_location_context.py` — so location-dependent skills receive coordinates instead of improvising. The prompt makes a successful `run_skill_script` FINAL (retry only after an explicit error, once) and the final message VERBATIM.
- **Resources only (no scripts)** → L2 instructions + all reference files loaded in Python and injected in the prompt. No extra LLM call.
- **Neither** → L2 passive injection only.

A synthetic `tool_calls` entry is added to the result `AIMessage` so the streaming service Route 3 detects the activation and shows the frontend badge.

### 4. Resource Loading (L3)

`read_skill_resource(skill_name, path)` reads bundled files (references/, templates, etc.) listed in `<skill_resources>` after L2 activation. Two modes:
- **Skills with scripts**: resources loaded on-demand by the `ReactSubAgentRunner` via the `read_skill_resource` tool.
- **Skills without scripts**: resources loaded directly in Python by the `response_node` and injected in the prompt alongside L2 instructions. No extra LLM call.

### 5. Deterministic Bypass (Optimization)

Skills with `plan_template.deterministic: true` bypass the LLM planner entirely via `SkillBypassStrategy`. Eligibility is resolved by the **semantic identification** produced by `QueryAnalyzer`: when the LLM detects that the user's request aligns with a skill's description, it populates `QueryIntelligence.detected_skill_name`; `SkillBypassStrategy` then loads the template by name and builds the plan directly.

**Matching logic**:
- `can_handle` is a cheap presence check on `intelligence.detected_skill_name`.
- `plan` performs the **user-scoped** lookup via `SkillsCache.get_by_name_for_user(name, user_id)` — user skills override admin skills of the same name, and no other user's skill is ever reachable.
- The resolved skill must have `plan_template.deterministic = true` and be present in `active_skills_ctx` for the current user. Any mismatch falls through to the LLM planner gracefully.

No domain-overlap heuristic is used anywhere: skill identification is purely description-driven. This ensures the same signal carries both deterministic and non-deterministic skills, avoiding false positives on queries that share domains with a skill but not its intent (e.g., *"send the weather by email to my wife and plan us a meeting"* covers {weather, email, event} but is not a briefing).

**Descriptions must be written trigger-first** (2026-07 over-match incident): because identification is purely description-driven, an example-flavored description over-matches adjacent queries — `briefing-quotidien` mentioning *"what's on my schedule today"* captured *"my next N appointments"* (whose D+2 agenda window structurally cannot answer it), and a trailing *"Do NOT use for…"* clause proved insufficient for the classifier. Write the strict positive trigger condition FIRST (*"Trigger ONLY when the user explicitly asks for a briefing or a WHOLE-day overview"*), then explicitly exclude the adjacent single-category intents with the instruction to leave `skill_name` null. For a guaranteed opt-out from LLM selection, `disable_model_invocation: true` removes the skill from the analyzer catalogue entirely.

**Scope-aware step filtering**: after lookup, the bypass filters out template steps whose tools require OAuth scopes the user hasn't granted. This allows graceful partial execution (e.g., a briefing without email for users who haven't connected Gmail). The `depends_on` references to removed steps are automatically cleaned up.

**Example**: *"Je veux mon briefing quotidien"* → QueryAnalyzer reads the `briefing-quotidien` description and sets `detected_skill_name="briefing-quotidien"` → `SkillBypassStrategy.plan` loads the template for the user → deterministic plan with all 5 steps (or fewer if OAuth scopes are missing).

### 6. Early Detection Guard

The planner has an "early insufficient content detection" feature that short-circuits LLM planning when required parameters are missing (e.g., *"send an email"* without subject/body). This must be skipped whenever the user's request has been identified as a skill invocation — otherwise the skill's template or instructions would be replaced by a clarification prompt.

**Solution**: `_has_potential_skill_match()` in `planner_node_v3.py` returns `True` whenever `intelligence.detected_skill_name` is set, regardless of whether the skill is deterministic. Downstream, `SkillBypassStrategy` handles deterministic skills and the LLM planner handles the rest.

## Backend Files

| File | Purpose |
|------|---------|
| `domains/skills/__init__.py` | Module init |
| `domains/skills/loader.py` | Parse SKILL.md, scan directories |
| `domains/skills/cache.py` | SkillsCache singleton |
| `domains/skills/injection.py` | L1 catalogue builder |
| `domains/skills/activation.py` | L2 structured wrapping |
| `domains/skills/executor.py` | Script subprocess executor |
| `domains/skills/tools.py` | LangChain tools (activate_skill, run_skill_script, read_skill_resource) |
| `domains/skills/catalogue_manifests.py` | Tool manifests |
| `domains/skills/router.py` | API endpoints (list, import, delete, toggle, reload) |
| `core/config/skills.py` | SkillsSettings |

## Frontend Files

| File | Purpose |
|------|---------|
| `hooks/useSkills.ts` | API hook (list, import, delete, reload, toggle, download, translateDescription, updateDescription, deleteAdmin) |
| `components/settings/SkillsSettings.tsx` | User skills (Features tab) — list, import, delete, toggle, download |
| `components/settings/AdminSkillsSection.tsx` | Admin skills (Administration tab) — list, import, reload, translate, edit description, download, delete |
| `components/settings/SkillGuideModal.tsx` | User guide modal (SKILL.md format, plan_template reference) |

## API Endpoints

### User Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/skills` | User | List skills (admin + user, override semantics) |
| POST | `/skills/import` | User | Import SKILL.md or .zip (user scope) |
| POST | `/skills/import-from-url` | User | Install from an https URL (v1.25.16) — SSRF-validated fetch feeding the same hardened pipeline |
| GET | `/skills/{name}/preview` | User | Gallery preview image — serves ONLY `assets/preview.png` (name-pattern traversal guard, 2 MiB cap, 404 for admin-disabled system skills) |
| DELETE | `/skills/{name}` | User | Delete user skill |
| PATCH | `/skills/{name}/toggle` | User | Toggle skill on/off for current user |
| GET | `/skills/{name}/download` | User | Download skill as .zip (own or admin skills) |

### Admin Endpoints (Superuser only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/skills/admin/import` | Superuser | Import SKILL.md or .zip (admin scope) |
| GET | `/skills/admin/{name}/download` | Superuser | Download admin skill as .zip |
| DELETE | `/skills/admin/{name}` | Superuser | Delete admin (system) skill |
| PATCH | `/skills/admin/{name}/description` | Superuser | Update description + auto-translate to all 6 languages |
| POST | `/skills/admin/{name}/translate-description` | Superuser | Re-translate existing description to all 6 languages |
| POST | `/skills/reload` | Superuser | Force reload all skills from disk |

### Description Update Flow

When `PATCH /skills/admin/{name}/description` is called with `{ description, source_language }`:

1. LLM translates the description to all 6 languages (fr, en, es, de, it, zh) in a single call
2. The `en` translation is written back to `SKILL.md` (YAML frontmatter update)
3. All 6 translations are saved to `translations.json` in the skill directory
4. `SkillsCache.invalidate_and_reload()` reloads from disk and publishes cross-worker invalidation via Redis Pub/Sub (ADR-063)

The translation uses the existing `skill_description_translation_prompt.txt` which accepts any source language and produces all 6 outputs simultaneously.

### Download Format

Downloaded files are `.zip` archives:
- If the skill has only `SKILL.md` → single-file zip
- If the skill has `scripts/`, `references/`, `assets/` subdirectories → full directory zip
- Frontend uses the `fetch` + blob URL trick with credentials for authenticated download

## Install from URL (v1.25.16)

`POST /skills/import-from-url {url}` downloads a `SKILL.md` or `.zip` from a
user-supplied address and hands the raw bytes to the **untouched**
`SkillImportService.import_upload` (S1 traversal / S2 cross-scope 409 /
S3 zip-bomb / S4 validation all apply verbatim). Hardening layers, in order:

1. **https-only** pre-check (no http→https upgrade for code imports);
2. the reused SSRF validator (`agents/web_fetch/url_validator.validate_url`):
   hostname blacklist, DNS resolution, blocked ranges (RFC 1918, loopback,
   link-local/metadata, CGNAT, ULA, IPv4-mapped IPv6);
3. `follow_redirects=False` — a 3xx answer is a refusal, not a hop;
4. streamed read bounded by `SKILLS_URL_IMPORT_MAX_BYTES` (aborts mid-transfer)
   under a **TOTAL** transfer deadline (`asyncio.timeout` — httpx timeouts are
   per-phase and would never trip on a dripping server);
5. content sniffing (zip magic / markdown frontmatter) before the pipeline;
6. a per-user Redis sliding-window rate limit (failed imports consume no skill
   quota, hence the dedicated window; fail-open on Redis outage, like auth).

Error `detail` prefixes are a stable frontend contract (`url_not_https`,
`url_blocked`, `url_fetch_failed`, `url_too_large`, `url_not_skill_content`)
mapped to localized toasts. Outcomes are counted in
`skill_url_imports_total{outcome}` (ok | blocked | too_large | fetch_failed |
invalid_content | pipeline_rejected). Residual DNS-rebinding risk (resolve
then connect without IP pinning) is documented in `url_import.py` with its
mitigations; an IP-pinned transport or hostname allowlist are noted as future
hardening.

## Configuration

```env
# URL import (v1.25.16)
SKILLS_URL_IMPORT_ENABLED=true
SKILLS_URL_IMPORT_MAX_BYTES=5242880
SKILLS_URL_IMPORT_TIMEOUT_SECONDS=15
SKILLS_URL_IMPORT_RATE_MAX_CALLS=10
SKILLS_URL_IMPORT_RATE_WINDOW_SECONDS=3600

# Feature flag
SKILLS_ENABLED=false

# Paths
SKILLS_SYSTEM_PATH=data/skills/system
SKILLS_USERS_PATH=data/skills/users

# Limits
SKILLS_MAX_PER_USER=20

# Import hardening (ADR-118)
SKILLS_CHAT_IMPORT_ENABLED=true
SKILLS_ZIP_MAX_DECOMPRESSED_KB=2048
SKILLS_ZIP_MAX_FILES=64

# Script execution
SKILLS_SCRIPTS_ENABLED=false
SKILLS_SCRIPT_TIMEOUT_SECONDS=30
SKILLS_SCRIPT_MAX_OUTPUT_KB=50
SKILLS_SCRIPT_MAX_INPUT_KB=100
```

## Import Pipeline (ADR-118)

Every skill import — user upload, admin upload, or chat-driven — goes through
the single hardened pipeline in `src/domains/skills/import_service.py`
(`SkillImportService`). Stages:

1. **Stage** into a temp directory: bare `SKILL.md` write, bounded zip
   extraction (decompressed-size cap `SKILLS_ZIP_MAX_DECOMPRESSED_KB`,
   member-count cap `SKILLS_ZIP_MAX_FILES`, per-member zip-slip check, only
   the SKILL.md subtree extracted), or text-file map (chat path — text
   extensions only).
2. **Validate**: strict agentskills.io name contract
   (`^[a-z0-9][a-z0-9-]*[a-z0-9]$`, ≤64 chars, no consecutive hyphens, no
   `claude`/`anthropic` prefix) enforced BEFORE any write into the live tree
   (path-traversal guard), then full `parse_skill_file` content validation.
3. **Conflict + quota** (user imports): rejects names owned by a system skill
   or another user (409, existence not disclosed); re-importing one's own
   skill upserts; `SKILLS_MAX_PER_USER` enforced.
4. **Commit**: atomic swap staging → live tree, DB registration
   (`create_skill_for_import`), `SkillsCache.invalidate_and_reload()`
   (cross-worker, ADR-063).

### Chat-driven import (`import_user_skill` tool)

The skill-generator delivers finished skills directly: it calls
`import_user_skill(files={path: content, ...})` (in `skills_tools`, so it is
available inside the skill ReAct runner), then announces the imported skill
by name. Gated by `SKILLS_CHAT_IMPORT_ENABLED`, rate-limited 5/min/user.
Failures return structured errors (invalid name, conflict, quota) that the
LLM uses to fix the files and retry once; after two failures it falls back to
the legacy code-block delivery protocol.

Failure atomicity: the previous version of a re-imported skill is parked in
the staging temp directory during the swap and restored if the DB
registration or commit fails — a failed import can neither destroy an
existing skill nor leave disk and DB diverging. A lost registration race
(concurrent import winning the name between check and flush) rolls the disk
back and answers the same 409 as the up-front conflict check.

### Dialogue skills (`dialogue: true` extension field)

Skills whose workflow spans several turns (the skill-generator's
clarify → answer → generate flow) declare `dialogue: true` in their
frontmatter (LIA extension, default `false`). Effect: the QueryAnalyzer's
chat override — which normally clears a detected `skill_name` on confidently
conversational turns to prevent history contamination — preserves the
detection for dialogue skills, because the user's conversational reply IS
part of the skill's flow. Combined with the conversation history forwarded to
the skill ReAct runner (`<conversation_history>` block in the runner task),
the dialogue resumes where it left off instead of restarting. One-shot skills
(qr-code, dice-roller…) keep the anti-contamination behavior.

## Script Execution Security

### Default mode — throwaway container (SEC-001)

`SKILLS_SCRIPT_SANDBOX=container` (the default) runs every script in a
one-shot sibling container instead of a local subprocess. This is what
actually removes the Docker socket from a script's reach: the in-process path
below only isolates when the API itself runs as root, and in production it
runs as `appuser`, a member of the `docker` group — a group a child process
inherits, socket included.

| Property | Enforcement |
| --- | --- |
| Docker socket | Not mounted — the container has no `/var/run/docker.sock` at all |
| Network | `--network none` (no LAN, no metadata service, no egress) |
| Filesystem | `--read-only` root + a `--tmpfs /tmp` sized by `SKILLS_SCRIPT_SANDBOX_TMPFS_MB`; `HOME=/tmp` |
| Identity | `--user 65534:65534`, `--cap-drop=ALL`, `--security-opt no-new-privileges` |
| Resources | `--memory`, `--pids-limit`, `--ulimit cpu`/`fsize` from the same `SKILLS_SCRIPT_MAX_*` settings |
| Secrets | None: no bind mount, so no `config/`, no credentials, no user data |

The script **source** is passed inline (`python -c <source>`) rather than
mounted: the API is itself a container, so a bind of `/app/data/skills/...`
would resolve against the *host* filesystem, and user skills live in a named
volume. Passing the source also keeps stdin free for the JSON payload, which
is the contract every skill relies on. Two consequences for skill authors:
a script cannot read files from its own skill directory, and it cannot import
a sibling module from `scripts/` — a single self-contained file, stdin in,
stdout out.

The image is pinned per environment in `docker-compose*.yml`
(`SKILLS_SCRIPT_SANDBOX_IMAGE`) so the sandbox interpreter and packages match
the API exactly. The prod image installs dependencies with `pip install
--user`, hence `SKILLS_SCRIPT_SANDBOX_PYTHONPATH`; the dev image installs
them system-wide and sets it empty.

If the Docker daemon is unreachable the execution is **refused**
(`Script sandbox unavailable`) — it never falls back to the in-process path,
since a sandbox that downgrades on demand protects nothing.

### Legacy mode — in-process subprocess

`SKILLS_SCRIPT_SANDBOX=subprocess` keeps the historical path, retained for
environments with no Docker daemon:

1. **Process isolation**: `subprocess.run()` (no `shell=True`)
2. **Environment filtering**: Only PATH, HOME, LANG, LC_ALL, TZ
3. **Privilege drop** (POSIX, when the API runs as root): the subprocess is dropped to an unprivileged uid/gid (`setgroups([])` → `setgid` → `setuid` in `preexec_fn`, supplementary groups cleared first). This denies the root-owned Docker socket to skill scripts — the mount-namespace mask the audit proposed is impossible without `CAP_SYS_ADMIN` — and makes `RLIMIT_NPROC` effective. Configurable via `SKILLS_SCRIPT_DROP_PRIVILEGES` / `SKILLS_SCRIPT_UNPRIVILEGED_UID`/`GID`.
4. **Resource limits** (POSIX `rlimit` in the same `preexec_fn`): `RLIMIT_AS` (memory), `RLIMIT_NPROC` (fork bombs), `RLIMIT_FSIZE` (disk), `RLIMIT_CPU` (CPU spin) — a runaway/malicious script is killed by the kernel. Configurable via `SKILLS_SCRIPT_MAX_MEMORY_MB` / `_MAX_PROCESSES` / `_MAX_FILE_SIZE_MB` / `_MAX_CPU_SECONDS`.
5. **Network isolation** (Linux, when `CAP_SYS_ADMIN` is available): `unshare -rn`
6. **Temporary working directory**: No write access to skill/app dirs
7. **Path traversal protection**: `resolve()` + `relative_to()` check
8. **Timeout + output limits**: Configurable via env vars

See [ADR-097](../architecture/ADR-097-Concurrency-GDPR-Sandbox-Wave4-Audit.md) for the privilege-drop and resource-limit hardening (audit A1/A2). Scripts receive input via stdin JSON and return output via stdout.

## Override Semantics

Per agentskills.io, the cache resolves a user skill over an admin skill with the same name (`get_by_name_for_user`, last-one-wins) — this remains for pre-existing data. **New imports can no longer create such shadows**: since ADR-118 the import pipeline rejects a user import whose name collides with a system skill or with another user's skill (the DB `skills.name` column is globally unique, so a shadow import used to silently rewrite the other row's display metadata).

## Skill Archetypes

Three patterns cover all use cases:

### 1. Prompt Expert (pure instructions)

No tools. The LLM activates the skill and follows the expert instructions.
Best for: writing assistance, coaching, analysis frameworks, structured reasoning.

```yaml
---
name: redaction-professionnelle
description: >
  Provides expert guidance for writing professional emails, reports, and messages
  with appropriate tone, structure, and formulas. Use when drafting formal
  communications, cover letters, or business correspondence.
category: communication
priority: 60
---

# Rédaction Professionnelle

## Instructions

1. Identify the communication type (email, report, letter, etc.)
2. Assess required tone: formal / business-casual / empathetic
3. Apply the appropriate structure (see references/formules.md)
4. Suggest improvements in tone, clarity, brevity
5. Offer 2-3 alternative formulations for key phrases

## Règles stylistiques
- Objet email : < 8 mots, sans ponctuation finale
- Corps : 3 parties max (contexte → demande → suite attendue)
- Formule de politesse : adaptée au niveau hiérarchique
```

### 2. Advisory (structured hints)

No tools. The LLM applies a framework but can still call tools on its own.
Best for: methodology, decision frameworks, multi-step analysis.

```yaml
---
name: synthese-recherche
description: >
  Guides structured web research with source cross-referencing and critical
  synthesis. Use when the user needs in-depth research, literature review,
  or comprehensive analysis of a topic.
category: recherche
priority: 55
---

# Synthèse de Recherche

## Méthodologie

1. **Cadrage** : identifier la question centrale + 3-5 sous-questions
2. **Recherche** : 3+ sources min. (web, Wikipedia, Perplexity ou Brave)
3. **Recoupement** : confirmer chaque fait sur ≥ 2 sources indépendantes
4. **Critique** : évaluer fiabilité, date, biais potentiel de chaque source
5. **Synthèse** : structurer en réponse principale + nuances + limites

## Format de sortie
- Réponse directe (3-5 phrases)
- Sources utilisées (avec URL)
- Limites et incertitudes identifiées
```

### 3. Plan Template (deterministic automation)

Tools called automatically, bypassing the LLM planner. The response LLM then
synthesizes the collected data using the L2 instructions.
Best for: dashboards, briefings, recurring data aggregation workflows.

```yaml
---
name: briefing-quotidien
description: >
  Generates a comprehensive daily briefing combining calendar events, priority
  tasks, weather forecast, recent emails, and pending reminders. Use when the
  user asks for a briefing, daily summary, or "what's on my schedule today".
category: quotidien
priority: 70
plan_template:
  deterministic: true
  steps:
    - step_id: get_events
      agent_name: event_agent
      tool_name: get_events_tool
      parameters: {days_ahead: 2, max_results: 5}
      depends_on: []
      description: Retrieve today's and tomorrow's events
    - step_id: get_tasks
      agent_name: task_agent
      tool_name: get_tasks_tool
      parameters: {show_completed: false}
      depends_on: []
      description: List active and priority tasks
    - step_id: get_weather
      agent_name: weather_agent
      tool_name: get_weather_forecast_tool
      parameters: {days: 3}
      depends_on: []
      description: Weather today + 3-day trend
    - step_id: get_emails
      agent_name: email_agent
      tool_name: get_emails_tool
      parameters: {query: "in:inbox newer_than:1d", max_results: 5}
      depends_on: []
      description: 5 most recent inbox emails today
    - step_id: get_reminders
      agent_name: reminder_agent
      tool_name: list_reminders_tool
      parameters: {}
      depends_on: []
      description: List pending reminders for the day
---

# Briefing Quotidien

## Instructions
1. Récupérer les rdv du jour et du lendemain via calendar
2. Lister les tâches prioritaires, en retard et à venir
3. Obtenir la météo locale (aujourd'hui + tendance 3 jours)
4. Récupérer les 5 derniers emails reçus dans la boîte de réception aujourd'hui
5. Lister les rappels en attente pour la journée
6. Formater en sections : Agenda → Tâches → Météo → Emails → Rappels → À noter
```

---

## Available Agents & Tools Reference

All `agent_name` values (from `domains/agents/constants.py`):

### Calendar & Productivity

| agent_name | tool_name | Key parameters | Notes |
|------------|-----------|----------------|-------|
| `event_agent` | `get_events_tool` | `query`, `time_min`, `time_max`, `days_ahead`, `include_today` | Unified v2: search, list, or get by ID |
| `event_agent` | `create_event_tool` | `title`, `start_time`, `end_time`, `location`, `description` | |
| `event_agent` | `update_event_tool` | `event_id`, fields to update | |
| `event_agent` | `delete_event_tool` | `event_id` | |
| `event_agent` | `list_calendars_tool` | — | |
| `task_agent` | `get_tasks_tool` | `query`, `show_completed`, `task_list_id` | Unified v2 |
| `task_agent` | `create_task_tool` | `title`, `due`, `notes`, `task_list_id` | |
| `task_agent` | `update_task_tool` | `task_id`, fields to update | |
| `task_agent` | `complete_task_tool` | `task_id` | |
| `task_agent` | `delete_task_tool` | `task_id` | |
| `task_agent` | `list_task_lists_tool` | — | |

### Email & Contacts

| agent_name | tool_name | Key parameters | Notes |
|------------|-----------|----------------|-------|
| `email_agent` | `get_emails_tool` | `query` (Gmail syntax), `max_results`, `message_id` | Unified v2. Query examples: `"in:inbox newer_than:1d"`, `"from:john"`, `"subject:invoice"` |
| `email_agent` | `send_email_tool` | `to`, `subject`, `body`, `cc`, `bcc` | |
| `email_agent` | `reply_email_tool` | `message_id`, `body` | |
| `email_agent` | `forward_email_tool` | `message_id`, `to`, `body` | |
| `email_agent` | `delete_email_tool` | `message_id` | |
| `contact_agent` | `get_contacts_tool` | `query`, `contact_id` | Unified v2 |
| `contact_agent` | `create_contact_tool` | `first_name`, `last_name`, `email`, `phone` | |
| `contact_agent` | `update_contact_tool` | `contact_id`, fields | |
| `contact_agent` | `delete_contact_tool` | `contact_id` | |

### Information & Research

| agent_name | tool_name | Key parameters | Notes |
|------------|-----------|----------------|-------|
| `weather_agent` | `get_weather_forecast_tool` | `days` (1-10), `location` | Best for plan_template |
| `weather_agent` | `get_current_weather_tool` | `location` | Current conditions only |
| `weather_agent` | `get_hourly_forecast_tool` | `hours`, `location` | |
| `wikipedia_agent` | `search_wikipedia_tool` | `query`, `language` | |
| `wikipedia_agent` | `get_wikipedia_summary_tool` | `title`, `language` | |
| `wikipedia_agent` | `get_wikipedia_article_tool` | `title`, `language` | Full article |
| `perplexity_agent` | `perplexity_search_tool` | `query` | AI-powered web search (requires user API key) |
| `perplexity_agent` | `perplexity_ask_tool` | `question` | Direct Q&A mode |
| `brave_agent` | `brave_search_tool` | `query`, `count` | Web search (requires user API key) |
| `brave_agent` | `brave_news_tool` | `query`, `count` | News search |
| `web_search_agent` | `unified_web_search_tool` | `query` | Meta-agent: routes to best available search |
| `web_fetch_agent` | `fetch_web_page_tool` | `url` | Fetch and read a web page |

### Reminders

| agent_name | tool_name | Key parameters | Notes |
|------------|-----------|----------------|-------|
| `reminder_agent` | `list_reminders_tool` | — | Lists all pending reminders. No OAuth required (internal). |
| `reminder_agent` | `create_reminder_tool` | `content`, `original_message`, `trigger_datetime` | |
| `reminder_agent` | `cancel_reminder_tool` | `reminder_identifier` | UUID or natural reference ("next", "le prochain") |

### Location & Navigation

| agent_name | tool_name | Key parameters | Notes |
|------------|-----------|----------------|-------|
| `place_agent` | `get_places_tool` | `query`, `location`, `radius`, `type` | Unified v2 |
| `place_agent` | `get_current_location_tool` | — | Browser geolocation |
| `route_agent` | `get_route_tool` | `origin`, `destination`, `mode` (driving/walking/transit) | |
| `route_agent` | `get_route_matrix_tool` | `origins[]`, `destinations[]`, `mode` | Matrix of travel times |

### Files & Drive

| agent_name | tool_name | Key parameters | Notes |
|------------|-----------|----------------|-------|
| `file_agent` | `get_files_tool` | `query`, `mime_type`, `folder_id` | Unified v2 (Google Drive) |
| `file_agent` | `search_files_tool` | `query` | Legacy search |
| `file_agent` | `delete_file_tool` | `file_id` | |

---

## plan_template Fields

| Field | Required | Description |
|-------|----------|-------------|
| `deterministic` | Yes | `true` to bypass LLM planner and execute steps directly. |
| `steps` | Yes | List of execution steps (see below). |

### Step Fields

| Field | Required | Description |
|-------|----------|-------------|
| `step_id` | Yes | Unique identifier. Used in `depends_on` of other steps. |
| `agent_name` | Yes | Agent constant from table above. |
| `tool_name` | Yes | Tool function name (snake_case). |
| `parameters` | No | Dict passed to the tool. Use `{}` for no parameters. |
| `depends_on` | Yes | `[]` = parallel with other steps. `["step_id"]` = sequential. |
| `description` | No | Human-readable description (used in debug panel). |
| `step_type` | No | Default: `"TOOL"`. Other values: `"CONDITIONAL"`, `"REPLAN"`. |

**Parallel execution**: all steps with `depends_on: []` run simultaneously via `asyncio.gather`. This is the recommended default for data fetching steps.

**Sequential chaining example**:
```yaml
steps:
  - step_id: search_contacts
    agent_name: contact_agent
    tool_name: get_contacts_tool
    parameters:
      query: "{{user_input}}"
    depends_on: []
  - step_id: get_emails_from_contact
    agent_name: email_agent
    tool_name: get_emails_tool
    parameters:
      query: "from:{{search_contacts.email}}"
    depends_on: ["search_contacts"]   # waits for search_contacts
```

---

## Description Writing Guide

The `description` field is the **L1 catalogue entry** — the LLM reads it to decide whether to activate the skill.

**Template**: `"[Action verb, 3rd person]. [What it does]. Use when [trigger condition with natural language examples]."`

**Rules**:
- 3rd person: `"Generates..."` not `"Generate..."` or `"I generate..."`
- Include trigger phrases users would naturally say
- Max 2 sentences, max 1024 chars
- Do NOT use `<` or `>` characters (XML injection protection)

**Good examples**:
```
"Provides expert guidance for writing professional emails, reports, and messages
with appropriate tone, structure, and formulas. Use when drafting formal
communications, cover letters, or business correspondence."

"Guides structured web research with source cross-referencing and critical
synthesis. Use when the user needs in-depth research or comprehensive analysis
of a topic."
```

---

## Adding a New System Skill

1. Create `data/skills/system/<skill-name>/SKILL.md`
2. Follow YAML frontmatter format (name, description required)
3. Optionally add `scripts/`, `references/`, `assets/` directories
4. Restart API or call `POST /skills/reload` (superuser)
5. Optionally call `POST /skills/admin/{name}/translate-description` to generate translations for all 6 languages

## Importing Skills from Marketplaces

Users can import skills via the Settings > Features > My Skills section:

1. Download a SKILL.md file or .zip package from a marketplace (e.g., skillsmp.com)
2. Click "Import skill" and select the file (.md or .zip accepted)
3. The skill is stored in `data/skills/users/{user_id}/{skill-name}/`
4. The cache is automatically reloaded
5. Toggle it on/off with the switch control

## Downloading Skills

Any user can download skills they have access to (their own + admin skills):

```
GET /skills/{name}/download          → .zip archive (user auth)
GET /skills/admin/{name}/download    → .zip archive (superuser auth)
```

The download includes the full skill directory: `SKILL.md`, `scripts/`, `references/`, `assets/`, `translations.json`.

## Localized Descriptions

Skills can have localized descriptions stored in `translations.json` alongside `SKILL.md`:

```json
{
  "fr": "Génère un briefing matinal complet...",
  "en": "Generates a comprehensive morning briefing...",
  "es": "Genera un resumen matutino completo...",
  "de": "Erstellt ein umfassendes Morgenbriefing...",
  "it": "Genera un briefing mattutino completo...",
  "zh": "生成综合晨间简报..."
}
```

The UI displays the localized description based on the user's app language (`skill.descriptions?.[lng]`), falling back to `skill.description` (English from SKILL.md).

## Per-User Toggle

Each user can enable/disable individual skills independently. Skill state is stored in two normalized tables:

- **`skills`** — Skill registry (synced from disk): name, is_system, owner_id, admin_enabled, description, descriptions.
- **`user_skill_states`** — Per-user activation: user_id, skill_id, is_active.

Active skills are loaded into an `active_skills_ctx` ContextVar per request (positive set).

- System skills disabled by **admin** (`admin_enabled=false`): hidden from users entirely, is_active set to false for all users.
- System skills disabled by **user** (`is_active=false`, `admin_enabled=true`): shown in settings but toggled off, excluded from assistant.
- User's own skills: always visible in settings, togglable by the owner.

## Admin Skill Management UI

The Administration tab (`AdminSkillsSection.tsx`) exposes per-skill action buttons (visible on hover via `group-hover:opacity-100`):

| Button | Action |
|--------|--------|
| Pencil (✏️) | Open edit description dialog → writes in admin's app language → auto-translates |
| Languages (🌐) | Trigger re-translation of existing description to all 6 languages |
| Download (⬇️) | Download skill as .zip archive |
| Trash (🗑️) | Delete skill with confirmation dialog |
| Toggle | Enable/disable skill for all users |

## Testing

```bash
# With SKILLS_ENABLED=true in .env:
# 1. Check cache loads at startup (log: "skills_cache_loaded count=5")
# 2. "fais-moi un briefing" → SkillBypassStrategy matches → deterministic plan
# 3. "rédige un email professionnel" → planner sees catalogue → sets skill_name
# 4. Import SKILL.md via API → file on disk + cache reloaded
# 5. SKILLS_ENABLED=false → normal pipeline, no injection
# 6. Admin: edit description → translated to 6 langs → SKILL.md updated → cache reloaded
# 7. User: download own skill → .zip downloaded with credentials
# 8. Admin: delete system skill → file removed → cache reloaded
# 9. SKILLS_SCRIPTS_ENABLED=true → run_skill_script executes sandboxed Python
# 10. Script timeout / path traversal → clean error returned
# 11. Rich output skill (frame/image) → SKILL_APP RegistryItem → sentinel → widget
```

## Rich Outputs (Frames + Images)

Skills can return interactive iframes and images through a typed JSON contract
on stdout. The full flow is:

```
Python script stdout JSON
     │
     ▼  parse_skill_stdout()  (src/domains/skills/script_output.py)
SkillScriptOutput { text, frame?, image? }
     │
     ▼  build_skill_app_output()  (src/domains/skills/output_builder.py)
UnifiedToolOutput.data_success(
    message=text,
    registry_updates={ rid: RegistryItem(type=SKILL_APP, payload=...) }
)
     │
     ▼  run_skill_script  →  ReactToolWrapper._accumulated_registry
     │
     ▼  ReactSubAgentRunner.run()  →  react_result.accumulated_registry
     │
     ▼  response_node.py  (merge into current_turn_registry + state.registry)
     │
     ▼  generate_html_for_registry()  →  SkillAppSentinel.render()
<div class="lia-skill-app" data-registry-id="skill_app_...">
     │
     ▼  SSE registry_update chunk  +  sentinel HTML in message content
     │
     ▼  Frontend: MarkdownContent.tsx detects sentinel
     │
     ▼  SkillAppWidget (iframe srcDoc/src + optional image card)
```

### JSON contract — `SkillScriptOutput`

```json
{
  "text": "Required — caption used for voice, LLM, accessibility.",
  "frame": {
    "html": "Inline HTML (srcDoc)",
    "url":  "https://external.example.com/...",
    "title": "Frame header title",
    "aspect_ratio": 1.333
  },
  "image": {
    "url": "data:image/png;base64,...  OR  https://...",
    "alt": "Required alt text"
  }
}
```

Rules:
- `text` is always required (voice, TTS, accessibility, LLM context).
- `frame.html` XOR `frame.url` — a frame has exactly one source.
- `frame.html` capped at `SKILLS_FRAME_MAX_HTML_BYTES` (200 KB).
- `image.url` must be `data:` or `https://` (no `http://`, no `javascript:`).
- `image.alt` required and non-empty.
- The three channels (text, frame, image) are independent and combinable.
- Plain-text stdout (non-JSON) is auto-wrapped as `{text: <stdout>}` for
  backward compatibility — existing skills continue to work unchanged.

### Security model

| Layer | Behavior |
|---|---|
| iframe sandbox | `allow-scripts allow-popups` — NEVER `allow-same-origin` |
| CSP (user skills) | Strict `<meta>` tag auto-injected into `frame.html` blocking `connect-src` (no outbound fetch/XHR) and `frame-src` (no nested iframes) |
| CSP (system skills) | No injection — admin-curated, trusted |
| External `frame.url` | HTTPS only; remote site controls its own headers |
| Image `url` | Only `data:` and `https://` schemes accepted |
| Bridge (`useSkillAppBridge`) | Supports only `ui/initialize`, `size-changed`, `ui/open-link` (HTTPS), `notifications/message`. NO `tools/call`, `resources/read`, `ui/download-file` |
| Script stdout | JSON only; logs on stderr. Mixed stdout falls back to text mode (no crash) |

### Runtime conventions (v1.16.8)

The backend transparently enriches the script runtime and the frontend bridge
so that Visualizer / Generator skills stay consistent with the app:

| Behaviour | Where | Details |
|---|---|---|
| `_lang` / `_tz` auto-injection | `run_skill_script` | Reads `user_language`, `user_timezone` from `runtime_configurable` and injects them into `parameters` before calling the executor. Scripts should use these — POSIX locales are not installed in the container, `strftime`+`setlocale` falls back to English silently. |
| Theme & locale sync | `useSkillAppBridge` | On iframe `load`, pushes `ui/theme-changed` + `ui/locale-changed` to each frame (with double `requestAnimationFrame` defer). A `MutationObserver` on `<html class>` and `<html lang>` propagates live theme / locale changes. Scripts listen and swap CSS via `html[data-theme="dark"]` selectors. |
| Auto-resize | Injected snippet in `build_skill_app_output._AUTORESIZE_SCRIPT` | Measures `document.body.getBoundingClientRect().bottom` and emits `ui/notifications/size-changed`. The bridge clamps and applies `aspectRatio: 'auto'` on the iframe container. |
| Client-side interactivity | CSP constraint | `onclick` inline handlers forbidden → use `addEventListener`. Use `crypto.getRandomValues` (CSPRNG) + rejection sampling for uniform randomness. |
| Parameter coercion | `_coerce_parameters` helper | Accepts `dict | str | None`. Workaround for Qwen serializing `parameters` as a JSON string instead of an object. |
| Widget always rendered | `INTERACTIVE_WIDGET_TYPES` in `data_registry/models.py` | `SKILL_APP`, `MCP_APP`, `DRAFT` are injected as HTML regardless of `user_display_mode` (HTML / Markdown / Cards). Other registry items render only in CARDS mode. |
| Skill instructions primacy | `response_node` | `skills_context` is injected as a dedicated 2nd system message prefixed with `"SKILL INSTRUCTIONS CONTRACT (PRIORITY: HIGHEST)"` so the LLM honours the skill's `references/*.md` over generic `<ResponseGuidelines>` (primacy effect). |
| Proactive initiative suppression | `response_node` | Cross-domain initiative is disabled when a skill is active — the skill owns the response. |

### Key files

Backend:
- `apps/api/src/domains/skills/script_output.py` — `SkillScriptOutput`, `parse_skill_stdout()`
- `apps/api/src/domains/skills/output_builder.py` — `build_skill_app_output()` + CSP injection + `_AUTORESIZE_SCRIPT`
- `apps/api/src/domains/skills/tools.py` — `run_skill_script` parses stdout and emits registry, auto-injects `_lang` / `_tz`
- `apps/api/src/domains/agents/data_registry/models.py` — `INTERACTIVE_WIDGET_TYPES` frozenset
- `apps/api/src/domains/agents/display/components/skill_app_sentinel.py` — sentinel HTML emitter
- `apps/api/src/domains/agents/nodes/response_node.py` — wraps `skills_tools` with `ReactToolWrapper`, merges `accumulated_registry`, splits rendering into widget vs data-card paths

Frontend:
- `apps/web/src/types/skill-apps.ts` — `SkillAppRegistryPayload`
- `apps/web/src/components/chat/SkillAppWidget.tsx` — iframe + image card (transparent background)
- `apps/web/src/hooks/useSkillAppBridge.ts` — minimal postMessage bridge + live theme/locale observers
- `apps/web/src/components/chat/MarkdownContent.tsx` — sentinel `lia-skill-app` detection

## Tool output contract for skill scripts (`structured_data`)

Deterministic plan templates can chain steps via ``$steps.<step_id>.<key>``
resolution. The values resolved by the Jinja2 template engine come from the
``structured_data`` field of ``UnifiedToolOutput``. See
[ADR-074](../architecture/ADR-074-Structured-Data-Contract.md) for the
full rationale and rules.

### What a skill script can reference

```yaml
# Example: weather-dashboard SKILL.md
plan_template:
  deterministic: true
  steps:
    - step_id: get_weather
      agent_name: weather_agent
      tool_name: get_weather_forecast_tool
      parameters: { location: auto, days: 5 }

    - step_id: render_dashboard
      agent_name: query_agent
      tool_name: run_skill_script
      parameters:
        skill_name: weather-dashboard
        script: render_dashboard.py
        parameters:
          forecasts: "$steps.get_weather.forecasts"   # ← exposed via structured_data
          location: "$steps.get_weather.location"
      depends_on: [get_weather]
```

### Canonical keys exposed by native tools

| Tool family | Plural key(s) in `structured_data` | Notes |
|---|---|---|
| `build_contacts_output` | `contacts` + `count`, `query`, `operation`, `from_cache` | google_contacts_tools, resolver |
| `build_emails_output` | `emails` + `count`, `query`, `user_timezone`, `from_cache` | emails_tools |
| `build_events_output` | `events` + `count`, `query`, `time_min`, `time_max`, `calendar_id`, `user_timezone` | calendar_tools |
| `build_tasks_output` | `tasks` + `count`, `task_list_id`, `user_timezone` | tasks_tools |
| `build_files_output` | `files` + `count`, `query`, `folder_id`, `user_timezone` | drive_tools |
| `build_places_output` | `places` + `count`, `query`, `operation`, `center`, `radius` | places_tools |
| `build_weather_output` | `weathers` (list of 1) + `count`, `location`, `city_name` | weather_tools helper (current weather) |
| `get_weather_forecast_tool` | `forecasts` (list), `location`, `days` | weather_tools (forecast) |
| `brave_tools` | `braves` + `count`, `query`, `endpoint` | brave search |
| `hue_tools::ListHueRoomsTool` | `rooms` + `count` | Hue rooms list |
| `hue_tools::ListHueScenesTool` | `scenes` + `count` | Hue scenes list |
| `hue_tools::Control*` / `Activate*` | `action`, `success`, resource id/name/state | Action confirmations |

### Rules in short

1. **Domain entities live in `structured_data`**, never in `metadata`. `metadata`
   is reserved for debug/telemetry (cache flags, execution_time_ms, totals).
2. **Flat layout** — entities are reachable in one Jinja hop:
   `{{ steps.search.contacts[0].name }}`.
3. **`count` is always present** when a list is exposed.
4. **Plural keys** are aligned with the canonical `REGISTRY_TYPE_TO_KEY`
   mapping in `apps/api/src/domains/agents/tools/output.py`.
5. When a tool also returns `registry_updates`, the parallel executor merges
   registry-derived payloads with the tool's `structured_data` without
   overwriting — registry wins on conflict (preserves `_registry_id`).

### Writing a new tool (checklist)

When adding a new native tool to LIA:

- Use `ToolOutputMixin._build_items_structured_data(items, plural_key, **meta)`
  via the existing `build_*_output` helpers, or pass `structured_data=` explicitly
  to `UnifiedToolOutput.data_success()` / `action_success()`.
- Expose at least `<plural_key>` and `count`; include search/context metadata
  (`query`, `operation`, `user_timezone`, …) when applicable.
- Never put domain entities in `metadata` — a code review tripwire.
- Add a unit test asserting the `structured_data` shape (see
  `tests/unit/domains/agents/tools/test_mixins_structured_data.py` for the
  reference pattern).
