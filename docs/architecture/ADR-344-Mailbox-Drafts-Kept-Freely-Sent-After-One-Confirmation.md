# ADR-344 — A mailbox draft is the person's own: kept freely, sent after one confirmation

- **Status**: Accepted
- **Date**: 2026-10-13
- **Amends**: ADR-263 (a write declares what it owes: `reversible` with its
  written reason), ADR-276 lot 7 (the digest lock), ADR-287 (one e-mail
  vocabulary at the client boundary), ADR-288 (a FOR_EACH lot of drafts),
  ADR-289 (one card description, drawn per surface), ADR-303 (a partial is a
  success stating its partial), ADR-309 (a single call's layout), ADR-272 (a
  call is billed through the turn's config), ADR-318 (one bound wording, read
  by both readers), ADR-335 (a resource handle and its only sources), ADR-336
  (outcome evidence)
- **Scope**: the mailbox draft half of the three e-mail clients
  (`gmail_drafts_mixin.py`, `gmail_compose.py`, `outlook_drafts_mixin.py`,
  `apple_drafts_mixin.py`, `apple_compose.py`, `apple_imap.py`,
  `mailbox_drafts.py`, `email_compose.py`), `infrastructure/email/recipients.py`,
  the tools `agents/tools/mailbox_draft_*.py` and `mailbox_drafts_tools.py`,
  their manifests (`agents/emails/mailbox_drafts_manifests.py`), the reply a
  model writes (`agents/emails/reply_drafting.py`, `mailbox_reply_draft_prompt`),
  `DraftType.MAILBOX_DRAFT_SEND` and the registries it feeds, the draft card,
  the planner / validator / agent / critique prompts, the web locales

## Context

The owner asked, on 2026-10-13, for the person's mailbox drafts — Gmail,
Outlook and iCloud — to be managed from the conversation: create one, or
prepare a reply or a forward as a draft, with no confirmation; list them,
filtered or limited (« my last 5 drafts », « my drafts for Marie »), with no
confirmation; edit one with no confirmation; delete one or several with no
confirmation; send one or several, where a confirmation is mandatory.

Nothing touched a mailbox draft. The word « draft » named the confirmation card
LIA builds before an action (`DraftType`), and `get_emails_tool` with
`label:DRAFT` listed drafts as received messages — whose message id, handed to
`reply_email_tool`, answers one's own draft.

What the providers do was measured before the design was fixed (Gmail, on the
owner's dev account) or read from their documentation:

| Fact | Source |
|---|---|
| `drafts.update` keeps the draft id and gives it a NEW message id | measured |
| `messages.trash` on a draft's message moves it to the trash, recoverable; the draft leaves the drafts listing | measured |
| A multipart upload keeps the draft in its thread; a media upload loses the thread | measured |
| An unknown draft id answers 404; a draft without `To` is accepted; `q=to:` works on drafts | measured |
| Graph writes the `comment` of `createReply` / `createForward` into the SENT message only, never into a saved draft; `createForward` needs a recipient | documented |
| Graph refuses `$filter` with `$orderby` unless the sort property leads the filter (`InefficientFilter`) and answers `contentType` in lower case | documented |
| IMAP: `APPEND` names the new UID (`APPENDUID`) only under UIDPLUS; an edited draft is a NEW message, so a NEW handle | protocol |

## Decision

1. **One contract, three providers.** `list_drafts`, `get_draft`,
   `create_draft`, `create_reply_draft`, `create_forward_draft`,
   `update_draft`, `trash_drafts`, `send_draft` on the three clients, held equal
   by parity tests. A draft is read whole (its quoted history kept), written
   with its thread, and its handle is `mailbox_draft_id` — Gmail's draft id,
   Graph's message id, a scoped IMAP handle. The handle is a RESOURCE_ID (ADR-335):
   nobody dictates one, only the listing or the tool that saved the draft
   produces it, and a draft's message id stays UNTYPED so the catalogue never
   offers it as a message to answer.

   Every native IMAP message ID binds its UID to the server endpoint, account, folder and
   SELECT's UIDVALIDITY; a draft has a distinct `d.` handle for that resource.
   A renamed/recreated folder or changed account cannot retarget a listed UID.
   Old unscoped IDs must be listed again before an action. The message cache
   is isolated by server endpoint, account and scoped ID. The selected session supplies the
   generation; a later STATUS request of a recreated folder name cannot
   replace that evidence. Missing or malformed UIDVALIDITY refuses the read
   before fetching messages ([IMAP UID identity](https://www.rfc-editor.org/rfc/rfc3501#section-2.3.1.1)).

2. **Keeping, editing and trashing ask nothing; sending asks once.** The five
   write tools declare `mutation_policy="reversible"` with their written
   reasons: a draft stays in the person's own mailbox and reaches nobody, and a
   trashed draft stays recoverable in the mailbox's trash (Gmail and iCloud
   trash, Outlook's Deleted Items) — never a permanent deletion. Sending
   declares `draft`: a confirmation card, `DraftType.MAILBOX_DRAFT_SEND`,
   registered in every registry a confirmation type needs (display, preview,
   summary, executor, effect label, activity family, modifier fields, FOR_EACH,
   result and cancel wordings in six languages).

3. **What is confirmed is what leaves.** The card shows the draft as the
   mailbox holds it — recipients, subject, the person's own words, its files —
   and carries a digest of it: recipients, subject, the WHOLE text, quote
   included, the files' descriptors and the complete provider revision. Gmail's
   underlying message id changes with every replacement, Graph supplies its
   `changeKey`, and IMAP drafts carry a SHA-256 of their complete MIME bytes.
   A same-named, same-sized file replacement or an HTML-only edit therefore
   changes the fingerprint too. A missing revision refuses the send proposal;
   existing confirmation cards from the earlier fingerprint format must be
   shown again. At the confirmation the executor reads the
   draft again: edited in the mailbox meanwhile → `DRAFT_CHANGED`, nothing
   sent; gone → `DRAFT_GONE`; no recipient left → `NO_RECIPIENT`. A change
   asked on the card itself (« make it shorter », « send it to Paul instead »)
   is written to the draft first, its quote kept, and only then does it leave
   — recipients compared by address, never by spelling. A send is one attempt,
   never retried; its result names no draft handle (the draft became a
   message), and `draft_kept` says when IMAP filed the message but could not
   take the draft out. `sent_copy_filed` independently reports whether an IMAP
   Sent copy was stored; neither filing result implies the other. A kept draft
   or missing Sent copy is stated without suggesting another SMTP send.
   The owner's receipt names blind-copy recipients too, including a draft
   addressed only in blind copy, on both the chat card and the plain surface.

   Both an instruction-based edit and a retouch on the send card carry the
   complete revision through the client's final read. A changed revision
   refuses the write. Gmail replacement and Graph PATCH run once: replaying an
   edit after a lost acknowledgement could overwrite a subsequent mailbox edit.

   The fingerprint compares the preview with the confirmation-time read. It
   does not establish an atomic compare-and-send operation at a provider;
   concurrency between that read and the external send must not be described
   as a stronger guarantee than the provider actually supports.

4. **Recipients are read once for every road**
   (`infrastructure/email/recipients.py`): strictly for what LIA writes — an
   unreadable address refuses the field, a named recipient is never dropped in
   silence — tolerantly for a header a provider handed back; a display name
   outside ASCII is encoded alone, so the address never hides inside an encoded
   word. A name the person gives is resolved from the contacts recipient by
   recipient, never by judging a list from its first entry.
   Recipient segmentation scans complete quoted/bracketed spans in linear
   time, including malformed unclosed spans, so hostile headers do not stall
   the event loop by repeatedly rescanning their suffixes.
   Replies honor the original `Reply-To` through the same neutral vocabulary
   and recipient rule as the confirmation card. A chosen recipient takes
   priority; replying to one's own message still answers its recipients.
   Graph names are quoted as RFC addresses, including names containing commas.
   A forward requesting files refuses before any write when a file cannot be
   downloaded; it never silently drops that file or reports it as transferred.
   Gmail's decoded bytes must match the published size; missing or malformed
   base64 data is refused. Named inline MIME parts are carried too, through
   the same reader, without exposing their encoded data in file descriptors
   ([Gmail MessagePartBody](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments)).

   IMAP and SMTP over TLS use an explicit validating context before login.
   Every IMAP entry, including credential validation, uses the configured
   Apple connection timeout. A certificate refusal is one connection failure,
   never a revoked password, regardless of the diagnostic's wording. Credential
   validation checks every requested protocol; CalDAV closes its SDK session
   on success and failure. IMAP owns its connection before login and folder
   selection, so refusals also close it; a closing failure is reported by type
   and cannot replace the original operational refusal. Refusals retain typed guidance in the account's
   declared language, never provider prose or the account identifier.
   Once SMTP has begun, a stop cannot recall a message: one retained task
   finishes its send and filing through repeated cancellations. A late failure
   is recorded by type and cannot replace the caller's cancellation; writes
   that fail before any cancellation still raise normally. This is tested with
   simulated SMTP/IMAP, not a live iCloud account.

   Cancellation of a native IMAP write can also leave a worker finishing a
   write whose acknowledgement the caller never received. The effect ledger
   records that result as unknown, not success or failure, and refuses replay
   under the same ledger key. An accepted APPEND with a delayed acknowledgement
   is covered by the native-client/gate simulation; a stop is no recall promise.

   IMAP trash moves run once, including the COPY path: an acknowledgement lost
   after COPY cannot trigger another copy. Cleanup never calls global EXPUNGE,
   which would also remove other clients' messages already marked deleted.
   Native MOVE is used when offered; otherwise COPY requires UIDPLUS and
   expunges only the requested UIDs. Replacing a draft requires targeted
   removal before APPEND; a server without UIDPLUS refuses that edit before
   writing. If cleanup after an acknowledged SMTP send is unavailable, the
   send remains acknowledged and the kept draft is reported; it is never sent
   again ([UIDPLUS targeted removal](https://www.rfc-editor.org/rfc/rfc4315#section-2.1)).

   After APPEND, a changed selected namespace preserves the original UID and
   reports that a replacement was saved but its cleanup could not be completed.
   APPENDUID receipts are bounded and checked against that namespace before
   fetching or removing any UID. The fetched message must carry the generated
   Message-ID; an inconsistent receipt preserves the original and reports the
   acknowledged saved copy. Without APPENDUID, exactly one valid UID matching
   that generated Message-ID is required; an ambiguous result never authorizes
   cleanup.
   An absent/unparseable Date is unknown metadata, not a mailbox failure;
   a timezone-free mail date is normalized to UTC.

   Refused folder choices remain bounded external data, including requested
   names and available full paths; labels cannot close the canonical untrusted
   envelope. A local cut is stated and never offers a partial path as a usable
   choice. Parser errors expose only the centrally owned input guidance, never
   arbitrary exception text. Out-of-range Unix dates become the same readable
   date-format refusal on Windows and Linux before an unbounded integer is
   constructed. Background-task failures retain their traceback in DEBUG;
   visible operational events state the exception type without its private text.

5. **A reply nobody dictated is written once, from the received message as
   DATA.** One structured call on the e-mail slot, the original wrapped as
   external content and cut to its first part, the static rules as the system
   message (ADR-309), billed to the turn (ADR-272), refused with a code the
   model can act on (a spending ceiling, an unusable answer, an empty reply). An
   edit by instruction runs the draft modifier on the person's OWN words only;
   the quoted message stays the mailbox's.

6. **A deletion names its drafts one way** — their handles, a search and/or a
   count, or all of them — moves at most `EMAIL_DRAFTS_BULK_MAX` per call, and
   says what remains (`more_remaining`, a count beyond the bound included) and
   what became of each draft (`failed[]`: `not_found`, `refused`,
   `unavailable`). Trashing none of the named ones is a failure; trashing some
   is a success stating its partial (ADR-303). An invalid explicit count is
   refused before selection; it never becomes a default-sized deletion.

7. **A bound is published to both readers from one wording** (ADR-318): the
   listing's and the deletion's `max_results` read the same text in the
   manifest the planner reads and in the schema the ReAct loop binds.

8. **Every surface knows the family.** The catalogue (the email agent and its
   builder), the step labels and the effect labels in six languages, the
   outcome evidence (every item under `emails`, never a top-level key read as
   « awaiting confirmation », ADR-336), the FOR_EACH confirmation, and the
   tool-name domain map (`mailbox` → `emails`, so « the second one » after a
   listing still points into the e-mails). The planner, validator, email agent
   and critique prompts state the rule: « prepare / draft » saves a draft and
   sends nothing; sending an existing draft asks first; the validator never
   halts for the person's own drafts.

   Google scopes are checked where Google may serve the category. A category
   with only active non-Google providers owes no Google scopes. If Google and
   another provider both remain active, their type set cannot establish which
   row is newest, so the scope check is retained conservatively. The historical
   Gmail alias uses the resolver's same alias declaration. Provider-bound tools
   still require their exact active connector type.

9. **Found on the way, fixed, each with its test.** The HITL reply card named
   the original SENDER alone and its executor then imposed it: a reply to all
   lost every other recipient, a reply to one's own message went back to
   oneself, and on Outlook and iCloud the card read a Gmail header tree they do
   not have and named nobody. The card now reads the provider-neutral message,
   shows the recipients the clients' own rule addresses (`reply_recipients`),
   and exactly those leave — Graph would otherwise address the reply its own
   way. The draft modifier's recipient fallback replaced the recipient with an
   address the model had already put in copy or in the text. The shared
   recipient resolver left a name unresolved when the list began with an
   address. The HITL « Modify » ran without the turn's config, so under
   Langfuse its spend reached no ledger. And the card chips « Prepare a reply /
   a forward » now say « Reply / Forward »: on a card the action answers, where
   « prepare » now means a draft kept in the mailbox.

## Consequences

- The confirmation types grow by one, and the effect register names a sent
  draft by its first recipient. A draft written, edited or trashed is an act
  of LIA's the register records under its own wording.
- « Prepare a reply to Marie's e-mail » now keeps a draft in the mailbox
  instead of opening a send confirmation — the briefing's « reply » chip
  included, whose wording already said « prepare ».
- `hitl_dispatch_node` shrank (its draft-type change tables moved to
  `nodes/draft_type_changes.py`) to carry the turn's config.

## Measured

On dev, the owner's Gmail, 2026-10-13: the client layer (create with a
non-ASCII display name and a Bcc, list by `to:`, update keeping the draft id,
reply and forward drafts in the thread, trash partial, a trashed draft hidden,
send) and then the TOOLS themselves: a subject put on one line, the drafts
saved as the current or listed items, an edit keeping the handle, a reply draft
showing only the person's words while it quotes the original, a partial trash
stated as such, a send refused with `DRAFT_CHANGED` after an edit in Gmail, a
send carrying the subject changed on its card (`edited: ["subject"]`, the sent
message's subject the confirmed one, no handle surviving), and the HITL reply
card leading with the sender and excluding the person's own address. Every
probe draft was deleted; the one message sent, to the owner's own Hotmail
address, was moved to the trash.

## Not measured

- **Outlook, live**: the dev Outlook connector has been in error since
  2026-08-01; reconnecting it is the owner's act. Its half is proven by parity
  tests against the documented Graph contract.
- **iCloud, live**: no iCloud account is configured.
- **The model paths** — a reply written from the received message, an edit by
  instruction, content written from an instruction — are tested with doubles; a
  measurement on real models is a paid one and waits for a budget.

## Rejected

- **A confirmation on keeping, editing or trashing a draft**: the owner's
  rule, and nothing reaches anyone.
- **Permanent deletion**: every provider offers a recoverable trash.
- **Drafts through `get_emails_tool`**: a draft is not a received message, and
  its message id must never be answered.
