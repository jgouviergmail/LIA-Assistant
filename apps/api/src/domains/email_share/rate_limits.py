"""UI and native email paths spend the same account send/suggestion windows."""

from src.core.config import settings
from src.domains.auth.dependencies import create_user_rate_limiter

rate_limit_email_share = create_user_rate_limiter(
    "email_share",
    max_calls=settings.email_share_rate_limit_calls,
    window_seconds=settings.email_share_rate_limit_window_seconds,
)
rate_limit_recipient_suggestions = create_user_rate_limiter(
    "email_share_recipients",
    max_calls=settings.email_share_suggest_rate_limit_calls,
    window_seconds=settings.email_share_suggest_rate_limit_window_seconds,
)
