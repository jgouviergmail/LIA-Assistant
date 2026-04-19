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
| compatibility | string | no | Prerequisites shown in catalogue. Use for connector-dependent skills. Example: "Requires Calendar and Email connectors" |

### Rich Outputs Field (declarative, for Visualizer / Generator archetypes)

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| outputs | list[string] | no | What the skill script can emit. Values: `text`, `frame`, `image`. Purely declarative — the actual emission is controlled by the Python script via the SkillScriptOutput JSON contract. |

Examples:
- `outputs: [text]` — plain text response (default, no script needed or legacy script)
- `outputs: [text, frame]` — interactive iframe (map, dashboard, mini-app)
- `outputs: [text, image]` — image artifact (QR code, chart, diagram)
- `outputs: [text, frame, image]` — both frame and image coexisting

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

## Rich Outputs Contract (SkillScriptOutput)

Skills emitting an interactive iframe, an image, or both must write a JSON
object to stdout matching the `SkillScriptOutput` schema. Plain-text stdout
is still supported — the parser wraps it as `{text: <stdout>}` automatically.

### JSON Schema (stdout)

```json
{
  "text": "Required. Short caption or textual response (used for voice, LLM context, accessibility).",
  "frame": {
    "html": "Optional. Inline HTML rendered via iframe srcDoc. Exclusive with 'url'.",
    "url": "Optional. External HTTPS URL rendered via iframe src. Exclusive with 'html'.",
    "title": "Optional. Display title for the frame header.",
    "aspect_ratio": 1.333
  },
  "image": {
    "url": "Required if image present. data: URI or https:// URL.",
    "alt": "Required if image present. Alt text for accessibility."
  },
  "error": "Optional. Graceful error message."
}
```

All combinations are allowed: `{text}` alone, `{text, frame}`, `{text, image}`,
or `{text, frame, image}`. Rendering order in the chat: **text → image → frame**.

### Constraints

- `text` is ALWAYS required (even when frame/image are present — used by TTS and accessibility).
- `frame.html` XOR `frame.url` — a frame has exactly one source.
- `frame.html` max size: 200 KB (enforced; exceeding size is rejected).
- `frame.url` must start with `https://`.
- `image.url` must be `data:` or `https://` (no `http://`, no `javascript:`, no `file:`).
- `image.alt` must be non-empty.

### Stdout / Stderr Convention

- The Python script MUST write **only** the JSON object to stdout.
- Logs, progress indicators, debug prints MUST go to stderr.
- If stdout mixes text and JSON, the parser falls back to text mode and the frame/image is NOT emitted (graceful degradation, not a crash).

### Minimal Script Skeleton

```python
import json
import sys


def main() -> None:
    # Read parameters passed via stdin (JSON with 'parameters' key).
    payload = json.loads(sys.stdin.read() or "{}")
    params = payload.get("parameters", {})

    # Your logic here...
    result_text = "Short caption describing the output."

    # Emit the SkillScriptOutput JSON on stdout.
    print(json.dumps({
        "text": result_text,
        # "frame": {"url": "https://...", "title": "...", "aspect_ratio": 1.333},
        # "image": {"url": "data:image/png;base64,...", "alt": "..."},
    }))


if __name__ == "__main__":
    main()
```

### Security (User Skills)

When a **user-owned** skill emits `frame.html`, LIA automatically injects a
strict CSP `<meta>` tag at the top of the HTML to protect the user and the
app:

- `connect-src 'none'` — blocks all fetch, XHR, WebSocket (no exfiltration)
- `frame-src 'none'` — blocks nested iframes (no phishing chains)
- `script-src 'unsafe-inline'` — allows your inline scripts only
- `style-src 'unsafe-inline' https:` — inline styles + CDN stylesheets
- `img-src data: https:` — data URIs and https images only

System (admin-curated) skills are trusted and receive no CSP injection.

In ALL cases, the iframe sandbox omits `allow-same-origin`, so parent
cookies and storage are unreachable.

### `frame.url` vs `frame.html`

- **`frame.url` (external)**: use for embedding third-party widgets (Google
  Maps, YouTube, etc.). No CSP is injected (the remote server controls its
  own headers). Cannot communicate with the parent (SOP).
- **`frame.html` (inline)**: use for custom content you fully control. The
  iframe can receive `postMessage` from the parent (for `ui/initialize`,
  `ui/notifications/size-changed`, `ui/open-link`). CSP is injected for
  user skills (see above).

## Runtime Conventions

The LIA runtime auto-provides several behaviors so skills can focus on
their logic without boilerplate. This section documents what is injected
automatically and how scripts should adapt.

### Auto-injected parameters

Every call to ``run_skill_script`` enriches the ``parameters`` dict with
framework-managed keys prefixed with ``_``. Your script can read them to
localize output or format dates in the user's timezone.

| Key | Source | Typical use |
|-----|--------|-------------|
| ``_lang`` | User's app language (fr, en, es, de, it, zh) | Localize labels, captions, weekday / month names. |
| ``_tz`` | User's IANA timezone (e.g. ``Europe/Paris``) | Format timestamps in the user's local time. |

Explicit ``_lang`` or ``_tz`` values passed by the plan template or the
LLM are preserved — the injection only fills blanks.

```python
params = payload.get("parameters", {})
lang = (params.get("_lang") or "en").lower().split("-")[0]
LABELS = {
    "fr": {"hello": "Bonjour", "reroll": "Relancer"},
    "en": {"hello": "Hello", "reroll": "Re-roll"},
    # ... other locales
}
labels = LABELS.get(lang, LABELS["en"])
```

Do NOT rely on ``locale.setlocale(LC_TIME, "fr_FR.UTF-8")`` for date
formatting: the container image does not ship system locales, so
``strftime`` silently falls back to English. Use inline translation
tables for weekday / month names instead (see the Visualizer example).

### Theme & locale sync (for `frame.html`)

The LIA host pushes the app theme and language to the iframe via JSON-RPC
postMessage notifications. The runtime snippet LIA injects automatically
applies them to the iframe's `<html>` element:

- ``document.documentElement.dataset.theme = 'light' | 'dark'``
- ``document.documentElement.lang = '<locale>'``

**Use ``html[data-theme="dark"]`` selectors** in your frame CSS (NOT
``@media (prefers-color-scheme: dark)``) so the iframe honors the app
override, not the OS preference:

```css
body { color: #1f2937; }
html[data-theme="dark"] body { color: #e5e7eb; }
```

Messages exchanged (you do not have to implement them — they are
supplied by the backend snippet):

| Method | Direction | Effect |
|--------|-----------|--------|
| ``ui/initialize`` | iframe → host | Request host context (theme, locale, …). |
| ``ui/theme-changed`` | host → iframe | User toggled light/dark. Snippet applies ``data-theme``. |
| ``ui/locale-changed`` | host → iframe | User switched app language. Snippet updates ``html[lang]``. |
| ``ui/notifications/size-changed`` | iframe → host | Emitted by the auto-resize snippet. |
| ``ui/open-link`` | iframe → host | Opens an HTTPS link in a new tab (your own JS can call this). |

### Iframe auto-resize

The backend snippet measures ``document.body.getBoundingClientRect().bottom``
and pushes ``ui/notifications/size-changed`` so the iframe grows / shrinks
to match the actual content height. You do NOT need to hard-code an
``aspect_ratio`` that fits — ``aspect_ratio`` only controls the initial
skeleton before the snippet measures the real content.

CSS pre-requisites (enforced by the snippet via ``!important``):

```css
html, body { margin: 0; padding: 0; }   /* default margins skew the measurement */
body { background: transparent; }        /* let the host page show through */
```

Both rules are injected automatically — you should keep your own
``body { padding: … }`` on inner containers rather than on ``body``.

### Client-side interactivity

Frames can embed their own ``<script>`` block to implement interactive
behavior without round-tripping to the backend. Typical patterns:

- A **"Re-roll"** button that regenerates values client-side via
  ``crypto.getRandomValues`` (CSPRNG, no new tool call needed).
- A **live converter** that reacts to input changes with inline JS.
- A **countdown timer** with ``setInterval``.

Use ``addEventListener('click', …)`` — inline ``onclick=""`` is blocked by
the default browser CSP for user skills.
