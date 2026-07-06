# ADR-093: Security Hardening — Trusted Proxy Chain & XSS Sanitization Boundary

**Status**: ✅ IMPLEMENTED (2026-07-03)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-034](ADR-034-Security-Hardening.md) (earlier hardening batch), [ADR-020](ADR-020-Observability-Stack.md) (GeoIP/metrics consumers of the client IP)

## Context

A systemic audit surfaced the two highest-severity findings left in the
backlog, both security posture defects rather than single bugs:

1. **Client IP was never trustworthy.** The prod API port was published
   `"8000:8000"` (every host interface — LAN clients could bypass Cloudflare
   entirely), uvicorn ran without `--proxy-headers` (so
   `request.client.host` was the Docker gateway for every request: the
   per-IP rate limit was one shared global bucket, GeoIP always "local",
   logs had no real IP), and the auth path read the raw `X-Forwarded-For`
   header with no trust validation (any direct client could forge it to
   rotate per-IP auth rate-limit keys).
2. **LLM output rendered as unsanitized HTML.** The chat markdown pipeline
   ran `rehype-raw` (`allowDangerousHtml`) with no sanitizer — the
   documented react-markdown XSS anti-pattern. The LLM can relay verbatim
   third-party content (email bodies, fetched pages, MCP output); embedded
   HTML executed with the user's session (httpOnly cookie auto-attached to
   same-origin API fetches). `urlTransform` and server-side `escape_html`
   were partial mitigations, not a boundary.

## Decision

### Trusted proxy chain (one coupled invariant)

- Published prod ports `8000`/`9091` are **loopback-bound**
  (`127.0.0.1:8000:8000`): cloudflared (host systemd → localhost) is the
  single public entry point; the in-container healthcheck and
  compose-network traffic (web SSR → `http://api:8000`, Prometheus scrape
  → `api:9091`) are unaffected. Postgres `5432` stays LAN-exposed by
  explicit user decision (external DB management).
- uvicorn runs `--proxy-headers --forwarded-allow-ips="*"` — `"*"` is safe
  **only because of** the loopback binding (every peer that can reach the
  port is trusted). The coupling is documented at both sites; changing one
  side requires revisiting the other.
- Application code never reads raw `X-Forwarded-For`:
  `request.client.host` (validated by uvicorn) is the single source of
  client IP for slowapi, GeoIP, logging and the auth rate limiter.

### XSS sanitization boundary

`rehype-sanitize` is inserted in the markdown pipeline with the exact
order `rehypeRaw → rehypeSanitize → rehypeMathInText → rehypeKatex`
(KaTeX output is generated after the boundary; the math nodes it
consumes survive via allowed `className`). `rehypeMathInText`
(`src/lib/rehype-math-in-text.ts`) sits between the boundary and KaTeX:
it converts `$…$`/`$$…$$` found inside the raw HTML the assistant emits
into KaTeX marker spans (remark-math only sees markdown, never the HTML
blocks answers are wrapped in). It reads only already-sanitized text and
emits fixed-class `<span>`s, so it adds no XSS surface. The schema (`src/lib/markdown-sanitize-schema.ts`)
extends the GitHub `defaultSchema` from a full audit of every legitimate
HTML producer: `button` tag, `className`/`style`/`data*` everywhere —
including the tags `defaultSchema` constrains (`a`, `code`, `h2`, `li`,
`ol`, `section`, `ul`), whose per-tag `className` allow-lists take
precedence over the wildcard and stripped card-title classes — plus
`tel:` links; `<style>` blocks are stripped (legacy inline-CSS messages).
`script`/`iframe`/`form`/event handlers are dropped. MCP/Skill App HTML
never goes through markdown: the server emits a sentinel `<div>` replaced
by the sandboxed widget component.

A nonce-based frontend CSP (Next App Router) is deliberately deferred as
defense-in-depth follow-up; the backend CSP already exists.

## Consequences

- Per-IP rate limiting is effective per real visitor; GeoIP dashboards
  populate; logs carry the public IP. Post-deploy validation: app works
  via the tunnel, LAN `curl :8000` refused, forged XFF ignored.
- Rendering guarantees are pinned by tests in both directions (attack
  vectors stripped / every legitimate markup category surviving), and the
  live regression found during visual validation (constrained
  `className`) is covered.
- Any new HTML-producing feature must extend the sanitize schema
  explicitly — silent stripping is the failure mode to watch in visual QA.
