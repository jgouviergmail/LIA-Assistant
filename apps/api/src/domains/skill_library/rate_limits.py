"""One UI/native per-account limiter for the library's shared anonymous network allowance."""

from src.core.config import settings
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter

rate_limit_library = create_user_rate_limiter(
    "skill_library",
    max_calls=settings.skill_library_rate_limit_calls,
    window_seconds=settings.skill_library_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)
