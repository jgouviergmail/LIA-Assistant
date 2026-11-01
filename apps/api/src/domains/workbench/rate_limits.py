"""Per-account windows of the « Tools » section (ADR-369).

A person clicks; a script replaying a session would otherwise spend the
instance's provider quotas (the OAuth projects are the instance's). Five
windows, one per kind of act, each a setting. The account is read through the
route's own door — a session of its own, closed before the provider is called
(ADR-304) — so the limiter pins no request session either.

An act on a selection is charged once its size is read: the bulk window above
one item, the write window for one — filing messages one by one is not a bulk
act, and the bulk window is the narrowest.
"""

from src.core.config import settings
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User

rate_limit_read = create_user_rate_limiter(
    "workbench_read",
    max_calls=settings.workbench_read_rate_limit_calls,
    window_seconds=settings.workbench_read_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)
rate_limit_write = create_user_rate_limiter(
    "workbench_write",
    max_calls=settings.workbench_write_rate_limit_calls,
    window_seconds=settings.workbench_write_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)
rate_limit_send = create_user_rate_limiter(
    "workbench_send",
    max_calls=settings.workbench_send_rate_limit_calls,
    window_seconds=settings.workbench_send_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)
rate_limit_bulk = create_user_rate_limiter(
    "workbench_bulk",
    max_calls=settings.workbench_bulk_rate_limit_calls,
    window_seconds=settings.workbench_bulk_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)
rate_limit_download = create_user_rate_limiter(
    "workbench_download",
    max_calls=settings.workbench_download_rate_limit_calls,
    window_seconds=settings.workbench_download_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)


async def charge_selection(user: User, size: int) -> None:
    """Charge an act on ``size`` items to its window (429 when it is spent).

    Args:
        user: The signed-in account.
        size: How many items the act carries.
    """
    await (rate_limit_bulk if size > 1 else rate_limit_write)(user)
