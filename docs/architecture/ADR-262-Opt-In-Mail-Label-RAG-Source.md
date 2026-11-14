# ADR-262 — Opt-in Gmail label as a RAG source

**Date**: 2026-09-03
**Status**: Accepted
**Context**: The audit of 2026-09-03 asked whether LIA should historise
e-mail and calendar into the RAG spaces, so that "what did we agree on the
Dupont file in March?" could be answered from the corpus rather than from a
live search bounded to the last weeks. Indexing the whole mailbox was
rejected by the owner and by us, for three measured reasons: it duplicates
an entire personal archive into a second store (encrypted at rest, but
still a second copy to protect, back up and delete), the embedding cost is
proportional to a corpus that is mostly noise (measured on the reference
account: promotions, notifications and lists dominate the volume), and
retrieval quality drops when the corpus is dominated by text nobody would
have chosen to keep. The alternative the owner accepted: **the user
designates what matters, with a tool they already use every day — a Gmail
label.**

## Decision

1. **The opt-in IS the label.** A space follows a Gmail label
   (`rag_mail_sources`, one row per (space, label), unique). Only the
   threads carrying that label are rendered and indexed. Removing the label
   in Gmail removes the document at the next pass — the user's own gesture
   is the deletion, so there is no second place to manage. The feature ships
   behind `RAG_SPACES_MAIL_SYNC_ENABLED`, **OFF by default**: nothing about
   a mailbox is copied because a package was installed.
2. **One thread is one document.** `mail_render.py` is pure — thread in,
   Markdown out: the subject as the title, one section per message in date
   order, the plain-text body preferred (HTML converted by the Gmail
   client's own extractor, never a second parser), **attachment names
   only**, and a hard size cap (`RAG_MAIL_MAX_THREAD_CHARS`). The document's
   display name is the **subject**, never a participant, so a file listing
   leaks no address.
3. **Two ways in, one ingestion.** The full sync lists the label's threads
   (`sync_source`), the incremental path replays Gmail's history
   (`apply_history`); both call the same `ingest_thread`, which skips an
   unchanged thread by its newest message stamp and replaces a changed one.
   Two readings of "how a thread becomes a document" would diverge
   (ADR-255); so would two readings of "how bytes become a PENDING
   document" — that step is `drive_ingest.create_pending_document`, shared
   with the Drive source, and its symmetric `discard_document`.
4. **The full sync anchors BEFORE it lists.** `history.list`'s id is read
   from the profile first, then the threads are listed. A message arriving
   during the listing is therefore replayed by the next incremental pass —
   where the unchanged check makes the replay free — instead of falling in
   the gap between "listed" and "anchored". The reverse order loses mail
   silently.
5. **The incremental path rides ADR-261's wake, and answers to no gate.** A
   Gmail push notification already wakes the sweep; before any heartbeat
   gate (cooldown, window, quota), the sweep feeds the user's label sources.
   Indexing is not a decision: it costs no notification budget, it is
   counted on its own metric, and a failure there never costs the wake.
   `threads_to_revisit` reads exactly what the history names — a label added
   or removed, a message added to a thread that is indexed or already
   carries the label — and the thread itself decides: it carries the label →
   (re)render; it does not → remove. An expired or absent anchor falls back
   to a full sync (`resynced`), never to silence.
6. **A synced source is a durable job, whichever kind.** `rag_mail_sources`
   carries the same lease/heartbeat/attempts/worker columns as
   `rag_drive_sources`, and `RAGJobsRepository`'s three source jobs take the
   TABLE as a parameter — validated against a two-name allowlist, the only
   way a name reaches the SQL text. The reaper recovers a crashed label sync
   exactly like a crashed folder sync, and a PENDING document of a LIVE
   label sync is excluded from recovery for the same reason as a Drive one:
   its sync will claim it.
7. **A count shown is exact** (ADR-185): `synced_thread_count` is a
   `COUNT(*)` of READY documents, never a sum of per-run guesses.

8. **The incremental path depends on ADR-261's wake, and says so.** With
   `PUSH_WAKE_ENABLED` off, a label source is still correct — it is fed by the
   manual sync and by the reaper — but it is no longer *incremental*. That
   dependency is stated in the setting's own description, in `.env.example`
   and here, because a feature that silently needs a second flag is a feature
   nobody can enable correctly.

## Alternatives rejected

- **Indexing the whole mailbox** — the context above: a second archive, a
  cost proportional to noise, and worse retrieval.
- **A saved Gmail search instead of a label** — a query is not a durable
  designation: it re-scopes silently as mail arrives, and the user has no
  gesture to remove one thread.
- **Caching the fetched threads in Redis** — a thread read here becomes a
  document on disk, not a prompt; a cached copy would only double the
  personal content at rest.
- **Storing the full text in the row** — the RAG pipeline already owns
  storage, chunking, embedding and deletion; the mail source stops at
  "produce the bytes, create the PENDING document".

## Consequences

- New table `rag_mail_sources`, three `rag_documents` columns
  (`mail_source_id`, `mail_thread_id`, `mail_last_message_at`), migration
  `f1a2b3c4d5e6`. A document from a label is not movable (like a Drive or
  meeting document) and shows a `Mail` badge.
- New endpoints under the space: `mail-labels` (the user's own labels — the
  system ones are never offered), `mail-sources` (list/link/unlink),
  `…/sync`, `…/sync-status`. Ownership is the space's and hides existence.
- New metrics on dashboard 18: `rag_mail_sync_runs_total`,
  `rag_mail_sync_threads_total`, `rag_mail_push_index_total`,
  `rag_mail_sources_total_count`.
- The Drive and mail sources now share their card (`SourceSyncCard`) and
  their unlink dialog (`UnlinkSourceConfirm`) — the two copies had already
  drifted on the `idle` tone.
- **Not decided here**: calendar historisation. A meeting's value is in what
  was said and written around it, which the mail source and the meeting
  minutes (ADR-258) already capture; indexing event rows would add
  timestamps without text.

## Amendment 2026-11-10 — whoever takes the lease by SQL reads the row before releasing it

From v1.40.0 (2026-09-04) every Gmail push left its label sources `syncing`. The push pass loads
the sources, takes each lease with one conditional SQL statement the session never sees, then
releases it through the repository on the object loaded BEFORE the lease. The ORM writes only what
differs from the loaded state: `sync_status`, `lease_expires_at`, `attempts` and `worker_id` were
left as the lease had set them, while `last_sync_at` and the history anchor were written. Five
minutes later the reaper logged a recovered worker crash and replayed a full label sync. Measured
on production on 2026-11-10: 236 replays and 127,585 Gmail thread reads in 24 hours, on a rate
limit the connector shares with the person's own Gmail tools. The log line said `sync_status` had
been updated; the unit tests mocked the lease.

- `_serve_source` now reads the row again once it holds the lease (`db.refresh`), as the Drive push
  path loads its source after the lease. It is also the anchor to resume from.
- `tests/integration/domains/rag_spaces/test_mail_push_lock_release.py` holds the push pass on real
  PostgreSQL: the lease is returned, the reaper finds nothing to recover, a changed thread is
  indexed and the anchor advances.
- `RagSourceRecoveryLoop` (ADR-119 amendment of the same day) says so when a source is recovered
  over and over.

Left open: the loop replayed a full sync after every push, so in the seven days Prometheus keeps,
the incremental path never once answered `indexed` — nothing had needed it, or it does not work on
Gmail's real history. The first labelled mail after the fix is the proof
(`rag_mail_push_index_total{outcome="indexed"}`).
