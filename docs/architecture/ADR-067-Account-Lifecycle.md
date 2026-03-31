# ADR-067: Account Lifecycle (Active / Deactivated / Deleted / Erased)

## Status

Accepted

## Date

2026-03-31

## Context

LIA had only two account states: active (`is_active=True`) and deactivated (`is_active=False`). Hard deletion via GDPR endpoint removed ALL data including billing history. This created two problems:

1. **No billing preservation**: When an account was hard-deleted, token usage logs and consumption history were lost, making dispute resolution impossible.
2. **Background task leakage**: Scheduled jobs (proactive notifications, journal consolidation, reminders, scheduled actions) continued processing deactivated users, consuming LLM tokens unnecessarily.

## Decision

### Account Lifecycle: 4-State Model

```
ACTIVE → DEACTIVATED → DELETED → ERASED (GDPR)
```

- **Active** (`is_active=True, deleted_at=NULL`): Normal operation.
- **Deactivated** (`is_active=False, deleted_at=NULL`): Admin-reversible, sessions invalidated, no login allowed.
- **Deleted** (`is_active=False, deleted_at=timestamp`): All personal data purged, user row kept with email/name for billing contact. Irreversible.
- **Erased** (row removed): GDPR hard-delete, removes the user row entirely. Only available after deletion.

### Implementation: `deleted_at` Timestamp + `is_deleted` Property

We chose a `deleted_at: DateTime | None` column over an enum to avoid refactoring 50+ queries filtering on `is_active`. The `@property is_deleted` provides readability.

### Preconditions Enforce Sequential Flow

- Deletion requires `is_active=False` (must be deactivated first).
- GDPR erasure requires `deleted_at IS NOT NULL` (must be deleted first).
- This eliminates race conditions: deactivated users cannot have active sessions.

### Centralized Enforcement via `_compute_status()`

The `UsageLimitService._compute_status()` method was extended to check `is_active` and `deleted_at` as **priority 0** (before manual blocks and usage limits). Since this method is already called by `is_user_blocked_for_llm()`, all background tasks using this helper are automatically protected.

### Billing Data Preservation

Tables WITHOUT FK to users (preserved after deletion):
- `token_usage_logs`, `message_token_summary`, `user_statistics`

Tables with FK changed to SET NULL:
- `google_api_usage_logs`, `admin_broadcasts.sent_by`

### Account Deletion Purges (22 Tables)

The `AccountDeletionService` explicitly deletes data from 22 tables in FK-safe order, plus LangGraph Store, checkpoints, Redis caches, and physical files (attachments, RAG documents).

## Consequences

### Positive
- Billing history preserved for dispute resolution.
- Defense-in-depth: SQL filters + `_compute_status()` + per-task checks.
- Sequential lifecycle prevents race conditions.
- Physical files cleaned up (not just DB rows).

### Negative
- User row persists indefinitely (email/name stored for billing).
- Orphaned user_ids in billing tables (no FK enforcement).
- Langfuse traces not cleaned (external service limitation).

### Risks
- Large RAG datasets may slow the deletion transaction. Mitigation: files deleted before DB transaction.
- OAuth revocation is best-effort (external API). Acceptable: user is already deactivated.

## Files Changed

- `src/domains/auth/models.py` — `deleted_at`, `deleted_reason`, `is_deleted`
- `src/domains/users/account_deletion_service.py` — New orchestration service
- `src/domains/usage_limits/service.py` — `_compute_status()` extended
- `src/domains/connectors/repository.py` — Health check + token refresh filters
- 7 scheduler/background task files — User status guards
