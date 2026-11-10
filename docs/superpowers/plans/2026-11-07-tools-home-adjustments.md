# Tools and home adjustments Implementation Plan

> **For agentic workers:** executed inline by the session that wrote it (owner's rule: no sub-agent), with
> superpowers:executing-plans and superpowers:test-driven-development. Steps use checkbox (`- [ ]`) syntax.
> No commit and no `git add`: the owner stages.

**Goal:** one door for LIA in the mail reader, complete acts, home items that open in their tool, the
usual writing helpers where they were missing, calls and texts among a contact's exchanges, and a
selection bubble on a mail's words.

**Architecture:** the Tools' two bounded contexts stay apart: `domains/workbench/` (by hand, no model)
and `domains/tool_assists/` (one click, one call, one proposal). The home page reaches the Tools through
their addresses and their routes; it gains no model path. New model work is new `ToolAssist` members
behind `run_assist`.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 (async), Next.js 16, React 19, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-07-tools-home-adjustments-design.md`

**Ledger:** `.superpowers/sdd/2026-11-07-tools-home/progress.md` (rulings, evidence, resume point).

## Global Constraints

- CLAUDE.md (root and `apps/web/`) applies in full: typed contracts, no raw `HTTPException`, structlog,
  no PII above DEBUG, six locales with strict parity, `ToolForm` for every form of the Tools,
  `NativeSelect` for every list, a field never under 16 px on touch, `generateUUID()` for page keys.
- A prompt lives in `domains/agents/prompts/v1/`, is named in `PromptName`, states what the code
  enforces, and every `{placeholder}` has a producer; third-party words reach a model through
  `wrap_external_content`.
- A new tunable value: constant in `core/constants.py`, setting in `core/config/workbench.py`, the env
  templates (root and the four demonstrator ones), published to the page when the page needs it.
- Every interactive change: light, dark, OLED; 390 px and 1440 px; keyboard and focus; six languages.
- Direct acts (home, Tools) write no register row; an assist files its read and bills its spend through
  `run_assist` (ADR-372).
- Do not touch the files the ADR-373 lot changed under `domains/telephony/`, `domains/live/`,
  `domains/voice*`; add to the shared files (`locales/*`, `core/constants.py`, `prompt_loader.py`)
  without rewriting their other hunks.

## Review Focus

- A message with no plain-text body, or only an HTML one → the forms are still read (the body the
  client cleaned), never refused for an empty body when the headers carry the facts.
- A home card item cached before this change (no calendar or list id) → the click falls back to the
  tool's default view, never a broken page.
- A contact whose numbers are written nationally while the calls and texts were stored in E.164 (or the
  reverse) → the history finds them under both spellings.
- A selection that crosses the text view's edge, or is made on a phone where tapping clears it → the
  quote is frozen when the toolbar renders, never read again at the click.
- The demonstrator (Tools off, assists off) → every click and menu line still leads somewhere that
  exists.

---

## Lot 1 — Mail: one door, complete acts, dictation

### Task 1.1: Complete extraction (backend)

**Files:**
- Modify: `apps/api/src/domains/tool_assists/actions.py`, `schemas.py`, `router.py`, `mail.py` (brief day)
- Modify: `apps/api/src/domains/agents/prompts/v1/tool_assist_task_prompt.txt`, `tool_assist_event_prompt.txt`
- Test: `apps/api/tests/unit/domains/tool_assists/test_actions.py` (and the router's)

**Interfaces:**
- Produces: `MailTaskAssist(MessageAssist)` with `lists: list[ListName]` (the `TaskSentenceAssist`
  bound and validator, shared) and `focus: OptionalInstruction`; `MailEventAssist(MessageAssist)` with
  `focus`.
- Produces: `task_from_message(run, message_id, clock, lists, focus) -> ProposedTask`,
  `event_from_message(run, message_id, clock, focus) -> ProposedEvent`.
- Produces: `ProposedTask.importance: Literal["high"] | None`; `ProposedEvent.conference: bool`.
- Produces: `form_source(message: dict[str, Any]) -> str` — from, to, cc, date, subject, attachment
  names and the first part of the body, wrapped as external content.

- [ ] Tests first: `test_form_source_names_every_header`, `test_task_importance_only_high_is_kept`,
  `test_task_lists_reach_the_prompt`, `test_focus_reaches_the_prompt_or_nothing`,
  `test_event_conference_flag_is_kept`, `test_mail_task_route_takes_lists_and_focus` (422 past the bound).
- [ ] Implement; prompts rewritten (complete notes and description, the importance rule, the video link
  in the place, the conference rule, Q1 guests, the focus line).
- [ ] `pytest tests/unit/domains/tool_assists -q` green; prompt placeholder guards green.

### Task 1.2: « New task » form (frontend)

**Files:**
- Create: `apps/web/src/components/workbench/tasks/NewTaskDialog.tsx`
- Modify: `TasksTool.tsx` (handoff opens the dialog), `TaskDetailFields.tsx` (`TaskDetails` takes
  `details: Pick<WorkbenchTask, 'importance' | 'reminder' | 'repeat'>`), `hooks/useWorkbenchTasks.ts`
  (`NewTaskBody` + `importance`, `reminder`, `repeat`), `lib/workbench/handoff.ts`
  (task: `list_name?: string | null`, `importance?: 'high' | null`)
- Test: `components/workbench/tasks/__tests__/NewTaskDialog.test.tsx`, `TasksTool.test.tsx`

- [ ] Tests first: the handoff opens the dialog with every value shown; Save posts `list_id` of the named
  list, `due`, `notes`, `importance` (To Do only); a refusal keeps the form; Cancel creates nothing;
  Google shows no To Do field; the title is required.
- [ ] Implement through `ToolForm`, `NativeSelect`, `FieldAssist kind="task_notes"`.

### Task 1.3: Reader and summary (frontend)

**Files:** `mail/MailTool.tsx`, `mail/MessageReader.tsx`, `assist/useMailAssist.tsx`,
`assist/MailSummaryView.tsx`, `lib/workbench/assist.ts`, a lists reader for the mail page.
- [ ] Tests first: « … » holds no task/event line while assists are offered and holds both when they are
  not; the summary's task button asks `/mail/task` with `focus` and the lists, then hands a complete
  task; the event line sends no list; the ticket brief carries the received day.
- [ ] Implement.

### Task 1.4: Dictation and compose with LIA (frontend)

**Files:** `assist/ComposerAssist.tsx`, `assist/WritingAssist.tsx` (`InstructionForm` microphone),
`lib/workbench/handoff.ts` (compose: `assisted?: boolean`), `mail/MailTool.tsx`, `mail/Composer.tsx`.
- [ ] Tests first: the subject list offers « Dictate » where the body's does; an instruction box offers a
  microphone where dictation is offered and none elsewhere, the words joining what is typed; a compose
  handoff with `assisted` opens the composer on « Write from an instruction ».
- [ ] Implement (the recorder mounts on press only).

### Task 1.5: Lot 1 close

- [ ] Docs: `TOOL_ASSISTS.md`, `WORKBENCH.md`, ADR-372 amendment (R1, R2, focus, dictation), FAQ ×6.
- [ ] Gates: `task lint`, `task test:backend:unit:fast`, `task test:frontend`, affected e2e journeys.
- [ ] Real proof on the proof account (one mail proposing a meeting, one asking for an urgent act).
- [ ] Cold exhaustive review, ledger, report.

## Lot 2 — Home: items open in their tool, fuller menus, birthdays everywhere

### Task 2.1: Card items carry their ids (backend)

**Files:** `domains/briefing/schemas.py`, `formatters.py`, `fetchers.py`, `connectors/birthdays.py`,
`heartbeat/context_aggregator.py` (consumer), cache schema versions; `types/briefing.ts`.
- Produces: `AgendaEventItem.calendar_id`, `conference_url`; `TaskItem.list_id`;
  `BirthdayItem.contact_id`, `email`, `phone`; the TS mirror for mail and document ids.
- [ ] Tests first: ids are present; `@default` resolves to a real list id; birthdays are read from the
  active contacts provider of each of the three kinds (D1); a cached payload without the new fields still
  parses.

### Task 2.2: Tools open what the home names (backend + frontend)

**Files:** `workbench/tasks_router.py` + service (`GET /workbench/tasks/task`), `TasksTool.tsx`
(off-page task), `calendar/useCalendarScreen.ts` (alias `primary` resolved to the real calendar).
- [ ] Tests first: a task not on the page opens; an unknown one says `item_gone`; `?cal=primary&event=`
  opens the event in the primary calendar and the address takes the real id.

### Task 2.3: Cards (frontend)

**Files:** `components/dashboard/cards/*`, `CardItemRow.tsx` (navigation by link), a home reminder host.
- [ ] Tests first: each row's destination (Tools on, Tools off); each card's menu (≤ 5, order, gating by
  data); each direct act calls its route and refreshes the card; SMS block asks first.
- [ ] Implement; e2e journey home → each tool.

### Task 2.4: Lot 2 close — docs (`BRIEFING_DOMAIN.md`, `WORKBENCH.md`, ADR-369 amendment), FAQ ×6, gates,
real proof, cold review, ledger, report.

## Lot 3 — Contacts

### Task 3.1: Contact from a sentence; notes written with LIA

**Files:** `tool_assists/contact_card.py` (or a sibling), `catalogue.py` (`CONTACT_FROM_WORDS`),
`router.py`, prompt `tool_assist_contact_words_prompt.txt`, `text.py` (`WritingKind.CONTACT_NOTES`),
`contacts/ContactEditor.tsx`, `assist/CardAssist.tsx` (a line of a list).
- [ ] Tests first: a sentence fills the form (addresses and numbers held to what is written); nothing of
  the kind is `assist_not_found`; the title icon lists both lines; Notes offers the writing list.

### Task 3.2: Call through LIA; D2; E2

**Files:** `assist/useContactAssist.tsx`, `assist/lines.ts`, `relations/RelationDetailPanel.tsx`.
- [ ] Tests first: one call line per number when telephony is offered and its connector active, none
  otherwise; the chat receives the words unsent; Relations hides « Call » when the instance switch is off;
  « Write to them with LIA » hands an assisted compose.

### Task 3.3: Calls and texts among the latest exchanges

**Files:** `workbench/contacts_history.py`, `schemas/contacts.py`, `contacts_router.py` (`no-store`),
`core/constants.py` + config (`WORKBENCH_CONTACT_HISTORY_MAX_PHONES`, the calls scan bound), telephony
and SMS read helpers (new modules, no change to the ADR-373 files), `ContactHistory.tsx`, `ContactDetail.tsx`.
- [ ] Tests first (unit + integration on PostgreSQL): both spellings of a number find its calls and texts;
  only third-party calls; never the number in the answer; the scan bound is stated; sources say
  `disabled` (switch off, connector off) and `unavailable` (read failed); a contact with numbers alone.

### Task 3.4: Lot 3 close — ADR-357 amendment, `WORKBENCH.md`, `TOOL_ASSISTS.md`, FAQ ×6, gates, proof,
review, ledger, report.

## Lot 4 — Selection bubble

### Task 4.1: Passage assist (backend)

**Files:** `tool_assists/text.py` (or `passage.py`), `catalogue.py` (`TEXT_PASSAGE`), `schemas.py`,
`router.py`, prompt `tool_assist_passage_prompt.txt`.
- Produces: `POST /tool-assists/text/passage` `{passage, act: explain|translate|simplify|ask, question?}`
  → `TextAnswer`; the passage wrapped as external content; the reader's language.
- [ ] Tests first: each act's prompt; `ask` requires a question; bounds; an injected order stays data.

### Task 4.2: Selection toolbar and bubble (frontend)

**Files:** `hooks/useTextSelection.ts` (a scope parameter), `components/workbench/assist/SelectionAssist.tsx`
(toolbar + bubble), `MessageReader.tsx` (text view scope; « Act on a passage »), `viewers/*` (E5).
- [ ] Tests first: toolbar on a selection inside the scope only; frozen quote; each act; the bubble's
  states (running, refused, done), copy, close, Escape, focus return; the task proposal adds through the
  Tasks route; the event opens the editor; 390 px layout.
- [ ] e2e: select → explain → bubble, keyboard path, phone width.

### Task 4.3: Lot 4 close — docs, FAQ ×6, gates, proof, review, ledger, report.

## Lot 5 — Extras E1, E3, E4

**Files:** `assist/useEventAssist.ts` (E1), `tasks/TasksTool.tsx` + task acts (E3),
`assist/useFileAssist.tsx` (E4).
- [ ] Tests first for each line's gating and handoff; docs, FAQ ×6, gates, review, ledger, report.

## Final

- [ ] `task ci:fast` on a frozen export of the whole tree, full e2e, final self-assessment, report.
