# ADR-357 — Phone ingestion and personal SMS

**Status:** Accepted — software integration; physical iPhone/FCM acceptance is separate.
**Date:** 2026-10-20
**Scope:** Scoped phone ingestion, SMS archive, assistant reads and private notifications.

## Context

iPhone Shortcuts already sends health samples to LIA. SMS needs the same accessible HTTP entry point with different semantics: an immutable personal message, replay-safe receipt, sensitive-content exclusion, per-device delivery and explicit assistant consent. Future phone sources should reuse the ingestion boundary without becoming untyped blobs or sharing write authority.

## Decision

- Keep the generic [ingestion foundation](../../apps/api/src/domains/ingestion/) separate from the [SMS domain](../../apps/api/src/domains/sms/). Resource policies declare credential prefix/scope and admission contracts; each resource keeps its strict schema and persistence. Existing health credentials remain compatible.
- Authenticate a write-only device credential, then recheck owner/source/token authority under an owner-first transaction fence. Store the encrypted message, blind lexical index, content-free receipt and delivery outbox atomically.
- Use a tenant key wrapped at rest for HMAC equality/index/receipt keys. Credential rotation does not rotate this material. Tombstones preserve replay decisions after message erasure.
- Reject identifiable access secrets deterministically before persistence. This is a bounded heuristic, not a general classifier of private information; medical/banking messages remain archive content unless an excluded access secret is recognized.
- Separate ingestion, assistant consent and immediate reception push. The assistant starts without SMS access. Personal archive reads, manual deletion and exports have their own authenticated contracts.
- Mount the shared read-only archive below statistics in the SMS settings pane, in a disclosure open on arrival. Preserve existing notification and card links through a redirect from `/dashboard/sms` to `/dashboard/settings?section=sms`, carrying the focused message identifier.
- Default to sender threads and expose single-message, complete-sender and account-civil-day erasure through the existing scoped approval contract. Keep source time provenance in data/model contracts without a repeated capture-time disclaimer in the UI. Place relationship SMS immediately above exchanged provider emails.
- A later explicit UI refinement removes the misleading archived-state wording. Clicking a single message's red trash icon beneath its date prepares and confirms only that exact ID without a dialog; the client rejects broader scope, a different ID or an expired proposal. The same server command writer and receipts remain authoritative. Bulk deletion and agent mutations retain reviewed approval; no general unconfirmed mutation endpoint is added.
- Reuse server-enforced application approval for agent mutations, token management and archive deletion. Explicit settings toggles save one preference directly through the authenticated session, with the same owner lock, delivery cancellation and consent invalidation as agent commands. They do not create an approval draft. A raw credential is returned once, only to the originating authenticated browser; never through the model, a checkpoint or a notification.
- Use one live bounded projection across tools, relationship views and direct aggregations. Source proof, owner, revision and freshness are rechecked before model use and publication. Text is external evidence, never instructions; truncation and unknown read/receipt status are explicit.
- Keep home counts exact. The personal dashboard additionally displays bounded previews of the latest retained messages, configured by `BRIEFING_MAX_SMS_ITEMS`, with the Mails row primitive and direct links into SMS settings. This personal display does not grant assistant access: metadata-only aggregation and consent-gated model evidence remain separate projections. No SMS source cache or last-good fallback is used; publication revalidates source proof after awaited work, HTTP responses prohibit caching, and browser invalidation masks old previews until a fresh read succeeds. Invalidation also discards current and in-flight home text without an automatic paid regeneration.
- Reuse existing proactive calls, quotas, accounting and quiet windows. Only offered message IDs supporting a concrete useful fact may be consumed, after known successful delivery. A reception push is a separate immediate, content-free standing instruction.
- Any proactive model context containing SMS makes the result private to LIA, independently of model source attribution. Mask the push, suppress external chat-channel forwarding, exclude these archived notifications from Radio and future decision windows, and skip the continuity memory copy.
- Integrate the consented source explicitly in Radio's personal-source registry and the owner's phone/direct-Live domain registry. Radio receives bounded sensitive day facts with private source proof, rechecked at model and production boundaries; withdrawal yields nothing to air and preserves spent usage. The spoken native adapter keeps the SMS catalogue name/capability while translating flat filters to the existing strict read/search requests. Both integrations retain their existing quotas, token projection, accounting and surface exclusions; neither adds a mutation tool or reuses private proactive notification copies.
- Personal export streams readable messages in bounded partitions. Hosted exports are invalidated on erasure. Account purge covers every new root. Historical conversations, explicit memories and already downloaded archives have separate retention.

## Consequences

A sender is resolved from a unique complete contact match, then relationships, else the original sender. Ambiguous or incomplete evidence stays raw. Time is stored in UTC and displayed in the account timezone. A source timestamp marked captured/unknown never becomes a claim of exact receipt time.

Transport acknowledgement is not physical exactly-once display. An unknown result is terminal; automatic replay could duplicate a notice. The iOS native relay forwards a content-free wake, not an SMS-specific native banner or deep link. Restores keep workers stopped until current revocations, erasures and tombstones are reconciled.

A new phone resource means a reviewed policy/schema/source writer and explicit integration in the relevant user/assistant registries. It does not inherit assistant, Radio, phone, peer or routine permissions implicitly.

## Amendment 2026-10-21 — the in-app notice names its sender

Owner request: the in-app "new SMS" notice shows the sender in bold and the message. The signal stays content-free on every wire (Redis, FCM data, the iOS wake) and the OS push keeps its generic sentence. The open application reads the message through the session-only archive read (`GET /sms/{id}`, `no-store`) when the signal arrives — the read that opening the focused message already makes — and announces the arrival alone when that read fails or exceeds its bound. Nothing new is stored, logged or forwarded.

## References

- [Technical reference](../technical/SMS_INGESTION.md)
- [iPhone Shortcuts guide](../guides/GUIDE_IPHONE_SHORTCUTS_SMS.md)
- [Recovery runbook](../runbooks/SMS_INGESTION_RECOVERY.md)
- [Qualification matrix](../technical/SMS_QUALIFICATION.md)
- [Approved design](../superpowers/specs/2026-10-19-phone-ingestion-sms-design.md)
