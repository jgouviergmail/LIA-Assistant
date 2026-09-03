"""The template library service (ADR-259): built-ins read-only, user rows bounded.

Every reference the API receives is parsed here (``TemplateRef``) and resolved
against the two sources — the catalogue for ``builtin:`` and the user's own
rows for ``user:`` — with ownership enforced like every other meetings resource
(a foreign row and an unknown catalogue key both read as 404).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, NoReturn

import structlog
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.core.i18n_meeting_templates import TEMPLATE_KEYS
from src.domains.meetings.models import MeetingTemplate
from src.domains.meetings.repository import MeetingPreferenceRepository, MeetingTemplateRepository
from src.domains.meetings.schemas import (
    MeetingTemplateCreate,
    MeetingTemplateListResponse,
    MeetingTemplateResponse,
    MeetingTemplateSummary,
    MeetingTemplateUpdate,
    TemplateCategory,
    TemplateSection,
)
from src.domains.meetings.template_catalogue import (
    BUILTIN_BY_KEY,
    builtin_sections,
    builtin_summary,
    builtin_template,
)
from src.domains.meetings.template_ref import TemplateRef
from src.domains.meetings.templates import parse_sections, sections_to_json

logger = structlog.get_logger(__name__)


# ============================================================================
# Refusals (pattern: core/exceptions.py raise_* functions)
# ============================================================================


def raise_template_not_found(ref: str) -> NoReturn:
    """404 — a foreign row and an unknown catalogue key read the same."""
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "template_not_found"},
        log_event="meeting_template_not_found",
        ref=ref,
    )


def raise_template_ref_invalid(ref: str) -> NoReturn:
    """422 — the reference has neither of the two legal shapes."""
    raise BaseAPIException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "template_ref_invalid"},
        log_event="meeting_template_ref_invalid",
        ref=ref,
    )


def raise_template_readonly(ref: str) -> NoReturn:
    """409 — a built-in is customized by duplication, never edited in place."""
    raise BaseAPIException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "template_readonly"},
        log_event="meeting_template_readonly",
        ref=ref,
    )


def raise_template_limit(maximum: int) -> NoReturn:
    """409 — the user keeps as many templates as the instance allows; the bound is published."""
    raise BaseAPIException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "template_limit_reached", "max": maximum},
        log_event="meeting_template_limit_reached",
        max=maximum,
    )


# ============================================================================
# Resolved template — what the pipeline consumes
# ============================================================================


@dataclass(frozen=True)
class ResolvedTemplate:
    """A template ready to fill: its identity, name, category and sections."""

    ref: TemplateRef
    name: str
    category: TemplateCategory
    sections: list[TemplateSection]
    auto_selectable: bool
    description: str | None = None


def parse_ref(value: str) -> TemplateRef:
    """``TemplateRef.parse`` with the API refusal on a malformed value."""
    try:
        return TemplateRef.parse(value)
    except ValueError:
        raise_template_ref_invalid(value)


# ============================================================================
# Service
# ============================================================================


class MeetingTemplateService:
    """Library reads and writes; resolution of references for the pipeline."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = MeetingTemplateRepository(db)
        self.preference_repo = MeetingPreferenceRepository(db)

    # ------------------------------------------------------------------ reads

    async def library(
        self, user_id: uuid.UUID, language: str | None
    ) -> MeetingTemplateListResponse:
        """Every built-in (localized) followed by the user's own rows."""
        rows = await self.repo.list_for_user(user_id)
        items = [builtin_summary(key, language) for key in TEMPLATE_KEYS]
        items.extend(self._summary(row) for row in rows)
        return MeetingTemplateListResponse(
            items=items, max_user_templates=settings.meetings_max_user_templates
        )

    async def get(
        self, user_id: uuid.UUID, ref: str, language: str | None
    ) -> MeetingTemplateResponse:
        """One template with its sections, built-in or owned."""
        parsed = parse_ref(ref)
        if parsed.kind == "builtin":
            if parsed.key not in BUILTIN_BY_KEY:
                raise_template_not_found(ref)
            return builtin_template(str(parsed.key), language)
        return self._response(await self._owned_row(parsed, user_id))

    async def resolve(self, user_id: uuid.UUID, ref: str, language: str | None) -> ResolvedTemplate:
        """The sections behind a reference, for the pipeline and the preferences."""
        parsed = parse_ref(ref)
        if parsed.kind == "builtin":
            template = BUILTIN_BY_KEY.get(str(parsed.key))
            if template is None:
                raise_template_not_found(ref)
            summary = builtin_summary(template.key, language)
            return ResolvedTemplate(
                ref=parsed,
                name=summary.name,
                category=template.category,
                sections=builtin_sections(template.key, language),
                auto_selectable=template.auto_selectable,
                description=summary.description,
            )
        row = await self._owned_row(parsed, user_id)
        return ResolvedTemplate(
            ref=parsed,
            name=row.name,
            category=TemplateCategory(row.category),
            sections=parse_sections(row.sections),
            auto_selectable=True,
            description=row.description,
        )

    async def candidates(self, user_id: uuid.UUID, language: str | None) -> list[ResolvedTemplate]:
        """What automatic selection may choose from: auto-selectable built-ins + user rows."""
        candidates = [
            await self.resolve(user_id, str(TemplateRef.builtin(template.key)), language)
            for template in BUILTIN_BY_KEY.values()
            if template.auto_selectable
        ]
        for row in await self.repo.list_for_user(user_id):
            candidates.append(
                ResolvedTemplate(
                    ref=TemplateRef.user(row.id),
                    name=row.name,
                    category=TemplateCategory(row.category),
                    sections=parse_sections(row.sections),
                    auto_selectable=True,
                    description=row.description,
                )
            )
        return candidates

    # ----------------------------------------------------------------- writes

    async def create(
        self, user_id: uuid.UUID, request: MeetingTemplateCreate, language: str | None
    ) -> MeetingTemplateResponse:
        """A new user row, from sections or by duplicating a reference; bounded by the cap."""
        maximum = settings.meetings_max_user_templates
        if await self.repo.count_for_user(user_id) >= maximum:
            raise_template_limit(maximum)
        payload = await self._creation_payload(user_id, request, language)
        row = await self.repo.create(payload)
        await self.db.commit()
        logger.info(
            "meeting_template_created",
            user_id=str(user_id),
            template_id=str(row.id),
            duplicate_of=request.duplicate_of,
        )
        return self._response(row)

    async def update(
        self, user_id: uuid.UUID, ref: str, request: MeetingTemplateUpdate
    ) -> MeetingTemplateResponse:
        """Replace a user row (PUT semantics); a built-in is read-only."""
        parsed = parse_ref(ref)
        if parsed.kind == "builtin":
            raise_template_readonly(ref)
        row = await self._owned_row(parsed, user_id)
        row = await self.repo.update(
            row,
            {
                "name": request.name,
                "description": request.description,
                "category": request.category.value,
                "sections": sections_to_json(request.sections),
            },
        )
        await self.db.commit()
        return self._response(row)

    async def delete(self, user_id: uuid.UUID, ref: str) -> bool:
        """Delete a user row; a preference pointing at it goes back to automatic.

        Returns:
            True when the default-format preference pointed at the row and was reset.
        """
        parsed = parse_ref(ref)
        if parsed.kind == "builtin":
            raise_template_readonly(ref)
        row = await self._owned_row(parsed, user_id)
        await self.repo.delete(row)
        reset = await self.preference_repo.clear_default_template_if(user_id, str(parsed))
        await self.db.commit()
        logger.info(
            "meeting_template_deleted",
            user_id=str(user_id),
            template_id=str(row.id),
            preference_reset=reset,
        )
        return reset

    # ---------------------------------------------------------------- helpers

    async def _owned_row(self, ref: TemplateRef, user_id: uuid.UUID) -> MeetingTemplate:
        assert ref.id is not None  # kind == "user" — the parser guarantees it
        row = await self.repo.get_for_user(ref.id, user_id)
        if row is None:
            raise_template_not_found(str(ref))
        return row

    async def _creation_payload(
        self, user_id: uuid.UUID, request: MeetingTemplateCreate, language: str | None
    ) -> dict[str, Any]:
        if request.duplicate_of is None:
            assert request.sections is not None and request.name is not None  # validator
            return {
                "user_id": user_id,
                "name": request.name,
                "description": request.description,
                "category": request.category.value,
                "builtin_key": None,
                "sections": sections_to_json(request.sections),
            }
        source = await self.resolve(user_id, request.duplicate_of, language)
        description = request.description
        if description is None and source.ref.kind == "builtin":
            description = builtin_summary(str(source.ref.key), language).description
        return {
            "user_id": user_id,
            "name": await self._unique_name(user_id, request.name or source.name),
            "description": description,
            "category": (
                request.category.value
                if request.category is not TemplateCategory.CUSTOM
                else source.category.value
            ),
            "builtin_key": source.ref.key if source.ref.kind == "builtin" else None,
            "sections": sections_to_json(source.sections),
        }

    async def _unique_name(self, user_id: uuid.UUID, name: str) -> str:
        """``name`` unless the user already owns it, then ``name (2)``, ``name (3)``…

        A duplicate is a starting point the user renames; two rows with one name
        would be told apart by nothing in the library or the format pickers.
        """
        taken = {row.name for row in await self.repo.list_for_user(user_id)}
        if name not in taken:
            return name
        counter = 2
        while f"{name} ({counter})" in taken:
            counter += 1
        return f"{name} ({counter})"

    @staticmethod
    def _response(row: MeetingTemplate) -> MeetingTemplateResponse:
        return MeetingTemplateResponse(
            ref=str(TemplateRef.user(row.id)),
            id=row.id,
            name=row.name,
            description=row.description,
            category=TemplateCategory(row.category),
            sections=parse_sections(row.sections),
            builtin=False,
            builtin_key=row.builtin_key,
            auto_selectable=True,
        )

    @staticmethod
    def _summary(row: MeetingTemplate) -> MeetingTemplateSummary:
        return MeetingTemplateSummary(
            ref=str(TemplateRef.user(row.id)),
            name=row.name,
            description=row.description,
            category=TemplateCategory(row.category),
            builtin=False,
            sections_count=len(row.sections),
            auto_selectable=True,
        )
