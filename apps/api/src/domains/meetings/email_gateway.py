"""Seal original email renderings and send through the existing owned service."""

import hashlib
import json
from dataclasses import asdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import normalize_language
from src.domains.meetings.delivery import minutes_subject
from src.domains.meetings.models import Meeting
from src.domains.meetings.render import build_header, render_html, render_markdown
from src.domains.meetings.schemas import MeetingReport
from src.domains.meetings.service import MeetingService, raise_meeting_not_found
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.infrastructure.email.email_service import get_email_service
from src.infrastructure.meeting_email import MeetingEmailConfirmation, MeetingEmailSnapshot


def email_snapshot(meeting: Meeting, report: MeetingReport, actor: User) -> MeetingEmailSnapshot:
    language = normalize_language(actor.language)
    header = build_header(meeting, report, language=language, gaps=meeting.audio_gaps)
    subject = minutes_subject(report, language)
    sender = get_email_service().smtp_from
    return MeetingEmailSnapshot(
        meeting_id=meeting.id,
        title=report.title,
        recipient=str(actor.email),
        sender=sender,
        subject=subject,
        language=language,
        participants_count=len(report.participants),
        sections_count=len(report.sections),
        previous_sent_at=meeting.email_sent_at,
        source_digest=hashlib.sha256(
            json.dumps(
                {
                    "header": asdict(header),
                    "report": report.model_dump(mode="json"),
                    "html": render_html(report, header),
                    "text": render_markdown(report, header),
                    "recipient": str(actor.email),
                    "sender": sender,
                    "subject": subject,
                    "language": language,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest(),
    )


class SavedMeetingEmail:
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingEmailSnapshot:
        actor = await UserRepository(db).get_by_id(actor_id)
        if actor is None:
            raise_meeting_not_found(meeting_id)
        meeting, report = await MeetingService(db)._ready_with_report(actor_id, meeting_id)
        return email_snapshot(meeting, report, actor)

    async def send(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: MeetingEmailConfirmation,
    ) -> None:
        actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
        service = MeetingService(db)
        if (
            actor is None
            or await service.repo.get_for_user(meeting_id, actor_id, lock=True) is None
        ):
            raise_meeting_not_found(meeting_id)
        meeting, report = await service._ready_with_report(actor_id, meeting_id)
        await confirmation.validate(email_snapshot(meeting, report, actor))
        await confirmation.check()
        await service.email(actor, meeting_id, confirmation=confirmation)
