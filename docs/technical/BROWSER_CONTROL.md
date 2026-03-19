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
  `press_key`, `screenshot` — used by the ReAct agent, not by the planner directly.

## Configuration

All settings in `.env` (technical tuning only — activation via admin connector panel):

```env
BROWSER_MAX_CONCURRENT_SESSIONS=1     # Global max (Redis-coordinated)
BROWSER_SESSION_TIMEOUT_SECONDS=300   # Idle timeout
BROWSER_PAGE_LOAD_TIMEOUT_SECONDS=30  # Navigation timeout
BROWSER_ACTION_TIMEOUT_SECONDS=10     # Click/fill timeout
BROWSER_AX_TREE_MAX_TOKENS=10000     # Max tokens for AX tree output
BROWSER_MEMORY_LIMIT_MB=1024         # Memory limit per Chromium instance
BROWSER_RATE_LIMIT_READ_CALLS=40     # Rate limit for read tools
BROWSER_RATE_LIMIT_WRITE_CALLS=40    # Rate limit for write tools
```

## Security

- **SSRF prevention**: Reuses `validate_url()` from web_fetch (DNS resolution, private IP check)
- **Input sanitization**: Fill values stripped of control chars, max length enforced
- **Key whitelist**: Only Enter, Tab, Escape, Arrow keys, etc. allowed
- **Request interception**: Blocks dangerous schemes (javascript:, data:, file:)
- **Anti-detection**: Chrome UA, `navigator.webdriver` removed, locale/timezone from user prefs
- **Cookie auto-dismiss**: Generic multi-language selectors (no site-specific)
- **`--no-sandbox`**: Required in Docker, isolation by container (see ADR-057)

## Session Management

- Sessions are process-local (Playwright BrowserContext can't be serialized)
- Metadata stored in Redis (`browser:session:{user_id}`) with TTL = session timeout
- Cross-worker recovery: if follow-up lands on different worker, re-navigates to stored URL
- Global session count coordinated via Redis key counting (excludes own recovery)
- Page crash recovery: corrupted pages are closed and recreated on next navigation

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
