# ADR-316 — A generated image is shared with a connection as a copy, with an optional comment quoted literally

**Status**: accepted — 2026-09-24 (owner request: share a generated image with a peer as messages are shared, ideally the image alone, landing in the peer's generated files as if they had generated it on reception; owner arbitration Q3: the image is shown in the recipient's chat like a shared message; Q4: the image alone — an optional comment travels with it)
**Amends**: the peers program (ADR-180, ADR-186), ADR-279 (the generated-files gallery), ADR-304 (no transaction across a network call), ADR-185 (exact counts), ADR-184 (published bounds)

## Context

A message reaches a connection through the sender's assistant: a draft the person
confirms, a delivery sweep, and a wording in the recipient's assistant's voice. None of
that fits an image: there is nothing to reword, and the owner wants the image itself to
arrive — in the recipient's chat and in their gallery, « as if they had generated it
when it arrived ».

## Decision

1. **An explicit click is the confirmation.** « Share with a connection » sits on every
   generated image card of the chat and of the gallery, and opens a dialog: the accepted
   connections as a radio group, an optional comment, one button. No assistant, no draft,
   no model call — nothing is spent.
2. **`POST /peers/connections/{connection_id}/images`** (the peers router, under its
   capability switch) checks, copies, records and COMMITS, then reaches the recipient's
   chat on a session of its own, best-effort:
   - the connection is accepted, the sender is part of it (404 otherwise, hide-existence),
     no block separates the pair, the recipient is active (`peers_not_connected`);
   - the image is the sender's OWN, live, GENERATED image with its file on disk — an
     upload, a screenshot, someone else's id or an expired one answer the same
     `peers_image_not_shareable`;
   - the daily quotas hold (`PEERS_IMAGE_SHARE_MAX_PER_DAY`, `…_PER_PAIR`), counted on the
     share ledger and serialised per sender by a transaction-scoped advisory lock: two
     shares racing for the last slot cannot both land (proven with two connections on real
     PostgreSQL, and proven to fail without the lock); a refusal is a 429
     `peers_image_quota_reached` with `Retry-After` at the next UTC midnight;
   - the file is copied under the recipient's folder, and their gallery row and the ledger
     row are written in one transaction; a failed write withdraws the copy.
3. **The recipient's copy is filed like an image they generated when it arrived**: origin
   `generated_image`, a lifetime of its own (the attachment TTL from reception), the
   sender's title, and `attachments.shared_by_name` — a snapshot the gallery shows as
   « Shared by … », never a source of truth on who that person is.
4. **The ledger `peer_image_shares`** records who shared with whom, on which connection,
   and which copy (SET NULL once it expires). It stores NO comment. It is two-sided:
   exported to both and purged with either account.
5. **The recipient's chat shows it as a peer's bubble** (`proactive_peer_image`, the
   tint, the reply and block actions of a relayed message) carrying the very card an
   image LIA generated for them carries (`to_wire_metadata`, one wire shape), live and
   after a reload. The line above it is in the recipient's language; the comment follows
   as a LITERAL quote (`domains/shared/markdown_literal`): the chat renders Markdown with
   raw HTML and images from any `https:` host, so a third party's words must not load a
   tracking image, hide a link behind friendly text or draw markup that reads like LIA's.
   The neutralisation uses numeric character references, never backslashes: measured in
   the browser, the chat's math step renders an escaped `\[x\]` as a formula. The
   comment is bounded (`PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS`, 500), published to the
   dialog, and kept nowhere but in the recipient's chat.
6. **Observed**: `peers_image_shares_total{outcome}` (`shared`, `not_connected`,
   `not_shareable`, `quota`, `failed`) on dashboard 09, in a peers row that also wired the
   two peers metrics nobody could see (the coverage baseline fell from 42 to 40).

## Consequences

- The recipient may share a copy they received in turn: it is theirs, like an image they
  generated.
- A push opened before the chat's live event shows the bubble's text; the card appears
  with the conversation's next read — the same road a relayed message takes.
- The dialog tells « still loading », « could not be read » and « no connection yet »
  apart; an expired card offers no share.
- The dialog's axe scan found a defect older than this ADR: muted text on the translucent
  dialogs (the v1.27.0 frosted-glass signature, over a dark overlay) measured 4.19:1 in
  light mode, below AA. The descriptions of the two dialog primitives now use
  `text-foreground/80` (allowed by the contrast contract); other muted text inside
  dialogs is left to a design decision on the glass itself.
