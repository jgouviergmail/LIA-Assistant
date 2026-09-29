"""One access policy for chat debug output and background native diagnostics."""

from src.domains.system_settings.service import (
    get_debug_panel_enabled,
    get_debug_panel_user_access_enabled,
)
from src.domains.users.models import User
from src.domains.users.schemas import UserProfile


async def can_read_debug(user: User | UserProfile) -> bool:
    if not user.is_active:
        return False
    if user.is_superuser:
        return await get_debug_panel_enabled()
    return bool(user.debug_panel_enabled) and await get_debug_panel_user_access_enabled()
