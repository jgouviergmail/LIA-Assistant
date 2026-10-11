"""Fresh, fail-closed application tool availability at every execution boundary.

The generic settings reader intentionally degrades to its default on outages.
For this management surface a failed read must not undo an operator's refusal;
read the persisted switch on the operation's short-lived database session.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings as settings
from src.core.exceptions import AuthorizationError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability


def application_access_error_code(error: AuthorizationError) -> str:
    """Project only finite public reasons, without serializing dependency details."""
    if isinstance(error.detail, dict):
        if error.detail.get("error_code") == "CAPABILITY_DISABLED":
            return "CAPABILITY_DISABLED"
        if error.detail.get("error_code") == "SERVICE_UNAVAILABLE":
            return "DEPENDENCY_ERROR"
    return "FORBIDDEN"


async def require_application_tools(db: AsyncSession) -> None:
    await require_capability_fresh(db, PlatformCapability.APPLICATION_TOOLS)
