"""Offer SMS reads only after live source permission; settings stay independently usable."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.sms.reads import require_read
from src.infrastructure.database.session import get_db_context


async def without_unconsented_sms(
    manifests: Sequence[ToolManifest], owner: UUID
) -> list[ToolManifest]:
    if not any(manifest.agent == "sms_agent" for manifest in manifests):
        return list(manifests)
    try:
        async with get_db_context() as db:
            await require_read(db, owner, assistant=True)
        return list(manifests)
    except AuthorizationError, SQLAlchemyError, OSError, TimeoutError:
        return [manifest for manifest in manifests if manifest.agent != "sms_agent"]
