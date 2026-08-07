"""Administration of the instance-wide daily spend ceiling.

The ceiling is stored in the generic settings store but administered from the
BUDGET domain: the dependency points usage_limits -> system_settings and never
back (putting this on the store side closed an import cycle, F009).

What must hold:
- the operator sees what is ENFORCED, not only what they typed: a value above
  the deployment bound is stored but never applies;
- the consumption of the day is reported next to the ceiling — a limit without
  its counter cannot be piloted;
- clearing the ceiling is a real action, and a non-positive one is refused by
  the schema ("allow nothing" is expressed by disabling the feature).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.usage_limits.instance_budget_admin import InstanceBudgetAdminService
from src.domains.usage_limits.schemas import InstanceDailyBudgetUpdate

pytestmark = pytest.mark.unit


def _db(
    existing_value: str | None = None,
    *,
    ledger: tuple[Decimal, int] | None = None,
) -> MagicMock:
    """A session serving the setting row and today's ledger row."""
    setting = None
    if existing_value is not None:
        setting = MagicMock(id=uuid4(), value=existing_value, updated_by=None, updated_at=None)
    result = MagicMock()
    result.scalar_one_or_none.return_value = setting
    result.first.return_value = ledger
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


def _added_of_type(db: MagicMock, expected: type) -> object:
    """The single object of ``expected`` handed to ``session.add``."""
    matches = [call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], expected)]
    assert len(matches) == 1, f"expected exactly one {expected.__name__}, got {len(matches)}"
    return matches[0]


def _request() -> MagicMock:
    request = MagicMock()
    request.client.host = "203.0.113.10"
    request.headers = {"user-agent": "pytest"}
    return request


# ---------------------------------------------------------------------------
# Spend ceiling (live-demonstrator programme)
# ---------------------------------------------------------------------------


async def test_ceiling_read_exposes_both_the_operator_value_and_the_deployment_bound() -> None:
    service = InstanceBudgetAdminService(_db("0.50"))
    with patch("src.domains.usage_limits.instance_budget_admin.settings") as fake_settings:
        fake_settings.instance_daily_budget_eur = Decimal("1")
        response = await service.get()
    assert response.ceiling_eur == Decimal("0.50")
    assert response.deployment_ceiling_eur == Decimal("1")
    # The operator must SEE what actually applies, not only what they typed.
    assert response.effective_ceiling_eur == Decimal("0.50")


async def test_ceiling_read_shows_the_deployment_bound_when_no_operator_value() -> None:
    service = InstanceBudgetAdminService(_db(None))
    with patch("src.domains.usage_limits.instance_budget_admin.settings") as fake_settings:
        fake_settings.instance_daily_budget_eur = Decimal("1")
        response = await service.get()
    assert response.ceiling_eur is None
    assert response.is_default is True
    assert response.effective_ceiling_eur == Decimal("1")


async def test_an_operator_value_above_the_deployment_bound_does_not_apply() -> None:
    service = InstanceBudgetAdminService(_db("100"))
    with patch("src.domains.usage_limits.instance_budget_admin.settings") as fake_settings:
        fake_settings.instance_daily_budget_eur = Decimal("1")
        response = await service.get()
    # Stored as typed, but the smallest bound is what the runtime enforces.
    assert response.ceiling_eur == Decimal("100")
    assert response.effective_ceiling_eur == Decimal("1")


@patch("src.domains.system_settings.service.invalidate_setting_cache", new_callable=AsyncMock)
async def test_ceiling_write_stores_an_exact_decimal(invalidate: AsyncMock) -> None:
    db = _db(None)
    service = InstanceBudgetAdminService(db)
    with patch("src.domains.usage_limits.instance_budget_admin.settings") as fake_settings:
        fake_settings.instance_daily_budget_eur = None
        await service.set(
            InstanceDailyBudgetUpdate(ceiling_eur=Decimal("0.50")), uuid4(), _request()
        )
    setting = _added_of_type(db, SystemSetting)
    assert setting.value == "0.50"
    invalidate.assert_awaited_once_with(SystemSettingKey.INSTANCE_DAILY_BUDGET_EUR)


@patch("src.domains.system_settings.service.invalidate_setting_cache", new_callable=AsyncMock)
async def test_clearing_the_ceiling_stores_an_empty_value(invalidate: AsyncMock) -> None:
    db = _db("1")
    service = InstanceBudgetAdminService(db)
    with patch("src.domains.usage_limits.instance_budget_admin.settings") as fake_settings:
        fake_settings.instance_daily_budget_eur = None
        response = await service.set(
            InstanceDailyBudgetUpdate(ceiling_eur=None), uuid4(), _request()
        )
    assert response.ceiling_eur is None


def test_a_zero_or_negative_ceiling_is_refused_by_the_schema() -> None:
    for invalid in (Decimal("0"), Decimal("-1")):
        with pytest.raises(ValueError):
            InstanceDailyBudgetUpdate(ceiling_eur=invalid)


# ---------------------------------------------------------------------------
# Today's consumption alongside the ceiling
# ---------------------------------------------------------------------------


async def test_the_ceiling_is_reported_next_to_what_was_already_spent() -> None:
    service = InstanceBudgetAdminService(_db("1", ledger=(Decimal("0.42"), 17)))
    with patch("src.domains.usage_limits.instance_budget_admin.settings") as fake_settings:
        fake_settings.instance_daily_budget_eur = None
        response = await service.get()
    # A ceiling without the consumption next to it cannot be piloted.
    assert response.spent_today_eur == Decimal("0.42")
    assert response.runs_today == 17


async def test_a_day_that_has_not_spent_yet_reports_zero_not_an_error() -> None:
    service = InstanceBudgetAdminService(_db("1", ledger=None))
    with patch("src.domains.usage_limits.instance_budget_admin.settings") as fake_settings:
        fake_settings.instance_daily_budget_eur = None
        response = await service.get()
    assert response.spent_today_eur == Decimal("0")
    assert response.runs_today == 0
