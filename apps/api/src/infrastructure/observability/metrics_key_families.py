"""Prometheus metrics for the Redis key-family registry (ADR-260).

The conversation reset deletes keys by declared family; what it keeps and
what it does not recognise must be visible, because an undeclared family is
exactly the blind spot that let learning state die silently for a month.
"""

from __future__ import annotations

from prometheus_client import Counter

conversation_reset_keys_deleted_total = Counter(
    "conversation_reset_keys_deleted_total",
    "Redis keys deleted by a conversation reset, per declared family "
    "(conversation and user-cache scopes only).",
    ["family"],
)

conversation_reset_keys_kept_total = Counter(
    "conversation_reset_keys_kept_total",
    "Redis keys a conversation reset matched but deliberately kept, per scope "
    "(user_learning, user_runtime, global, or undeclared).",
    ["scope"],
    # scope: user_learning | user_runtime | global | undeclared
)

reset_undeclared_family_total = Counter(
    "reset_undeclared_family_total",
    "User-keyed Redis keys a reset matched whose family declares no scope — "
    "each is a key the registry can neither purge nor protect knowingly; "
    "declare it in infrastructure/cache/key_families.py.",
    ["family"],
    # family: the key's first segment (code-defined, bounded)
)
