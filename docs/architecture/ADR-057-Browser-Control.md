# ADR-057: Browser Control Architecture (Playwright)

## Status

Accepted — 2026-03-19

## Context

LIA needs to interact with websites beyond simple page fetching (web_fetch).
Use cases: fill forms, search products on e-commerce sites, extract dynamic
JS-rendered content, navigate multi-page workflows.

## Decision

### Architecture: Connector pattern with autonomous ReAct agent

Browser control follows the same connector pattern as Wikipedia:
- Infrastructure in `src/infrastructure/browser/` (pool, session, security, accessibility)
- Primary tool: `browser_task_tool` — takes a natural language task, delegates to a
  ReAct agent that navigates, searches, clicks, fills autonomously
- Internal tools: `browser_navigate_tool`, `browser_snapshot_tool`, `browser_click_tool`,
  `browser_fill_tool`, `browser_press_key_tool` — used by the ReAct loop, not by the planner
- Activation via admin connector panel (no `.env` feature flag)

### Key decisions

1. **`--no-sandbox` in Docker** — Required because Docker containers don't provide
   user namespaces. Isolation is ensured by the container itself.

2. **CDP direct for accessibility tree** — `await page.context.new_cdp_session(page)`
   + `Accessibility.getFullAXTree`. Stable Chrome DevTools Protocol API (Playwright's
   `page.accessibility.snapshot()` is deprecated since v1.41).

3. **Session-per-user with Redis recovery** — Sessions are process-local (Playwright
   BrowserContext can't be serialized). Metadata (URL, title) stored in Redis with TTL.
   Cross-worker recovery: re-navigate to stored URL transparently.

4. **Autonomous ReAct agent** — The planner calls `browser_task_tool` with a natural
   language instruction. The tool runs `create_react_agent` (langgraph.prebuilt) with
   browser tools internally. This enables multi-step interaction (navigate → search →
   click → read) that a static ExecutionPlan can't achieve.

5. **Content extraction via `page.inner_text()`** — Navigate returns visible text content
   (not raw AX tree). Tries semantic HTML5 containers (`main`, `article`) first, falls back
   to `body`. The AX tree is reserved for `snapshot` (interaction with [EN] refs).

6. **Anti-detection** — Chrome UA, `navigator.webdriver` removed, `AutomationControlled`
   disabled, locale/timezone from user preferences. Generic cookie banner auto-dismiss.

## Consequences

- Browser is the most resource-intensive agent (Chromium ~300-600MB RAM per session)
- Sites with strong anti-bot (DataDome, Cloudflare Turnstile) may still block
- ReAct loop adds latency (~15-60s per task) and token cost (~$0.01-0.03)
- Global session coordination via Redis prevents OOM on RPi5

## References

- [BROWSER_CONTROL.md](../technical/BROWSER_CONTROL.md) — Technical documentation
- [SECURITY.md](../technical/SECURITY.md) — Browser security section
