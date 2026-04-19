# ADR-075: Rich Skill Outputs — Interactive Frames and Images

**Date**: 2026-04-20
**Status**: Accepted
**Context**: Formalize a typed JSON contract (`SkillScriptOutput`) that lets Python skill scripts emit — in addition to text — interactive HTML frames and static images, rendered as sandboxed widgets in the chat. The feature reuses the existing Data Registry pipeline (already live for MCP Apps since evolution F2.5).

## Context

Skills ([ADR-071](ADR-071-Skill-Semantic-Identification.md)) initially accepted text-only output. Their three archetypes (Prompt Expert, Advisory, Plan Template) consumed tool results and produced natural-language responses. This was limiting for use cases where a visual artefact is the primary answer:

- A user asks for a map of Paris → a text description reads poorly; the actual value is an embedded Google Maps view.
- A user asks for a QR code → text output cannot replace the image.
- A user wants a monthly calendar view or a dashboard → Markdown tables are inadequate for dense visual data.

Three design tensions had to be resolved:

1. **Who decides the rendering?** Either the application infers intent from tool signatures (fragile, grows complex) or the skill declares its own rendering via a contract (explicit, stable).
2. **How to avoid reinventing the transport?** LIA already ships `MCP_APP` widgets (interactive iframes streamed via the Data Registry → SSE → React widget pipeline). Duplicating this for skills would fork maintenance surface.
3. **How to sandbox user-authored HTML?** System skills are admin-curated (trusted), but user-imported skills can contain arbitrary HTML/JS. Without strong isolation, a malicious skill could exfiltrate cookies, call internal APIs, or attempt clickjacking.

## Decision

### 1. A typed JSON contract on stdout — `SkillScriptOutput`

The skill script writes a single JSON object on stdout. `text` is required; `frame` and `image` are independent and combinable. Plain-text stdout is auto-wrapped as `{text: <stdout>}` for backward compatibility.

```json
{
  "text": "Required caption (voice, LLM, accessibility).",
  "frame": {
    "html": "<inline HTML via srcDoc>",
    "url":  "https://external.example.com/...",
    "title": "Frame header title",
    "aspect_ratio": 1.333
  },
  "image": {
    "url":  "data:image/png;base64,...  OR  https://...",
    "alt":  "Required alt text"
  }
}
```

Rules enforced by Pydantic validators in [src/domains/skills/script_output.py](../../apps/api/src/domains/skills/script_output.py):

- `text` is required and non-empty.
- `frame.html` **XOR** `frame.url` — exactly one source per frame (srcDoc vs src).
- `frame.html` is capped at `SKILLS_FRAME_MAX_HTML_BYTES = 200 KB`.
- `image.url` must use `data:` or `https://` — `http://` and `javascript:` rejected.
- `image.alt` is required and non-empty (accessibility contract).
- No list form (`frames: [...]`, `images: [...]`) in v1 — a single skill that needs multiple images produces a `frame.html` with a grid. Extension deferred without breakage.

### 2. Reuse the Data Registry pipeline via a new `SKILL_APP` type

A new `RegistryItemType.SKILL_APP` is introduced and hooked into the same infrastructure that powers `MCP_APP`:

```
Python script stdout JSON
     │
     ▼  parse_skill_stdout()             (src/domains/skills/script_output.py)
SkillScriptOutput { text, frame?, image? }
     │
     ▼  build_skill_app_output()         (src/domains/skills/output_builder.py)
UnifiedToolOutput.data_success(
    message=text,
    registry_updates={ rid: RegistryItem(type=SKILL_APP, payload=...) },
)
     │
     ▼  run_skill_script → ReactToolWrapper._accumulated_registry
     │
     ▼  ReactSubAgentRunner.run() → react_result.accumulated_registry
     │
     ▼  response_node (merge into current_turn_registry + state.registry)
     │
     ▼  generate_html_for_interactive_widgets() → SkillAppSentinel.render()
       <div class="lia-skill-app" data-registry-id="skill_app_...">
     │
     ▼  SSE registry_update chunk + sentinel HTML in message content
     │
     ▼  Frontend: MarkdownContent.tsx detects sentinel
     │
     ▼  SkillAppWidget (iframe srcDoc/src + optional image card)
```

Consequence: zero new transport layer. The feature ships as an additive registry type, a sentinel component, a React widget, and a minimal postMessage bridge.

### 3. Defence in depth — sandbox, CSP, bridge restrictions

| Layer | Behavior |
|---|---|
| iframe sandbox | `allow-scripts allow-popups` — **never** `allow-same-origin`. Parent cookies/storage unreachable. |
| CSP (user skills) | Strict `<meta>` tag auto-injected into `frame.html`: `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https:; img-src data: https:; font-src https:; connect-src 'none'; frame-src 'none';` — blocks outbound fetch/XHR and nested iframes. |
| CSP (system skills) | Not injected — admin-curated, trusted at the same level as backend Python code. |
| External `frame.url` | HTTPS only; remote site controls its own headers. |
| Image `url` | Only `data:` and `https://` schemes accepted. |
| Bridge (`useSkillAppBridge`) | Supports only `ui/initialize`, `ui/notifications/size-changed`, `ui/open-link` (HTTPS), `ui/theme-changed`, `ui/locale-changed`, `notifications/message`. **No** `tools/call`, `resources/read`, or `ui/download-file` — reduces attack surface. |
| HTML budget | `SKILLS_FRAME_MAX_HTML_BYTES = 200 KB` enforced by Pydantic validator. |
| Path traversal | Already covered by `SkillScriptExecutor` (existing). |

### 4. Runtime conventions — theme, locale, auto-resize, CSPRNG

To keep skill frames consistent with the host app without each script having to reimplement the plumbing:

- **`_lang` and `_tz` auto-injection** — `run_skill_script` automatically adds the user's ISO 639-1 language and IANA timezone to `parameters` before invoking the executor. Scripts rely on inline translation tables (the Docker image lacks POSIX locales, so `strftime`+`setlocale` silently falls back to English).
- **Theme & locale sync** — the React bridge pushes `ui/theme-changed` + `ui/locale-changed` on iframe `load` (double `requestAnimationFrame` defer) and maintains a `MutationObserver` on `<html class>` and `<html lang>` for live propagation. Scripts flip CSS via `html[data-theme="dark"]` selectors — **not** `@media (prefers-color-scheme)`, which is independent of the in-app theme toggle.
- **Auto-resize** — an injected snippet measures `document.body.getBoundingClientRect().bottom` (iframe-resizer pattern) and emits `ui/notifications/size-changed`. The host iframe grows/shrinks to fit content. `scrollHeight`/`offsetHeight` are **not** used — they include the iframe's own viewport, producing spurious heights.
- **Client-side interactivity** — the injected CSP forbids inline `onclick` handlers; scripts must use `addEventListener` in a `<script>` block. CSPRNG (`crypto.getRandomValues` + rejection sampling) is the canonical source of randomness.

### 5. Skill instructions primacy via a 2nd system message

`skills_context` (the active skill's `references/*.md` content) is injected as a **dedicated second system message** prefixed with `"SKILL INSTRUCTIONS CONTRACT (PRIORITY: HIGHEST)"` and an explicit override of the generic `<ResponseGuidelines>`. This exploits the LLM's primacy effect: references authored by the skill dominate the default response rules. Previously, `skills_context` was interpolated into the base system prompt template, where the LLM gave it the same weight as other sections.

### 6. Split widget rendering from data-card rendering

A new frozenset in [src/domains/agents/data_registry/models.py](../../apps/api/src/domains/agents/data_registry/models.py):

```python
INTERACTIVE_WIDGET_TYPES = frozenset({
    RegistryItemType.SKILL_APP,
    RegistryItemType.MCP_APP,
    RegistryItemType.DRAFT,
})
```

`response_node` renders these **regardless** of `user_display_mode` (Rich HTML / Markdown / Cards); other registry items remain conditional on Cards mode. Before this fix, users in Rich HTML / Markdown display modes could not see skill frames at all — a regression that made rich outputs invisible for the majority of display configurations.

### 7. Qwen-tolerance — parameter coercion

A `_coerce_parameters(value: dict | str | None) -> dict` helper accepts JSON strings in addition to dicts. Qwen models occasionally serialize `parameters` as a stringified JSON object rather than a native object, which previously caused `GraphRecursionError` in the ReAct loop. The helper normalizes the input so the rest of the pipeline only ever sees a dict.

## Consequences

### Positive

- **Full backward compatibility** — existing skills that emit plain text (or the legacy `ScriptResult` shape wrapped by the executor) continue to work unchanged; `parse_skill_stdout` falls back to `SkillScriptOutput(text=stdout)` when the stdout is not valid JSON.
- **Zero new transport** — reuses Data Registry + SSE + sentinel + React widget pipeline shipped for MCP Apps.
- **Sandboxed-by-default** — the default posture for user-imported skills is the strictest: sandboxed iframe + CSP + no same-origin + limited bridge.
- **Seven pilot skills shipped** — `interactive-map`, `weather-dashboard`, `calendar-month`, `qr-code`, `pomodoro-timer`, `unit-converter`, `dice-roller` — proving the contract across the Visualizer (frame) and Generator (image) archetypes, and across deterministic (plan_template) and A1 (ReAct-only) activation paths.
- **Documented runtime conventions** — `skill-generator` and the user-facing Skills Guide both formalize `_lang`/`_tz`, theme sync, auto-resize, and CSPRNG patterns so new skills produced either by the LLM generator or by users-by-hand pass on the first try.

### Trade-offs

- **No localStorage persistence inside frames** — skills needing stateful behavior (e.g. a mood-tracker) would require a dedicated backend tool; deferred to a future iteration with validated demand.
- **Frames lost on history reload** — when a conversation is reloaded, the registry isn't re-hydrated, so frames fall back to a placeholder card (same behavior as MCP Apps). Resolution requires persisting registry items in the conversation API — orthogonal to this ADR.
- **Double LLM cost if `plan_template` + scripts coexist** — a skill with both a deterministic plan and a script runs the plan then the script; each LLM touchpoint costs tokens. Existing bypass rules limit this but don't eliminate it. Future optimization: detect the combo in `_skill_needs_runner` and skip one layer when the plan already carries all parameters.
- **Bridge limited — no `tools/call`** — a frame cannot call back into LIA's API. This is intentional (reduces attack surface) but limits the richness of interactive widgets. If a concrete use case emerges with a clear security model, the bridge can be extended.
- **Grid of 7 widgets is asymmetric on some layouts** — unrelated to the contract, but the landing page TechSection initially went from 6 → 7 cards before being rebalanced to 8 for visual symmetry.

### Testing

- **Backend** — `test_script_output.py` (7 parsing cases), `test_output_builder.py` (5 builder cases), `test_tools.py` (rich / compat), `test_skill_app_sentinel.py` (sentinel HTML render), `test_validate_skill.py` (extended for `outputs:` frontmatter). Non-regression: `test_skill_bypass_strategy`, `test_planner_v3_skill_guard`, `test_routing_decider_skill`.
- **Frontend** — `SkillAppWidget.test.tsx` (iframe frame, image card, missing-registry fallback), `useSkillAppBridge.test.ts` (blocked methods: `tools/call`).

## Key files

**Backend**:

- [apps/api/src/domains/skills/script_output.py](../../apps/api/src/domains/skills/script_output.py) — `SkillScriptOutput`, `SkillFrame`, `SkillImage`, `parse_skill_stdout()`.
- [apps/api/src/domains/skills/output_builder.py](../../apps/api/src/domains/skills/output_builder.py) — `build_skill_app_output()` + CSP injection + `_AUTORESIZE_SCRIPT` snippet.
- [apps/api/src/domains/skills/tools.py](../../apps/api/src/domains/skills/tools.py) — `run_skill_script` parses stdout, auto-injects `_lang` / `_tz`, emits registry.
- [apps/api/src/domains/agents/data_registry/models.py](../../apps/api/src/domains/agents/data_registry/models.py) — `RegistryItemType.SKILL_APP`, `INTERACTIVE_WIDGET_TYPES` frozenset.
- [apps/api/src/domains/agents/display/components/skill_app_sentinel.py](../../apps/api/src/domains/agents/display/components/skill_app_sentinel.py) — sentinel HTML emitter.
- [apps/api/src/domains/agents/nodes/response_node.py](../../apps/api/src/domains/agents/nodes/response_node.py) — wraps `skills_tools` with `ReactToolWrapper`, merges `accumulated_registry`, splits widget vs data-card rendering, injects the "SKILL INSTRUCTIONS CONTRACT" 2nd system message.

**Frontend**:

- [apps/web/src/types/skill-apps.ts](../../apps/web/src/types/skill-apps.ts) — `SkillAppRegistryPayload`.
- [apps/web/src/components/chat/SkillAppWidget.tsx](../../apps/web/src/components/chat/SkillAppWidget.tsx) — iframe + image card with transparent background.
- [apps/web/src/hooks/useSkillAppBridge.ts](../../apps/web/src/hooks/useSkillAppBridge.ts) — minimal postMessage bridge + live theme/locale `MutationObserver`.
- [apps/web/src/components/chat/MarkdownContent.tsx](../../apps/web/src/components/chat/MarkdownContent.tsx) — `lia-skill-app` sentinel detection.

**Constants**:

- `SKILLS_FRAME_MAX_HTML_BYTES` in [src/core/constants.py](../../apps/api/src/core/constants.py).

**Documentation**:

- [docs/technical/SKILLS_INTEGRATION.md](../technical/SKILLS_INTEGRATION.md) § Rich Outputs + Runtime conventions.
- [docs/knowledge/12_skills.md](../knowledge/12_skills.md) § Rich outputs.
- Skill-generator references: [data/skills/system/skill-generator/references/format-specification.md](../../data/skills/system/skill-generator/references/format-specification.md), [archetype-examples.md](../../data/skills/system/skill-generator/references/archetype-examples.md).

## Alternatives considered and rejected

1. **Single shared widget type for MCP Apps and Skills** — merging `MCP_APP` and `SKILL_APP` under one `INTERACTIVE_APP` type. Rejected: the two have distinct security models (MCP apps are per-user-opted, skill frames are per-import), different bridge capabilities (MCP bridge supports `tools/call`, skill bridge does not), and different payload shapes. Keeping them distinct preserves auditability.
2. **Running the script inside the frame** (no SSR, the browser receives the Python source) — rejected for obvious security reasons and because the Python sandbox (subprocess isolation, network `unshare`) is server-side only.
3. **Frontmatter `render: html|image|text`** instead of JSON stdout — rejected: forces the skill to declare rendering at authoring time, even for dynamic behavior. The JSON contract lets a single script switch between pure text and rich output based on parameters.
4. **Lists (`frames`, `images`)** as first-class fields — rejected in v1: skills that need multiple images build a grid inside `frame.html`. Extension to lists can be added later without breaking the contract (additive fields).
5. **`allow-same-origin` in the sandbox** — rejected unconditionally: grants access to parent cookies and defeats the CSP. If a frame needs to call back, it must go through the `ui/open-link` bridge (HTTPS only) or be promoted to an MCP App.

## References

- [ADR-071: Skill Semantic Identification](ADR-071-Skill-Semantic-Identification.md) — how `QueryAnalyzer` picks the skill.
- [ADR-074: `structured_data` Contract for Tool Outputs](ADR-074-Structured-Data-Contract.md) — how skill scripts consume upstream tool results in `plan_template`.
- google-ai-edge/gallery — external inspiration for the rich-output pattern (skill decides, app routes).
