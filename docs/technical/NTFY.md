# ntfy notifications

**Decision**: [ADR-391](../architecture/ADR-391-Ntfy-Brings-The-Notifications-To-Any-Device.md).
**Flows around it**: [NOTIFICATIONS_FLOW.md](NOTIFICATIONS_FLOW.md).

LIA's notifications reach the free [ntfy](https://ntfy.sh) app (Android, iPhone, web) as well as
Firebase devices. A person subscribes the app to a TOPIC on a server; LIA publishes every
notification of that person to each of their subscriptions. The topic is the only secret.

## Where a publication starts

Every road a push takes reaches one door, `push_to_ntfy` / `deliver`
(`apps/api/src/domains/notifications/ntfy_delivery.py`):

| Road | Caller | What the person receives | On failure |
|---|---|---|---|
| Push door (reminders, routines, proactive notices, sign-in alerts, exports, broken connectors) | `FCMNotificationService.send_to_user` | What the push shows; the click opens the push's `url` | Logged (`ntfy_push_failed`); the Firebase result stands |
| Proactive discussion opening | `infrastructure/proactive/discussion_delivery._publish_to_ntfy` | What the push shows; opens the discussion | Logged; the opening reads as delivered only if a device or a topic accepted it |
| Ingested message (SMS) | Durable outbox, destination `ntfy` (`ingestion_transport`) | The generic notice; opens the message | `NtfyBatch.retryable` decides; unreadable subscriptions → `RETRYABLE` |
| Administrator broadcast | `BroadcastService` | The translated words, by language group | Counted in `broadcast_ntfy_sent` |

## Two roads

| | Instance server | A person's server |
|---|---|---|
| Address | `NTFY_SERVER_URL`, as written (may be private, e.g. `http://ntfy:80`) | Typed by the person, https only |
| Checked | Trusted (the operator's configuration) | At the form (`server_url_refusal`) and before every publication (`validate_url` + `pinned_stream`, ADR-326) |
| Token | `NTFY_PUBLISH_TOKEN` (the operator's) | The person's, optional, encrypted |
| Client method | `NtfyClient.publish_trusted` | `NtfyClient.publish_checked` |

A publication is JSON posted to the server's root (the topic in the body, never in a URL a proxy
logs). Redirects are never followed.

## Content

| Choice | What leaves | Default |
|---|---|---|
| `minimal` | The generic notice of `notification_preview` (`IN_APP_SENSITIVE`), in the person's language | Yes (owner decision 2026-11-16) |
| `full` | The push's title and words | Per subscription |

A notification kept private in LIA always leaves as the notice. Measured limits (ntfy 2.37.2):
a message of 4 096 bytes or more becomes an attachment — so a message is cut on a character under
`NTFY_MESSAGE_MAX_BYTES` (4 095) — and a title over `NTFY_TITLE_MAX_BYTES` (1 024) is refused.

## Outcomes

`NtfyOutcome` is closed: `sent`, `auth_refused`, `not_found`, `too_large`, `rate_limited`,
`refused`, `server_error`, `unreachable`, `no_answer`, `url_refused`, `not_configured`. Only
`rate_limited`, `server_error` and `unreachable` may be retried (nothing reached a device); a
request that left unanswered is `no_answer` and is never sent again (ADR-221). A `Retry-After` is
read by `infrastructure/utils/retry_after.delivery_retry_delay` (shared with the Firebase outbox),
bounded between `DELIVERY_RETRY_AFTER_DEFAULT_SECONDS` and `DELIVERY_RETRY_AFTER_MAX_SECONDS`.

Each outcome is written on the subscription (`last_sent_at`, `last_error_code`, `last_error_at`)
in a session of its own after the publications; a refusal never deactivates a subscription.

## Settings API

All routes are guarded by the `ntfy` capability and are private input routes (no echo of what was
typed in a refusal, `Cache-Control: no-store`).

| Route | Purpose |
|---|---|
| `GET /notifications/ntfy` | The instance server, the rules (`custom_servers_enabled`, `max_subscriptions`) and the subscriptions |
| `POST /notifications/ntfy` | Subscribe: `{"server": "instance"}`, or `{"server": "custom", "server_url", "topic"?, "token"?}`, with `content` |
| `PATCH /notifications/ntfy/{id}` | Change `content` or `is_active` |
| `DELETE /notifications/ntfy/{id}` | Remove |
| `POST /notifications/ntfy/{id}/test` | Publish a test to that subscription (paused or not), per-account limit `RATE_LIMIT_NTFY_TEST_PER_MINUTE` |
| `GET /notifications/ntfy/{id}/qr` | The QR code (PNG data URI) of the `ntfy://` link, drawn on demand |

Refusals carry `detail.code` (`apps/api/src/domains/notifications/ntfy_errors.py`), translated by
the web (`apps/web/src/components/settings/ntfy/ntfy-labels.ts`); the ceiling's refusal carries
`max`. A subscription whose secrets no longer decrypt is listed without its topic so it can be
removed.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `NTFY_ENABLED` | `true` | Deployment ceiling of the `ntfy` capability |
| `NTFY_SERVER_URL` | empty | Where LIA publishes on the instance's own server; empty: none |
| `NTFY_PUBLIC_URL` | empty | The instance server as people's apps reach it; empty: `NTFY_SERVER_URL` |
| `NTFY_PUBLISH_TOKEN` | empty | LIA's access token on the instance server (`tk_…`) |
| `NTFY_CUSTOM_SERVERS_ENABLED` | `true` | Let a person name a public server of their own choosing |
| `NTFY_MAX_SUBSCRIPTIONS_PER_USER` | `3` | Subscriptions one account may hold |
| `NTFY_TIMEOUT_SECONDS` | `10` | Timeout of one publication |

Read by the `ntfy` service alone, never by the API (see below):

| Variable | Default | Meaning |
|---|---|---|
| `NTFY_ACCOUNT_HASH` | empty | 53 characters of `[./A-Za-z0-9]` completing `$2a$10$`: the hash of LIA's account on the instance server |
| `NTFY_BEHIND_PROXY` | `false` | `true` behind a proxy: the server reads the client's address from `X-Forwarded-For` |
| `NTFY_UPSTREAM_BASE_URL` | empty | `https://ntfy.sh` to wake iPhones at once (see « iPhone ») |

The demonstrator runs with `NTFY_ENABLED=false`.

## The instance's own server

LIA ships the server as the `ntfy` service of `docker-compose.prod.yml` and
`docker-compose.dev.yml`, behind the `ntfy` profile, **off** unless the operator asks (owner
decision 2026-11-16). The installer asks `ntfy_server` (default `no`), then `ntfy_domain` behind a
proxy and `ntfy_ios_relay` (default `no`), and writes every value above
(`scripts/install/ntfy.py`, `envgen._ntfy_environment`).

- **Who may do what.** `NTFY_AUTH_DEFAULT_ACCESS=deny-all`; the `lia` account writes `lia_*` only;
  everyone reads `lia_*` only, so the topic's random name is the password; no login, no sign-up.
  The ACL's prefix is the backend's `NTFY_TOPIC_PREFIX`, held equal by
  `test_self_host_compose_contract.py`.
- **LIA's account has no password.** Its hash is random characters in bcrypt's shape
  (`NTFY_ACCOUNT_HASH`), which no password matches — the wizard is stdlib-only, without bcrypt —
  so `NTFY_PUBLISH_TOKEN` (`tk_` + 29 of `[a-z0-9]`) is its only key. Both are generated when the
  server first runs, kept across reconfigurations and while it is off, and replaced only when
  the server could not start on them. Measured on the pinned image: no password opens the
  account; a replaced token stops working at the next start.
- **Nothing of LIA's reaches it.** No `env_file`: the container receives its own `NTFY_*`
  variables alone (guarded). It runs `read_only`, with `cap_drop: ALL` and
  `no-new-privileges`; the account file and the message cache (12 h) live in the `ntfy_data`
  volume. About 17 MiB after a burst of 150 publications.
- **A broadcast is absorbed.** A broadcast publishes once per subscription: at ntfy's default
  visitor limits (a burst of 60, then one every 5 s) it met `429`s; the service runs with a
  burst of 300 and one more a second, which took 150 at concurrency 8 without a refusal.

| Exposure | Where LIA publishes | Where phones subscribe | How it is published |
|---|---|---|---|
| `lan` | `http://ntfy:80` | `http://<host>:2586` | The installer's override publishes `2586` on every interface |
| `proxy` | `http://ntfy:80` | `https://<ntfy_domain>` | The operator's proxy routes the name to `127.0.0.1:2586`, unbuffered |
| `caddy` | `http://ntfy:80` | `https://<ntfy_domain>` | `infrastructure/caddy/Caddyfile.ntfy.template` adds the site |

ntfy serves no sub-path, so the server takes a name of its own, which the installer refuses when
it repeats the web or API domain (`Question.distinct_from`): one proxy cannot serve a name twice.
Proven end to end on 2026-11-16: the installer's `.env`, the real compose file in an isolated
project, LIA's own client, a burst, a reconfiguration. At every run, the compose matrix
(`task test:install:compose-matrix`) validates every exposure × mode × profile.

## Security

- Topics LIA draws are `lia_` + 28 characters of `[A-Za-z0-9]` (about 166 bits); topics and tokens
  are stored encrypted (`encrypt_data`); neither ever reaches a log.
- A person's server: https, no credential, query or fragment in the address, no private network,
  checked again on the address it resolves to before each publication.
- On the instance server, LIA's token publishes to `lia_*` only and everyone reads `lia_*` only
  (verified against ntfy 2.37.2): knowing the topic is what grants reading.

## Observability

`ntfy_publications_total{server_kind, outcome}`, on the « ntfy » row of the Channels dashboard
(`12-channels.json`). Logs: `ntfy_delivered` (counts), `ntfy_publication_unanswered`,
`ntfy_server_refused` (host only), `ntfy_outcomes_unrecorded`, `ntfy_subscription_unreadable`.

## iPhone

Apple wakes an app instantly only through its own push service, which the iOS ntfy app receives
through ntfy.sh. A self-hosted server delivers instantly to an iPhone only when it is allowed to
ask ntfy.sh to wake the phone (`NTFY_UPSTREAM_BASE_URL`, ntfy's `upstream-base-url`): ntfy.sh then
receives each message's id and the SHA-256 of its topic's address, never its text. Otherwise
notifications still arrive, but ntfy's documentation warns that delivery can take hours. A
privacy decision, so the operator's: the installer asks, `no` by default, as `PUSH_RELAY_URL` has
no default (ADR-246). Android is not concerned.
