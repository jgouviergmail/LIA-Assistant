"""Read the original UI owners, excluding credentials, raw audio and diagnostic messages."""

import json
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.meeting_reports import MeetingReport
from src.domains.meetings.read_projection import (
    MEETING_DETAIL_FIELDS,
    MEETING_LIMIT_FIELDS,
    MEETING_SUMMARY_FIELDS,
    content_page,
)
from src.domains.meetings.schemas import MeetingDetailResponse
from src.domains.meetings.service import MeetingService
from src.domains.meetings.template_service import MeetingTemplateService
from src.infrastructure.meeting_reads import (
    CONTENT_VIEWS,
    MeetingReadInput,
    MeetingReadPage,
    MeetingReadView,
    TemplateReadInput,
    TemplateReadView,
)


def _page(
    view: MeetingReadView | TemplateReadView,
    data: dict[str, JsonValue],
    total: int,
    offset: int,
    count: int,
) -> MeetingReadPage:
    end = offset + count
    return MeetingReadPage(
        view=view,
        observed_at=datetime.now(UTC),
        data=data,
        total=total,
        offset=offset,
        next_offset=end if count and end < total else None,
    )


def _project_detail(detail: MeetingDetailResponse, query: MeetingReadInput) -> MeetingReadPage:
    if query.view in CONTENT_VIEWS:
        included: set[str] = {query.view}
        data = detail.model_dump(mode="json", include=included)[query.view]
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        page = content_page(query.view, text, query.offset, query.characters, query.expected_digest)
        return page.model_copy(
            update={"data": {"meeting_id": str(detail.id), "available": data is not None}}
        )
    metadata = detail.model_dump(mode="json", include=MEETING_DETAIL_FIELDS)
    metadata["has_report"] = detail.report is not None
    metadata["has_template_snapshot"] = detail.template_snapshot is not None
    metadata["error_message_withheld"] = detail.last_error_message is not None
    return _page(query.view, metadata, 1, 0, 1)


async def _meeting_detail(
    service: MeetingService, actor_id: UUID, query: MeetingReadInput
) -> MeetingReadPage:
    assert query.meeting_id is not None
    if query.view == "generated_report":
        meeting = await service.get(actor_id, query.meeting_id)
        generated = (
            MeetingReport.model_validate(meeting.report_generated).model_dump(mode="json")
            if meeting.report_generated is not None
            else None
        )
        text = json.dumps(generated, ensure_ascii=False, separators=(",", ":"))
        page = content_page(query.view, text, query.offset, query.characters, query.expected_digest)
        return page.model_copy(
            update={
                "data": {
                    "meeting_id": str(meeting.id),
                    "available": generated is not None,
                    "version": "generated",
                }
            }
        )
    detail = await service.detail(
        actor_id, query.meeting_id, include_transcript=query.view == "transcript"
    )
    return _project_detail(detail, query)


class SavedMeetingReads:
    async def meetings(
        self, db: AsyncSession, actor_id: UUID, query: MeetingReadInput
    ) -> MeetingReadPage:
        service = MeetingService(db)
        if query.view == "limits":
            return _page(
                query.view,
                {"limits": service.limits().model_dump(mode="json", include=MEETING_LIMIT_FIELDS)},
                1,
                0,
                1,
            )
        if query.view == "list":
            rows, total = await service.list_meetings(
                actor_id, limit=query.limit, offset=query.offset
            )
            summaries: list[JsonValue] = [
                service.to_summary(row).model_dump(mode="json", include=MEETING_SUMMARY_FIELDS)
                for row in rows
            ]
            return _page(
                query.view,
                {"items": summaries, "pagination": "live"},
                total,
                query.offset,
                len(summaries),
            )
        if query.view == "active":
            row = await service.get_live(actor_id)
            if row is None:
                return _page(query.view, {"active": None}, 0, 0, 0)
            return _project_detail(service.to_detail(row, include_transcript=False), query)
        return await _meeting_detail(service, actor_id, query)

    async def templates(
        self, db: AsyncSession, actor_id: UUID, query: TemplateReadInput, language: str | None
    ) -> MeetingReadPage:
        service = MeetingTemplateService(db)
        if query.view == "template":
            assert query.ref is not None
            template = await service.get(actor_id, query.ref, language)
            text = json.dumps(
                template.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
            )
            page = content_page(
                query.view, text, query.offset, query.characters, query.expected_digest
            )
            return page.model_copy(
                update={"data": {"ref": template.ref, "builtin": template.builtin}}
            )
        library = await service.library(actor_id, language)
        selected = library.items[query.offset : query.offset + query.limit]
        data: dict[str, JsonValue] = {
            "items": [item.model_dump(mode="json") for item in selected],
            "max_user_templates": library.max_user_templates,
            "pagination": "live",
        }
        return _page(query.view, data, len(library.items), query.offset, len(selected))
