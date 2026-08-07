"""Administration of the instance-wide daily spend ceiling.

The ceiling is stored in the generic ``system_settings`` key/value store, but
it is a BUDGET concern, so it lives here: the dependency points
``usage_limits -> system_settings`` and never back. Putting this service on
the store side made the store import the budget domain, which closed an
import cycle (F009) — the store must know nothing about who stores in it.

What the operator gets: the value they typed, the deployment bound they
cannot exceed, the ceiling actually enforced, and what has been spent today.
An enforced constraint the operator cannot see is a trap, not a contract.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.system_settings.service import (
    read_setting_with_metadata,
    write_setting,
)
from src.domains.usage_limits.instance_budget import InstanceBudgetService
from src.domains.usage_limits.models import InstanceDailyBudget
from src.domains.usage_limits.schemas import (
    InstanceDailyBudgetResponse,
    InstanceDailyBudgetUpdate,
)

if TYPE_CHECKING:
    from fastapi import Request

logger = structlog.get_logger(__name__)

_KEY = SystemSettingKey.INSTANCE_DAILY_BUDGET_EUR


class InstanceBudgetAdminService:
    """Read and write the operator ceiling, next to today's consumption."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with a database session.

        Args:
            db: Async session used for both the setting and the ledger.
        """
        self.db = db

    async def get(self) -> InstanceDailyBudgetResponse:
        """Return both configured bounds, the enforced one, and today's spend.

        Returns:
            The full picture an operator needs to pilot the ceiling.
        """
        ceiling, setting = await read_setting_with_metadata(self.db, _KEY)
        spent, runs = await self._today_ledger()
        return self._response(ceiling, setting, spent=spent, runs=runs)

    async def set(
        self,
        update: InstanceDailyBudgetUpdate,
        admin_user_id: UUID,
        request: Request,
    ) -> InstanceDailyBudgetResponse:
        """Set (or clear) the operator ceiling.

        Args:
            update: New ceiling in euros; ``None`` clears the operator value
                and leaves only the deployment bound in force.
            admin_user_id: Admin making the change.
            request: FastAPI request, for the audit trail.

        Returns:
            The updated picture, including today's spend.
        """
        setting = await write_setting(
            self.db,
            _KEY,
            update.ceiling_eur,
            action="instance_daily_budget_changed",
            admin_user_id=admin_user_id,
            request=request,
            change_reason=update.change_reason,
        )
        spent, runs = await self._today_ledger()
        return self._response(update.ceiling_eur, setting, is_default=False, spent=spent, runs=runs)

    async def _today_ledger(self) -> tuple[Decimal, int]:
        """Return what the instance spent today and how many runs it charged.

        A missing row means the day has not started spending, not an error.
        """
        utc_day = datetime.now(UTC).date()
        result = await self.db.execute(
            select(InstanceDailyBudget.spent_cost_eur, InstanceDailyBudget.run_count).where(
                InstanceDailyBudget.utc_day == utc_day
            )
        )
        row = result.first()
        if row is None:
            return Decimal("0"), 0
        return Decimal(str(row[0])), int(row[1])

    @staticmethod
    def _response(
        ceiling: Decimal | None,
        setting: SystemSetting | None,
        *,
        is_default: bool | None = None,
        spent: Decimal | None = None,
        runs: int = 0,
    ) -> InstanceDailyBudgetResponse:
        """Assemble the response, resolving what actually applies."""
        deployment = settings.instance_daily_budget_eur
        return InstanceDailyBudgetResponse(
            ceiling_eur=ceiling,
            deployment_ceiling_eur=deployment,
            effective_ceiling_eur=InstanceBudgetService.resolve_ceiling(deployment, ceiling),
            spent_today_eur=spent if spent is not None else Decimal("0"),
            runs_today=runs,
            updated_by=setting.updated_by if setting else None,
            updated_at=setting.updated_at if setting else None,
            is_default=(setting is None) if is_default is None else is_default,
        )
