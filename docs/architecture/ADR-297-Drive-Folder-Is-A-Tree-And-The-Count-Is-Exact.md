# ADR-297 — A linked Drive folder is a tree, and a sync past the threshold states its exact count

**Date**: 2026-09-17
**Status**: Accepted
**Amends**: ADR-261 (push-driven incremental Drive sync), ADR-262 (synced sources of a space), ADR-185 (a count is exact or does not exist), ADR-184 (a bound is published), ADR-263 (a read is recorded)

## Context

Google Drive lists ONE level per call (`'{id}' in parents`): a source linked
to a folder indexed the files sitting directly in it and never a sub-folder's.
The owner asked for the sub-folders to be indexed too, with a guard against
over-indexing: past ten files, the person sees the exact number of files
that are about to be indexed and confirms or cancels.

Two facts shaped the design:

- the push path (ADR-261) routed a change on its file's DIRECT parent
  (`_touched_sources`): with recursion, a change in a sub-folder would have
  been invisible to the push;
- two sources of one space dedupe documents by `drive_file_id` alone: a
  folder linked INSIDE an already linked tree would have had its files
  discarded and re-created by the other source at every synchronisation.

## Decision

- **One walk, shared by the synchronisation and the count.**
  `rag_spaces/drive_walk.py` walks the folders breadth-first, bounded twice
  (`RAG_DRIVE_MAX_FILES_PER_SYNC`, `RAG_DRIVE_MAX_FOLDERS_PER_WALK`); a walk
  that hits a bound says so (`truncated`) so every figure derived from it is a
  floor, never a total. A shortcut is neither listed nor followed, a folder
  reached twice is walked once, an unreadable sub-folder is counted and
  skipped — the root being unreadable is the one error. The synchronisation
  reads the tree, records ONE consultation for the act (`space_read`, which
  the background sync never called before), and prunes what left the tree.
- **The walked folder set travels with the source** (`rag_drive_sources
  .folder_ids`, JSONB, migration `b8d4f6c0e2a3`, reassigned as a new list on
  every write). The push routes a change on that set — the root alone before
  the first walk — and lets the set follow the feed: a folder created under
  the tree joins it so the files created inside it, later in the same feed,
  route too; a trashed one leaves it (Drive reports the folder, not each
  descendant; the next full sync prunes the documents).
- **A nested link is refused** (`409 {code: drive_folder_nested}`): the
  candidate's ancestors against every linked root, and each linked root's
  ancestors — plus its walked set — against the candidate, both readings
  bounded (`RAG_DRIVE_MAX_ANCESTOR_DEPTH`). Siblings stay linkable.
- **The count is computed by the code that indexes.** `GET
  …/drive-sources/{id}/preflight` walks the tree and classifies every file
  with the ingest's own predicates (`is_supported_drive_file`, `is_unchanged`
  — extracted from `ingest_drive_file` so the two cannot disagree) under the
  space's document cap: `new`, `modified`, `unchanged`, `unsupported`,
  `over_capacity`, `to_index = modified + new within capacity`, the folders,
  the unreadable ones, `truncated`, and the published `threshold` and bounds.
  The threshold is `rag_drive_sync_confirm_threshold` (default 10), a
  courtesy against over-indexing; the hard bounds stay the space's document
  cap and the walk's own.
- **The confirmation is asked at the click**, not at the link (linking never
  synchronised): the Sync button asks the preflight, and past the threshold an
  alert dialog states the exact figures — « at least » when the walk was cut,
  the new files the space cannot hold named — and posts the sync only on
  « Index them »; a count the API cannot compute starts nothing.

## Consequences

- Measured on dev 2026-09-17 against a real Drive: the walk descended six
  folders from the root under a six-folder bound and reported the cut.
- The push path's per-source routing set is a persisted list rebuilt at every
  full synchronisation; sources linked before this ADR route on their root
  alone until their next synchronisation.
- **The consultation was recorded into nothing** (found 2026-09-17, after
  delivery): the register keeps only what a published collector gathers, and
  no act of a space — a link from the settings page, a background
  synchronisation, a push — ever published one, so every `space_read` since
  ADR-262 was dropped by the sink in silence (zero `space:*` rows on dev,
  ever). `space_read` now opens a run of its own when none is active
  (`consultation_collector`, the seam the briefing and the debrief already
  use; `collector_is_active` joined the seam so a read inside a turn still
  joins the turn), and the Gmail label sync reads under it too
  (`mail_sync.sync_label_background`, the mirror of the Drive one). Measured
  on dev: one `space:mail` row per act, `scheduled`, under `space_mail_<id>`.
- The Drive id shape is now validated (`^[A-Za-z0-9_-]+$`) at the link door.

## Rejected

- **A server-side confirmation gate** (a signed preflight token, or a second
  walk inside the sync request): the threshold protects the person's own
  quota and space, both already bounded by the server; a gate would have
  added a token or a synchronous walk for a courtesy.
- **Storing the relative path in the document's name**: no column carries a
  path, homonyms in two sub-folders stay distinct by `drive_file_id`.
- **Walking at push time to route a change** (ancestors per change): a push
  fires often and a persisted set costs nothing to read.
