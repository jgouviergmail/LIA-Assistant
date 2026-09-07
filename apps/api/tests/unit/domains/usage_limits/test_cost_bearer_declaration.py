"""Whose key paid decides whether the account is billed for it.

The rule the owner stated: *« on ne compte pas les coûts des outils ou
connecteurs avec une clé de l'utilisateur »*. Today the code obeys it exactly —
verified 2026-09-07 in both directions:

- ``provider_api_keys`` has **no** ``user_id`` column, so every model call,
  image, speech and Maps request runs on the self-hoster's key, and all five
  families are summed into the account's cost ceiling;
- ``get_api_key_credentials(user_id, connector_type)`` is per-account, so
  Perplexity, Brave and the weather connector run on the person's own key —
  and none of them touches a counter.

Nothing states that frontier. It holds because several people had the same
reflex, which is not a guarantee: reading it backwards twice in ten minutes is
what motivated this file. The next paid capability will be classified by
whoever adds it, and the sum the quota enforces must keep matching the
declaration — in BOTH directions, because the two failures are opposite and
equally bad.

- An instance-paid family missing from the sum: the self-hoster funds a spend
  no ceiling can see.
- A user-paid family present in the sum: the account is charged, against its
  own quota, for euros it already paid to its own provider.
"""

from __future__ import annotations

import ast
import inspect
from textwrap import dedent

import pytest

pytestmark = pytest.mark.unit


def _families_summed_by_the_quota() -> set[str]:
    """The ``*_cost_eur`` columns the per-account ceiling actually adds up.

    Read from the expression builder itself rather than re-listed here: a
    hand-kept copy drifts, and this guard exists precisely because a
    declaration that stops describing the code is worse than none.

    Returns:
        Column names summed into the enforced ``cycle_cost`` expression.
    """
    from src.domains.usage_limits.repository import _build_user_stats_columns

    source = dedent(inspect.getsource(_build_user_stats_columns))
    tree = ast.parse(source)
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr.startswith("cycle_")
        if node.attr.endswith("_cost_eur")
    }


class TestEveryPaidFamilyNamesItsPayer:
    """The registry is complete, and its vocabulary is closed."""

    def test_every_family_declares_a_bearer_and_a_reason(self) -> None:
        from src.domains.usage_limits.cost_bearers import COST_FAMILIES, CostBearer

        assert COST_FAMILIES, "no paid family declared at all"
        for family, spec in COST_FAMILIES.items():
            assert isinstance(spec.bearer, CostBearer), f"{family}: unknown bearer"
            assert spec.reason.strip(), f"{family}: no reason saying whose key pays"

    def test_a_user_paid_family_names_the_connector_that_holds_the_key(self) -> None:
        """« The user pays » is only credible if we can say with what.

        A family placed on the user's side without naming the credential it
        uses is an assertion, not a fact — and it is the assertion that
        exempts it from every counter.
        """
        from src.domains.usage_limits.cost_bearers import COST_FAMILIES, CostBearer

        for family, spec in COST_FAMILIES.items():
            if spec.bearer is CostBearer.USER:
                assert spec.credential, f"{family}: user-paid but names no credential"


class TestTheQuotaSumsExactlyTheInstanceFamilies:
    """The declaration and the enforced arithmetic say the same thing."""

    def test_no_instance_family_escapes_the_ceiling(self) -> None:
        from src.domains.usage_limits.cost_bearers import (
            COST_FAMILIES,
            QUOTA_COLUMN_OF,
            CostBearer,
        )

        summed = _families_summed_by_the_quota()
        for family, spec in COST_FAMILIES.items():
            if spec.bearer is not CostBearer.INSTANCE:
                continue
            column = QUOTA_COLUMN_OF[family]
            assert column in summed, (
                f"{family} is paid by the instance but {column} is not summed "
                "into the enforced cost ceiling"
            )

    def test_no_user_paid_family_is_billed_to_the_account(self) -> None:
        from src.domains.usage_limits.cost_bearers import (
            COST_FAMILIES,
            QUOTA_COLUMN_OF,
            CostBearer,
        )

        summed = _families_summed_by_the_quota()
        for family, spec in COST_FAMILIES.items():
            if spec.bearer is not CostBearer.USER:
                continue
            column = QUOTA_COLUMN_OF.get(family)
            assert column is None or column not in summed, (
                f"{family} runs on the account's own key, yet {column} is "
                "charged against their quota"
            )

    def test_every_summed_column_belongs_to_a_declared_family(self) -> None:
        """A column that appears in the sum without a family is unclassified.

        This is the direction that catches an addition: someone widening the
        ceiling to a new silo must say who pays for it, or the ceiling starts
        enforcing something nobody described.
        """
        from src.domains.usage_limits.cost_bearers import QUOTA_COLUMN_OF

        summed = _families_summed_by_the_quota()
        declared_columns = {column for column in QUOTA_COLUMN_OF.values() if column}
        unclassified = summed - declared_columns
        assert (
            not unclassified
        ), f"columns summed by the quota with no declared family: {sorted(unclassified)}"
