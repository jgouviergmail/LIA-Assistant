"""Prometheus metrics for the conversation sync signal (ADR-320).

A change to a person's conversation is announced to their open tabs once the
transaction that wrote it commits. The signal is best-effort by design — a tab
that misses one catches up when it comes back to the foreground or reconnects —
so a failure surfaces nowhere else: it is counted here.
"""

from prometheus_client import Counter

conversation_sync_signals_total = Counter(
    "conversation_sync_signals_total",
    "Conversation change signals sent to a person's open tabs after commit",
    # kind: conversation_updated | conversation_reset
    # outcome: published | no_redis | failed | no_loop
    ["kind", "outcome"],
)
