# Recipient-owned skills, MCP servers and plugins shared by peers

From the existing settings cards, an owner selects an accepted, unblocked peer,
reviews a server-generated preview and explicitly confirms its digest. The
recipient receives an independent owned copy, durably **disabled** before the
first successful commit. Its settings badge names the sender and sharing time.
The existing editor, activation, credentials and deletion controls manage it.

Under each card's rule, the sender also sees a folded **Shared with** list —
each recipient once, with the date of the newest share and « incomplete » while
part of it is missing — and the share dialog never offers those recipients
again: a published share is final for now, decided by one server function
(`reshare_allowed` in
[the shares projection](../../apps/api/src/domains/shared/capability_shares.py)),
asked under the pair's lock at the preview and at the send (`409
peers_capability_already_shared`). Resuming a partial share sends the same
receipt and is never refused.

The confirmed send ends on a popup for the sender: what was shared with whom
when the copy is installed (the dialog then closes), why it did not complete
otherwise (the dialog stays open on its state and retry). The recipient's chat
line names the sender, the kind (skill, MCP server or plugin) and the title —
the sender as the badge would show them, so an account gone since reads "a
user" ([wording](../../apps/api/src/core/i18n_capability_sharing.py)).

The implementation is in [the peers domain](../../apps/api/src/domains/peers/capability_flow.py).
The closed [contracts](../../apps/api/src/domains/peers/capability_contracts.py)
define preview, receipt, installation and recoverable partial states. The
sender's package is sanitized once and pinned by digest; send never refetches
an upstream URL or silently replaces the bytes the confirmation described.

## Ownership, credentials and trust

The server checks source ownership, current feature availability, the accepted
pair, blocks, account state and quotas at the write boundary. Transfers do not
copy secrets, OAuth grants, token state, network/HITL exemptions or administrator
permissions. MCP installs offline with the original public endpoint/auth shape;
the recipient supplies credentials and explicitly tests or authorizes it before
activation. Plugin components use the native import paths and collision rules.

The owner explicitly accepted the [ADR-327 trust exception](../architecture/ADR-327-Skill-Library-And-Third-Party-Skills.md):
a shared skill, including a plugin's skill child, uses the recipient-authored
execution policy once enabled. Only server-written provenance can confer that
policy; the origin badge and uploaded manifest cannot. Ordinary third-party
imports retain their existing isolation. A received copy never becomes a system
skill and still follows connector permissions and mutation approvals.

Independent ownership means later sender edits, deletion or disconnection do
not edit or remove the recipient's copy. Retries preserve recipient edits,
activation and deletion. Account erasure anonymizes the retained sender origin;
exports omit another account's identifiers and secret package material.

Sender/time provenance is settings-only metadata. Native MCP and plugin readers
explicitly omit `shared_origin` before validating their closed assistant
contracts; the settings response keeps it. Their authorization, confirmation
snapshots and credential boundaries remain unchanged. The plugin settings list
uses one batched origin lookup in addition to its component queries, independent
of the number of plugins; integration tests measure that budget at multiple sizes.

## Transactions, recovery and retention

Network/archive validation runs outside SQL transactions. Durable leased claims,
database clocks and fencing prevent stale workers from committing after another
claim. Lost acknowledgements resolve through the same receipt; a partial plugin
retries only its matching native children. No duplicate action record is added.
The notification archive and sent flag commit together; live SSE follows commit.

Preview/snapshot retention is fixed at creation, never renewed by retries; see
the [source constants](../../apps/api/src/core/constants.py) and
[maintenance](../../apps/api/src/domains/peers/capability_notifications.py).
Maintenance stays scheduled when peers is off, reaping payloads without claiming
messages or publishing notifications. Disabled delivery resumes from the durable
outbox only after the feature is available again.

Real PostgreSQL, filesystem, migration and cancellation scenarios live in
[the transfer integration tests](../../apps/api/tests/integration/domains/peers).
[The browser journey](../../apps/web/e2e/smoke/settings-capability-sharing.spec.ts)
exercises all native kinds through desktop/mobile settings and explicit review.

The ownership and trust decision is recorded in [ADR-350](../architecture/ADR-350-Peer-Capability-Copies-Without-Credentials.md). Known credential fields are excluded structurally and recognizable embedded secrets are refused; arbitrary prose or opaque resources cannot be certified secret-free. Review the content before sharing.
