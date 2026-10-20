# Phone notice with an uncertain result

The archive commit is independent of notification transport. `unknown` means an
attempt started without an authoritative acknowledgement. It is terminal and is
never automatically retried: the device may already have received it.

Inspect `ingestion_deliveries` by state, attempt and fence and the linked effect
register. Do not print device credentials, sender identifiers or message bodies.
Check scheduler leadership, database connectivity, Redis and Firebase/relay health.
The dashboard `phone-ingestion-sms` separates SSE acceptance and device acceptance.
SDK and provider retries mean physical exactly-once delivery cannot be guaranteed.
A stable occurrence is used for platform collapse and client deduplication.

Never change a terminal row back to pending. Restore operations keep workers off
until credentials, erasures, receipt tombstones and delivery states are reconciled;
an old backup can revive state that a current account has revoked or erased.
