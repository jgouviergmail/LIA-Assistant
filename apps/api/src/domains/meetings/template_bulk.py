"""Template batches (ADR-259): add several built-ins to « My templates », delete several rows.

A batch never fails as a whole for one ref: every ref is reported created /
deleted or skipped with the stable code the UI localizes. Each item commits on
its own, so a failure leaves the earlier ones done and the later ones
attempted. A deleted row that the default-format preference pointed at resets
the preference — and the response says so, so the UI can tell the user.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog

from src.core.exceptions import BaseAPIException
from src.domains.meetings.schemas import (
    MeetingTemplateBulkDeleteResponse,
    MeetingTemplateBulkDuplicateResponse,
    MeetingTemplateCreate,
    MeetingTemplateSummary,
    TemplateBulkSkipped,
)
from src.domains.meetings.template_service import parse_ref

if TYPE_CHECKING:
    from src.domains.meetings.template_service import MeetingTemplateService

logger = structlog.get_logger(__name__)


def _code_of(exc: BaseAPIException, fallback: str) -> str:
    """The stable code a refusal carries, or ``fallback`` when it carries none."""
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        return str(detail["code"])
    return fallback


async def bulk_duplicate(
    service: MeetingTemplateService,
    user_id: uuid.UUID,
    refs: list[str],
    language: str | None,
) -> MeetingTemplateBulkDuplicateResponse:
    """Create one user row per ref (duplicates ignored), in request order.

    Args:
        service: The template service (cap, naming and persistence live there).
        user_id: The owner of the new rows.
        refs: Built-in or user refs to copy.
        language: The user's language, for the built-ins' localized names.

    Returns:
        The created summaries and the refs left untouched with their reasons.
    """
    created: list[MeetingTemplateSummary] = []
    skipped: list[TemplateBulkSkipped] = []
    for ref in dict.fromkeys(refs):
        try:
            # A malformed ref is refused with the same code a single request gets,
            # not with the request model's validation error.
            parse_ref(ref)
            row = await service.create(user_id, MeetingTemplateCreate(duplicate_of=ref), language)
        except BaseAPIException as exc:
            skipped.append(TemplateBulkSkipped(ref=ref, code=_code_of(exc, "duplicate_failed")))
            continue
        created.append(
            MeetingTemplateSummary(
                ref=row.ref,
                name=row.name,
                description=row.description,
                category=row.category,
                builtin=False,
                sections_count=len(row.sections),
                auto_selectable=row.auto_selectable,
            )
        )
    logger.info(
        "meeting_templates_bulk_duplicated",
        user_id=str(user_id),
        created=len(created),
        skipped=len(skipped),
    )
    return MeetingTemplateBulkDuplicateResponse(created=created, skipped=skipped)


async def bulk_delete(
    service: MeetingTemplateService,
    user_id: uuid.UUID,
    refs: list[str],
) -> MeetingTemplateBulkDeleteResponse:
    """Delete the user's rows named by ``refs``, reporting each one.

    Args:
        service: The template service.
        user_id: The owner.
        refs: User refs to delete; a built-in or a foreign row is skipped.

    Returns:
        The deleted refs, the skipped ones with their reasons, and whether the
        default-format preference was reset because it pointed at a deleted row.
    """
    deleted: list[str] = []
    skipped: list[TemplateBulkSkipped] = []
    preference_reset = False
    for ref in dict.fromkeys(refs):
        try:
            preference_reset = await service.delete(user_id, ref) or preference_reset
        except BaseAPIException as exc:
            skipped.append(TemplateBulkSkipped(ref=ref, code=_code_of(exc, "delete_failed")))
        except Exception as exc:  # noqa: BLE001 - reported per ref, never raised for the batch
            logger.warning("meeting_template_bulk_delete_failed", ref=ref, error=str(exc))
            await service.db.rollback()
            skipped.append(TemplateBulkSkipped(ref=ref, code="delete_failed"))
        else:
            deleted.append(ref)
    logger.info(
        "meeting_templates_bulk_deleted",
        user_id=str(user_id),
        deleted=len(deleted),
        skipped=len(skipped),
        preference_reset=preference_reset,
    )
    return MeetingTemplateBulkDeleteResponse(
        deleted=deleted, skipped=skipped, preference_reset=preference_reset
    )
