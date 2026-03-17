# SKILL.md Format Specification

Reference for generating valid SKILL.md files compliant with the agentskills.io standard and LIA extensions.

## File Structure

A SKILL.md file consists of YAML frontmatter delimited by `---` followed by a markdown body:

```
---
<YAML frontmatter>
---

<Markdown body>
```

## Frontmatter Fields

IMPORTANT: Only use the fields listed below. Do NOT invent new fields.
Fields like version, archetype, author, tags, trigger_phrases do NOT exist and will cause issues.

### Standard Fields (use these for every skill)

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| name | string | YES | Unique skill identifier. kebab-case [a-z0-9-], 2-64 chars, no consecutive hyphens. |
| description | string | YES | English, 3rd person ("Generates...", "Provides..."), max 1024 chars, no XML tags. |
| category | string | no | UI grouping. Use existing: quotidien, recherche, communication, organisation, productivite, developpement. |
| priority | int | no | Sort order in catalogue (default: 50, higher = shown first, range 1-100). |

### Plan Template Field (only for deterministic skills)

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| plan_template | object | no | Deterministic execution plan. See schema below. |
| compatibility | string | no | Prerequisites shown in catalogue. Use for OAuth-dependent skills. Example: "Requires Google Calendar and Gmail OAuth" |

### Advanced Fields (rarely needed)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| always_loaded | bool | false | Always inject L2 instructions (costs tokens every conversation). |
| license | string | null | License name (MIT, Apache-2.0...). |
| agent_visibility | list | null | Restrict to specific agent types. null = visible to all. |
| visibility_mode | string | "include" | "include" = whitelist, "exclude" = blacklist. |

### Reserved Name Prefixes

Names starting with `claude` or `anthropic` are reserved and will be rejected by the loader.

### Security

No XML tags (`<` or `>`) are allowed in the `name` or `description` fields. The loader rejects files containing XML in frontmatter.

## Plan Template Schema

For deterministic automation skills that bypass the LLM planner:

```yaml
plan_template:
  deterministic: true
  steps:
    - step_id: unique_identifier        # Required. Unique within the plan.
      step_type: TOOL                    # Optional. TOOL (default) | CONDITIONAL | PARALLEL | RESPONSE
      agent_name: event_agent            # Required. Must be a valid agent from domain_taxonomy.
      tool_name: get_events_tool         # Required for TOOL steps. Must be a registered tool.
      parameters:                        # Optional. Dict of tool parameters.
        days_ahead: 2
        max_results: 5
      depends_on: []                     # Optional. List of step_ids this step depends on.
                                         # Empty [] = runs in parallel with other independent steps.
                                         # ["step_a"] = waits for step_a to complete first.
      description: Fetch today's events  # Optional. Human-readable step description.
```

### Auto-Trigger Logic

Plan template skills are auto-triggered when the user's query covers ALL domains in the template.
Domain extraction: `agent_name.replace("_agent", "")`.
Example: a skill with steps using `event_agent` + `task_agent` + `weather_agent` triggers when the query covers domains `event` + `task` + `weather`.

### Parallel vs Sequential Execution

- Steps with `depends_on: []` run in parallel
- Steps with `depends_on: ["other_step_id"]` wait for the referenced step to complete
- Multiple dependencies are supported: `depends_on: ["step_a", "step_b"]`

## Body Structure

The markdown body follows the `---` closing delimiter. Recommended structure:

```markdown
# Skill Title

## Instructions
[Core instructions for the LLM — what role to assume, methodology to follow]

## Format de sortie / Output Format
[Expected output structure with sections, headers, bullet points]

## Ressources disponibles / Available Resources
- `references/filename.md` — Description of what this reference contains
- `scripts/script.py` — Description of what this script does
```

## Package Structure

A skill package is a directory containing:

```
skill-name/
├── SKILL.md              # Required. Skill definition file.
├── translations.json     # Optional. Translated descriptions (6 languages).
├── references/           # Optional. Reference documents loaded on demand (L3).
│   └── *.md
├── scripts/              # Optional. Python scripts executed in sandbox.
│   └── *.py
└── assets/               # Optional. Static assets (images, templates).
    └── *
```

### Resource Loading (3-Tier Model)

| Tier | When Loaded | Token Cost | Content |
|------|------------|------------|---------|
| L1 Catalogue | Session start | ~50-100/skill | Name + description (XML catalogue) |
| L2 Instructions | Skill activated | < 5000 | Full SKILL.md body + resource listing |
| L3 Resources | On demand | Variable | Individual files from references/, scripts/, assets/ |

### File Limits

- SKILL.md max size: 100 KB
- Resource file max size: 50 KB per file
- Scripts: only `.py` files allowed
- Max skills per user: 20

## Translations File

Optional `translations.json` for multilingual descriptions:

```json
{
  "fr": "Description en français...",
  "en": "English description...",
  "es": "Descripción en español...",
  "de": "Beschreibung auf Deutsch...",
  "it": "Descrizione in italiano...",
  "zh": "中文描述..."
}
```
