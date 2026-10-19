# ADR-350: Peer capability copies without credentials

**Status:** Accepted

**Date:** 2026-10-19

## Context

An accepted connection should be able to share a useful skill, MCP server or
plugin. A live reference to the sender's installation would share ownership,
credentials and future changes accidentally. Re-fetching an upstream package
after confirmation could also install bytes the sender never reviewed.

## Decision

Use the existing peer relationship and native installation paths. The server
creates a sanitized, immutable package and confirmation digest. Confirmation
checks the relationship, blocks, account state, ownership and quotas again.
The recipient receives an independently owned copy, committed disabled,
with sender/time provenance and ordinary editing, activation and deletion.
Credentials, OAuth grants, network exemptions and HITL overrides never transfer.

Delivery is resumable through durable claims, leases, fencing and receipts.
Retries reuse the confirmed package, preserve recipient changes and only resume
matching unfinished plugin children. Notification persistence follows the same
commit; live delivery happens afterwards. Snapshot retention is fixed rather
than extended on retry. Erasure anonymizes retained origin metadata.

The explicitly requested trust exception amends
[ADR-327](ADR-327-Skill-Library-And-Third-Party-Skills.md): after activation,
a peer skill uses the recipient-authored execution policy. Only server-written
provenance grants this treatment, including a plugin's skill child. A badge or
uploaded manifest cannot grant it. Connector permissions, action confirmations
and sandbox execution boundaries still apply. Ordinary third-party imports keep
their existing policy.

## Consequences and verification

Later changes or deletion at the sender do not update the received copy.
The recipient provides credentials and explicitly enables what was received.
Sharing executable instructions is a trust decision; disabled installation
provides a review point but does not prove the instructions harmless.

[The technical guide](../technical/PEER_CAPABILITY_TRANSFERS.md) describes the
contracts, recovery and retention. Real PostgreSQL/filesystem integration tests
exercise competing workers, cancellation, rollback, lost acknowledgement and
erasure; browser journeys cover the native settings on desktop and mobile.
