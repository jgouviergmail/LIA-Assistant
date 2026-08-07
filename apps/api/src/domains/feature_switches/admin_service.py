"""Administration of the platform capability switches.

Reads and writes go through the GENERIC settings store (``write_setting``,
``read_setting_with_metadata``): audit trail, cache invalidation and codecs
are already solved there, and this service adds only what an operator needs
on top — the deployment ceiling shown next to the switch.

Why both bounds are returned: a switch an operator can flip but that does
nothing (because the deployment forbids the capability) is a trap. The panel
shows ``available`` separately from ``enabled`` and explains which bound
applies.

Created: 2026-08-06 (live-demonstrator programme, lot 3)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from src.domains.feature_switches.registry import (
    CAPABILITY_SPECS,
    PlatformCapability,
    deployment_allows,
)
from src.domains.feature_switches.schemas import (
    CapabilitySwitchResponse,
    CapabilitySwitchUpdate,
)
from src.domains.system_settings.service import (
    read_setting_with_metadata,
    write_setting,
)

if TYPE_CHECKING:
    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class CapabilitySwitchAdminService:
    """List and flip the instance capability switches."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with a database session.

        Args:
            db: Async session used for every switch read and write.
        """
        self.db = db

    async def list_switches(self) -> list[CapabilitySwitchResponse]:
        """Every capability, its stored switch and what actually applies.

        Returns:
            One entry per capability, in declaration order.
        """
        capabilities = list(CAPABILITY_SPECS)
        rows = await asyncio.gather(*(self._read_one(capability) for capability in capabilities))
        return list(rows)

    async def set_switch(
        self,
        capability: PlatformCapability,
        update: CapabilitySwitchUpdate,
        admin_user_id: UUID,
        request: Request,
    ) -> CapabilitySwitchResponse:
        """Turn one capability on or off.

        Turning it "on" only lifts the operator's own restriction: a
        deployment that forbids the capability keeps it unavailable, and the
        response says so rather than pretending the switch took effect.

        Args:
            capability: The capability to flip.
            update: Desired state and optional reason.
            admin_user_id: Admin making the change.
            request: FastAPI request, for the audit trail.

        Returns:
            The capability's new reported state.
        """
        spec = CAPABILITY_SPECS[capability]
        await write_setting(
            self.db,
            spec.setting_key,
            update.enabled,
            action=f"capability_{capability.value}_changed",
            admin_user_id=admin_user_id,
            request=request,
            change_reason=update.change_reason,
        )
        logger.info(
            "capability_switch_updated",
            capability=capability.value,
            enabled=update.enabled,
            admin_user_id=str(admin_user_id),
        )
        return await self._read_one(capability)

    async def _read_one(self, capability: PlatformCapability) -> CapabilitySwitchResponse:
        """Assemble one capability's reported state."""
        spec = CAPABILITY_SPECS[capability]
        switch, setting = await read_setting_with_metadata(self.db, spec.setting_key)
        available = deployment_allows(capability)
        return CapabilitySwitchResponse(
            capability=capability.value,
            label_key=spec.label_key,
            switch_enabled=bool(switch),
            deployment_available=available,
            # What the runtime actually enforces.
            effective_enabled=available and bool(switch),
            enforced_in_catalogue=bool(spec.agents),
            enforced_on_routes=spec.route_enforced or spec.service_enforced,
            updated_by=setting.updated_by if setting else None,
            updated_at=setting.updated_at if setting else None,
            is_default=setting is None,
        )
