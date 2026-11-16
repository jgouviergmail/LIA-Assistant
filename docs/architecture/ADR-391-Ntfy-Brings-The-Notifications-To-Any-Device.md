# ADR-391 — ntfy brings the notifications to any device

**Status**: Accepted, 2026-11-16.
**Date**: 2026-11-16

**Builds on**:
[ADR-280](ADR-280-Complete-Capability-Control.md) — a switch removes the capability, read at the act;
[ADR-304](ADR-304-No-Transaction-Across-A-Network-Call.md) — nothing is held across a wait;
[ADR-221](ADR-221-Timeout-Par-Emplacement-Applique.md) — a request whose outcome is unknown is
never sent again;
[ADR-326](ADR-326-Linear-Flatteners-And-Pinned-Fetches.md) — a validated URL is reached on the address
the check saw;
[ADR-317](ADR-317-A-Log-Line-Carries-Facts-Never-The-Words.md) — logs carry facts, never words;
[ADR-263](ADR-263-Execution-Authority-Chain-And-Effect-Register.md) — a delivery is closed from an
explicit result.

## Context

Every push LIA sends went through Firebase Cloud Messaging. A self-hosted instance without a
Firebase project, a phone without Google services, and every person who would rather not route
their notifications through Google received nothing outside the open app — the reminder rang in
an empty room.

[ntfy](https://ntfy.sh) is an open-source publish/subscribe notification service: a server, and
free apps for Android (Play, F-Droid), iPhone and the web. An app subscribes to a TOPIC on a
server; whoever publishes to that topic reaches every app subscribed to it. The topic is the only
secret — ntfy's own documentation calls it a password. Servers are public (ntfy.sh) or
self-hosted.

Owner decisions of 2026-11-16 (wave 6, lot 28): the notifications stay MINIMAL by default — a
notice that LIA has something — with « full text » a choice the person makes per subscription;
LIA ships its own ntfy server, off by default, offered by the installer (lot 28c).

## Decision

1. **One door publishes to ntfy**, `push_to_ntfy` / `deliver`
   (`domains/notifications/ntfy_delivery.py`), and every road a push takes reaches it: the push
   door (`FCMNotificationService.send_to_user`: reminders, routines, proactive notices, sign-in
   alerts, exports, broken connectors), a proactive discussion's opening, an ingested message's
   durable outbox (one more destination, `ntfy`) and an administrator's broadcast. A publication a
   server accepted counts as delivered, like a push.
2. **Two roads, never mixed** (`infrastructure/external/ntfy_client.py`). The instance's server is
   the operator's configuration: reached as written (`NTFY_SERVER_URL`, it may be private), with
   the operator's token. A server a person typed is a stranger's address: refused at the form when
   no URL can be read from it or it names a private network (`server_url_refusal`: no space or
   control character — `urlsplit` silently drops a line break —, a port a socket can use, https,
   no credential in the address), then validated again and reached on the address the check saw
   before every publication (ADR-326). A redirect is never followed.
3. **What leaves is chosen by the person, and never more than the push shows.** A subscription is
   `minimal` by default: the notice of `notification_preview` (the generic sentence in the
   person's language). `full` carries the words the push shows. A notification kept private in LIA
   (`IN_APP_SENSITIVE`) always leaves as the notice.
4. **The topic is a password.** A topic LIA draws is `lia_` and 28 characters of `[A-Za-z0-9]`
   (about 166 bits); topics and tokens are stored encrypted; the settings routes are private input
   routes (a refusal never reflects what was typed, an answer is never cached); a log carries
   counts, outcomes and a server's host, never a topic, a token or a word.
5. **One closed vocabulary of outcomes** (`NtfyOutcome`), retried only when nothing could have
   reached a device (`RETRYABLE_OUTCOMES`: too many, server error, unreachable). A request that
   left unanswered is `no_answer`, never sent again (ADR-221). A server's `Retry-After` is read by
   ONE door shared with the Firebase outbox (`infrastructure/utils/retry_after.delivery_retry_delay`),
   bounded between a minute and a day: `DeliveryResult` refuses anything outside, so an unbounded
   delay was a `ValueError` waiting in the worker.
6. **A failure is said where it belongs.** Subscriptions that cannot be read raise
   `NtfyTargetsUnreadable` — nothing left, so the outbox tries again rather than filing « nobody
   subscribed » or « unknown »; outcomes that cannot be recorded never unsay what left; a topic that
   fails never unsays the devices (the push door and the discussion delivery log it and keep the
   Firebase result).
7. **Nothing is held across a wait** (ADR-304). Targets are read in a short session and leave it
   detached; publications run with no transaction open; the push door publishes BEFORE it writes
   the devices' status (a status write takes a row lock the caller's transaction keeps); a test
   publication ends the request's read first. A person's topics are published together — a push
   waits for one server's timeout at most, never the sum — and a broadcast bounds its burst
   (`NTFY_BROADCAST_CONCURRENCY`). Lists of accounts are bound `SQL_IN_CLAUSE_CHUNK` at a time: a
   broadcast reads a whole language group, and asyncpg refuses more than 32 767 bound values.
8. **A capability like the others** (ADR-280): `PlatformCapability.NTFY` (family « reach »),
   `NTFY_ENABLED` its ceiling, the operator's switch read at the act. Switched off, the routes
   refuse and the door publishes nothing; the subscriptions stay. The public demonstrator runs
   with ntfy off: a stranger must not make it publish to a server of their choosing.
9. **The settings** (`/notifications/ntfy`): a per-account ceiling counted and written under one
   advisory lock; refusals named by a stable code (`ntfy_errors`, `detail.code`) the web
   translates (`ntfy-labels.ts`, held equal by `test_ntfy_web_vocabulary.py`); a subscription
   whose secret no longer decrypts is still listed, without its topic, so it can be removed; a test
   publication reaches that one subscription, paused or not, within a per-account limit; the QR
   code a phone scans is drawn on demand by the one QR door (`infrastructure/utils/qr_code.py`,
   shared with the TOTP enrolment) from the `ntfy://` link — written only for a server at its
   root, the app reads nothing else.
10. **Measured, not assumed** (ntfy 2.37.2, a throwaway server under the access policy of lot 28c):
    a message of 4 096 bytes or more becomes an attachment — refused when attachments are off, a
    file instead of words when they are on — so a message stays under it
    (`NTFY_MESSAGE_MAX_BYTES = 4095`); a title over 1 024 bytes is refused. LIA's token publishes
    to `lia_*` and nowhere else; an anonymous client reads `lia_*` and publishes nowhere.
11. **The instance's own server ships off, and the installer offers it** (lot 28c). The `ntfy`
    service of both compose files, behind the `ntfy` profile, pinned by digest, is declared by
    variables alone: `deny-all`, the `lia` account writing `lia_*` (the backend's
    `NTFY_TOPIC_PREFIX`), everyone reading `lia_*`, no login, no sign-up. **LIA's account there has
    no password**: its hash is random characters in bcrypt's shape (`NTFY_ACCOUNT_HASH`), which no
    password matches, so its token is its only key — the installer is stdlib-only and has no
    bcrypt, and a start script hashing a password would be one more moving part for a password
    nobody uses. The container receives its own variables alone — never LIA's `.env` — and runs
    read-only with no capability. The installer asks `ntfy_server` (`no`), then a name of its own
    behind a proxy (ntfy serves no sub-path; a name the proxy already serves is refused,
    `Question.distinct_from`) and whether iPhones are woken through ntfy.sh (`no`: a privacy
    decision, as `PUSH_RELAY_URL` has no default, ADR-246); it generates the token and the hash
    once and keeps them, replacing them only when the server could not start on them. Measured on
    the pinned image: no password opens the account, a replaced token stops working at the next
    start, ntfy's default visitor burst (60, then one every 5 s) refused a broadcast where the
    service's (300, then one a second) took 150 at once, about 17 MiB.

The per-account rate limiter moved beside the per-IP one
(`infrastructure/rate_limiting/user_limiter.py`): the settings live in the `notifications` domain,
which the `auth` domain imports, and limiting them from `auth` was a cycle. Its Redis key and log
events are unchanged; `domains/auth/dependencies` re-exports it for its existing callers.

## Consequences

- A person reaches LIA's notifications on any device, with or without Google services, on the
  instance's server or on one they trust.
- The first notification of a public server's day is the operator's concern: ntfy.sh limits what
  an anonymous visitor publishes per day, and every subscription on it without a token counts
  against the instance's address. The instance's own server (lot 28c) is the answer.
- On an iPhone, a self-hosted server delivers instantly only when it lets ntfy.sh wake the phone
  (`NTFY_UPSTREAM_BASE_URL`): ntfy.sh then receives each message's id and a hash of its topic's
  address, never its text; without it, ntfy's documentation warns that delivery can take hours
  (FAQ).
- An operator who answers `yes` runs one more small service and, behind a proxy, routes one more
  name to it; a LAN install publishes one more port (`2586`).

## Enforced by

`test_ntfy_client.py`, `test_ntfy_publication.py`, `test_ntfy_delivery.py`, `test_ntfy_router.py`,
`test_push_door_reaches_ntfy.py`, `test_delivery_reaches_ntfy.py`, `test_sms_ntfy_destination.py`,
`test_ntfy_web_vocabulary.py`, `test_retry_after.py`, `test_qr_code.py`; on PostgreSQL,
`test_ntfy_subscriptions_db.py` (the ceiling under two simultaneous requests, the table's checks,
a language group past the driver's bound, an unreadable row that stays removable); the capability
tables (`test_capability_coverage.py`, `test_capability_route_wiring.py`, the route table), the
demonstrator's exposed routes, the domain cycle and complexity ratchets; on the web,
`useNtfySubscriptions.application.test.tsx`, `NtfySettings.test.tsx`, `ntfy-labels.test.ts`.
The instance's server: `test_self_host_compose_contract.py` (the service's access policy and
hardening, its own variables alone), `test_installer_wizard_backend_alignment.py` (what the
installer writes is what the API reads), the installer's tests (`scripts/install/tests`:
questions, answers, state, environment, compose, report) and its compose matrix.

## Alternatives rejected

- **Publishing by URL path** (`POST /<topic>`): the topic — a password — would sit in every proxy's
  access log. JSON to the server's root carries it in the body.
- **Retrying inside the client**: a publication that left unanswered may have been shown; only the
  durable outbox, reading the closed outcome, decides a retry.
- **Fire-and-forget publications**: a publication's acceptance is what counts it as delivered; a
  door that does not wait cannot say so.
- **A password hashed at the server's start** (prototyped: a shell entrypoint piping a generated
  password to `ntfy user hash`): it worked, but it parses a CLI's output, overrides the image's
  entrypoint and keeps a password nobody uses. The password-less account is declarative.
- **Relaying iPhones through ntfy.sh by default**: it tells a third party when each notification
  leaves; the operator decides.
