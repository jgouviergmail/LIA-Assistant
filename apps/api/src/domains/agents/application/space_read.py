"""Read source space UI data with current authority and bounded output, without any provider."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_not_found_or_unauthorized
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.space_read_schemas import (
    SPACE_READ_MAX_BYTES,
    SpaceUIProjection,
    SpaceUIQuery,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces import ui_queries
from src.domains.rag_spaces.document_catalogue import read_document_catalogue
from src.domains.rag_spaces.schemas import (
    RAGDocumentResponse,
    RAGDriveSourceResponse,
    RAGMailSourceResponse,
)


async def _read_access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    await load_actor(db, actor_id)


def _protect_support_diagnostics(result: SpaceUIProjection) -> None:
    """Raw provider/support errors can contain credentials and storage paths."""
    rows: list[RAGDocumentResponse | RAGDriveSourceResponse | RAGMailSourceResponse] = [
        *result.documents,
        *result.drive_sources,
        *result.mail_sources,
    ]
    result.technical_diagnostics_withheld = any(row.error_message is not None for row in rows)
    for row in rows:
        row.error_message = None


async def _read_owned_section(
    db: AsyncSession, actor_id: UUID, selected: SpaceUIQuery, result: SpaceUIProjection
) -> list[UUID]:
    assert selected.space_id is not None
    space = await ui_queries.owned_space(db, actor_id, selected.space_id)
    paging = {"limit": selected.limit, "offset": selected.offset}
    if selected.section == "space":
        result.space = await ui_queries.space_metadata(db, space)
    elif selected.section == "documents":
        result.documents, result.total = await ui_queries.documents_page(db, space.id, **paging)
    elif selected.section == "drive_sources":
        result.drive_sources, result.total = await ui_queries.drive_sources_page(
            db, space.id, **paging
        )
    else:
        result.mail_sources, result.total = await ui_queries.mail_sources_page(
            db, space.id, **paging
        )
    return [space.id]


async def read_space_ui(db: AsyncSession, actor_id: UUID, query: SpaceUIQuery) -> SpaceUIProjection:
    selected = SpaceUIQuery.model_validate(query.model_dump(exclude_unset=True))
    await _read_access(db, actor_id)
    result = SpaceUIProjection(section=selected.section, observed_at=datetime.now(UTC))
    paging = {"limit": selected.limit, "offset": selected.offset}
    if selected.section == "spaces":
        result.spaces, result.total = await ui_queries.spaces_page(db, actor_id, **paging)
        identities = [space.id for space in result.spaces]
    elif selected.section == "attachable_documents":
        catalogue = await read_document_catalogue(db, actor_id, q=selected.q, **paging)
        result.attachable_documents, result.total = catalogue.items, catalogue.total
        identities = list(dict.fromkeys(item.space_id for item in catalogue.items))
    else:
        identities = await _read_owned_section(db, actor_id, selected, result)
    await _read_access(db, actor_id)
    if await ui_queries.count_owned_observations(db, actor_id, identities) != len(identities):
        raise_not_found_or_unauthorized("space", selected.space_id)
    _protect_support_diagnostics(result)
    next_offset = selected.offset + selected.limit
    result.next_offset = (
        next_offset if result.total is not None and next_offset < result.total else None
    )
    if len(result.model_dump_json().encode("utf-8")) > SPACE_READ_MAX_BYTES:
        raise ValueError("Space UI page too large; request a smaller page")
    return SpaceUIProjection.model_validate(result.model_dump(mode="json"))
