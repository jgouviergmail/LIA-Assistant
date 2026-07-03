# ADR-096: Performance, Network & Trust Boundaries from the Wave-3 Audit

**Status**: ✅ IMPLEMENTED (2026-07-03)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-093](ADR-093-Security-Hardening-Proxy-XSS.md) (proxy/XSS hardening), [ADR-094](ADR-094-Remove-Dead-Per-Node-Windowing-Helpers.md) (wave-1), [ADR-095](ADR-095-Systemic-Guards-Wave2-Audit.md) (wave-2 systemic guards), [ADR-085](ADR_INDEX.md) (boot-time completeness asserts), [infrastructure/README.md](../../infrastructure/README.md) (network exposure model)

## Context

Wave 3 of the 2026-07 full-codebase audit targeted three boundaries that the
earlier waves did not: the **async/event-loop boundary** (synchronous work
freezing the loop), the **network-exposure boundary** (internal services
reachable from the LAN), and the **trust boundary** (LLM output rendered as
HTML). Alongside these it closed four localized performance/correctness
defects. As in the prior waves, the "definition of done" was a measured
before/after (latency or call count) and a red-first regression test — never
an unquantified "should be faster".

Unlike waves 1–2, this wave **does** carry a DB schema change (one JSONB
column + Alembic migration) and **two** new `.env` keys — both are
performance caches, opt-outable.

The nine items:

1. **A6 — synchronous work on the async path.** `firebase_admin.messaging.send`
   (FCM push + broadcast), Pillow decode/LANCZOS/encode (image edit), and two
   embedding calls (`embed_documents`/`embed_query` in interests + heartbeat)
   ran inline on the event loop, freezing *every* concurrent coroutine (SSE
   included) for the duration. Measured stalls: 261 ms (single FCM), 496 ms
   (2-token broadcast), 251 ms (resize). One docstring already *claimed*
   `asyncio.to_thread` without using it.
2. **N-129 — per-call User query + invalid locale.** `get_user_preferences`
   (25+ tools, several calls per plan) opened a DB session and queried `User`
   on **every** call, and derived the locale as `f"{lang}-{lang.upper()}"` —
   producing nonexistent locales `en-EN`, `zh-ZH` (the latter also broke
   Chinese date formatting). The bug was duplicated inline in `emails_tools.py`
   (2 sites).
3. **N-175 — sequential domain scan on a hot path.** `list_active_domains`
   (called by `resolve_reference`) issued ~2 sequential store reads per
   registered domain.
4. **N-194.8 — sequential Gmail metadata fetches.** Gmail's list endpoint
   returns IDs only; `search_emails` then fetched each message one-by-one (N
   sequential round-trips).
5. **N-213.2 — broadcast translations recomputed per read.** A broadcast shown
   to a non-source-language user was re-translated by an LLM on **every** read
   (login, tab focus).
6. **N-219.1 — unregistered translation LLM.** `PersonalityTranslationService`
   hardcoded provider/model/temperature/max_tokens, invoked the provider
   adapter with a `personality_translation` `llm_type` that **did not exist**
   in `LLM_TYPES_REGISTRY` (invisible in the admin LLM Configuration UI, immune
   to DB overrides), and inlined its prompt in Python.
7. **A3 — internal services exposed on the LAN.** 13 ports (Postgres, Grafana,
   Prometheus, Loki, Tempo/OTLP, Portainer, cAdvisor, exporters) were published
   on `0.0.0.0` in `docker-compose.prod.yml`. Docker inserts its own iptables
   chain **before** ufw, so a `ufw deny` did not protect them.
8. **A4 — LLM greeting rendered as raw HTML.** The dashboard hero greeting was
   injected via `dangerouslySetInnerHTML` on LLM output that can echo
   third-party text (e.g. a calendar event title). No Content-Security-Policy
   header existed as a backstop.
9. **N-194.10 — Gmail reply body double-encoded.** `reply_email` called
   `set_payload(bytes)` on a `MIMEText` whose `Content-Transfer-Encoding` was
   already `base64`, relying on undocumented re-encoding behavior of the
   `email` package.

## Decision

Fix every occurrence, measure before/after, and attach a regression test:

| Item | Fix | Evidence / guard |
|------|-----|------------------|
| A6 (event-loop blocking) | `asyncio.to_thread` (Firebase send, Pillow resize via new `resize_image_b64_async`, disk read) + native async embeddings (`aembed_documents`/`aembed_query`) | **Event-loop stall tests** (`tests/helpers/event_loop.py`): a ticker measures the max scheduling gap while the workload runs. 261→11 ms, 496→12 ms, 251→11 ms. |
| N-129 (per-call query + locale) | Per-worker TTL cache `UserPreferencesCache` (invalidated on profile update); `LANGUAGE_TO_LOCALE` mapping replaces the buggy derivation; the 3 sites (helper + 2 inline in emails) call one helper | 1 User query per TTL window per user (was 1/call). Boot-time completeness assert on `LANGUAGE_TO_LOCALE` (ADR-085). `en→en-US`, `zh-CN→zh-CN`. New key `USER_PREFERENCES_CACHE_TTL_SECONDS` (0 disables). |
| N-175 (sequential scan) | `asyncio.gather` per domain, registry order preserved | 631→63 ms on a 10-domain bench (store 20 ms/read). Full gain lands with the V5 connection pool (the Store still serializes reads); the call pattern is ready. |
| N-194.8 (N+1 Gmail fetch) | Bounded `asyncio.gather` (semaphore = `EMAILS_SEARCH_FETCH_CONCURRENCY`, default 8); each fetch still passes the rate limiter | 331→62 ms for 10 results (30 ms/fetch). Same payloads, same order. New key `EMAILS_SEARCH_FETCH_CONCURRENCY`. |
| N-213.2 (re-translated per read) | New JSONB column `admin_broadcasts.message_translations`, filled at send time, lazily backfilled on read; server-side atomic `coalesce(...) \|\| :new` merge | 0 LLM calls when reading an already-translated broadcast. **Migration** `admin_broadcast_translations_001`. Failed translations (fallback = source text) are never frozen. |
| N-219.1 (unregistered LLM) | Register `personality_translation` in `LLM_TYPES_REGISTRY` + `LLM_DEFAULTS`; route through `get_llm()`; move prompt to `prompts/v1/` | Slot appears in the admin LLM Config UI (verified via the API); a DB override is honored. The import-time registry/defaults sync assert covers it. |
| A3 (LAN exposure) | Bind all internal services to `127.0.0.1` in `docker-compose.prod.yml`; `cloudflared` remains the single public entry | 13→1 published port (only `web`). Documented in [infrastructure/README.md](../../infrastructure/README.md): the ufw bypass and the `DOCKER-USER` chain as the supported hook. |
| A4 (XSS + no CSP) | Render the greeting as auto-escaped React children (like `BriefingSynthesis`); add a strict CSP header in `next.config.ts` | A `<img src=x onerror=alert(1)>` event title is inert (test). CSP blocks external scripts + `eval`, keeps WASM/workers/fonts/API working; 0 violations verified in-browser across login/dashboard/chat/landing/FAQ. |
| N-194.10 (reply encoding) | Build `body + quoted_block` **before** constructing `MIMEText` (parity with `apple_email`/`forward_email`) | Test decodes the exact raw sent to the API; a real dev send confirmed correct accents. See note below. |

The two most architecturally significant items are the **network exposure
model** (now: `cloudflared` is the only public entry, everything else is
loopback-bound, with the ufw/Docker interaction written down) and the
**Content-Security-Policy** (a defense-in-depth backstop behind the primary
React-escaping boundary — an injected `<script src>` or `eval()` is blocked
even if a future rendering bug reintroduces raw HTML).

## Consequences

- **One DB schema change + migration** (`message_translations` JSONB) and
  **two new `.env` keys** (`USER_PREFERENCES_CACHE_TTL_SECONDS`,
  `EMAILS_SEARCH_FETCH_CONCURRENCY`) — both performance caches, opt-outable
  (TTL 0 / concurrency 1). Documented in `.env.example` and `.env.prod.example`.
- **The event-loop stall test helper is reusable** for any future async-path
  regression — it directly measures loop responsiveness, not just correctness.
- **Cross-worker staleness for user preferences is bounded by the TTL** (default
  5 min): the updating worker is invalidated immediately, the others converge
  within the window — the same trade-off as `LLMConfigOverrideCache`.
- **CSP uses `'unsafe-inline'` in `script-src`** because Next.js App Router
  ships inline bootstrap scripts and static headers cannot carry a per-request
  nonce. The header still blocks every external script origin and `eval()`; the
  React-escaping boundary remains the primary XSS defense. A future move to
  nonces would require middleware + dynamic rendering (deferred — costly on the
  RPi5 target).
- **N-194.10 was a latent-only defect.** The double-encoding bug did **not**
  reproduce on the runtimes actually in use (Python 3.12 container, 3.13 host):
  `as_string()` re-encodes via the retained charset. The refactor is still
  justified (it removed reliance on undocumented behavior and aligned Gmail
  with the two other mail clients) and was validated by a real send, but it is
  recorded as hardening, not a user-visible bug fix.

## Alternatives considered

- **Thread-pool executor tuning instead of `asyncio.to_thread`.** Rejected —
  `to_thread` uses the default executor, which is sufficient for these
  low-frequency blocking calls; a dedicated pool adds configuration surface for
  no measured benefit here.
- **Redis-backed shared preferences cache instead of per-worker.** Rejected for
  this wave — the per-worker in-memory cache matches the existing
  `LLMConfigOverrideCache` pattern, needs no network round-trip on the hot
  path, and the staleness window is acceptable for timezone/language. A shared
  cache can build on the same interface later.
- **CSP with per-request nonces.** Deferred (see Consequences) — correct
  long-term direction but disproportionate for this wave.
- **Host firewall (ufw) rules to close the LAN exposure instead of loopback
  binding.** Rejected — Docker bypasses ufw; loopback binding is enforced by
  the kernel at bind time and does not depend on any firewall rule. `DOCKER-USER`
  is documented as the hook for the cases that genuinely need host-level
  filtering of container traffic.
