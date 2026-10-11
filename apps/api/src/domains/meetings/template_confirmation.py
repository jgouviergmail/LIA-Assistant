"""Original template writes expose fresh facts and a known commit acknowledgment."""

from typing import Literal

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.schemas import MeetingTemplateResponse
from src.infrastructure.confirmed_commit import commit_confirmed_write
from src.infrastructure.meeting_templates import (
    TemplateCommitUnknown as TemplateCommitUnknown,
)
from src.infrastructure.meeting_templates import (
    TemplateWriteConfirmation as TemplateWriteConfirmation,
)
from src.infrastructure.meeting_templates import (
    TemplateWriteFacts as TemplateWriteFacts,
)


def template_receipt(
    kind: Literal["meeting_template_created", "meeting_template_updated"],
    response: MeetingTemplateResponse,
) -> dict[str, JsonValue]:
    """The chat receipt identifies the saved row without repeating private instructions."""
    return {
        kind: {
            "ref": response.ref,
            "name": response.name,
            "sections_count": len(response.sections),
            "saved": True,
        }
    }


async def validate_template_write(
    confirmation: TemplateWriteConfirmation | None, facts: TemplateWriteFacts
) -> None:
    if confirmation is not None:
        await confirmation.check()
        await confirmation.validate(facts)


async def commit_template_write(
    db: AsyncSession,
    confirmation: TemplateWriteConfirmation | None,
    values: dict[str, JsonValue],
    *,
    no_op: bool = False,
) -> None:
    await commit_confirmed_write(db, confirmation, values, no_op=no_op)
