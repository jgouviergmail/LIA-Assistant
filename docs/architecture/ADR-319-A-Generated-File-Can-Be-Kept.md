# ADR-319 — A generated file can be kept past its deadline, and a chat card states the lifetime its file has now

**Status**: accepted — 2026-09-25 (owner request: in « My generated files », let a person keep some images, documents and screenshots — no automatic deletion; owner arbitration Q3: a ceiling per account in files and in megabytes, and « stop keeping » means a fresh deadline from now, never an immediate deletion)
**Amends**: ADR-279 (the generated-files gallery — « the retention stays », « a person who wants to keep a file downloads it »), ADR-316 (sharing a generated image — its per-sender lock becomes a shared seam), ADR-318 (`find_generated_files_tool` reports what is kept), ADR-185 (exact counts), ADR-184 (published bounds)

## Context

ADR-279 gave the files LIA produces a gallery and made their deadline visible, and
decided on purpose that the gallery would not push it back: every attachment carries
`expires_at = now + ATTACHMENTS_TTL_HOURS`, and a periodic sweep deletes what has passed
it. A person who wanted to keep a report had one way out — download it.

The owner asked for the other way: keep, from the gallery, the few files that matter,
and have the automatic cleanup leave them alone.

Measured before the change:

1. **`expires_at` was `NOT NULL` on every row**, and six readers assumed a deadline
   exists: the gallery's sort and filters, the ADR-318 tool, the ADR-316 share check, the
   image and document producers, and the chat cards.
2. **The sweep read, then deleted.** `get_expired` loaded every expired row, then each
   one was removed from disk and deleted in turn. A file kept between the read and the
   delete would have been removed anyway, and a disk that refused left a row pointing
   at a deleted file or a file with no row, depending on which half failed.
3. **A chat card carries the deadline written when the file was produced**, in the
   message metadata. Once a file can be kept or deleted from the gallery, that stored
   date is a claim about a state that no longer exists: a kept image announced
   « expired » and lost its share button; a deleted one announced « available until … »
   over a broken image.

## Decision

1. **A kept file has NO deadline.** `attachments.expires_at` becomes nullable (migration
   `6c871f348887`); `NULL` means kept. The sweep deletes `expires_at <= now()`, and a
   comparison with `NULL` is never true: the cleanup cannot reach a kept file by the
   semantics of SQL, not by a filter someone must remember to write. A CHECK
   (`ck_attachments_upload_expires`) keeps the invariant an upload relies on — an upload
   always has a deadline; keeping is a gallery act and the gallery lists what LIA
   produced. The downgrade gives every kept file the deadline a release would give it,
   then restores `NOT NULL`.

2. **The sweep is ONE conditional statement.** `AttachmentRepository.delete_expired`
   runs `DELETE … WHERE expires_at <= :now RETURNING file_path`; the service commits,
   then removes the files off the event loop. The condition is evaluated by the
   statement that deletes, never by an earlier read, so a keep that commits first wins:
   under READ COMMITTED the DELETE re-checks the row it waited for and finds `NULL`.
   Rows first, files after the commit: a crash between the two leaves an orphan file,
   never a card pointing at nothing. Proven with two actors on real PostgreSQL
   (`tests/integration/domains/attachments/test_keep_db.py`).

3. **Two ceilings per account, published and exact.** `GENERATED_ASSETS_KEEP_MAX_FILES`
   and `GENERATED_ASSETS_KEEP_MAX_MB` bound what one account keeps (either at `0`
   switches keeping off: the pin disappears, and a file already kept can still be
   released). Every
   gallery page carries `keep` — the account's kept files and bytes, counted over its
   whole set, and both ceilings — so the limit is stated before a click is refused
   (ADR-184, ADR-185). A selection that would pass either ceiling is refused WHOLE
   (409, `GeneratedAssetKeepLimitError`, a translated sentence naming both ceilings):
   keeping half of what a person selected is a result nobody asked for.

4. **Counted and written under one lock per account.** The count and the update run
   under a transaction-scoped advisory lock, so two keeps racing for the last slot
   cannot both land (proven on PostgreSQL, two sessions). ADR-316 held the same idiom
   for its daily share quotas; both now call ONE seam,
   `infrastructure/database/owner_lock.hold_owner_lock(db, scope, owner_id)` — 64-bit
   hashing, transaction scope, one scope per feature. Its name is not a Redis key; the
   first draft spelled it as a literal f-string, which the Redis key-family guard
   (ADR-260) cannot tell from one and flagged.

5. **`POST /generated-assets/keep {ids, kept}`** answers `{updated, skipped, keep}`. Only
   the caller's generated files move; an upload, another account's file or an id that is
   gone is SKIPPED, never counted; the same id twice is one file; keeping a kept file
   reports it kept again. **Releasing** (`kept: false`) gives the file a fresh deadline,
   one TTL from now — never an immediate deletion the person did not ask for. A file
   whose deadline passed but that the sweep has not reached yet can still be rescued.

6. **A chat card states the lifetime its file has NOW.** The history read path
   (`GET /conversations/me/messages`) restates every file card from its row
   (`domains/attachments/card_lifetimes.py`): kept → `expires_at: null, kept: true`;
   present → its current deadline; missing → `gone: true`. A card is recognised by its
   SHAPE — an object naming `/api/v1/attachments/{id}` and carrying an `expires_at` —
   so a card type added later inherits the rule; one batched read per page, never one
   query per card; the stored metadata is never rewritten. The web draws a gone file as
   an inert card with its name and a sentence (no preview that would load a 404, no
   download, no share) and a kept one says so where its deadline was. The live path
   carries the same flag (`PendingImage.kept`, `PendingDocument.kept`, set when the
   ADR-318 lookup shows a kept file), so a card reads the same live and after a
   reload.

7. **Every reader of the deadline learned the new state.** The gallery's `expires_asc`
   sort puts kept files last and its `expires_after` filter keeps them; the ADR-318 tool
   returns `kept` and never prints a missing deadline; a kept image stays shareable
   (ADR-316), and the recipient's copy gets its own fresh deadline from one helper.

8. **Observed.** The sweep publishes `attachments_kept_count` and
   `attachments_kept_bytes` — the disk no sweep will reclaim — drawn on dashboard 09
   (« Kept generated files »).

9. **The demonstrator** keeps the capability with ceilings of its own, lower, in its
   four environment files, and exposes the route (a pin shown over a hidden route would
   be a button that fails). Its nightly account purge removes a visitor's directory
   whole, kept files included — as account deletion does everywhere.

## Consequences

- A person keeps what matters without downloading it, and nothing kept is lost to the
  sweep.
- A chat card no longer contradicts the gallery: kept, current deadline or gone — the
  row decides, at every read.
- The sweep is one statement instead of N reads and N deletes, and its failure mode is
  an orphan file rather than a dangling row.
- **Kept files hold disk the sweep never reclaims.** It is bounded per account by the
  two ceilings and visible instance-wide through the two gauges; an operator sizes the
  ceilings against the disk (the demonstrator's are lower).
- A card from history that predates the expiry notice (no `expires_at` key) stays
  silent, as before: it is not recognised as a card, and nothing is invented for it.

## Alternatives rejected

- **A far-future deadline instead of `NULL`.** Every reader would announce a date in
  the year 9999, and « kept » would be a convention on a magic value that each new
  reader has to know.
- **A `kept` boolean beside the deadline.** Two authorities on one question — a kept row
  with a deadline, a released row without — and the sweep's predicate would have to
  remember to read the second column.
- **Rewriting the chat metadata when a file is kept or deleted.** A JSONB rewrite across
  every conversation that shows the file, and a file swept by the TTL would still lie;
  reading the row is exact by construction.
- **Copying kept files to a separate store.** The storage, the ownership check and the
  download route twice (ADR-279 rejected the same shape for the gallery itself).
