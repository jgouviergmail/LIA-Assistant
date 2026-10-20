"""Content-free, bounded ingestion-delivery metrics (no owner/device labels)."""

from prometheus_client import Counter, Gauge

ingestion_delivery_outcomes_total = Counter(
    "ingestion_delivery_outcomes_total",
    "Committed delivery outcomes by destination kind.",
    ["destination", "outcome"],
)
ingestion_delivery_sweep_timestamp_seconds = Gauge(
    "ingestion_delivery_sweep_timestamp_seconds",
    "Last successfully completed delivery sweep.",
)
