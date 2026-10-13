"""The kept answers as a portrait source: what the person chose to keep (2026-10-12).

Installed into ``domains/shared/portrait_sources`` so ``journals`` reads it
without importing this domain. One gate read at call time, the operator switch.
Every bookmark is rendered newest first with the request it answered, its date
and a bounded EXCERPT of the answer: a kept answer can be pages long, so the
excerpt stops at ``BOOKMARK_EXCERPT_MAX_CHARS`` and the section header states
that bound. The cut carries no marker: a line with one was invisible to the
model (the catalogue admits whole lines only — measured 2026-10-12), and the
excerpt IS the item, the same text at generation and at review. A read that
fails is ``unavailable``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.markup_detection import looks_like_html
from src.domains.bookmarks.models import MessageBookmark
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.rag_spaces.processing import html_to_markdown
from src.domains.shared.portrait_sources import (
    FreshnessProbe,
    PortraitSourceSection,
    empty_section,
    flat_item,
    install_portrait_source,
    portrait_lines,
)
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

KEY = "bookmarks"

#: The longest excerpt of a kept answer the prompt carries; the header states it.
BOOKMARK_EXCERPT_MAX_CHARS = 600

#: A kept notification answered no request (ADR-282): the line says so with a dash.
NO_REQUEST = "—"


async def _allowed(user_id: UUID | None = None) -> bool:
    return await is_capability_enabled(PlatformCapability.BOOKMARKS)


async def _rows(db: Any, user_id: UUID) -> list[MessageBookmark]:
    """Every kept answer, the newest first, then id."""
    stmt = (
        select(MessageBookmark)
        .where(MessageBookmark.user_id == user_id)
        .order_by(MessageBookmark.answered_at.desc(), MessageBookmark.id)
    )
    return list((await db.execute(stmt)).scalars().all())


def _excerpt(content: str) -> str:
    text = flat_item(html_to_markdown(content) if looks_like_html(content) else content)
    return text[:BOOKMARK_EXCERPT_MAX_CHARS].rstrip()


async def read_bookmarks(*, user_id: UUID, language: str) -> PortraitSourceSection:
    """Render every kept answer of one account.

    Args:
        user_id: The account.
        language: Unused — a kept answer is already in the person's language.

    Returns:
        The section; never raises.
    """
    try:
        if not await _allowed(user_id):
            return empty_section(KEY, "disabled")
        async with get_db_context() as db:
            rows = await _rows(db, user_id)
        if not rows:
            return empty_section(KEY, "empty")
        lines = portrait_lines()
        items = [
            lines["bookmarks_item"].format(
                request=flat_item(row.request_content or "") or NO_REQUEST,
                date=f"{row.answered_at:%Y-%m-%d}",
                excerpt=_excerpt(row.content),
            )
            for row in rows
        ]
        header = lines["bookmarks_header"].format(
            shown=len(items), total=len(items), excerpt_max=BOOKMARK_EXCERPT_MAX_CHARS
        )
        return PortraitSourceSection(
            key=KEY,
            status="used",
            text="\n".join([header, *items]),
            used=len(items),
            total=len(items),
        )
    except Exception as exc:  # noqa: BLE001 — a blind source is named, never read as empty
        logger.warning("portrait_source_unavailable", source=KEY, error_type=type(exc).__name__)
        return empty_section(KEY, "unavailable")


FRESHNESS = FreshnessProbe(
    table="message_bookmarks",
    user_column="user_id",
    stamp_column="created_at",
    allowed=_allowed,
    semantic_columns=("content", "request_content", "answered_at"),
)

install_portrait_source(KEY, read_bookmarks, FRESHNESS)

__all__ = ["BOOKMARK_EXCERPT_MAX_CHARS", "FRESHNESS", "KEY", "read_bookmarks"]
