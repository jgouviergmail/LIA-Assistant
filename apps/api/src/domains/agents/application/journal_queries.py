"""Journal management observation is separate from semantic search and prompt injection."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.journal_read_schemas import JournalRead, JournalsProjection
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.journals.management_projection import (
    available_journal_themes,
    build_journal_settings,
    build_journal_theme_counts,
)
from src.domains.journals.management_read import read_journal_page
from src.domains.journals.schemas import JournalSettingsUpdate
from src.domains.journals.service import JournalService
from src.domains.users.models import User


async def require_journal_access(db: AsyncSession, actor_id: UUID) -> User:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.JOURNALS)
    return await load_actor(db, actor_id)


async def read_journals(db: AsyncSession, actor_id: UUID, query: JournalRead) -> JournalsProjection:
    selected = JournalRead.model_validate(query.model_dump())
    actor = await require_journal_access(db, actor_id)
    preferences = {name: getattr(actor, name) for name in JournalSettingsUpdate.model_fields}
    service = JournalService(db)
    page = await read_journal_page(
        db,
        actor_id,
        theme=selected.theme,
        status=selected.status,
        limit=selected.limit,
        after_id=selected.after_id,
    )
    source = await build_journal_settings(actor, service)
    themes = build_journal_theme_counts(await service.get_theme_counts(actor_id), actor_id)
    refreshed = await require_journal_access(db, actor_id)
    if preferences != {
        name: getattr(refreshed, name) for name in JournalSettingsUpdate.model_fields
    }:
        raise ValueError("Journal preferences changed while reading; retry")
    rows, more = page.rows[: selected.limit], len(page.rows) > selected.limit
    return JournalsProjection(
        entries=rows,
        total=page.total,
        by_theme=themes,
        total_chars=source.size_info.total_chars,
        max_total_chars=source.size_info.max_total_chars,
        usage_pct=source.size_info.usage_pct,
        settings=source,
        themes=available_journal_themes(),
        returned_count=len(rows),
        truncated=more,
        next_cursor=rows[-1].id if more else None,
        observed_at=datetime.now(UTC),
    )
