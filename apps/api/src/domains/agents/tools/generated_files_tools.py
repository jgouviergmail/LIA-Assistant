"""Generated-files lookup — the files LIA produced, found again and SHOWN (ADR-318).

« Show me the image you made yesterday », « where is the report? » — the gallery
holds them (ADR-279) and this tool finds them for a turn, across the families
at once, newest first, with the EXACT total beside a capped page (ADR-185).

What it finds it SHOWS: each file is queued as the chat's own card — an image
card for images and screenshots, a document card for documents — through the
stores the producers use, keyed by the CONVERSATION (stable across a sub-agent's
synthetic thread), so the card lands under the answer and survives a reload
like the original did. The model is told the cards are shown, so it adds no
link of its own. A voice surface draws no card: the domain is deliberately
absent from ``PHONE_DOMAINS``.

Only a file that can still be opened is listed — its deadline not passed: the
cleanup removes a row at its next pass, and a card must not point at a file
about to vanish. Read-only; the logs carry counts only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Annotated, Any, Final
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.constants import AGENT_GENERATED_FILE
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.generated_file.catalogue_manifests import (
    GENERATED_FILE_ORIGINS,
    GENERATED_FILES_END_DESCRIPTION,
    GENERATED_FILES_FAMILY_DESCRIPTION,
    GENERATED_FILES_MAX_RESULTS_DESCRIPTION,
    GENERATED_FILES_QUERY_DESCRIPTION,
    GENERATED_FILES_START_DESCRIPTION,
    GeneratedFileFamily,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.lookup_parameters import bounded_count, read_period
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.attachments.gallery_queries import GalleryFilters
from src.domains.attachments.models import Attachment, AttachmentOrigin
from src.domains.attachments.service import AttachmentService
from src.domains.attachments.urls import attachment_url
from src.domains.document_generation.document_store import PendingDocument, store_pending_document
from src.domains.image_generation.image_store import store_pending_image
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

#: The family each generated origin reads as, for the model.
_FAMILY_OF: Final[dict[str, str]] = {
    origin.value: family for family, origin in GENERATED_FILE_ORIGINS.items()
}
#: The inclusive gallery bound one tick below an exclusive instant (timestamps
#: are stored to the microsecond).
_TICK: Final = timedelta(microseconds=1)
#: What a document card calls a file whose name carries no extension.
_UNTYPED_DOCUMENT: Final = "file"


def _origins(family: str | None) -> list[AttachmentOrigin] | UnifiedToolOutput:
    """The gallery origins a family names — every one when omitted — or the refusal."""
    if family is None:
        return list(GENERATED_FILE_ORIGINS.values())
    origin = GENERATED_FILE_ORIGINS.get(family)
    if origin is None:
        return UnifiedToolOutput.failure(
            message=f"Unknown family '{family}'; accepted: {', '.join(GENERATED_FILE_ORIGINS)}.",
            error_code=ToolErrorCode.INVALID_PARAM_VALUE.value,
        )
    return [origin]


async def _search(
    user_id: UUID,
    origins: list[AttachmentOrigin],
    *,
    needle: str | None,
    bounds: tuple[datetime | None, datetime | None],
    now: datetime,
    limit: int,
) -> tuple[list[Attachment], int]:
    """Each family's newest page, merged newest first under ONE cap, and the exact total.

    The gallery statement serves one origin at a time; each page is already
    capped at ``limit``, so the merge holds at most ``limit`` per family before
    the cut, and the total is the sum of the exact per-family totals (ADR-185).
    """
    since, until = bounds
    async with get_db_context() as db:
        service = AttachmentService(db)
        pages = [
            await service.list_generated(
                user_id,
                GalleryFilters(
                    origin=origin,
                    query=needle,
                    created_after=since,
                    created_before=until - _TICK if until else None,
                    expires_after=now,
                    limit=limit,
                ),
            )
            for origin in origins
        ]
    merged = [row for page_rows, _total, _bytes in pages for row in page_rows]
    merged.sort(key=lambda row: (row.created_at, row.id), reverse=True)
    return merged[:limit], sum(page_total for _rows, page_total, _bytes in pages)


def _local(moment: datetime, zone: tzinfo) -> str:
    return moment.astimezone(zone).isoformat(timespec="minutes")


def _file_item(row: Attachment, zone: tzinfo) -> dict[str, str | int | None]:
    """One file as the model reads it."""
    return {
        "title": row.title or row.original_filename,
        "file_name": row.original_filename,
        "family": _FAMILY_OF.get(row.origin, row.origin),
        "created": _local(row.created_at, zone),
        "expires": _local(row.expires_at, zone),
        "size_bytes": row.file_size,
        "shared_by": row.shared_by_name,
    }


def _show(rows: list[Attachment], conversation_id: str) -> None:
    """Queue every file as the chat's own card, under this conversation's answer."""
    for row in rows:
        url = attachment_url(row.id)
        expires = row.expires_at.isoformat()
        if row.origin == AttachmentOrigin.GENERATED_DOCUMENT.value:
            extension = Path(row.original_filename).suffix.lstrip(".").lower()
            store_pending_document(
                conversation_id,
                PendingDocument(
                    url=url,
                    filename=row.original_filename,
                    doc_type=extension or _UNTYPED_DOCUMENT,
                    size_bytes=row.file_size,
                    expires_at=expires,
                ),
            )
        else:
            store_pending_image(
                conversation_id,
                url=url,
                alt_text=row.title or row.original_filename,
                expires_at=expires,
            )


def _message(total: int, shown: int) -> str:
    if total == 0:
        return (
            "No generated file matches. LIA keeps the files it produces "
            f"{settings.attachments_ttl_hours} hours: an older one is gone."
        )
    text = (
        f"{total} generated file(s) match; the {shown} most recent are SHOWN to the user as "
        "cards below the answer — do not add a link or an image."
    )
    if shown < total:
        text += f" The {total - shown} older matches are counted, not shown."
    return text


@read_tool(name="find_generated_files", agent_name=AGENT_GENERATED_FILE)
async def find_generated_files_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    query: Annotated[str | None, GENERATED_FILES_QUERY_DESCRIPTION] = None,
    family: Annotated[GeneratedFileFamily | None, GENERATED_FILES_FAMILY_DESCRIPTION] = None,
    start_date: Annotated[str | None, GENERATED_FILES_START_DESCRIPTION] = None,
    end_date: Annotated[str | None, GENERATED_FILES_END_DESCRIPTION] = None,
    max_results: Annotated[int | None, GENERATED_FILES_MAX_RESULTS_DESCRIPTION] = None,
) -> UnifiedToolOutput:
    """Find again the files LIA produced for the user — they are SHOWN as cards.

    Generated images and documents, browser screenshots, images a connection
    shared. Never add a link or an image yourself: the cards are drawn below
    the answer.

    Args:
        runtime: LangChain tool runtime (injected).
        query: Words of the file's title or name.
        family: image, document or screenshot; every family when omitted.
        start_date: Produced on or after this day.
        end_date: Produced on or before this day.
        max_results: How many files to return and show, clamped to the setting.

    Returns:
        UnifiedToolOutput with ``{files: [...], total, shown}``, newest first;
        a typed refusal on an unreadable period or an unknown family.
    """
    config = validate_runtime_config(runtime, "find_generated_files_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    context = tool_runtime_context(runtime)
    zone = resolve_user_timezone(context)
    now = datetime.now(UTC)
    period = read_period(start_date, end_date, zone, now=now, default_days=None)
    if isinstance(period, UnifiedToolOutput):
        return period
    origins = _origins(family)
    if isinstance(origins, UnifiedToolOutput):
        return origins

    user_id = UUID(str(config.user_id))
    rows, total = await _search(
        user_id,
        origins,
        needle=(query or "").strip() or None,
        bounds=period,
        now=now,
        limit=bounded_count(max_results, settings.generated_files_search_max_results),
    )
    if rows and context is not None:
        _show(rows, context.conversation_id)
    logger.info(
        "generated_files_lookup_completed",
        user_id=str(user_id),
        total=total,
        shown=len(rows),
        families=len(origins),
    )
    return UnifiedToolOutput.data_success(
        message=_message(total, len(rows)),
        structured_data={
            "files": [_file_item(row, zone) for row in rows],
            "total": total,
            "shown": len(rows),
        },
    )


__all__ = ["find_generated_files_tool"]
