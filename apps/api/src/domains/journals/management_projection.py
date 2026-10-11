"""Management API and native readers share source setting, size, cost and theme projection."""

from uuid import UUID

from src.core.config import settings
from src.core.constants import (
    JOURNAL_CONSOLIDATION_ENABLED_DEFAULT,
    JOURNAL_CONSOLIDATION_WITH_HISTORY_DEFAULT,
)
from src.domains.journals.models import JournalTheme
from src.domains.journals.schemas import (
    JournalSettingsResponse,
    JournalThemeInfo,
    JournalThemesResponse,
    ThemeCount,
)
from src.domains.journals.service import JournalService
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def build_journal_theme_counts(theme_counts: dict[str, int], user_id: UUID) -> list[ThemeCount]:
    """Convert raw per-theme counts into validated response items.

    A theme string absent from :class:`JournalTheme` is skipped, not raised on:
    ``JournalTheme(unknown)`` raises ``ValueError``, which would turn a single
    unexpected row into a 500 on ``GET /journals`` — the whole journal page,
    not just one counter. Skipping keeps the page usable; the warning keeps the
    anomaly visible rather than silently swallowed.

    Args:
        theme_counts: Mapping of raw theme code to active entry count.
        user_id: Owner user UUID, for the anomaly log.

    Returns:
        One ``ThemeCount`` per recognised theme.
    """
    counts: list[ThemeCount] = []
    for raw_theme, count in theme_counts.items():
        try:
            theme = JournalTheme(raw_theme)
        except ValueError:
            logger.warning(
                "journal_unknown_theme_in_corpus",
                user_id=str(user_id),
                theme=raw_theme,
                count=count,
            )
            continue
        counts.append(ThemeCount(theme=theme, count=count))
    return counts


def available_journal_themes() -> JournalThemesResponse:
    """Expose the management API's canonical themes without another registry."""
    return JournalThemesResponse(
        themes=[
            JournalThemeInfo(code=theme.value, label=theme.value.replace("_", " ").title())
            for theme in JournalTheme
        ]
    )


async def build_journal_settings(
    user: User, service: JournalService, *, portrait_invalidated: bool | None = None
) -> JournalSettingsResponse:
    """Build full settings response with size and cost info.

    Args:
        user: Authenticated User model with journal_* fields.
        service: JournalService instance for size queries.

    Returns:
        Complete JournalSettingsResponse with size and cost info.
    """
    max_total_chars = getattr(
        user, "journal_max_total_chars", settings.journal_default_max_total_chars
    )
    size_info = await service.get_size_info(user.id, max_total_chars)
    last_cost = JournalService.build_cost_info_from_user(user)

    return JournalSettingsResponse(
        journals_enabled=getattr(user, "journals_enabled", settings.journals_enabled),
        portrait_invalidated=portrait_invalidated,
        journal_consolidation_enabled=getattr(
            user, "journal_consolidation_enabled", JOURNAL_CONSOLIDATION_ENABLED_DEFAULT
        ),
        journal_consolidation_with_history=getattr(
            user, "journal_consolidation_with_history", JOURNAL_CONSOLIDATION_WITH_HISTORY_DEFAULT
        ),
        journal_max_total_chars=max_total_chars,
        journal_context_max_chars=getattr(
            user, "journal_context_max_chars", settings.journal_default_context_max_chars
        ),
        journal_max_entry_chars=getattr(
            user, "journal_max_entry_chars", settings.journal_max_entry_chars
        ),
        journal_context_max_results=getattr(
            user, "journal_context_max_results", settings.journal_context_max_results
        ),
        size_info=size_info,
        last_cost=last_cost,
    )
