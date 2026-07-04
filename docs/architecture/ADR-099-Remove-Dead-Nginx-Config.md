# ADR-099: Remove Dead nginx Reverse-Proxy Config

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-096](ADR-096-Performance-Boundary-Hardening-Wave3-Audit.md) (loopback binding, cloudflared as sole entry), [ADR-098](ADR-098-CSP-Widget-Airlock.md) (the investigation that re-surfaced this file), [ADR-033](ADR-033-Deployment-Architecture.md)

## Context

`infrastructure/nginx/` (a `Dockerfile` + an 8.9 KB `nginx.conf`) shipped
with the initial v1.0.0 open-source release and was **never wired**: no
Compose file in the repository's entire history has ever referenced it
(`git log -S "infrastructure/nginx"` over `*.yml` is empty), no Taskfile
target, no deploy script (`prepare-prod.ps1` generates the real prod deploy;
production ingress is the host-level `cloudflared` tunnel — ADR-096 bound
everything else to loopback). `infrastructure/README.md` already labeled it
"legacy/local scenarios".

Dead configuration is not neutral. This file was **actively misleading**:

- It declares a permissive global CSP
  (`default-src 'self' http: https: data: blob: 'unsafe-inline'`) that
  contradicts the real, strict app policy (`apps/web/src/lib/csp.ts`,
  ADR-098). During the ADR-098 investigation it had to be ruled out as a
  potential second CSP source (two CSP headers = intersection) — real
  analysis time spent on a component that does not exist at runtime.
- Its security headers (`X-XSS-Protection`, `Referrer-Policy:
  no-referrer-when-downgrade`) diverge from the actual ones in
  `next.config.ts`, inviting copy-paste of stale values.

Per the CLAUDE.md systemic rule: *"Dead code is deleted, not kept 'for
later'… Wire it or remove it — record the decision in a short ADR."*

## Decision

Delete `infrastructure/nginx/` entirely (Dockerfile + nginx.conf).
`infrastructure/ssl/` is **kept**: its `generate-certs.sh` is live (mounted
by `docker-compose.dev.yml` to generate the dev HTTPS certificates).
`infrastructure/README.md` updated accordingly.

If a reverse proxy is ever needed in front of LIA (e.g. non-Cloudflare
self-hosting), write a fresh config against the then-current header set in
`next.config.ts` / `src/lib/csp.ts` — resurrecting this file would reintroduce
contradicting security headers.

## Consequences

- One less false lead for security audits (single source of truth for
  response headers: `next.config.ts` for the web app, `core/middleware.py`
  for the API).
- Self-hosters who want nginx must write their own config; the generic
  guidance in `docs/GETTING_STARTED.md` (reverse-proxy section) still applies.
