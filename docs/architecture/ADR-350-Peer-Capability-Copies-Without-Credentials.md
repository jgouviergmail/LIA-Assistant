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

Sender/time provenance belongs to settings displays. Native MCP and plugin
inventories explicitly exclude that UI field before validating their own closed
schemas; extending an HTTP response must not change an assistant contract.

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

## Amendment 2026-10-24 — whom it went to, and a share that is final for now

**Owner request.** Below the card's rule, a sender sees a folded « Shared with »
listing each recipient and when; a recipient sees « Shared by … on … »; and a
capability is never offered again to a connection that already received it.

**Decision.**

- A share is PUBLISHED once its receipt carries `transferred_at` — the instant
  its first component reached the recipient, the predicate that gives the
  recipient's copy its origin. `domains/shared/capability_shares.py` reads the
  sender's published shares through the registered metadata (the origin
  module's one-way rule) in ONE query per page, one line per recipient (the
  newest share), the recipient anonymised once their account is closed. The
  sender sees their own acts only, never the state of the recipient's copy.
- Whether a capability may be shared again is ONE function, `reshare_allowed`.
  The owner made a published share final « for now, without closing the door »:
  no index or constraint encodes it, the function receives the version about to
  be shared so a « newer version » rule would change it alone, and each listed
  recipient carries the server's verdict (`can_share_again`) so no client
  decides it.
- The policy is asked under the pair's lock at the preview AND at the send: two
  receipts previewed before either was sent must not both reach the recipient,
  and a share still installing counts as given, since the lock is released
  before the installation runs. Resuming a partial share sends the SAME
  receipt, which the policy excludes; a replayed preview key returns its
  receipt. A refusal is `409 peers_capability_already_shared`.
- `shared_with` is a settings field: the native MCP and plugin inventories
  exclude it like `shared_origin`, and their closed-contract tests name it.
