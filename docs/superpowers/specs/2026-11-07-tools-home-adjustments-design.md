# Tools and home: one door for LIA, complete acts, items that open where they live

**Status**: approved by the owner on 2026-11-07 (analysis in the chat, rulings Q1–Q5, three reactions).
**Date**: 2026-11-07.
**Builds on**: [ADR-369](../../architecture/ADR-369-Workbench-The-Persons-Own-Door-To-Their-Services.md)
(the Tools, by hand), [ADR-372](../../architecture/ADR-372-What-LIA-Does-From-The-Tools-A-Click-A-Call-A-Proposal.md)
(what a click asks of LIA), [ADR-357](../../architecture/ADR-357-Phone-Ingestion-And-Personal-SMS-Archive.md)
(the SMS archive).

## 1. Intent

The Tools shipped in v4.3.0–v4.5.0. Using them, the owner found four kinds of friction:

1. The home page's cards still send a click to the chat, although every item now has a screen of its own.
2. In the mail reader, the same two acts (« Make it a task », « Make it an event ») exist twice, once
   without LIA in « … » and once with LIA under « Ask LIA ». And what LIA fills in is thinner than the
   message: a task handed to the Tasks tool lands in the quick add with its title alone, its due day and
   notes saved unseen, its list lost.
3. Some usual helpers are missing where they are expected: « Dictate » in a new mail's subject and in
   the instruction boxes, writing with LIA in a new contact, calling a contact through LIA, calls and
   text messages among a contact's latest exchanges.
4. The chat lets a person act on a selected passage. A mail cannot, and leaving the mail for the chat
   breaks the reading.

## 2. Rulings

| # | Ruling (owner, 2026-11-07) |
|---|---|
| R1 | Every act of LIA in the mail reader goes through « Ask LIA » alone. |
| R2 | An act LIA prepares is complete: it uses everything the message says. |
| Q1 | An event read in a mail proposes the sender as a guest when the mail proposes or confirms a meeting with the reader, and the other people it names with an address. Saving sends them an invitation; the form shows them and one click removes them. |
| Q2 | On the home page, « Mark as done » and « Postpone » become direct acts (no chat, no token, no register row), as in the Tasks tool. |
| Q3 | The original layout of a mail stays an opaque, isolated frame. The selection bubble works on the text view; a line « Act on a passage » switches to it. |
| Q4 | Two neighbouring defects are fixed too: birthdays read from the active contacts provider, whichever it is (D1); Relations offers « Call » only when the instance offers telephony (D2). |
| Q5 | All five extras are in: write to an event's guests with LIA (E1), write to a contact with LIA (E2), block a slot for a task (E3), send a file by mail with LIA (E4), the selection bubble in the file viewers too (E5). Order of the lots: the engineer's call. |
| Reaction 1 | A calendar's default is the one its connector names; when it names none, the account's primary calendar, under its real id. |
| Reaction 2 | A click opens the Tools whenever the instance offers them. The only case they do not is the operator's switch (`WORKBENCH_ENABLED=false`, the demonstrator); there the click keeps today's chat. |
| Reaction 3 | A selected passage may travel from the page: it is the person's explicit act. The server still hands it to the model as external content, which costs nothing and keeps the injection defence. |

## 3. What changes

### 3.1 Mail (lot 1)

- « … » of the reader no longer lists « Make it a task » and « Make it an event » when the assists are
  offered. Where they are switched off, those two lines stay: they are then the only way out.
- LIA reads a message for a form with its full headers (from, to, cc, date, subject, attachment names)
  and is asked for complete values:
  - **task**: notes that let the person act without reopening the mail (who asks, what exactly, figures,
    references, amounts, addresses, links, the deadline as written); one of the person's lists when the
    mail points to one (the lists are sent with the request); `high` importance when the mail says it is
    urgent.
  - **event**: a complete description (agenda, references, access details); a video link stands in the
    place when there is no physical place; the « video meeting » box is ticked when the mail asks for a
    video call without a link (where the provider creates one); guests per Q1.
  - the link back to the message still ends the notes or the description.
- A task handed from another tool opens a new **« New task »** form in Tasks, filled in: title, notes,
  due day, list, and where the provider keeps them (To Do) importance, reminder and repetition. The
  quick add stays for a task typed by hand.
- The summary's « Make a task » button asks LIA for **that** action's complete task (a focused read of
  the message: one short call, its cost said), then opens the same form. The summary itself is the
  assistant's digest and does not change.
- The ticket brief of a mail names the day it was received, so the ticket's run finds that message.
- « Dictate » is offered in the composer's subject list as in its body list, and every instruction box
  of the Tools takes dictation (a microphone beside « Propose »).
- A tool can hand the mail a message to write **with LIA**: the composer opens on « Write from an
  instruction » (used by E1, E2, E4).

### 3.2 Home (lot 2)

- A click on an agenda, mail, task, document or birthday item opens it in its tool (SMS keeps its own
  page). The demonstrator, whose Tools are switched off, keeps the chat.
- The cards carry what their tool needs: the calendar and event, the task list and task, the message,
  the file, the contact. An alias (`primary`, `@default`) is resolved to the real id.
- The Tasks tool opens a task that is not on the page it loaded (a route reads one task).
- Each card's « More actions » holds at most five acts, direct ones first, then what LIA does:

| Card | Direct | With LIA |
|---|---|---|
| Agenda | Route (when there is a place) · Join the video call (when there is a link) · Remind me | Prepare this meeting |
| Mail | Mark as read · Archive · Tell me when they reply | Summarise · Propose a reply |
| Task | Mark as done · Postpone to tomorrow · Remind me | Help me move forward |
| Document | Download · Send by mail · Open in Drive or OneDrive | Summarise · Ask a question |
| Birthday | Write a mail · Call (when there is a number) · Remind me | Birthday message |
| SMS | Call the sender · Add to contacts · Block the sender · Remind me | — |

- Direct acts call the Tools' routes: no model, no register row (ADR-369 D5). An act that removes the
  item from the card (read, archived, done, postponed) refreshes the card.
- **D1**: birthdays come from the active contacts provider (Google, Microsoft or Apple), with the
  contact's id, a mail address and a phone number for the menu.

### 3.3 Contacts (lot 3)

- The new-contact form's title icon becomes « Write with LIA »: « Describe the contact in a sentence »
  (new assist; the sentence may be dictated) and « Read a business card ». Notes take the usual writing
  list (write from an instruction, fix, shorten, more formal, warmer, translate, dictate), on a new
  contact and on a change alike.
- « Ask LIA » on a contact offers « Call {name} » (one line per number, its kind named) when the
  instance offers telephony, the telephony connector is active and the contact has a number. It opens
  the chat on « Call {name} on {number} to: », unsent: the person says why, and the chat's confirmation
  card places the call. **D2**: Relations' « Call » follows the same instance switch.
- « Ask LIA » on a contact offers « Write to them with LIA » (E2).
- « Latest exchanges » also reads the contact's numbers and shows the five latest calls LIA placed to
  them (when, outcome, length, purpose; never the number) and the five latest text messages received
  from them (excerpt). Each source says why it has nothing, as mail and meetings already do. The
  response is never cached (ADR-357). A contact with numbers and no address now has exchanges too.

### 3.4 Selection bubble (lot 4)

- In a mail's text view, a selection raises a toolbar: Explain · Translate · Simplify · Ask a question ·
  Make it a task · Make it an event · Remind me.
- The answer stands in a small rounded window anchored to the passage (copy, close, cost, Escape), never
  in the chat. A question is typed in the window and answered there. A task shows its proposal with
  « Add » and « Edit in Tasks »; an event opens the calendar's editor.
- In the original layout, « Ask LIA » offers « Act on a passage », which switches to the text view and
  says to select.
- **E5**: the same bubble in the Files' text and Markdown viewers (no message around them: a task or an
  event is read from the passage alone).

### 3.5 Extras (lot 5)

- **E1** — an event's « Ask LIA » offers « Write to the guests with LIA »: the composer, addressed to
  the guests, the subject named after the event, on « Write from an instruction ».
- **E3** — a task's « … » offers « Block a slot »: the calendar's editor, filled from the task (title,
  notes, the due day), no model.
- **E4** — a file's « Ask LIA » offers « Send by mail with LIA »: the composer with the file attached,
  on « Write from an instruction ».

## 4. Non-goals

- No call is placed from the Tools without the chat's confirmation card.
- No sent text message is read: LIA keeps none.
- The phone's own call log is not read: only the calls LIA placed exist.
- The original layout's frame stays as isolated as it is (Q3).
- The mail summary (digest) keeps its shape: it is the assistant's too.

## 5. Constraints

- Inline execution, TDD, a cold exhaustive review at the end of each lot; no commit and no change to
  the git index: the owner stages.
- The working tree also holds another session's uncommitted lots (ADR-373, memory bounds lot 2). The six
  locale files, `core/constants.py` and `prompts/prompt_loader.py` already carry their changes; the
  telephony modules they changed are not touched here.
- Every user-facing feature gets its FAQ entry in the six languages; every new string exists in the six
  languages; every new setting has its constant, its env templates (the four demonstrator ones
  included) and its published bound.
- Real proofs run on the proof account, with production's slots held in memory, under 0.20 EUR.
