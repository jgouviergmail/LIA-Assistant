"""Adaptive ReAct iteration budget (Lot 5-C4).

The configured max becomes a CEILING; the effective budget grows with the
query's domain span. Unknown complexity falls back to the ceiling — an
uninformed guess must never under-budget a hard query.
"""

import pytest

from src.domains.agents.utils.react_budget import effective_react_budget


@pytest.mark.unit
class TestEffectiveReactBudget:
    def test_single_domain_gets_the_base(self):
        assert effective_react_budget(1, base=6, per_extra_domain=3, ceiling=15) == 6

    def test_each_extra_domain_widens_the_budget(self):
        assert effective_react_budget(3, base=6, per_extra_domain=3, ceiling=15) == 12

    def test_ceiling_is_never_exceeded(self):
        assert effective_react_budget(8, base=6, per_extra_domain=3, ceiling=15) == 15

    def test_unknown_complexity_falls_back_to_the_ceiling(self):
        # 0 domains = the analyzer produced nothing usable: never under-budget.
        assert effective_react_budget(0, base=6, per_extra_domain=3, ceiling=15) == 15

    def test_base_above_ceiling_is_clamped(self):
        # A misconfigured base cannot escape the ceiling.
        assert effective_react_budget(1, base=20, per_extra_domain=3, ceiling=15) == 15
