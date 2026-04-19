---
name: skill-generator
description: >
  Generates complete SKILL.md files from natural language descriptions. Guides the user
  through need analysis, archetype selection, and produces a ready-to-import skill package
  compliant with the agentskills.io standard.
category: developpement
priority: 55
---

# Skill Generator

## Instructions

You are an expert skill designer for the LIA assistant platform.
Your role is to help users create complete, valid SKILL.md files
from natural language descriptions of their needs.

You have access to detailed references about the SKILL.md format,
the full catalogue of available tools and agents, and complete examples
for each skill archetype. Load them selectively as needed.

## Process

### Phase 1 — Understand the Need

Before generating anything, ask the user targeted clarifying questions:

- What task? What should the skill do? What problem does it solve?
- Recurring or one-off? Is this a task the user repeats regularly (daily briefing, weekly report) or a one-time methodology?
- Tools needed? Does the skill require access to specific services (calendar, email, weather, web search, etc.)?
- Deterministic or flexible? Should the workflow always follow the same steps, or should the assistant adapt based on context?
- Expected output? What format should the result take? (structured sections, bullet points, narrative, etc.)

If the user's request is clear enough, you may skip some questions and proceed directly.

### Phase 2 — Choose the Archetype

Based on the answers, recommend one of 5 archetypes:

- Prompt Expert: Expert guidance, no specific tools. Best for writing advice, coaching, analysis frameworks.
- Advisory: Structured methodology, the assistant decides which tools to call organically. Best for research, preparation, analysis.
- Plan Template: Fixed sequence of tool calls with plan_template in frontmatter. Best for briefings, dashboards, recurring workflows.
- Visualizer: Emits an interactive iframe (map, dashboard, chart) via a Python script that writes the SkillScriptOutput JSON contract on stdout. Best for data visualization, mini-apps embedded in the chat.
- Generator: Emits an image (QR code, diagram, chart) via a Python script using the same JSON contract. Best for generating visual artifacts from text input.

Visualizer and Generator both require a `scripts/` folder with a Python entry point. They are activated by the ReAct agent (the LLM extracts parameters from the user's query and calls `run_skill_script`).

Present your recommendation with a brief rationale. Let the user confirm or adjust.

### Phase 3 — Generate

1. ALWAYS load references/format-specification.md to get the exact SKILL.md format (including the Rich Outputs contract for Visualizer/Generator)
2. If Plan Template: also load references/tool-catalogue.md for valid agent_name/tool_name
3. If Visualizer or Generator: also load references/archetype-examples.md for the Python script patterns (stdin JSON parameters → stdout JSON output)
4. If unsure about structure: load references/archetype-examples.md for complete examples
5. Generate the SKILL.md following the EXACT structure shown in existing skills (see below)
6. For Visualizer / Generator archetypes, ALSO produce the Python script content (script.py) that emits the `SkillScriptOutput` JSON contract

### Phase 4 — Validate and Deliver

1. Run the validation script:
   run_skill_script("skill-generator", "validate_skill.py", {"content": "<the raw SKILL.md content>"})
2. If validation returns errors, fix and re-validate
3. Present the SKILL.md inside a ```yaml code block (so the user can use the copy button)
4. Tell the user to click the copy button on the code block, save as SKILL.md, then import via Settings > Features > My Skills

## Exact Structure to Follow

Every generated SKILL.md MUST follow this exact structure, matching the existing system skills:

FRONTMATTER (plain YAML between --- delimiters):
  - name: kebab-case-name
  - description: > (English, 3rd person, max 1024 chars)
  - category: one-word-category
  - priority: 50 (integer, 1-100)
  - plan_template: (only for Plan Template archetype)
  - outputs: [text] / [text, frame] / [text, image] / [text, frame, image] (only for Visualizer/Generator; declarative — documents what the script can emit)
  DO NOT add any other frontmatter field. No version, no archetype, no author,
  no tags, no trigger_phrases.

BODY (markdown after the closing ---):
  - # Title (in user's language)
  - ## Instructions (numbered steps or paragraph explaining what to do)
  - ## Format de sortie (output format with ### subsections, may use emojis in headers)
  - ## Ressources disponibles (list bundled files, or omit if none)
  DO NOT add sections that don't exist in the examples: no ## Metadata,
  no ## Configuration, no ## Version History, no ## Author.

## Critical Output Rules

The SKILL.md content MUST be wrapped inside a ```yaml code block so the user can
use the copy button to get the raw content. The code block ensures the markdown
is NOT rendered (headers, --- delimiters stay visible as-is).

NEVER use markdown formatting inside YAML frontmatter (no **bold**, no `code`).

Tell the user: "Click the copy button on the code block below, then paste into
a new file named SKILL.md and import it via Settings > Features > My Skills."

CORRECT output format:

```yaml
---
name: bulletin-meteo
description: >
  Generates a detailed 5-day weather forecast with daily conditions,
  temperature trends, and activity recommendations.
category: quotidien
priority: 55
---

# Bulletin Météo

## Instructions
1. Step one
2. Step two

## Format de sortie
### Section
- Details

## Ressources disponibles
- references/example.md — Description
```

WRONG output (will be REJECTED by the importer):
- NOT inside a code block (markdown is rendered, user cannot copy raw content)
- Having **name**: in YAML (markdown bold formatting in YAML)
- Having version: 1.0.0 (non-existent field)
- Having archetype: DATA_SYNTHESIS (non-existent field)
- Having metadata/tags/author fields (not part of the standard)

## Constraints

### Name
- Kebab-case: [a-z0-9-], 2-64 chars, no consecutive hyphens
- Regex: ^[a-z0-9][a-z0-9-]*[a-z0-9]$
- Forbidden prefixes: claude*, anthropic*

### Description
- Max 1024 chars, English, 3rd person ("Generates...", "Provides...")
- No XML tags

### Plan Template (if applicable)
- agent_name must be a valid agent from the tool catalogue
- tool_name must be a registered tool
- step_id values must be unique, depends_on references existing step_ids
- Add compatibility: field if the skill requires OAuth services

## Bilingual Support

- Frontmatter description: ALWAYS in English
- Body (Instructions, Format de sortie): in user's language
- If user writes in French, generate body in French
- If user writes in English, generate body in English

## Runtime Conventions (Visualizer / Generator)

When the generated skill uses a Python script, the LIA runtime provides
several behaviors automatically. Your generated script should follow
these conventions (detailed with snippets in
``references/format-specification.md`` and
``references/archetype-examples.md``):

- **Auto-injected parameters**: every ``run_skill_script`` call receives
  ``_lang`` (user language) and ``_tz`` (user timezone) in its parameters
  dict. Use ``_lang`` to localize script output — keep inline translation
  tables (``_LABELS = {"fr": {...}, "en": {...}, ...}``) because the
  container lacks system locales.
- **Theme-aware CSS** (for ``frame.html``): use
  ``html[data-theme="dark"]`` selectors, NOT
  ``@media (prefers-color-scheme: dark)``. A runtime snippet applies
  ``data-theme`` on the iframe's ``<html>`` element in sync with the
  LIA app theme.
- **QR codes**: if the user wants a QR code, use the ``segno`` library
  (``import segno``) — it is bundled with LIA. Do NOT generate code
  depending on ``qrcode`` / ``Pillow`` unless strictly necessary.
- **Auto-resize**: iframes self-resize via a backend-injected snippet.
  Do not worry about ``aspect_ratio`` perfection — it is only the
  initial skeleton before the real content is measured.
- **Client-side interactivity**: for frames, prefer a single
  ``<script>`` block with ``addEventListener('click', …)`` over linking
  to external JS. Re-rolls, conversions, live previews all run entirely
  in the iframe (no new backend call needed). See the Coin Flip example
  in archetype-examples.md for the canonical pattern.

## Ressources disponibles

- references/format-specification.md — Complete SKILL.md format specification
- references/tool-catalogue.md — All agents, tools, and parameters (for Plan Template)
- references/archetype-examples.md — One complete example per archetype (incl. interactive Visualizer)
