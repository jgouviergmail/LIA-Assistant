# Peer Connections — Lot 3 (Chat Lifecycle Integration) Implementation Plan

> INLINE execution (no subagents). NEVER commit — checkpoints log the proposed message.

**Goal:** Every connection-lifecycle event reaches the affected users' chats through their
assistant: incoming request (with the provenance-framed note + a one-click path), request
outcome for the requester, and removal notified to BOTH sides (explicit spec requirement).

**Sequencing decision (recorded):** bodies link to the settings deep link
(`{frontend_url}/dashboard/settings?section=peer-connections`, connectors-precedent — no
locale segment, the middleware resolves it). The `?intent=` accept/refuse upgrade ships
with the agents lot (Lot 6): an intent sentence without tools to execute it would strand
the user. Spec §6 stays the end-state; this lot is the delivery mechanism.

**Canonical models:** `NotificationDispatcher` (archive-first, `notification.py:231`),
`_send_approval_notification` (`scheduled_action_executor.py:90`), `ProactiveMessages`
(`core/i18n_proactive.py` — titles + body templates ×6, `zh-CN` canonical).

## Tasks

1. **i18n** — `ProactiveMessages`: `_TITLES` += `peer_request`, `peer_connection`;
   body factories ×6: `peer_request_body(requester_name, context_message, url, language)`
   (note quoted as plain text — provenance framing), `peer_accepted_body(peer_name, url,
   language)`, `peer_declined_body(peer_name, language)` (neutral, no reason),
   `peer_removed_body(peer_name, language)`. TDD: completeness test — every factory returns
   non-empty, distinct-per-language strings for the 6 codes, and the request body embeds
   the URL and the (escaped) note.
2. **Dispatch module** — `domains/peers/notifications.py`:
   `dispatch_peer_events(events, db)` — per `PeerEvent.kind`: `request_created` →
   addressee (affected minus actor); `request_accepted`/`request_declined` → the other
   side (minus actor); `connection_removed` → BOTH (each in their own language, actor
   included — spec: both assistants announce it). ORM `User` rows via `db.get` (NEVER
   `get_user_by_id` — UserProfile trap); skip inactive/deleted recipients; each dispatch
   in its own try/except (`logger.warning`, ids only) — best-effort by contract, one
   failed recipient never blocks the others. TDD: recipients per kind, language per
   recipient, actor exclusion, removed→both, failure isolation.
3. **Router wiring** — after `db.commit()` in create_request / respond_to_request /
   remove_connection: `await dispatch_peer_events(service.pending_events, db)` wrapped
   best-effort (a dispatch failure must never fail the API call that already committed).
   TDD: router tests assert dispatch called with the service events after commit; failure
   swallowed.
4. **Gate** — peers suites + `task test:backend:unit:fast` + `task lint:backend`;
   evidence + proposed commit `feat(peers): chat lifecycle notifications (Lot 3)`.
