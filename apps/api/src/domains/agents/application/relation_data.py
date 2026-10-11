"""Reuse local source card identities, ownership, totals and privacy without provider work."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.relation_data_schemas import (
    BoundedRelationDetail,
    BoundedRelationsOverview,
    RelationDataProjection,
    RelationDataRead,
)
from src.domains.relations.service import RelationsService

_DETAIL_SECTIONS = {
    "open_loops": "open_loops_total",
    "recent_calls": "recent_calls_total",
    "memories": "memories_total",
    "peer_messages": "peer_messages_total",
    "merged_from": "merged_from_total",
}


async def read_relation_data(
    db: AsyncSession, actor_id: UUID, query: RelationDataRead
) -> RelationDataProjection:
    selected = RelationDataRead.model_validate(query)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    service = RelationsService(actor_id)
    overview = None
    detail = None
    source_page_has_more = False
    end = selected.offset + selected.limit
    if selected.name is None:
        source = await service.build_overview()
        overview = BoundedRelationsOverview.model_validate(
            {
                **source.model_dump(mode="json"),
                "relations": [
                    row.model_dump(mode="json") for row in source.relations[selected.offset : end]
                ],
            }
        )
        source_page_has_more = len(source.relations) > end
    else:
        card = await service.build_detail(selected.name)
        public = card.model_dump(mode="json")
        public["merged_from_total"] = len(card.merged_from)
        source_page_has_more = any(len(public[section]) > end for section in _DETAIL_SECTIONS)
        for section in _DETAIL_SECTIONS:
            public[section] = public[section][selected.offset : end]
        detail = BoundedRelationDetail.model_validate(public)
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    if overview is not None:
        overview = overview.model_copy(update={"debrief_enabled": actor.relation_debrief_enabled})
    return RelationDataProjection(
        overview=overview,
        detail=detail,
        overview_truncated=overview is not None
        and overview.relations_total > len(overview.relations),
        detail_truncated=detail is not None
        and any(
            getattr(detail, total) > len(getattr(detail, section))
            for section, total in _DETAIL_SECTIONS.items()
        ),
        observed_at=datetime.now(UTC),
        next_offset=end if source_page_has_more else None,
    )
