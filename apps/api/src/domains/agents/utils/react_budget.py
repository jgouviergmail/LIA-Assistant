"""Adaptive ReAct iteration budget (Lot 5-C4, ADR-238).

Pure math: the configured ``react_agent_max_iterations`` becomes a
CEILING, and the effective budget grows with the query's domain span
(the analyzer's ``domains`` list — the one complexity signal the setup
node already holds). Unknown complexity (no analysis, empty domains)
falls back to the ceiling: an uninformed guess must never under-budget
a hard query — the adaptive path only ever SAVES on provably simple ones.
"""

from __future__ import annotations


def effective_react_budget(
    domain_count: int, *, base: int, per_extra_domain: int, ceiling: int
) -> int:
    """Iteration budget for this turn.

    Args:
        domain_count: Domains the analyzer attributed to the query
            (0 = unknown — conservative fallback to the ceiling).
        base: Budget of a single-domain query.
        per_extra_domain: Extra iterations granted per additional domain.
        ceiling: Hard cap (the historical ``react_agent_max_iterations``).

    Returns:
        The effective budget, always in ``[1, ceiling]``.
    """
    if domain_count < 1:
        return ceiling
    budget = base + (domain_count - 1) * per_extra_domain
    return max(1, min(budget, ceiling))
