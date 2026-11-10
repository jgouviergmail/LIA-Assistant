# ADR-376 — A card opens its record in the Tools, on a signed proof of its source

**Status**: Accepted, 2026-11-09.
**Date**: 2026-11-09

**Amends**:
[ADR-332](ADR-332-Deterministic-Cards-Received-Facts-And-Message-Owned-Actions.md) — a card's
source title, file preview and source actions navigate to the native record instead of a
provider link.
[ADR-369](ADR-369-Workbench-The-Persons-Own-Door-To-Their-Services.md) — the Tools accept an
optional proof of source that constrains which connected account a page may read or act on.

## Context

A data card in the chat shows an e-mail, an event, a contact, a task, a file or a Hue light the
assistant read. Until this decision, its title opened the provider's own web page, or nothing.
The Tools (ADR-369) already hold every one of those records in a native screen, so the person
asked that the card open there.

Three facts made a plain link wrong:

- **The identifier is not the address.** An event needs its calendar, a task its list, an Apple
  mail its folder and UIDVALIDITY; a registry id or « the default calendar of today » can name
  another record than the one the card shows.
- **The account can change between the answer and the click.** A person reconnects another
  Google grant, switches the active mail provider, pairs another Hue bridge. A link built from
  the identifier alone would open, silently, a different record that happens to share it.
- **The card is archived HTML.** It is replayed weeks later, exported and rendered without the
  turn that produced it, and the model reads its semantic view, never its markup.

## Decision

1. **The producer signs the destination.** At the common connector-tool boundary,
   `agents/display/card_navigation.py` stamps each native card with a typed destination
   (`workbench/card_targets.py`) built from the received provider identifier and its received
   scope, never from a provider URL, a registry suffix or the current default. The envelope
   names the answering provider and the credential source fingerprint of
   `core/content_source.py` (an OAuth grant, an Apple principal, a known Hue bridge id), and is
   signed with HMAC-SHA256 over the instance secret and the LIA account. It lives in the
   registry item's display metadata and in the card's `data-card-target` attribute, outside every
   model-facing payload.
2. **The click asks the server, which re-resolves.** `POST /workbench/card-target` is
   authenticated, guarded by the Tools capability and read-rate-limited. It checks the signature
   against the authenticated account, resolves the active provider and source at that moment,
   and answers only the typed native address. It reads no record and grants no mutation. A
   missing or invalid proof, a changed source or an unavailable connection is refused with its
   reason; a network failure never falls back to a third-party site.
3. **The Tools page carries the proof to its own family.** The destination keeps the proof in
   its `card_source` parameter; `lib/workbench/card-source.ts` forwards it only from that Tools
   page to the same family's API routes, as the `X-LIA-Card-Source` header or, for direct
   downloads, exports and upload URLs, as a query parameter. The request dependency
   (`workbench/card_source.py`) accepts either transport, refuses two that disagree, and
   `open_tool_client` checks the expected provider and source on the client it actually acquired,
   before it reads or acts: a source replaced in between answers `409 card_source_changed`.
4. **A constraint, never a permission.** The proof narrows which account a request may reach; it
   grants nothing the Tools would not grant without it, applies to its own family only, and is
   stored nowhere once the page is left. Requests without a proof remain ordinary Tools
   navigation.
5. **History stays readable and honest.** An archived card keeps its original proof. An older
   card without one stays readable but opens nothing by guessing the current account, and says
   so. With the Tools switched off or their availability unknown, source actions disappear and
   titles stay plain text; the API guard remains authoritative.

## Consequences

- The chat and the Tools meet on one record: what a card showed is what the Tools open, or a
  stated refusal.
- Reconnecting another grant, changing the provider, the Apple principal or the Hue bridge, or
  rotating the instance secret makes older cards stop opening their record. That is the price
  of never opening the wrong one.
- Contextual links (meeting join links, directions, telephone, e-mail addresses, attachments,
  cited web sources) keep their own meaning and do not go through this door.
- The CORS policy allows `X-LIA-Card-Source` for the application's allowed web origins only;
  no third-party link ever receives the proof.

## References

- [WORKBENCH.md — Opening a record from an assistant card](../technical/WORKBENCH.md#opening-a-record-from-an-assistant-card)
- [HTML_CARDS.md — Native record navigation](../technical/HTML_CARDS.md#native-record-navigation)
- `apps/api/src/domains/agents/display/card_navigation.py`, `apps/api/src/domains/workbench/card_targets.py`,
  `apps/api/src/domains/workbench/card_opening.py`, `apps/api/src/domains/workbench/card_source.py`,
  `apps/web/src/lib/workbench/card-source.ts`
