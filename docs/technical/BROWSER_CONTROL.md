# Browser Control (F7) — Technical Documentation

## Overview

Browser Control enables LIA to interact with websites using a headless Chromium
browser via Playwright. It can navigate pages, search for content, click elements,
fill forms, and extract data from JavaScript-rendered pages.

## Architecture

```
User: "Find Nike Air prices on nike.com"
  ↓
Router → domain=browser (confidence 0.95)
  ↓
Planner → step_1: browser_task_tool(task="...")
  ↓
browser_task_tool → create_react_agent(llm, browser_tools)
  ↓
ReAct Loop:
  → browser_navigate_tool("https://www.nike.com/fr/w?q=nike+air")
  → reads visible text → finds products and prices
  → responds with structured results
  ↓
Response Node → synthesizes final answer for user
```

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| BrowserSettings | `src/core/config/browser.py` | Configuration (timeouts, rate limits, memory) |
| BrowserPool | `src/infrastructure/browser/pool.py` | Singleton pool, Redis coordination, session management |
| BrowserSession | `src/infrastructure/browser/session.py` | Page interaction, cookie dismissal, content extraction |
| BrowserSecurityPolicy | `src/infrastructure/browser/security.py` | SSRF prevention, input sanitization, key whitelist |
| AccessibilityTreeExtractor | `src/infrastructure/browser/accessibility.py` | CDP-based AX tree extraction for element interaction |
| browser_task_tool | `src/domains/agents/tools/browser_tools.py` | Primary tool — autonomous ReAct browsing |
| browser_navigate_tool | `src/domains/agents/tools/browser_tools.py` | Navigate to URL, return visible text |
| browser_snapshot_tool | `src/domains/agents/tools/browser_tools.py` | Get AX tree with [EN] refs for interaction |
| browser_click/fill/press_key | `src/domains/agents/tools/browser_tools.py` | Element interaction tools |

### Tool Design

- **`browser_task_tool`** (planner-facing): Takes a natural language task, runs
  a `create_react_agent` ReAct loop with all browser tools internally. The planner
  only sees this one tool.
- **Individual tools** (ReAct-facing): `navigate`, `snapshot`, `click`, `fill`,
  `press_key` — used by the ReAct agent, not by the planner directly.

> **Note**: The parent graph's `InMemoryStore` (`runtime.store`) is propagated to the nested
> browser ReAct agent via the `store` parameter of `create_react_agent`. This ensures that
> `validate_runtime_config` (and any other store-dependent validation) behaves identically
> inside the nested agent as it does in the top-level graph.

### Agent prompt (`prompts/v1/browser_agent_prompt.txt`)

The browser agent's behaviour is shaped by a versioned prompt loaded via
`load_prompt("browser_agent_prompt", version="v1")` (in `react_runner.py` and
`browser_agent_builder.py`). Key contracts it enforces:

- **Two task modes** — *read/search/extract* (direct search-URL navigation
  allowed; apply filters first) vs *transactional/form* (operate the site's own
  controls — search box, autocomplete, date pickers, primary buttons; **never**
  fabricate URLs with query parameters not seen on a loaded page).
- **Observe → act → verify** loop — `browser_snapshot_tool` before deciding,
  one action per cycle, `browser_snapshot_tool` after any state-changing action
  to verify it; `[ref]` ids are valid only in the snapshot they came from
  (a stale-ref error means re-snapshot, not retry).
- **Element rules** — `browser_fill_tool` only on real input controls
  (textbox/searchbox/combobox/spinbutton), never a link/button/logo; for
  autocomplete fields, fill → snapshot → click the matching suggestion (not
  Enter); ignore skip links / footer / accessibility shortcuts.
- **Obstacles** — dismiss cookie banners/modals first; don't retry a 403/bot-
  detection URL; never attempt login/account creation.
- **Stuck detection** — same URL 3+ cycles without progress, or same action
  fails twice → change strategy once, else stop and report.
- **Stopping** — never enter credentials/payment; for transactional tasks,
  advance up to (not past) the login/payment/final-validation step, then stop
  and report a summary; report only facts actually seen in a tool result
  (no fabricated URLs/prices/availability).

## Configuration

All settings in `.env` (technical tuning only — activation via admin connector panel):

```env
BROWSER_REACT_MAX_ITERATIONS=15       # Max ReAct loop iterations (create_react_agent recursion_limit)
BROWSER_MAX_CONCURRENT_SESSIONS=1     # Global max (Redis-coordinated)
BROWSER_SESSION_TIMEOUT_SECONDS=300   # Idle timeout
BROWSER_PAGE_LOAD_TIMEOUT_SECONDS=30  # Navigation timeout
BROWSER_ACTION_TIMEOUT_SECONDS=10     # Click/fill timeout
BROWSER_AX_TREE_MAX_TOKENS=15000     # Max tokens for AX tree output (truncated if exceeded)
BROWSER_MEMORY_LIMIT_MB=1024         # Memory limit per Chromium instance
BROWSER_RATE_LIMIT_READ_CALLS=40     # Rate limit for read tools
BROWSER_RATE_LIMIT_WRITE_CALLS=40    # Rate limit for write tools
```

> `BROWSER_REACT_MAX_ITERATIONS` mirrors `REACT_AGENT_MAX_ITERATIONS` (main ReAct
> execution mode) and `MCP_REACT_MAX_ITERATIONS` (MCP iterative sub-agent): it caps
> the `recursion_limit` passed to the browser agent's `create_react_agent` loop in
> `browser_task_tool`. Range: 1–50, default 15.
>
> **Step timeout:** `browser_task_tool` runs a full nested ReAct loop, so the
> parallel executor gives that step a dedicated wall-clock budget
> (`BROWSER_TOOL_TIMEOUT_SECONDS` = 300s floor, `MAX_BROWSER_TOOL_TIMEOUT_SECONDS`
> = 600s ceiling) instead of the generic 30s/120s tool timeout — otherwise the
> planner's chosen `timeout_seconds` would `asyncio.wait_for`-cancel the loop
> mid-task. `BROWSER_AX_TREE_MAX_TOKENS` controls how much of the page the LLM
> can see in a snapshot — too low and it can't reach form fields past the cutoff.

## Security

- **SSRF prevention**: Reuses `validate_url()` from web_fetch (DNS resolution, private IP check)
- **Input sanitization**: Fill values stripped of control chars, max length enforced
- **Key whitelist**: Only Enter, Tab, Escape, Arrow keys, etc. allowed
- **Request interception**: Blocks dangerous schemes (javascript:, data:, file:)
- **Anti-detection**: Chrome UA, `navigator.webdriver` removed, locale/timezone from user prefs
- **Cookie auto-dismiss**: Generic multi-language selectors (no site-specific)
- **`--no-sandbox`**: Required in Docker, isolation by container (see ADR-059)

## Session Management

- Sessions are process-local (Playwright BrowserContext can't be serialized)
- Metadata stored in Redis (`browser:session:{user_id}`) with TTL = session timeout
- Cross-worker recovery: if follow-up lands on different worker, re-navigates to stored URL
- Global session count coordinated via Redis key counting (excludes own recovery)
- Page crash recovery: corrupted pages are closed and recreated on next navigation

## Progressive Screenshots (SSE Side-Channel)

During browser navigation, LIA streams progressive screenshots to the frontend
via an SSE side-channel. These screenshots are **not processed by the LLM** — they
provide real-time visual feedback to the user during browsing.

### How It Works

```
Browser tool action (navigate/click/fill/press_key/snapshot)
  → session.screenshot_with_thumbnail()  (one Playwright call → full-res + thumbnail)
  → _emit_progressive_screenshot()
      ├── Thumbnail (640px, JPEG q60, ~30KB) → asyncio.Queue → SSE → frontend overlay
      └── Full-res (1280px, JPEG q80, ~120KB) → browser_screenshot_store (module-level)

service.py: _interleave_side_channel() polls queue every 300ms
  → yields side-channel chunks independently of graph stream timing

On STREAM_DONE:
  → Full-res saved as Attachment (disk + DB, TTL-based cleanup)
  → URL in done_metadata["browser_screenshot"] + assistant_metadata
  → Frontend renders persistent card inside assistant bubble
```

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `BROWSER_PROGRESSIVE_SCREENSHOTS` | `true` | Enable/disable progressive screenshot SSE streaming |
| `BROWSER_SCREENSHOT_DEBOUNCE_SECONDS` | `0.1` | Min interval between screenshots per user |

### Key Design Decisions

- **Side-channel queue** (`__side_channel_queue`): Generic `asyncio.Queue` in `RunnableConfig.configurable`, reusable by any tool for direct-to-frontend SSE events.
- **`_interleave_side_channel()`**: Wrapper that polls the queue every 300ms even when the graph is blocked in long node executions (ReAct browser loop).
- **`__parent_thread_id`**: Forwarded in ReAct `nested_config` to ensure the `browser_screenshot_store` uses the real `conversation_id` (not the synthetic ReAct `thread_id`).
- **Two outputs per capture**: Thumbnail for lightweight SSE overlay, full-res for persistent card (Retina-ready at 1.43x density for 448px card).
- **No auto-dismiss**: Overlay stays visible until replaced by a new screenshot or cleared by `STREAM_DONE`.
- **Final card in bubble**: Rendered before markdown content, with lightbox support (click to expand).

### Files

| File | Purpose |
|------|---------|
| `src/infrastructure/browser/session.py` | `screenshot_with_thumbnail()` method |
| `src/domains/agents/tools/browser_tools.py` | `_emit_progressive_screenshot()` helper + 5 call sites |
| `src/domains/agents/tools/browser_screenshot_store.py` | Module-level store for final card (pattern: `image_store.py`) |
| `src/domains/agents/tools/runtime_helpers.py` | `emit_side_channel_chunk()` generic helper |
| `src/domains/agents/api/service.py` | `_interleave_side_channel()` + queue creation + card Attachment save |
| `src/domains/agents/api/schemas.py` | `"browser_screenshot"` SSE chunk type |
| `apps/web/src/components/chat/BrowserScreenshotOverlay.tsx` | Inline overlay component |
| `apps/web/src/components/chat/ChatMessage.tsx` | `BrowserScreenshotCard` inline component |

## Metrics (Prometheus)

| Metric | Type | Labels |
|--------|------|--------|
| `browser_sessions_active` | Gauge | — |
| `browser_actions_total` | Counter | action_type, status |
| `browser_navigation_duration_seconds` | Histogram | — |
| `browser_snapshot_tokens` | Histogram | — |
| `browser_errors_total` | Counter | error_type |
| `browser_memory_bytes` | Gauge | — |

## Limitations

- Sites with strong anti-bot (DataDome, Cloudflare Turnstile) may block
- Headless Chromium consumes ~300-600MB RAM per session
- ReAct loop latency: 15-60s per browsing task
- Token cost: ~$0.01-0.03 per browsing session
- No login persistence across sessions (cookies reset on new BrowserContext)
