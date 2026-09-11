"""The bound a MODEL-produced domain name must clear before it is stored.

Two producers write a domain the analyzer chose into a durable, domain-keyed
record: the product-outcomes capture (a bounded column) and the recurrence
ledger write (a Redis key tail, later a word the heartbeat prompt quotes).
Each used to apply its own reading of « is this a domain » — one against
``DOMAIN_REGISTRY``, the other not at all (2026-09-11) — so the rule lives
here, once, beside the registry it reads. Its own module because
``domain_taxonomy`` is frozen at its audited size (file-size ratchet).
"""

from __future__ import annotations

from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY


def is_registered_domain(name: object) -> bool:
    """Whether ``name`` is a domain of the registry proper.

    Dynamic MCP domains are deliberately outside it: they are a server's
    name, not the vocabulary a habit is learned on or an outcome counted by.

    Args:
        name: The candidate, as the analyzer produced it.

    Returns:
        True for a registered domain name.
    """
    return isinstance(name, str) and name in DOMAIN_REGISTRY
