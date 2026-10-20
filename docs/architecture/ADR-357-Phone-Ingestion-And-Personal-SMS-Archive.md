# ADR-357 — Phone ingestion and a personal SMS archive

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
- Reuse server-enforced application approval for source mutations. A raw credential is returned once, only to the originating authenticated browser; never through the model, a checkpoint or a notification.
- Use one live bounded projection across tools, relationship views and direct aggregations. Source proof, owner, revision and freshness are rechecked before model use and publication. Text is external evidence, never instructions; truncation and unknown read/receipt status are explicit.
- Keep home counts exact and metadata-only; no SMS source cache or last-good fallback. Invalidation discards current and in-flight home text without an automatic paid regeneration.
- Reuse existing proactive calls, quotas, accounting and quiet windows. Only offered message IDs supporting a concrete useful fact may be consumed, after known successful delivery. A reception push is a separate immediate, content-free standing instruction.
- Any proactive model context containing SMS makes the result private to LIA, independently of model source attribution. Mask the push, suppress external chat-channel forwarding, exclude these archived notifications from Radio and future decision windows, and skip the continuity memory copy.
- Personal export streams readable messages in bounded partitions. Hosted exports are invalidated on erasure. Account purge covers every new root. Historical conversations, explicit memories and already downloaded archives have separate retention.

## Consequences

A sender is resolved from a unique complete contact match, then relationships, else the original sender. Ambiguous or incomplete evidence stays raw. Time is stored in UTC and displayed in the account timezone. A source timestamp marked captured/unknown never becomes a claim of exact receipt time.

Transport acknowledgement is not physical exactly-once display. An unknown result is terminal; automatic replay could duplicate a notice. The iOS native relay forwards a content-free wake, not an SMS-specific native banner or deep link. Restores keep workers stopped until current revocations, erasures and tombstones are reconciled.

A new phone resource means a reviewed policy/schema/source writer and explicit integration in the relevant user/assistant registries. It does not inherit assistant, Radio, phone, peer or routine permissions implicitly.

## References

- [Technical reference](../technical/SMS_INGESTION.md)
- [iPhone Shortcuts guide](../guides/GUIDE_IPHONE_SHORTCUTS_SMS.md)
- [Recovery runbook](../runbooks/SMS_INGESTION_RECOVERY.md)
- [Qualification matrix](../technical/SMS_QUALIFICATION.md)
- [Approved design](../superpowers/specs/2026-10-19-phone-ingestion-sms-design.md)
