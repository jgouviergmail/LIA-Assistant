# ADR-259 — Meeting template library, automatic selection and reformatting

- **Status**: Accepted
- **Date**: 2026-09-03
- **Related**: ADR-258 (meeting recording and structured minutes), ADR-129
  (entity-as-job durability), ADR-184 (published constraints), ADR-185 (exact
  counts), ADR-207/208 (action altitudes, row actions), ADR-226 (document
  generation), ADR-245 (one stored shape per provider)

## Context

ADR-258 shipped one template per user — the structure of the minutes was the
user's, and a library was announced for later. Using the feature for a day
surfaced what that single template could not do, and reading the code
surfaced what the release had left in the way. Every fact below was verified
in the code or measured before design (spec:
`docs/superpowers/specs/2026-09-03-meeting-template-library-design.md`):

1. **The minutes e-mail went through the user's connector.** `delivery.py`
   resolved the active e-mail provider and refused with
   `email_connector_missing` when there was none, while the platform already
   had `APPLICATION_SMTP_FROM` and an `EmailService` — whose SMTP exchange was
   synchronous, and called from an async path.
2. **A transcript had no section kind.** The four kinds (paragraph, bullets,
   topics, action items) all summarize; nothing could hand back the exchange
   itself, cleaned or professionalized, which several of the owner's model
   files (`modeles.txt`) required.
3. **The synthesis output was bounded by `max_tokens=8000` on the
   `meeting_synthesis` slot**, overridable in the database per deployment: a
   rewrite of a whole transcript does not fit in one answer, and a JSON
   truncated mid-array is not repairable by the permissive-to-strict fold.
4. **A regeneration could stay stuck.** `begin_regenerate` set
   `stage=synthesizing` on a READY row, and no reaper cleared it after a hard
   kill: the page showed « rebuilding » forever and refused every later rebuild.
5. **Chunks carry `space_id` denormalized** (`rag_chunks.space_id`, read by
   retrieval): a document moved by updating its row alone keeps answering
   from its old space.
6. **The chat shell's height arithmetic ignored the recording banner**: a
   banner inserted in the flow pushed the composer below the fold for the
   whole meeting (measured 2026-09-03).

## Decision

### A template has an identity, a category and a home

- **`TemplateRef`** (`domains/meetings/template_ref.py`) names a template
  everywhere: `builtin:<key>` for the catalogue, `user:<uuid>` for a row.
  Meetings, preferences and requests store and exchange refs, never rows,
  so a built-in needs no database row and a deleted user template leaves a
  dangling ref the readers know how to fall back from (`template_snapshot`
  + `template_name` on the meeting).
- **30 built-in templates in seven categories** (`template_catalogue/`),
  their names, descriptions and section labels in the data module
  `core/i18n_meeting_templates.py` for the six languages, with boot-time
  completeness asserts (ADR-085): every key named in every language, every
  section within the bounds `MeetingTemplateUpdate` enforces. What the
  validator can reject, the catalogue cannot ship.
- **A fifth section kind, `transcript`**, is rewritten part by part
  (`transcript_rewrite.py`): the turns are split under
  `MEETINGS_REWRITE_PART_CHARS`, each part is rewritten in its own call with
  an output budget derived from the slot's effective `max_tokens`
  (`MEETINGS_REWRITE_OUTPUT_SAFETY`), a missing index splits the part once,
  a suspiciously short answer (`MEETINGS_REWRITE_MIN_RATIO`) is retried once.
  Transcript templates are **never chosen automatically**: they are long and
  paid like a whole meeting, so they are an explicit choice after the fact.
- **The library is a page** (`/dashboard/meetings/templates`), not a
  settings accordion: thirty entries are content the user browses. A
  built-in can be previewed and duplicated; a user template edited and
  deleted; the cap (`MEETINGS_MAX_USER_TEMPLATES`) is **stated** on the
  toolbar (`aria-disabled` and a sentence), never hidden.

### The format is chosen once, in one place, and the meeting says which

`template_resolution.decide_template` is the ONE precedence: the meeting's
own ref (set while live, from the banner) → the preference's default → the
model's choice among the auto-selectable candidates over a transcript excerpt
(`MEETINGS_TEMPLATE_AUTO_EXCERPT_CHARS`), accepted above
`MEETINGS_TEMPLATE_AUTO_MIN_CONFIDENCE` → the default built-in. Every outcome
is counted (`meeting_template_selection_total{outcome}`, Grafana
`27-meetings`) and stored on the row: `template_ref`, `template_name`,
`template_selection` (auto | user | preference) and the model's one-line
reason, which the page shows next to the format. A regeneration reads the
**meeting's** ref, never the user's current default — the coupling ADR-258
had left.

### Reformatting: in place, or new minutes from the same transcript

`POST /meetings/{id}/reformat` `{template_ref, mode: replace | new}` writes
the minutes again from the stored transcript. `replace` reuses the durable
regeneration (`regeneration.py`, one lease, one stage); `new` creates a
second meeting row pointing at the source (`source_meeting_id`, FK SET
NULL), READY with no report while the server writes, indexed as **its own
RAG document** in the « Réunions » space. Nothing is ever a « copy »: the
vocabulary is « new minutes from this transcript », because the transcript
is the same and the minutes are not. A READY row whose write failed stays
explainable (`MeetingPendingPanel`: the error, a retry on the same template,
a delete), and the reaper now clears a regeneration whose lease expired
(`clear_stale_regenerations`) — fact 4 closed.

### The minutes leave from the platform

`send_minutes_email` sends from `APPLICATION_SMTP_FROM` through
`EmailService`, whose SMTP exchange now runs in `asyncio.to_thread`; the
subject is `<localized « Minutes »> · <title>`. The connector path and its
refusal code are gone. INFO logs carry counts and ids, never the recipient
or the subject.

### Recording surfaces (owner decision, 2026-09-03)

Recording is not an attachment: the composer's « + » is a file picker again.
On desktop the header carries one toggle (`MeetingRecorderControl`,
`aria-pressed`, a pulsing disc while live); on a phone the logo menu gains a
dynamic « Record / Stop » entry and its trigger pulses red during a
recording; the sticky banner stays on every dashboard page and publishes its
measured height (`--meeting-banner-h`) so the chat shell subtracts it —
fact 6 closed. While live, the banner offers the format ahead of processing;
the choice is saved on the meeting at once and remembered in the recorder
store, so a reload shows what the server holds.

### Knowledge spaces: download, archive, move, bulk delete

`document_access.py` is the only place that turns a row into a path (root /
owner / space / stored name, each segment resolved and contained) and the
one ownership check every operation shares. `document_ops.py` adds a
download, a zip archive of a selection (members named after the original
filenames, deduplicated, a `_missing.txt` listing files gone from the disk,
refused beyond `RAG_SPACES_ARCHIVE_MAX_MB`), a move and a bulk delete. A
batch never fails as a whole for one document: every id is reported done or
skipped with a stable reason the UI localizes. A move updates the row **and
its chunks** (fact 5), commits, THEN moves the file; a rename that fails
reverts both and reports `document_move_failed` for that document only. It is
refused wholesale while a reindex runs, and Drive-synced or meeting-owned
documents stay where their owner put them.

## Consequences

- Six new migration columns and one dropped (`is_default`), no data
  migration: no customized template existed before this release, so every
  account starts on automatic selection (owner decision).
- The catalogue is code, its words are data: adding a built-in is one entry
  and six names; a missing name fails the boot, not the user.
- A transcript template costs one call per part plus retries; the dialog
  says so before the user asks for it, and the meeting's cost line includes it.
- The selection bar, the row actions with a link, and the pure selection
  helpers are shared between meetings and knowledge spaces
  (`ui/selection-bar.tsx`, `ui/row-actions.tsx` `href`, `lib/selection.ts`):
  the next list with a selection composes them rather than copying them.

## Rejected alternatives

- **Copying the minutes row** for a reformat: a copy of the minutes is not
  what the user asked for — the transcript is the shared thing, so the new
  row points at its source and is written afresh.
- **Automatic selection including transcript templates**: the most expensive
  outcome would have been chosen by a model on an excerpt.
- **Moving a document by updating its row only**: retrieval reads the
  chunks' `space_id`; the document would have kept answering from its old
  space.
- **A per-screen mobile action dialog and hover-revealed row buttons** for
  the documents: ADR-208 already decided that a list row exposes its actions
  one way.
