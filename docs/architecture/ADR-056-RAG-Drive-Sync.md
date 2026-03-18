# ADR-056: RAG Spaces — Google Drive Folder Sync

**Status**: ✅ IMPLEMENTED (2026-03-17)
**Deciders**: JGO
**Technical Story**: Allow users to link Google Drive folders to RAG Spaces and
sync their contents into the RAG pipeline, eliminating the need to manually
download and re-upload files.
**Related Documentation**: `docs/architecture/ADR-055-RAG-Spaces-Architecture.md`

---

## Context and Problem Statement

RAG Spaces (ADR-055) currently only support manual file uploads. Users who store
documents in Google Drive need to download files first, then upload them — a
cumbersome workflow that discourages adoption. Since LIA already has a Google
Drive connector with OAuth integration (`ConnectorService`, `GoogleDriveClient`),
we can leverage it to sync Drive folder contents directly into RAG Spaces.

### Key Constraints

1. Google Drive API has per-user quota limits
2. Large folders can contain hundreds of files
3. Concurrent sync attempts on the same source must be prevented
4. Individual file failures should not block the entire sync
5. The feature must be toggleable without code changes

## Decision Drivers

### Must-Have
- Reuse existing Google Drive connector and OAuth flow
- Reuse existing RAG processing pipeline (extract → chunk → embed → store)
- Feature-flagged (`rag_spaces_drive_sync_enabled`) for easy rollback
- Per-file error isolation (one failure does not block the sync)
- Concurrency protection (no parallel syncs on the same source)

### Nice-to-Have
- Incremental sync (skip unmodified files)
- Automatic deletion of removed files
- Pagination cap to prevent runaway listing

## Considered Options

### Option 1: Automatic Periodic Sync (APScheduler)

**Pros**: Hands-free, always up-to-date.
**Cons**: Higher API quota consumption, complex scheduling logic, harder to
debug, unnecessary for V1 scope.
**Verdict**: ❌ Deferred — can be added later as an incremental enhancement.

### Option 2: Manual "Sync Now" Button (V1)

**Pros**: Simple, predictable, low API quota usage, user controls when sync
happens, easy to implement and debug.
**Cons**: Requires manual action, not real-time.
**Verdict**: ✅ Chosen.

### Option 3: Google Drive Push Notifications (Webhooks)

**Pros**: Real-time updates, efficient.
**Cons**: Requires public webhook endpoint, complex setup, OAuth scope changes,
infrastructure dependency on Google's push notification reliability.
**Verdict**: ❌ Rejected — too complex for V1, potential future enhancement.

## Decision

### Manual Sync (V1)

Users click "Sync Now" to trigger synchronization — no automatic periodic sync.
This reduces complexity and API quota usage. Auto-sync can be added later via
APScheduler (see Option 1).

### Non-Recursive Folder Listing

Only files directly in the linked folder are synced (no subfolder traversal).
This keeps the scope manageable and predictable for users.

### Automatic Deletion of Removed Files

When a file is deleted from Drive, the next sync removes the corresponding RAG
document, chunks, and physical file. This keeps the RAG space in sync with the
Drive folder state.

### Incremental Sync via modifiedTime

- Files are identified by `(space_id, drive_file_id)` for uniqueness
- If a file's `modifiedTime` has not changed since last sync, it is skipped
- Modified files are re-downloaded and re-processed from scratch

### Per-File Error Isolation

One failing file does not block the entire sync. Errors are logged per-file, and
the sync continues with the remaining files.

### Concurrency Controls

- **Atomic DB lock**: `UPDATE WHERE sync_status != 'syncing'` prevents concurrent
  syncs on the same source
- **asyncio.Semaphore(5)**: Throttles parallel `process_document` tasks to limit
  resource consumption
- **Pagination cap (500 files)**: `RAG_DRIVE_MAX_FILES_PER_SYNC` prevents runaway
  listing on very large folders

### MIME Type Handling

Two mapping dictionaries in `src/core/constants.py`:

- `RAG_DRIVE_GOOGLE_EXPORT_MAP` (3 entries): Maps Google-native MIME types
  (Docs, Sheets, Slides) to export formats (text/plain, text/csv)
- `RAG_DRIVE_REGULAR_FILE_MAP` (16 entries): Maps standard MIME types to stored
  content types and file extensions. Covers the same formats supported by manual
  upload.

### No Callback on Connector Revocation

Each Drive operation checks connector status at runtime. If revoked between
syncs, the next sync fails gracefully with a clear error message stored in
`error_message` on the source record.

## Architecture

### New Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `RAGDriveSyncService` | `src/domains/rag_spaces/drive_sync.py` | Link/unlink, browse, lock, status |
| `sync_folder_background()` | `src/domains/rag_spaces/drive_sync.py` | Background sync coroutine |
| `RAGDriveSourceRepository` | `src/domains/rag_spaces/repository.py` | DB operations for `rag_drive_sources` |
| `rag_drive_sources` table | Alembic migration | Source metadata, sync status, timestamps |
| 6 API endpoints | `src/domains/rag_spaces/router.py` | REST API for Drive operations |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{space_id}/drive-browse` | Browse Drive folders (folder picker) |
| `POST` | `/{space_id}/drive-sources` | Link a Drive folder |
| `GET` | `/{space_id}/drive-sources` | List linked folders |
| `DELETE` | `/{space_id}/drive-sources/{source_id}` | Unlink a folder |
| `POST` | `/{space_id}/drive-sources/{source_id}/sync` | Trigger sync (202 Accepted) |
| `GET` | `/{space_id}/drive-sources/{source_id}/sync-status` | Poll sync status |

### Sync Flow

```
User clicks "Sync Now"
  → POST /{space_id}/drive-sources/{source_id}/sync
    → try_acquire_sync_lock() [atomic UPDATE]
    → sync_folder_background() [fire-and-forget]
      → list_files(folder_id, files_only)
      → filter supported MIME types
      → for each file:
          → skip if unmodified (modifiedTime check)
          → download/export content
          → write to disk
          → create RAGDocument record
          → queue process_document()
      → detect removed files → delete docs + chunks + files
      → update source status (COMPLETED / ERROR)
```

## Consequences

### Positive
- Seamless integration with existing Google Drive connector
- Reuses the entire RAG processing pipeline (extract → chunk → embed → store)
- Feature-flagged (`rag_spaces_drive_sync_enabled`) for easy rollback
- Incremental sync reduces redundant processing and API calls
- Per-file error isolation improves reliability
- 4 new Prometheus metrics for observability

### Negative
- No real-time sync — users must manually trigger
- Non-recursive — deep folder hierarchies require multiple sources
- Google API quota consumption during sync (mitigated by rate limiter)

### Risks
- Large folders (>500 files) are capped — may frustrate users with large
  collections. The cap can be raised via `RAG_DRIVE_MAX_FILES_PER_SYNC`.
- Re-processing modified files from scratch (no delta) can be costly for large
  documents, but simplifies correctness.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `RAG_SPACES_DRIVE_SYNC_ENABLED` | `False` | Feature flag |
| `RAG_DRIVE_MAX_SOURCES_PER_SPACE` | `5` | Max linked folders per space |
| `RAG_DRIVE_MAX_FILES_PER_SYNC` | `500` | Pagination cap per sync run |

## Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `rag_drive_sources_total_count` | Gauge | Total linked Drive sources |
| `rag_drive_sync_runs_total` | Counter | Sync runs by status (started/completed/error) |
| `rag_drive_sync_files_total` | Counter | Files processed by result (synced/skipped/failed/deleted) |
| `rag_drive_sync_duration_seconds` | Histogram | Sync duration per run |
