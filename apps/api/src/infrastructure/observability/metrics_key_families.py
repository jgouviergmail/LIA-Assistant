"""Exact runtime key removal and refused inventories; no account-wide reset scan."""

from prometheus_client import Counter

conversation_reset_keys_deleted_total = Counter(
    "conversation_reset_keys_deleted_total",
    "Exact retired-runtime keys explicitly removed, by declared family.",
    ["family"],
)

conversation_cleanup_inventory_refusals_total = Counter(
    "conversation_cleanup_inventory_refusals_total",
    "Runtime cleanup attempts refused for malformed or foreign inventory state.",
)
