# Google Push Channels (lot H, 2026-08)

Real-time freshness for Google data: instead of waiting for a cache TTL to
elapse, Google notifies LIA when the watched resource changes and the matching
caches are invalidated immediately. **Polling remains the fallback**: with the
flags off (the default) or a stale channel, behavior is exactly the pre-lot-H
one — staleness bounded by cache TTLs.

## Architecture

- **Registry**: `webhook_channels` table (`src/domains/push_channels/models.py`)
  — one row per live watch (owner, provider, target, channel secrets, expiry).
- **Webhook**: `POST /api/v1/webhooks/google` (X-Goog-* channel notifications,
  phase 1) and `POST /api/v1/webhooks/google/pubsub` (Gmail Pub/Sub envelope,
  phase 2). Both always answer 200; authentication is internal (channel token /
  platform push token, constant-time) — an unknown or forged notification is
  silently ignored, never revealed.
- **Sync job**: `push_channel_sync` (leader-elected, every
  `PUSH_SYNC_INTERVAL_MINUTES`) ensures a channel per active Google connector
  and renews channels expiring within `PUSH_RENEWAL_MARGIN_SECONDS`.
- **Invalidation** (`cache_invalidation.py`): calendar → briefing `agenda`
  section; drive → briefing `documents`; gmail → briefing `mails` + per-user
  Gmail search caches. Debounced per channel
  (`PUSH_NOTIFICATION_DEBOUNCE_SECONDS`) against notification storms.
- **Idempotency**: Pub/Sub deliveries are at-least-once and unordered — the
  per-channel `last_history_id` ledger deduplicates; channel notifications are
  idempotent by nature (invalidation only).

## Phase 1 — Calendar + Drive (`PUSH_CHANNELS_ENABLED`)

Uses `events.watch` (primary calendar) and `changes.watch` (whole Drive) with
the user's existing OAuth tokens — **no new scope, no user action**.

Prerequisite (verified 2026-08-21): **Domain verification is no longer
required** — Google's API Console help now states it explicitly, and the
Domain verification console page is being retired. The only remaining
requirement is the webhook URL itself:

1. `PUSH_WEBHOOK_URL=https://<domain>/api/v1/webhooks/google` must be
   reachable over HTTPS with a **valid (non self-signed) certificate** — the
   Cloudflare tunnel provides this natively. Cloudflare trap: the free
   wildcard certificate covers ONE subdomain label only — keep the webhook
   host at one label under the zone.
2. Set `PUSH_CHANNELS_ENABLED=true`; the sync job opens the channels at its
   next tick.

If Google still rejects a `watch` call for any reason, the sync job logs the
failure per user (`push_sync_user_failed`) and polling continues unaffected.

## Phase 2 — Gmail (`GMAIL_PUSH_ENABLED`)

Uses `users.watch` with the existing Gmail scopes (no re-consent). Gmail does
not push directly: it publishes to a **Pub/Sub topic**, which pushes to our
endpoint. One-time platform-admin setup:

```bash
PROJECT=<gcp-project-id>
TOKEN=$(openssl rand -hex 32)

gcloud services enable pubsub.googleapis.com --project=$PROJECT
gcloud pubsub topics create lia-gmail-push --project=$PROJECT
# Gmail publishes through this Google-owned service account:
gcloud pubsub topics add-iam-policy-binding lia-gmail-push --project=$PROJECT \
  --member=serviceAccount:gmail-api-push@system.gserviceaccount.com \
  --role=roles/pubsub.publisher
gcloud pubsub subscriptions create lia-gmail-push-sub --project=$PROJECT \
  --topic=lia-gmail-push \
  --push-endpoint="https://<domain>/api/v1/webhooks/google/pubsub?token=$TOKEN"
echo "GMAIL_PUBSUB_TOPIC=projects/$PROJECT/topics/lia-gmail-push"
echo "GMAIL_PUBSUB_PUSH_TOKEN=$TOKEN"
```

Then set both variables plus `GMAIL_PUSH_ENABLED=true`. Gmail watches expire
after 7 days regardless of the requested TTL — the sync job re-issues them.
The heartbeat's `history.list` delta (lot G) stays the actual reader; push
only makes the caches fresh sooner.

## Consumers of a notification (ADR-261)

A processed notification has three consumers, in this order:

1. **Cache invalidation** (`cache_invalidation.py`) — the matching briefing
   section, the Gmail search caches, and for Calendar the cached departure
   advice (`heartbeat:departure:{user}:*`). This is the only consumer the
   lot H shipped with; measured on 2026-09-03 it was the only one running
   (802 Gmail notifications in 15 days, none of them followed by anything
   the user could notice).
2. **Heartbeat wake** (`wake.py`, `PUSH_WAKE_ENABLED`, OFF by default) — the
   user is queued (`heartbeat:wake:pending` + one payload per
   `(user, provider)`, `SET NX`: a storm is one wake) and a short
   leader-elected sweep (`infrastructure/scheduler/heartbeat_wake_sweep.py`)
   serves the queue under the FULL eligibility checker: staleness, wake
   cooldown, the user's source preference, the fresh delta (Gmail
   `history.list` previewed from the heartbeat's own anchor — never consumed
   unless the wake is served), the deterministic pre-filter
   (`wake_filter.py`, rules published as `PUSH_WAKE_*`), then the heartbeat
   task for that user only. The audit row carries `trigger = push`.
3. **Drive targeted reindex** (`rag_spaces/drive_ingest.py`) — the sweep
   drains `changes.list` from the channel's `page_token`, keeps the files
   directly under a linked folder, ingests the changed ones and removes the
   trashed ones under the manual sync's lock, then advances the token.

Metrics: `push_wakes_total{provider,outcome}`, `push_wake_latency_seconds`,
`rag_drive_push_reindex_total{outcome}` (dashboards 13 and 18).

## Edge cases handled

| Case | Behavior |
|------|----------|
| Duplicate / out-of-order Pub/Sub delivery | `last_history_id` ledger → `ignored_stale` |
| Notification storm | Redis debounce per channel (SET NX EX) |
| `sync` handshake on channel creation | Acknowledged, no invalidation, no wake |
| Notification storm on one channel | Debounced per channel; at most one queued wake per (user, provider) |
| Wake for a source the user refused in the heartbeat settings | Dropped (`source_disabled`), never a notification |
| Wake refused by the pre-filter | The Gmail delta is left untouched for the next tick (previewed, not consumed) |
| Drive change outside every linked folder | `no_linked_folder`, token still advanced |
| Linked folder already syncing | `locked`, left to the running sync |
| Channel expired during downtime | Sync job recreates at next tick (resync on schedule) |
| Forged notification (found URL) | Token mismatch → ignored, still 200 |
| Redis down | Invalidation/debounce best-effort — notification path never fails |
| Account deletion | `webhook_channels` purged (tokens are secret material); Google-side watches expire on their own TTL |

## Validation status

Unit-tested end to end (parsers, service outcomes, payload contracts, sync
sweep, router 200-contract). **Staging validation through the Cloudflare
tunnel is the remaining gate before enabling in production** (spec §6, risk 3).
