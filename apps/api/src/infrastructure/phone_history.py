"""Injected call-history read boundary; source schemas remain owned by telephony."""

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError

if TYPE_CHECKING:
    from src.domains.telephony.history_schemas import PhoneHistoryProjection, PhoneHistoryRead


class PhoneHistoryGateway(Protocol):
    async def read(
        self, db: AsyncSession, actor_id: UUID, request: PhoneHistoryRead
    ) -> PhoneHistoryProjection: ...


_gateway: PhoneHistoryGateway | None = None


def configure_phone_history(gateway: PhoneHistoryGateway | None) -> PhoneHistoryGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_phone_history() -> PhoneHistoryGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
