# ADR-379 — A listed mail says whether it was answered

**Status**: Accepted, 2026-11-11.
**Date**: 2026-11-11

**Amends**:
[ADR-261](ADR-261-Push-Driven-Heartbeat-Wake-And-Incremental-Drive-Sync.md) — a mail wake announces unread mail only.
[ADR-287](ADR-287-Email-Content-First-Detail-Levels-Digests-And-Neutral-Message.md) — the trimmer's markers are also read
inside one line, for a provider's preview.
[ADR-369](ADR-369-Workbench-The-Persons-Own-Door-To-Their-Services.md) — a conversation is
also read for a whole listed page, in one call.

## Context

The owner's report (2026-11-11): « on received e-mail the assistant sometimes asks whether I
want to reply, although I already have. How can LIA know whether I answered, and what I
answered? »

Two causes, each proven in the code and by a simulation on the real aggregator:

1. **No reader knew where a message stands in its conversation.** A message reached every
   surface ALONE: the qualification judged its text (« a reply is expected »), a digest listed
   what it asked for (cached thirty days), the response prompt suggested next steps and the
   initiative offered to draft a reply. The reply is ANOTHER message of the same conversation,
   and nothing read it.
2. **The heartbeat announced opened mail as unread.** Its delta and push-wake roads listed
   every NEW inbox message under « UNREAD EMAILS » without reading the `UNREAD` label, and a
   message cached at arrival still read unread after the person had opened it.

Found one surface at a time, the next surface forgets again. The owner's direction settled the
scope: every surface at once, so the assistant tells one fact everywhere.

## Decision

1. **One fact, with a closed vocabulary** (`core/mail_reply_state.py`). A message carries
   `reply_state` beside `classification`. A received message is `answered`, `answer_drafted`
   or `unanswered`; a message the person sent is `reply_received` or `awaiting_reply`. Absent
   means not known. `answered` and `reply_received` are facts and stay true; the three others
   are the reading of a moment and are told `not_checked` past `MAIL_REPLY_STATE_VALIDITY_SECONDS`,
   so an earlier turn's « no reply yet » is never repeated as current.
2. **One decider, pure** (`connectors/clients/conversation_replies.py`). A received message is
   answered when the person sent, STRICTLY later and in the same conversation, a message
   addressed to its sender or to the address it asked replies at — or when the mailbox itself
   marks it answered. A forward to someone else is no answer. A message addressed to nobody but
   its own sender (a note to oneself), a draft, a message with no date and a « nothing found »
   that a cut conversation cannot vouch for have NO state. Instants are stored in the account's
   own zone, the zone of the clock a model is given.
3. **One read per page on every provider** (`conversations_of`, `EmailClientProtocol`). Gmail:
   one `threads.get` per distinct thread, named headers and a partial response. Graph: one JSON
   batch, the owner's messages being those of the Sent folder (and every other copy of one),
   the answer mark being `PidTagLastVerbExecuted` (102 reply, 103 reply to all). IMAP: one
   session, a header search per folder, the `\Answered` flag — which LIA now sets when it sends
   a reply through SMTP.
4. **One door** (`connectors/mail_reply_states.py`). Every surface asks there. Nothing is
   cached, no model is called, and the door fails OPEN: the switch off, a mailbox that cannot
   be read or a time budget reached leave the page without states — « not known », never
   « unanswered » — counted by `mail_reply_state_reads_total{outcome}`.
5. **One projection for every annotation** (`core/annotation_projection.py`). What a model
   reads is decided when it is SHOWN: the state in words (« answered on … to … — … »), never
   the instants of the reading.
6. **What « I answered » carries is the writer's own words** (`reply_trimming.preview_own_words`).
   A provider's preview runs a short reply into the history it quotes; the trimmer's markers
   (ADR-287, six languages) are searched inside the line, and a preview that opens on the
   history hands over nothing.
7. **Every lister declares itself** (`connectors/mail_listers.py`). A module that lists a
   mailbox is `SITUATED` (it goes through the door), `MARKED` (it tells the mailbox's own
   mark alone, decision 15) or `NOT_SITUATED`, each with its reason; an AST guard walks every
   caller of `search_emails` and refuses an omission, a stale entry, and a declaration the
   module does not honour — each standing names the part of the door it goes through, and
   no other.
8. **The heartbeat tells unread mail only** (lot 0). One reading of the label
   (`core/mail_vocabulary.is_unread`), a fresh read on the delta and wake roads, the filter
   applied before the cap.
9. **A model is told what the state settles.** The response prompt and the ReAct prompt carry
   ONE identical block (`<MailReplyState>`, held equal by a test): `answered` settles
   `reply_expected` and what the mail asked for — it is reported as done, never as a priority
   or a pending action, and no reply is offered; `answer_drafted` is said instead of proposing
   a new reply; no state at all is « not known », never « not answered ». The initiative reads
   the state's line first in each item. A voice lookup (the phone, a direct Live session) runs
   the same tool and reads no nested value: it hears the state's one line, what happened, and
   « nothing yet » is not said (a test holds the two modules to it).
10. **The act of replying says it too.** The confirmation card of a reply opens on « Already
    answered: <date> » (`EmailReplyDraftInput.already_answered`), and a reply LIA writes — the
    mailbox-draft tool, the Tools' reply assist — reads the person's earlier answer
    (`agents/emails/previous_reply.py`), so it continues from it instead of repeating it.
11. **A card shows what stays true.** The chat's e-mail card, the Today briefing's mail card
    and the relationship view mark `answered` and `reply_received`, and withdraw « reply
    expected » from an answered mail. They never show the reading of a moment: a card is
    archived, or cached, longer than « nobody answered yet » stays true. One reader on the web
    (`lib/mail-reply-state.ts`), one badge component (`ClassificationBadges`).
12. **Out of turn, the same fact.** The heartbeat (`heartbeat/mail_context.py`) leaves out
    unread mail the person already answered — unread is not unanswered: a message answered
    from a phone's notification stays unread — before its cap and on its three roads, and
    marks an answer drafted and never sent on the mail's own line. The briefing's greeting and
    synthesis, and the radio's journal, read the state the card's item carries. The
    relationship view, the overview a model reads and the debrief read it per message, its
    instants in UTC like the rest of that contract; so does the by-name fallback.
13. **The Tools read the marks apart.** A listing is one search and never waits:
    `POST /workbench/mail/reply-marks` takes the rows of a page — in the body, a page of ids
    fits no address — and answers the marks to draw: `answered`, `answer_drafted`,
    `reply_received`. « Nothing yet » is no mark. The feature is published (`reply_marks`)
    exactly when the capability is on (ADR-184), so a page that is offered no mark asks for
    none; the page asks once per read of page one (`useMailReplyMarks`), a next page asks its
    own rows, and a read that fails marks nothing. The contact history carries the mark on
    each row it shows.
14. **The turn's answered mails are stated apart, last** (amendment of the same day). The
    response prompt carries a context section of its own (`answered_mail`,
    `<MailAlreadyAnswered>`), computed from the turn's registry
    (`agents/emails/answered_mail.py`): each answered mail by its item id and the instant of
    the answer, and nothing a correspondent wrote — outside the data block nothing marks a
    stranger's text as external. It is the LAST section, after the person's question: its
    place is measured (below), not chosen.
15. **A proactive discussion's mail tells what its mailbox marks, read with the message**
    (amendment of the same day). Its evidence is versioned by its content and every proof is
    read again at its version before any use (ADR-358): what it tells must come WITH the
    message, the same at every read, for no call of its own. That is the mailbox's own mark
    — Graph's last verb (`PidTagLastVerbExecuted` 102 or 103, dated by
    `PidTagLastVerbExecutionTime`), asked as the one expansion of a single-message read
    (`get_message(mailbox_mark=True)`); IMAP's `\Answered`, which every FETCH returns; Gmail
    keeps none through its API, and its search covers sent mail, so the person's reply is
    itself evidence in the window. The evidence states it ahead of the body
    (`"reply_state":"answered on <UTC instant>"`, `"answered"` where the mailbox dates
    nothing), through the door (`mail_reply_states.answered_mark`): a mail answered since
    it was read is another version, so the run stops as a changed fact, and a mail nothing
    is marked of keeps the text and the version it had. A marked mail also carries a
    usage nuance, as a discussion source's fact may (`discussion_evidence_lines.txt`,
    `email_answered_nuance`): the person already replied, the mail no longer awaits a
    reply from them, and no mark says nothing either way.
    The same decision repairs what kept an Outlook mail out of every discussion: a Graph
    listing carries a preview while a proof is read again whole, so the two never shared a
    version and the run stopped. A mailbox whose hits are not whole
    (`SEARCH_HITS_ARE_WHOLE` false) is now read one message at a time — one call lists, one
    reads each hit — and the page lists no more hits than the read's allowance reads whole
    (`min(item limit, DISCUSSION_READ_CALL_LIMIT − 1)`); the rest is the next page's.
    A message the door situates leaves it with its state alone: the provider's raw mark was
    the decider's evidence, never a second telling beside it.
16. **A bounded read's iCloud page comes in one command** (amendment of the same day).
    Every IMAP command is a call of the read's allowance, and `imap_tools` fetches one
    message per command: with the default bounds (five mails, an allowance of eight) a
    FULL page cost nine commands when the server's greeting carried no capabilities, and
    the read was refused as `budget` — said, never guessed, but the discussion read no
    mail. Inside a bounded read (`current_read_owner()`), the Apple client asks the page
    in ONE `UID FETCH` (`bulk`): five commands whatever the page's size, four when the
    greeting carries the capabilities. The page is then held whole while it is read, its
    size being the bound (`DISCUSSION_RESEARCH_ITEM_LIMIT`); any other read may list far
    more and keeps one message per command.

### What tells less, or no state, and why

`mail_listers` declares each of these, with a reason one can check:

- **A proactive discussion's mail source is `MARKED`** (decision 15): no conversation is
  read. One conversation read per listed message does not fit the physical-call allowance
  of a read on a mailbox that reads one thread per call, and read fail-open it would move a
  version between two reads and stop the run as a changed fact. The guard recomputes that
  arithmetic from the settings: the day the allowance holds a strict conversation read, the
  test fails and says to situate the source. What the mark does not see: an answer drafted
  and never sent; a reply that left no mark (written as a new message, or sent by a client
  that sets none); on Exchange, a reply followed by a forward — the mailbox keeps the LAST
  thing done with a message; and, on Gmail, anything but the reply's own presence in the
  window. Absent, the mark is « not known », never « unanswered ».
- **The radio's sent-mail reader**: the journal's « done » part tells what the listener SENT;
  the sending is the fact told.
- **The contact-card assist**: it reads a contact's latest messages for what their signature
  says; no message is told there as mail to deal with.
- **A routine's mail condition** lists through the briefing's read and opts out
  (`situate_items=False`): a watch waits for an ARRIVAL, answered since or not, and its
  executor's turn reads the state through the chat tool.

## Measurements (real mailboxes, 2026-11-11)

| What | Result |
|---|---|
| Gmail, a thread of 100 messages, every header | 588 KB |
| Same, named headers | 60 KB |
| Gmail, 51 threads at concurrency 5 | 0.9 s |
| Graph, 7 conversations one after the other | 0.85 s |
| Graph, the same 7 in one JSON batch | 0.22 s (0.29 s through the client) |
| Graph, a filter that does not lead with `receivedDateTime` | 4.3 s for 7 |
| Graph, the answer mark after a reply sent through Graph | stamped at once (verb 102) |
| Graph, the dates of two messages created in the same second | equal: « later » is strict |
| Graph, the preview of a reply | one line: 17 characters of the reply, 40 underscores, the quoted header block |
| `preview_own_words`, 600 hostile characters | under 0.5 ms (22 ms before a run of dashes was read once) |

Not measured: iCloud (no account at hand — its header searches are bounded by the door's time
budget), and the Gmail thread read with named headers AND a partial response together (each
was measured alone; the connector was unavailable afterwards).

## Proven on the providers' references, not on a mailbox (decisions 15 and 16)

No Outlook nor iCloud mailbox could be measured for decisions 15 and 16: no test mailbox was
available, and the project's rule since 2026-11-11 is no live proof on a consumer mailbox.
It is built on what the providers document and proven on mailboxes scripted from it, with
the real gateway, source and client above them (`test_mail_evidence_on_mailboxes.py`):

| What it stands on | Source |
|---|---|
| `GET /me/messages/{id}?$expand=singleValueExtendedProperties($filter=id eq '{type} {proptag}')`, each entry `{"id", "value"}` | Microsoft Graph, « Get singleValueLegacyExtendedProperty », « Outlook extended properties overview » |
| One relationship expandable per request on some APIs: the marked read leaves the files out | Microsoft Graph, « Use query parameters » |
| 0x1081 = last verb (102 reply to sender, 103 reply to all, 104 forward), 0x1082 = its time | [MS-OXOMSG] 2.2.1.14, [MS-OXPROPS] |
| `\Answered`: « Message has been answered »; flags are a FETCH data item | RFC 3501 §2.3.2, §6.4.5 |
| `fetch` asks `(BODY.PEEK[…] UID FLAGS RFC822.SIZE)`, one command per message, or one for the whole set (`bulk`) | `imap_tools` 1.15.0, read in its source |
| A FETCH names a sequence set: several messages in one command | RFC 3501 §6.4.5, §6.4.8 |

The expansion string itself was measured on a real Outlook mailbox the same day, on the
conversation read of decision 3 (the mark stamped at once after a reply); on the read of ONE
message it stands on the reference alone.

- **Outlook** (`graph_mailbox.py`, an `httpx` transport under the client's own HTTP client,
  hooks included): the listing answers the selected properties alone, so the defect is
  reproduced as it was — the run stopped as `evidence_changed` on any mail. A page of N
  mails now costs 1 + N requests (6 of the 8 allowed at the default five).
- **iCloud** (`imap_wire.py`, an IMAP4rev1 server behind the very socket `imaplib` opens;
  `imaplib` 3.14 and `imap_tools` run unreplaced): a bounded page costs 5 frames whatever
  its size — CAPABILITY, LOGIN, SELECT, UID SEARCH, ONE UID FETCH (decision 16; one per
  message, so 4 + N, before it and outside a bounded read) — or 4 when the server's
  greeting already carries its capabilities; the read of one message costs 7, or 6. The
  mark adds none, wherever the server states FLAGS in its answer.

**What the discussion models do with the mark (paid proof, 2026-11-11).** The real act —
the context loop, its re-reads, the decision and the wording — ran on the proof account, on
the instance's own slots, over a mailbox simulated at the client boundary (the real
normalisers on provider payloads) and a context store in memory using the store's own
preparation; nothing was published. Three mails, the mail source alone, and every sensitive
topic consented, so that a mail a model files under one could support an opening. Twelve
runs for about nineteen euro cents: a run costs about 1.6 cent there, which bounded the
sample.

| What the mailbox says of the mail that asks for a confirmation | Runs | The context call writes « a request awaiting, no reply known » about it | An opening is made |
|---|---|---|---|
| Nothing | 5 | 5 | 0 |
| Answered, dated (Graph), with its nuance | 5 | 0 | 0 |
| Answered, undated (IMAP), with its nuance | 1 | 0 | 0 |
| Answered, dated, its nuance removed in memory | 1 | 0 | 0 |

The mark is read: the context call no longer stores an answered mail as a pending request,
and in the two runs where the decision still weighed it, it called it « already dealt
with ». What the mark does to an opening's WORDS was not observed: no run opened a
discussion, with or without it — on mail alone the decision stays silent, a pending mail
being an alert's matter. One run of each five ran with no sensitive topic consented. Five
runs an arm tell a direction, not a rate, and the two single runs only that nothing
contradicted it.

**What the one-command page holds (decision 16).** Measured on the same scripted server
(`tracemalloc`, five mails): read in one command, a page peaks at what reading it one
message at a time peaks at PLUS the raw size of its other messages — 39 MB against 28 MB
for mails of 2.7 MB, 197 MB against 142 MB for mails of 13.7 MB. What iCloud's greeting
carries was not read and no longer decides anything: the page fits either way. The page
keeps its order, newest first, on a server that answers a set in mailbox order — what
`imap_tools` reverses; a server answering otherwise would order the page differently and
never change what it holds.

## What a model does with it (paid proof, 2026-11-11)

Both mail connectors of the development instance stopped answering that day (the test
mailbox was locked by its provider, the other's grant was refused at refresh), so the model
proofs ran against a mailbox SIMULATED at the provider boundary, with the real tool, the real
prompts and the instance's own models, on the proof account, for about twenty-four euro
cents in all.

| Question | Before | After |
|---|---|---|
| « What do my unread mails ask of me? », pipeline and ReAct, full detail | 11 of 11 judged answers present the answered mail as awaiting and offer to answer it | 12 of 12 say it was already answered, when and what, and offer to answer the other alone |
| Same, summary detail (a digest and its actions) | 4 of 4 offer to answer it | 4 of 4 say it is settled |
| ReAct, model calls to reach the answer | 3 to 4 (the loop reads the mailbox again) | 2 |
| A reply LIA writes to a mail already answered | repeats or contradicts the earlier agreement | continues from it, in the same register |

The pipeline arm of that proof sent the response prompt and the question alone. Read again
through the response node's own chain — the base prompt with the avatar's tone instruction,
the question, the language reminder — 12 whole answers of 12 still tell the mail answered,
when and what, and offer a reply to the other mail alone.

**A residual, measured and halved.** To an open question (« what do you advise? ») the
OPENING sentence of the pipeline's answer may still count the answered mail among those
« asking for a reply », while the advice and the offers that follow are right. The model
writes its opening from the requests it reads in the mails' own words, before it weighs each
record. Three leads were measured without effect and withdrawn: hiding « reply expected »
from the model view of an answered mail, stating the state first in the record, and a
counting rule added to the prompt block.

What the block of decision 14 does, on one scenario (three mails, one answered). An opening
is counted wrong when it counts the answered mail among those needing a reply or an action,
even when the same sentence goes on to say one is settled:

| Where the block is stated | Wrong openings | Measured on |
|---|---|---|
| Nowhere | 32 of 60 | the node's chain |
| Last context section, after the question (what ships) | 10 of 36 | the node's chain |
| The same words in the last message of the chain | 6 of 24 | the node's chain |
| A system message of its own | 9 of 12 | the node's chain |
| After the tone instruction | 10 of 12 | the node's assembled prompt |
| Right after the data | 11 of 12 | the response prompt alone |

It halves the residual and does not remove it. A first measurement, on the response prompt
alone, had read 2 wrong openings of 24 against 17: the tone instruction that follows the
context in a real turn takes most of that effect away — a prompt is measured as the node
sends it.

## Consequences

- A page of mail costs one more provider read (no model call). Past the budget
  (`MAIL_REPLY_STATE_TIMEOUT_SECONDS`) the page is served without states.
- On Graph and IMAP « the person's own message » means the Sent folder, or a copy found in it:
  a sent message filed elsewhere reads as received. The mailbox's own mark still says a
  message was answered when the reply is not found.
- A reply LIA sends through iCloud is flagged `\Answered` on the original; no copy is filed in
  the Sent folder by the direct reply path (the mailbox-draft path already files one).
- `unanswered` is a fact about the conversation, not a request: only a message that expects a
  reply needs one. The prompts say so.
- A turn that listed an answered mail sends one more section, a line per mail; every other
  turn sends the prompt it sent before.
- The Tools' listing costs one more read per page shown, apart from the listing: its rows
  never wait for it, and a mailbox that cannot tell leaves them unmarked.
- A mark on a cached or archived surface is a durable fact only. « A draft waits » is shown
  where the read is the person's own and fresh (the Tools), and told to a model while the
  reading is current.
- A discussion's mail page on Outlook costs one request per mail beside its listing, where
  it cost one request and could never be used. The marked read of a message carries no
  attachment list: Graph's one expansion is spent on the mark.
- `get_message` takes `mailbox_mark` on the three clients (`EmailClientProtocol`): asked on
  Graph, already in every IMAP read, without effect on Gmail. Every IMAP read now states the
  flag on the message; the door takes it off what it hands on.

## References

- `apps/api/src/core/mail_reply_state.py`, `apps/api/src/core/annotation_projection.py`
- `apps/api/src/domains/connectors/mail_reply_states.py`, `apps/api/src/domains/connectors/mail_listers.py`
- `apps/api/src/domains/connectors/clients/conversation_replies.py`
- `apps/api/src/domains/heartbeat/mail_context.py`, `apps/api/src/domains/agents/emails/previous_reply.py`
- `apps/api/src/domains/agents/emails/answered_mail.py`,
  `apps/api/src/domains/agents/prompts/v1/response_context_sections.txt`
- `apps/api/src/domains/workbench/mail_reading.py` (`read_reply_marks`)
- `apps/api/src/domains/connectors/discussion_sources.py`,
  `apps/api/src/domains/connectors/discussion_projections.py`,
  `apps/api/src/domains/agents/prompts/v1/discussion_evidence_lines.txt` (decision 15)
- `apps/api/tests/unit/domains/proactive_discussions/test_mail_evidence_on_mailboxes.py`,
  `apps/api/tests/unit/domains/connectors/clients/graph_mailbox.py`,
  `apps/api/tests/unit/domains/connectors/clients/imap_wire.py`
- `apps/web/src/lib/mail-reply-state.ts`, `apps/web/src/hooks/useMailReplyMarks.ts`
- `apps/api/tests/unit/domains/connectors/test_mail_listers_guard.py`
