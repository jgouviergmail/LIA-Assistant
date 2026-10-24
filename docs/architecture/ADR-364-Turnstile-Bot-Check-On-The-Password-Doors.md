# ADR-364 — A Cloudflare Turnstile bot check guards the password doors; only the sign-in rides through an outage

**Status**: accepted — 2026-10-24 (owner: « Turnstile : on y va ? oui » ; « si Cloudflare
ne répond pas → juste connexion » ; « le bouton Google : plus tard » ; « domaines
jetables : non »)
**Amends**: ADR-363 (its rejected CAPTCHA), ADR-098 (the CSP opens
`https://challenges.cloudflare.com` to scripts and frames), ADR-119 (one more core alert)

## Context

1. **The 2026-10-23 attack never used a browser.** About twenty-eight accounts, reset
   requests aimed at the administrator, forged and replayed tokens — all posted to the API
   by a script from rotating addresses. The per-IP limiters cannot see a source that
   rotates, and ADR-363 bounded what ONE account receives, not who may knock.
2. **Turnstile is free and fits.** Cloudflare's Free plan: up to 20 widgets, unlimited
   challenges, 10 hostnames per widget (plans page, read 2026-10-23). The browser widget
   yields a token that lives 300 s, is single-use and is at most 2048 characters; only the
   server's call to `siteverify` proves it — a script posting to the API never runs the
   widget.
3. **Measured before it was built on** (2026-10-24): a page served with the production CSP
   (`buildAppCsp`), COOP `same-origin` and COEP `credentialless` — then `require-corp` —
   rendered Cloudflare's test widget and received its token in Chromium, Firefox 155 and
   WebKit (Playwright): 6 of 6. Not measured: the native shells' Android WebView and iOS
   WKWebView (no emulator or Mac on this host) — Cloudflare documents WebView support.
4. **The production instance already sits behind Cloudflare** (its tunnel): the check
   adds no new third party for its visitors. A self-hoster opts in with their own widget.

## Decision

1. **Three doors carry a token**: `POST /auth/register`, `POST /auth/login` and
   `POST /auth/request-password-reset`, in `X-LIA-Turnstile-Response` (never a `CF-`
   name: Cloudflare's proxy owns those). Each door is a guard
   (`login_guard`, `register_guard`, `password_reset_request_guard` in
   `domains/auth/dependencies.py`): the per-IP limiter FIRST — a flood is refused locally
   before it costs a call to Cloudflare — then the check. A passkey sign-in, a second
   factor, the reset link itself are bound to a credential or a token and are not doors;
   the Google button is the owner's « later ».
2. **One check per door** (`domains/auth/turnstile_gate.py`): no token → `missing`; longer
   than 2048 → `rejected`; otherwise Cloudflare is asked through `TurnstileClient`
   (`infrastructure/external/turnstile_client.py`: never raises, two attempts under one
   idempotency key, each bounded WHOLE by `TURNSTILE_VERIFY_TIMEOUT_SECONDS` — httpx alone
   bounds each phase apart — so an outage holds a sign-in two timeouts at most). A token
   passes only if Cloudflare vouches for it AND it was made for THIS door (`action`) on
   THIS instance's pages (`hostname`: the host of `FRONTEND_URL` or of an origin in
   `CORS_ORIGINS` — the pages allowed to call the API with its cookie; an origin nobody
   can parse names none). A site sharing the widget is not one of them.
3. **When Cloudflare gives no usable answer, only the sign-in proceeds** (owner
   decision): a person must always reach their account, while a new account and a reset
   e-mail can wait. A sign-up or a reset request is then refused, 503
   `turnstile_unavailable`; a token Cloudflare REFUSED is refused at every door, 403
   `turnstile_failed`. « No usable answer » covers a timeout, a 5xx, Cloudflare's own
   `internal-error`, and a refusal of the SERVER's request (`invalid-input-secret`,
   `missing-input-secret`, `bad-request`): read as « bad token », one mistyped secret would
   have refused every sign-in. **An outage reaches the browser too**: the widget cannot load
   and the sign-in arrives WITHOUT a token, exactly like a script's. Only the server's own
   view tells them apart, so a tokenless sign-in proceeds only while Cloudflare does not
   answer THIS server either: the verdict of the worker's latest call to Cloudflare stands
   `TURNSTILE_REACHABILITY_TTL_SECONDS`, otherwise one question is asked about an EMPTY
   token — Cloudflare answers it `missing-input-response` when it is up (measured
   2026-10-24) — shared by every concurrent caller (`run_single_flight`). A tokenless
   sign-up or reset request is refused without asking.
4. **Cloudflare's testing keys decide only outside production.** Measured 2026-10-24 on
   siteverify: the always-passing testing secret answers `success: true` with NO `action`,
   `hostname: "example.com"` whatever the page, and `metadata.result_with_testing_key`. The
   action and hostname checks would refuse every such answer, so outside production its
   verdict alone is read (the chain can be tried end to end, the always-failing key
   included); in production it is no usable answer — a testing secret there voids the check
   (anyone may send the dummy token), and like a mistyped secret it must never lock the
   sign-in. It is logged `turnstile_testing_key_in_production` at ERROR and counted
   `unavailable`, so `TurnstileUnavailable` fires.
5. **The operator's own widget, off by default**: `TURNSTILE_ENABLED`,
   `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` (no default value; the boot refuses the
   check switched on without both keys), `TURNSTILE_VERIFY_TIMEOUT_SECONDS`. Read from the
   settings at every check, never frozen at import; a changed `.env` applies when the API
   container is recreated. The guided installer asks for the two keys when the instance
   is reached on a public domain — both or neither, hidden at the prompt, refused when
   they are Cloudflare's testing keys — and writes them with `TURNSTILE_ENABLED=true` to
   the private `.env` alone (`scripts/install/turnstile.py`); a resume never re-asks
   them, and a run that skips them keeps the operator's own lines.
6. **The site key reaches the sign-in pages alone**: `GET /auth/features` answers a
   `PublicAuthFeaturesResponse` (`turnstile_site_key`, null when the check is off), while
   the chat's security read keeps `AuthFeaturesResponse` — the review is recorded in
   `assert_security_projection_coverage`.
7. **The web asks once, shows rarely, speaks plainly**: `lib/turnstile.ts` loads
   Cloudflare's explicit-render script once per page, on demand; `TurnstileWidget`
   (`size: flexible`, `appearance: interaction-only` — most people never see it; the
   page's theme and language; a named group) and `useTurnstileDoor` serve the three
   forms. A form waits for the token, sends it, names a refusal (never « invalid
   password »), and asks for a new token after every submit — the API spent it; once the
   widget could not load, the sign-in alone submits without one (`SUBMITS_WITHOUT_WIDGET`,
   the mirror of `PROCEEDS_WHEN_UNAVAILABLE`) and its widget says so
   (`auth.turnstile.load_failed_sign_in`), while a sign-up or a reset says the check could
   not load rather than « wait ». A tokenless sign-in the API refuses — Cloudflare answers
   the API, so the block is in THIS browser — is named that way
   (`auth.turnstile.blocked`: allow `challenges.cloudflare.com`), never « try again ». The
   forgot-password page keeps one answer whatever the address, except a refused or
   unavailable check, which is about the visitor and never the address. CORS allows the
   header; the CSP allows the host (`script-src`, `frame-src`).
8. **Counted, drawn, alerted**: `turnstile_verifications_total{action, outcome}`
   (`passed`, `missing`, `rejected`, `unavailable`; every series exists at zero), dashboard
   09, and the core alert `TurnstileUnavailable` (unanswered checks past
   `ALERT_CORE_TURNSTILE_UNAVAILABLE_PER_15M` in 15 minutes), with its runbook and its
   ADR-266 evidence recipe.

## Consequences

- A script that posts to the API without running the widget is refused at the three
  doors; a burst like 2026-10-23's stops there, whatever addresses it rotates through.
- Most visitors see nothing; Cloudflare shows an interaction only when it wants one.
- The privacy policy (version 1.2, six languages) states the check, and that the browser
  signals it reads are Cloudflare's, not LIA's.
- A self-hosted instance changes nothing until its operator creates a widget; one widget
  serves up to ten hostnames (an instance and its demonstrator, for example).
- A tool that signs in through the API — the TTFT measurement (`scripts/perf/measure_ttft.py`),
  the benchmark — is exactly what the check refuses: it needs the check off on its target
  (the development stack runs it off).

## Stated limits

- **A token can be bought.** Solving services sell them: the check raises an attacker's
  cost, it is not a wall. The per-IP limiters and ADR-363's per-account budget stand
  behind it.
- **During a Cloudflare outage the sign-in is unverified** — the decision — and nobody can
  sign up or ask for a reset e-mail; `TurnstileUnavailable` tells the operator, and the
  runbook says how to switch the check off meanwhile.
- **A browser that blocks Cloudflare while the server reaches it is refused at every
  door**, the sign-in included — an extension blocking `challenges.cloudflare.com`, say.
  The visitor must allow it (the page and the FAQ say so); the server cannot tell such a
  browser from a script.
- **The Google button is not guarded yet** (owner: later). A Google sign-up creates an
  inactive account an administrator must activate, and `RegistrationBurst` counts it.
- **Not measured in the native shells' WebViews** (`task mobile:probe` needs an emulator
  or a Mac): Cloudflare documents WebView support; the shells run JavaScript and DOM
  storage, which it requires.

## Rejected

- **A disposable-address blocklist** (owner: no). Measured on 2026-10-23: the curated CC0
  list holds the domain of the attacker's two verified accounts, not its own domain.
- **Failing open everywhere, or closed everywhere** — the owner chose the sign-in alone.
- **The implicit widget** (`class="cf-turnstile"` auto-render): a client-rendered page must
  render, reset and remove the widget itself.
- **A React wrapper package**: the explicit API is four calls; a dependency for them would
  be supply chain without need.

## Implementation references

- `apps/api/src/infrastructure/external/turnstile_client.py`,
  `apps/api/src/domains/auth/turnstile_gate.py`, `apps/api/src/domains/auth/dependencies.py`
  (the guards), `apps/api/src/domains/auth/router.py`, `apps/api/src/core/middleware.py`
  (CORS), `apps/api/src/core/config/security.py`, `apps/api/src/core/constants.py`,
  `apps/api/src/domains/auth/schemas.py` / `security_queries.py` (the site key)
- `apps/web/src/lib/turnstile.ts`, `apps/web/src/components/auth/TurnstileWidget.tsx`,
  `apps/web/src/hooks/useTurnstileDoor.ts`, the login, register and forgot-password forms,
  `apps/web/src/lib/csp.ts`
- `scripts/install/turnstile.py`, `scripts/install/questions.py`,
  `scripts/install/envgen.py` (the installer's two questions)
- `infrastructure/observability/prometheus/alerts-core.yml.template` (`core_auth`),
  `thresholds/*.env`, `tests/alerts_core_test.yml`, dashboard 09,
  `docs/runbooks/alerts/TurnstileUnavailable.md`
- Tests: `tests/unit/infrastructure/external/test_turnstile_client.py`,
  `tests/unit/domains/auth/test_turnstile_gate.py`,
  `tests/unit/core/config/test_turnstile_settings.py`, the web unit tests beside each
  module, `apps/web/e2e/smoke/turnstile-sign-in.spec.ts`,
  `scripts/install/tests/test_optional_turnstile.py`
