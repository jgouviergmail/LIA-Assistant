"""Instance-wide durable discussion cleanup and execution recovery measurements."""

from prometheus_client import Gauge

conversation_cleanup_operations = Gauge(
    "conversation_cleanup_operations",
    "Outstanding retired discussion runtime cleanups by durable state",
    ["state"],
    multiprocess_mode="mostrecent",
)
conversation_cleanup_oldest_timestamp_seconds = Gauge(
    "conversation_cleanup_oldest_timestamp_seconds",
    "Creation time of the oldest outstanding cleanup by state, zero when empty",
    ["state"],
    multiprocess_mode="mostrecent",
)
conversation_executions_recovering = Gauge(
    "conversation_executions_recovering",
    "Occupied chat and Live reservations in the recovering phase",
    multiprocess_mode="mostrecent",
)
conversation_cleanup_snapshot_timestamp_seconds = Gauge(
    "conversation_cleanup_snapshot_timestamp_seconds",
    "Timestamp of the last successful discussion cleanup and recovery observation",
    multiprocess_mode="mostrecent",
)
