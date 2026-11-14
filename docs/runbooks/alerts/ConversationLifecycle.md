# Discussion lifecycle alerts

The **Conversations and Users** dashboard shows unfinished physical cleanup by durable state, the age of the oldest receipt, reservations in `recovering`, and the age of the last successful snapshot. A successful reset or deletion can precede physical cleanup. The receipt remains authoritative until it reaches `succeeded`.

## Cleanup delayed

`pending` is queued. `running` holds a renewable cleanup claim. `retry_wait` has a scheduled retry. `needs_attention` has reached the attempt limit and requires a targeted inspection. Compare the state and phase in the receipt with `conversation_cleanup_sweep` and `conversation_cleanup_sweep_failed`. `conversation_cleanup_inventory_refusals_total` identifies a refused runtime inventory. Logs and metrics carry operational facts only.

From `apps/api`, inspect the receipt identified by its internal operation UUID using `python -m scripts.data.recover_conversation_cleanup inspect --operation <operation-id>`. After correcting the failing checkpoint, context, pending-state or file phase, use the same command with `retry`. It retains the original retired generation and resumes its unfinished phase. The latest receipt can be read by the authenticated owner through the operation endpoint with its request UUID.

## Execution recovery required

Identify the `activity_id`, `kind` and exact `worker_id` from the durable execution record and the worker logs. The [graph recovery command](../../../apps/api/scripts/data/recover_execution.py) and [Live recovery command](../../../apps/api/scripts/data/recover_live_session.py) both offer `inspect` and `quarantine`. Before `close`, verify from the supervisor that the exact worker boot and its owned tasks stopped. For Live, verify every outstanding worker reported by `inspect` and supply a `--confirm-worker-stopped` argument for each. Redis TTL expiry alone cannot establish that work ended.

## Snapshot stale

Check the API scheduler leader, the PostgreSQL connection and the last completed sweep. The alert threshold and hold time are owned by the [alert profiles](../../../infrastructure/observability/prometheus/thresholds/production.env). After recovery, verify a fresh snapshot, the affected receipt's terminal state, and the corresponding account's ability to start work. A missing series means the measurement is unavailable.
