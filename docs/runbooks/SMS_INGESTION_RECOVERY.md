# SMS ingestion: recovery, key rewrap and restore

[Technical ownership](../technical/SMS_INGESTION.md) ·
[Unknown delivery](alerts/PhoneIngestionDeliveryUncertain.md)

## Triage without exposing personal content

Distinguish an ingress failure, an archived message awaiting delivery, a device transport failure, a source-consent refusal and a broad-search refusal. The archive transaction does not depend on successful notification display.

Use the phone-ingestion observability dashboard and bounded error codes. Inspect counts, status, attempt, owner/source identifiers and fences in an appropriately restricted operator session. Never dump tokens, senders, bodies, search text, device credentials or complete provider errors into incident logs.

Check the effective SMS capability, person preferences, source/token status, database and Redis admission, scheduler leadership and Firebase/relay availability. Limits and timeouts are defined in [IngestionSettings](../../apps/api/src/core/config/ingestion.py); changing one is an explicit capacity decision, not a response to an unidentified failure.

## Retry and uncertain transport

A client retry preserves source, event UUID and canonical payload. A missing response can follow a successful commit. A conflict must not be bypassed with a new event UUID.

Only explicitly retryable outcomes buy another attempt. A lease that expires after transmission started becomes unknown. Never reset sent, cancelled, permanent or unknown rows to pending: the person may already have received the notice. Consult the linked effect register as well as the outbox.

No acknowledgement proves physical exactly-once display. Platform collapse/client deduplication are bounded safeguards. The iOS relay wakes the app without forwarding SMS content, title, route or collapse metadata.

## Tenant-key rewrap and blind-index repair

The tenant HMAC key is not the ingestion token or the wrapping key. Rewrapping encryption must preserve the same decrypted tenant-key bytes. Back up and restrict the wrapping key according to the platform key procedure. Never regenerate missing tenant material for an archive that already has receipts or rows.

Changing tenant material breaks token-independent receipt identity, sender equality and the blind index. A credential rotation does not repair it. Diagnose the wrapping-key/source mismatch first and keep ingestion stopped if authority cannot be established.

Index rebuilding uses [the staged, owner-fenced builder](../../apps/api/src/domains/sms/search_index.py). It reads bounded partitions, then revalidates the active owner, platform capability and stable tenant key under the owner lock. A second staging pass includes late arrivals; the replacement joins only currently retained messages, excluding any erased after the first pass. A failed rebuild keeps the prior valid index rather than publishing a partial replacement. Use the service through a reviewed operator entry point; there is no undocumented public rebuild endpoint.

Logical archive occupancy, PostgreSQL physical space and receipt occupancy are different budgets. Content erasure need not free replay-tombstone capacity. Do not delete receipts to work around a limit or silently re-enable a revoked source.

## Restoring a backup

1. Stop the API/scheduler processes that can ingest, generate proactive content or dispatch notices. Restore into an isolated environment with external transports disabled.
2. Restore the database together with the required wrapping material, then apply the project's normal migration procedure.
3. Reconcile the authoritative post-backup account erasures, SMS erasures, revoked credentials, source states, extraction revisions and hosted-export invalidations. A restored backup alone cannot describe decisions made after it.
4. Preserve replay tombstones and the stable tenant key. Verify that an erased account/source cannot authenticate and that cancelled/erased messages cannot be dispatched or downloaded.
5. Treat restored unsettled deliveries as unreconciled. Do not automatically replay the backup's pending/sending rows; settle them through reviewed recovery with explicit duplicate-risk assessment.
6. Rebuild only a damaged derived index from the reconciled retained messages, under the same owner and publication checks.
7. Replay synthetic local probes for duplicate receipts, withdrawal, expired leases and export invalidation before enabling ingestion and then transports in a controlled order.

If the current erasure/revocation inventory is incomplete, keep workers stopped. This runbook deliberately does not claim automatic recovery of facts unavailable from an old backup.

## Verification

[Qualification matrix](../technical/SMS_QUALIFICATION.md) identifies the migration, concurrent-session, delivery, rebuild, export and browser tests. Hardware permissions, iOS background execution and real FCM display require device acceptance; mocked transport success is not that acceptance.
