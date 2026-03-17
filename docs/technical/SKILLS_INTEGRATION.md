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
    SkillBypassStrategy       Planner Prompt           Response Node
    (deterministic             (L1 catalogue XML)       (L2 structured
     plan_template)                   │                  wrapping)
                                      ▼
                            LLM decides activation
                                      │
                        ┌─────────────┼─────────────┐
                        ▼                           ▼
              Planner: skill_name          Response LLM:
              in JSON output               activate_skill tool
              (pre-activation)             (fallback)
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

### 1. Planner Pre-activation (Primary)

The LLM planner sees the L1 catalogue → includes `"skill_name": "<name>"` in JSON output → `response_node` loads L2 instructions with structured wrapping.

### 2. Dedicated Tool (Fallback)

`activate_skill_tool(name)` available to the response LLM for on-demand activation when the planner didn't anticipate the need.

### 3. Resource Loading (L3)

`read_skill_resource(skill_name, path)` reads bundled files (references/, templates, etc.) listed in `<skill_resources>` after L2 activation. This enables progressive disclosure: the LLM only loads resources when needed.

### 4. Deterministic Bypass (Optimization)

Skills with `plan_template.deterministic: true` bypass the LLM planner entirely via `SkillBypassStrategy`.

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
4. The in-memory `SkillsCache` is reloaded

The translation uses the existing `skill_description_translation_prompt.txt` which accepts any source language and produces all 6 outputs simultaneously.

### Download Format

Downloaded files are `.zip` archives:
- If the skill has only `SKILL.md` → single-file zip
- If the skill has `scripts/`, `references/`, `assets/` subdirectories → full directory zip
- Frontend uses the `fetch` + blob URL trick with credentials for authenticated download

## Configuration

```env
# Feature flag
SKILLS_ENABLED=false

# Paths
SKILLS_SYSTEM_PATH=data/skills/system
SKILLS_USERS_PATH=data/skills/users

# Limits
SKILLS_MAX_PER_USER=20

# Script execution
SKILLS_SCRIPTS_ENABLED=false
SKILLS_SCRIPT_TIMEOUT_SECONDS=30
SKILLS_SCRIPT_MAX_OUTPUT_KB=50
SKILLS_SCRIPT_MAX_INPUT_KB=100
```

## Script Execution Security

Scripts run in a sandboxed subprocess:

1. **Process isolation**: `subprocess.run()` (no `shell=True`)
2. **Environment filtering**: Only PATH, HOME, LANG, LC_ALL, TZ
3. **Network isolation** (Linux): `unshare -rn`
4. **Temporary working directory**: No write access to skill/app dirs
5. **Path traversal protection**: `resolve()` + `relative_to()` check
6. **Timeout + output limits**: Configurable via env vars

Scripts receive input via stdin JSON and return output via stdout.

## Override Semantics

Per agentskills.io: user skills override admin skills with the same name (last-one-wins). This allows users to customize system skills.

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
  Generates a comprehensive morning briefing combining calendar events, priority
  tasks, and weather forecast. Use when the user asks for a daily briefing,
  morning summary, or "what's on my schedule today".
category: quotidien
priority: 70
plan_template:
  deterministic: true
  steps:
    - step_id: get_events
      agent_name: event_agent
      tool_name: get_events_tool
      parameters: {}
      depends_on: []
      description: Retrieve today's and tomorrow's events
    - step_id: get_tasks
      agent_name: task_agent
      tool_name: get_tasks_tool
      parameters:
        show_completed: false
      depends_on: []
      description: List active and priority tasks
    - step_id: get_weather
      agent_name: weather_agent
      tool_name: get_weather_forecast_tool
      parameters:
        days: 3
      depends_on: []
      description: Weather today + 3-day trend
    - step_id: get_emails
      agent_name: email_agent
      tool_name: get_emails_tool
      parameters:
        query: "in:inbox newer_than:1d"
        max_results: 5
      depends_on: []
      description: 5 most recent inbox emails today
---

# Briefing Quotidien

## Instructions
1. Récupérer les rdv du jour et du lendemain via calendar
2. Lister les tâches prioritaires, en retard et à venir
3. Obtenir la météo locale (aujourd'hui + tendance 3 jours)
4. Récupérer les 5 derniers emails reçus dans la boîte de réception aujourd'hui
5. Formater en sections : Agenda → Tâches → Météo → Emails → À noter
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

## plan_template Step Fields

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
```
