# ADR-321 — A file or an answer sent by e-mail: one outgoing MIME, a road per mailbox, a ceiling per provider

**Status**: accepted — 2026-09-25 (owner request: « in the chat or in "My generated files", let the person send an image, a document, a capture or a message by e-mail, as an attachment, with a subject and an optional message »; owner arbitration Q2: free recipients through the connected mailbox, otherwise LIA's relay to the account's own VERIFIED address only; an answer travels as the `.md` file « Download » writes; the body is the typed words or nothing; the exact provider limits to be verified in their documentation)
**Amends**: ADR-314 (the relay's recipient rule, now shared with a second surface), ADR-316 (the click-is-the-confirmation precedent, extended to e-mail), ADR-279 and ADR-282 (the gallery and the bookmarks gain an action), ADR-304 (a new route commits before its network call), ADR-280 (a new operator switch)

## Context

A person could keep a generated file (ADR-319), download it, or share an image
with a connection (ADR-316) — but not send it to anyone else. Measured before
the change:

1. **No mail road could carry a file.** `EmailClientProtocol.send_email(to,
   subject, body, cc, bcc, is_html)` had no attachment; Gmail built a bare
   `MIMEText`, Outlook a body-only Graph message, Apple a single-part
   multipart, and LIA's own relay an `alternative` of text and HTML.
2. **Gmail's plain send could not have carried one anyway.** The client posts
   the message base64url-encoded in a JSON body to the METADATA URI of
   `users.messages.send`; a public report measured that URI refusing a request
   past 1 048 576 bytes (a 1.4 MB PDF). The API's discovery document gives the
   UPLOAD URI a `maxSize` of 36 700 160 bytes.
3. **Two forward paths built attachment parts by hand, and one was wrong.**
   Gmail re-encoded the part in place; Apple used `MIMEApplication` and then
   ASSIGNED `Content-Type`, which in the email package APPENDS a second header
   — readers kept the first, `application/octet-stream`.
4. **Each provider limits the MESSAGE, a person thinks in FILES**: iCloud
   « 20 MB » per message (Apple Support 102198), Microsoft Graph a file « under
   3 MB » inside the request (larger needs an upload session), Gmail 35 MiB
   through the upload URI, and an operator's relay whatever it was configured
   with (Postfix defaults to 10 240 000 bytes).

## Decision

1. **One outgoing MIME** (`infrastructure/email/outgoing.py`):
   `OutgoingAttachment(filename, mime_type, data, charset)`, `attachment_part`
   (base64, RFC 2231 name, the file's own type, a charset for text) and
   `with_attachments` (the body itself when there is no file — a message of
   words is built exactly as before — else a `mixed` message with the body
   first). Gmail, Apple and the relay build with it; Outlook's Graph carries
   the same `OutgoingAttachment` as a `fileAttachment`. Both forward paths now
   use the shared part: Apple's duplicate `Content-Type` is gone.

2. **`send_email` takes `attachments` on the three clients alike** (the parity
   contract holds the signature, `test_outgoing_attachments.py` the
   behaviour). A Gmail message carrying a file — a new one or a forward —
   leaves through the UPLOAD URI (`GmailSendMixin._send_message`, raw RFC 822,
   `uploadType=media`); a message of words keeps the metadata URI.
   `_make_request` gained a raw body and a per-call base URL, keyword-only.

3. **Each road publishes the largest file it carries, DERIVED from what its
   provider documents** — never re-typed as a file size: the client classes
   declare `OUTGOING_FILE_MAX_BYTES` (Gmail and Apple through
   `max_file_bytes(message limit)`: base64 lines plus a 64 KiB envelope
   headroom; Outlook the documented 3 000 000 bytes), the relay derives it from
   `EMAIL_SHARE_RELAY_MAX_MESSAGE_BYTES`. A runtime-checkable `OutgoingCeiling`
   protocol lets a caller holding only the CLASS read it without a cast.

4. **A domain of its own, `email_share`**, two routes under the capability
   guard: `GET /email-share/options` (the road, the relay's one recipient, the
   file ceiling, every bound the form meets — ADR-184) and `POST /email-share`
   (per-account rate limit). The road: the connected mailbox with free
   recipients (at most 10, deduplicated without case); without one, the relay
   to the account's address ONLY when it is verified (ADR-314's rule) — a
   broken mailbox is SAID (`mailbox_needs_reconnect`) while the relay serves.
   What may be sent: one of the person's OWN GENERATED files not past its
   deadline (a kept file has none — ADR-319), or an answer as Markdown built
   by the client exactly as « Download » writes it (the chat's
   `messageToMarkdown` — an HTML answer written as Markdown since ADR-177's
   2026-09-30 amendment —, the bookmarks' `bookmarkToMarkdown`, the same dated
   names). No model is called and nothing is written in the person's place.

5. **No transaction across the send** (ADR-304): the route resolves the road on
   a short session of its own, checks the file on the request session,
   COMMITS, and only then reads the file from disk (off the loop) and opens
   the mailbox through `open_active_client`.

6. **Every refusal names itself** (`detail.code`, translated by the web app in
   six languages): `file_gone` 404, `too_large` 413 with the ceiling,
   `no_recipient` 400, `recipients_locked` / `unavailable` /
   `mailbox_reconnect` 409, `refused` 502 (the provider answered no), `failed`
   503 (it could not be reached) — the per-account limit answers 429. Each is
   counted where it is raised (`email_shares_total{route,outcome}`, dashboard
   10, « Email share (ADR-321) »); a failure is logged by its class and the
   provider status, never by its text, and no address, subject or word of the
   person reaches a log above DEBUG.

7. **An operator switch** (`PlatformCapability.EMAIL_SHARE`, family
   « reach », env ceiling `EMAIL_SHARE_ENABLED`, off the capability map with
   its reason): the router IS the ability and keeps no record. The
   demonstrator switches it OFF — with its connectors closed a send would
   leave through the relay that also carries the verification e-mail
   activating every account.

8. **Six entry points, one dialog**: an answer's action row (a chip beside
   « Download »), the generated image, document and browser capture cards of
   the chat, the gallery's tiles and the bookmarks. The page reads the
   capability ONCE and hands it down (the connections' precedent); a card
   whose file is not ours or is past its deadline offers nothing; the dialog
   and its options request exist only once pressed. The dialog tells apart
   « still checking », « could not check » and « no road », proposes a subject
   within the published bound, checks recipients, size and subject before the
   server has to, and keeps itself open on a refusal.

Proven: the MIME is read back as a mail client reads it (RFC 2231 names,
charsets, the body first); the three clients and the relay carry the file (unit
parity tests); the file predicate on real PostgreSQL (another account's file,
an upload, a file past its deadline, an expired row: gone; a kept file: sent;
a file past the road's ceiling: 413 before a byte is read); the dialog's states,
roads, bounds and refusals (vitest); four hermetic browser journeys — an answer
leaves as its Markdown, a document through the relay to the account itself, a
refusal said in words, the dialog within 320 px and clean under axe.

## Consequences

- A generated file or an answer reaches anyone the person writes to, from
  their own mailbox, in two clicks; without a mailbox, it reaches themselves.
- The provider limits are stated once and published; a file past a road's
  ceiling is refused with the number, before anything leaves.
- Gmail forwards carrying files now leave through the upload URI too, which the
  metadata URI's 1 MiB bound had made fragile.
- **Limits, stated**: no send through a REAL provider account was measured —
  every road is proven against its documented wire shape, not a live mailbox
  (the owner's own accounts were not used for an outward effect). The upload
  URI is sent in one `uploadType=media` request, which Google describes « for
  quick transfer of smaller files, for example, 5 MB or less »; the documented
  bound is the `maxSize`. Outlook files of 3 MB and more are refused rather
  than sent through an upload session. A send is the person's act through the
  UI: like an image shared with a connection (ADR-316), it was recorded in no
  register, the provider's « Sent » folder its only trace (Apple's SMTP writes
  none) — superseded by the amendment of 2026-09-27 below: it is an action.

## Alternatives rejected

- **Letting the model write the e-mail** (the `send_email` tool's draft): the
  owner asked for the person's own subject and words, and a click needs no
  confirmation card when the dialog IS the confirmation.
- **The server rebuilding an answer's Markdown**: a second conversion of the
  same answer, bound to drift from the file « Download » gives.
- **One ceiling for every road**: the smallest (Outlook's 3 MB) would refuse
  what Gmail and iCloud carry; the largest would send what Outlook refuses.
- **The relay to any recipient**: an open relay aimed at strangers with the
  instance's domain; ADR-314 already refused it.

## Amendment 2026-09-27 — the send is an action in the register

**Amends:** the consequence above that recorded a send in no register (owner
request: every act reaches the transparency registers with its classification;
ADR-263's amendment of the same day).

A send is now one row in `agent_effects`: the person's act (source `user`), policy
`confirm` — the dialog IS the confirmation —, executed `direct`, one fresh run per
click, labelled « Sent an e-mail to N recipient(s) » in the six languages. It is
claimed after every refusal (the file gone, the relay refused, a road that cannot
carry the size) and before the send leaves, and settled from the send's explicit
result, never from the absence of an exception (`recorded_action`, the
`shared/action_sink` seam the register installs at import). What was sent — the
subject, the words, the recipients' addresses — is not copied into the row: the
count of recipients is the label's only value. No model decides anything, so no
turn is filed.

## Amendment 2026-10-01 — the recipient field suggests the person's contacts

**Amends:** the recipient field of decision 4 (owner request: suggest, while a
recipient is typed in any « Send by e-mail » dialog, the contacts matching it by
last name or first name — accents and punctuation ignored — or by a normalised
phone number, and insert the contact's ADDRESS; nothing without an active
contacts connector).

- **Published, then asked.** `GET /email-share/options` gains
  `recipient_suggestions` (true only on the mailbox road with an active contacts
  connector), `recipient_query_min_chars` and `recipient_suggestions_max` (ADR-184).
  `GET /email-share/recipients?q=` answers the contacts for ONE recipient being
  typed, under a rate limit of its own (`EMAIL_SHARE_SUGGEST_RATE_LIMIT_*`), and
  echoes the query so the field never shows an answer to an older one.
- **One match, not three.** The providers' own searches match three different
  ways, so each contacts client reads its book whole (`list_email_directory`,
  parity-pinned): Google People pages `connections` with every parameter repeated
  on each page, Graph follows `@odata.nextLink`, CardDAV reads its own cache —
  under `EMAIL_SHARE_DIRECTORY_MAX_CONTACTS`, a cut stated as `truncated`. The book
  is compacted to names, addresses and phones, cached under the declared
  `contacts_directory` family (`USER_CACHE`, ADR-260) with a version stamp, built
  once across workers (`shared_flight`) and dropped by every contacts write of the
  three clients. `email_share/recipient_match.py` matches it: names through
  `fold_name`, addresses through `fold_email`, phone digits through the telephony
  domain's `number_search_variants` (a query of digits alone is a phone query);
  names rank before addresses, addresses before phones.
- **Measured before shaped.** Projecting 5 000 contacts costs about 140 ms of CPU
  and the match about 12 ms, so the projection is memoised per worker by the
  book's version (bounded by entry count) and both run in a thread; a keystroke
  reads the small stamp first and opens neither the book nor the connector when
  that version is already projected.
- **A read of the book is a consultation** (ADR-263): filed on the `email_share`
  surface when a provider was actually opened, `failed` when the read failed, and
  nothing on a cache hit. The read runs under a timeout and every outcome is
  counted (`email_share_recipient_directory_reads_total{outcome}`, dashboard 10).
  No model, no spend, and no contact's data in a log.
- **The field is a WAI-ARIA combobox** (`RecipientCombobox`): debounced, arrows
  and Enter pick, a pick on `mousedown` keeps the phone keyboard open, Escape
  closes the list before the dialog (`DialogContent` lets an expanded combobox
  keep its Escape), and a name being typed is not reported as a wrong address
  until the field is left.
