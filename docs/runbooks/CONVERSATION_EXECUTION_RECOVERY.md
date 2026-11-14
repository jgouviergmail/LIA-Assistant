# Recover a stopped conversation execution

An unfinished graph keeps its account occupied in `running`, `draining` or
`recovering`. A missing Redis key, old heartbeat, disconnected browser or SSE
terminal event does **not** prove its worker stopped. Nothing automatically
replays an instruction whose provider result is unknown.

This privileged server procedure is for a worker that cannot finish its own
supervised shutdown. Ordinary cancellation stays in the chat. Live reservations
are deliberately refused here: their provider session and relay must close
through the voice-session protocol.

## Identify the exact invocation

Use the execution's `activity_id` and `worker_id` from the structured
`conversation_execution_reserved` / `conversation_execution_recovering` logs.
The reservation log also records the process ID; use the log's container/host
identity to locate it. A PID alone is reusable and proves nothing about a boot.

A read-only database query can identify candidates without reading content:

```sql
SELECT id, worker_id, user_id, conversation_id, kind, phase, heartbeat_at
FROM conversation_executions
WHERE phase <> 'closed'
ORDER BY heartbeat_at, id;
```

From the API environment, inspect one candidate:

```console
python -m scripts.data.recover_execution inspect --activity ACTIVITY_UUID --worker BOOT_UUID
```

The command reports operational identifiers and the observed phase only. It
never publishes the private owner token or changes messages, billing or effects.

## Revoke, establish the stop, close

1. Quarantine the exact graph:

   ```console
   python -m scripts.data.recover_execution quarantine --activity ACTIVITY_UUID --worker BOOT_UUID
   ```

   SQL commits `recovering` before the bounded Redis revocation. New guarded
   writes and external work refuse; occupancy remains. A failed Redis operation
   leaves the graph occupied and the command exits nonzero. Retry the same
   command after restoring the dependency. No transaction spans that I/O.

2. Establish that the identified worker **and its owned children** have actually
   stopped, from the process supervisor/container runtime. Wait for their exit.
   A heartbeat timeout, a cancellation signal, an unreachable host or the phase
   `recovering` is insufficient. If the exact process cannot be identified,
   stop **all** API/runner replicas for this deployment and verify their exit
   before using an isolated one-off API environment for the following command.
   Do not restart the stopped boot or restore its old memory snapshot.

3. Attest that verified stop and close only this activity:

   ```console
   python -m scripts.data.recover_execution close --activity ACTIVITY_UUID --worker BOOT_UUID --confirm-worker-stopped BOOT_UUID
   ```

   The repeated UUID is an explicit operator attestation, **not automatic
   process-death detection**. Missing/mismatched confirmation is refused before
   any connection. A graph not quarantined is refused. Redis closure precedes
   conditional SQL closure; a timeout leaves occupancy intact. Every transition
   retains the original owner token and fence, so retrying an old command cannot
   close a newer invocation. A lost successful acknowledgement can be retried.

4. Re-inspect and require `closed`. Restart any replicas deliberately stopped,
   then verify that a new ordinary chat turn completes and its activity closes.
   Keep the command logs and supervisor stop evidence with the incident record.

## Reconcile the unknown outcome separately

Closing occupancy does not report an action as successful, cancelled or refunded.
The structured recovery event states `provider_outcome=unresolved`. Preserve the
run ID, decision/effect records, billing, partial answer and pending questions.
Inspect the provider and LIA's registers to establish what happened. Never
resubmit the original instruction merely to discover its result. A later user
request is a separate act, subject to the normal confirmations and admission.

## Recover an interrupted file writer

Uploads and owned copies persist `uploaded` with their exact worker boot before
writing to disk. Neither the TTL sweep nor a removal lease may retire that writer:
an old thread could still be writing. The `attachment_write_reserved` event names
the boot, process and attachment IDs, without content or a filesystem path.
Imports and knowledge-space writes also retain a content-free account writer
until every disk write and rollback has joined (`account_file_writer_started`).
The inspection reports attachment uploads and account writers separately.

```console
python -m scripts.data.recover_file_writes inspect --worker BOOT_UUID
```

Establish the same complete worker/child-process stop described above. Then:

```console
python -m scripts.data.recover_file_writes retire --worker BOOT_UUID --confirm-worker-stopped BOOT_UUID
```

This atomically marks only that boot's unfinished uploads for deletion. It never
publishes an incomplete file, retries an upload, changes another boot's files or
removes a directory. The existing attachment sweep removes each recorded path;
failure preserves the row and its path for retry. Repeating the command is safe.
An attachment already published `ready` is outside this recovery operation.
The same transaction releases that boot's account writer records. It does not
restore an import or run it again. A pending account erasure can then resume its
normal complete directory removal; a failed removal remains an explicit failure.

## Retry a retired runtime's cleanup

A reset retires its old runtime in one committed transaction. The new revision
may serve immediately; an incomplete physical cleanup remains in
`conversation_operations`. Its phases remove the native checkpoint, exact tool
context, pending runtime state and eligible files. An unsuccessful operation
never expires. Only successful receipts have a configurable retention period.

The private HTTP status/retry endpoints use the client's `operation_id`. The
operator command below uses the **internal row ID**, as recorded by cleanup
events, and remains available after account deactivation or removal:

```console
python -m scripts.data.recover_conversation_cleanup inspect --operation ROW_UUID
python -m scripts.data.recover_conversation_cleanup retry --operation ROW_UUID
```

Retry only rearms `needs_attention`, preserving the exact old runtime and next
unfinished phase. It cannot take a running claim, reset the new discussion or
repeat an external assistant action. Resolve the reported storage/Redis failure
first, then inspect for `succeeded`. Pending and retry-wait operations are served
by the scheduler; an expired cleanup lease may be reclaimed because its work is
idempotent removal of already retired state. This never proves a graph writer
dead: interrupted graph and file writers still require the separate stop-proof
procedure above.

The legacy reset route waits for bounded physical completion. On a pending
response, reconcile its returned operation ID instead of sending another reset.
Legacy clients without an explicit request identity must never automatically
repeat a lost destructive request. The versioned client sends both the operation
identity and the revision the person reviewed.

## Evidence and implementation

- Admission and conditional transitions:
  [execution_repository.py](../../apps/api/src/domains/conversations/execution_repository.py).
- Operator composition and bounded Redis revocation:
  [run_recovery.py](../../apps/api/src/infrastructure/streaming/run_recovery.py).
- Actual PostgreSQL/Redis and terminated-process scenarios:
  [test_execution_recovery.py](../../apps/api/tests/integration/domains/conversations/test_execution_recovery.py).
- Stop-attestation and pool-ownership contracts:
  [test_recover_execution_cli.py](../../apps/api/tests/unit/scripts/test_recover_execution_cli.py).
- Transport/admission distinction:
  [ADR-117](../architecture/ADR-117-Background-Chat-Runs.md).
