"""What a renderer needs beyond the content (ADR-274).

The content says what the document contains; the context says for whom and
where: the reader's language (the labels the renderer writes itself), their
timezone (the date on the title block — the server's date is not theirs), the
deployment's page size, and whether the long-document apparatus — table of
contents, heading numbering, page breaks before parts — may switch itself on.

A caller that already shapes its document pins ``structure="plain"``: meeting
minutes carry their own dated header, so they gain the running head, the
pagination and the table craft, and keep their shape (owner decision
2026-09-08).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n import normalize_language
from src.core.i18n_documents import document_label
from src.core.time_utils import format_date_only

PageSize = Literal["a4", "letter"]
Structure = Literal["auto", "plain"]


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Reader- and deployment-side facts a renderer reads."""

    language: str
    timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE
    page_size: PageSize = "a4"
    generated_at: datetime | None = None
    structure: Structure = "auto"

    def label(self, key: str, **values: object) -> str:
        """A renderer-generated label in the reader's language.

        Args:
            key: One of the ``documents.*`` keys.
            **values: Placeholder values.

        Returns:
            The rendered label.
        """
        return document_label(self.language, key, **values)

    @property
    def date_line(self) -> str:
        """The localized generation date, or an empty string when no date is wanted."""
        if self.generated_at is None:
            return ""
        return format_date_only(self.generated_at, self.timezone, self.language)


def build_render_context(
    *,
    language: str,
    timezone: str,
    generated_at: datetime,
    structure: Structure = "auto",
) -> RenderContext:
    """The context of a document generated for a person.

    Args:
        language: Any locale spelling; normalised to the backend canon.
        timezone: The person's IANA timezone; empty falls back to the central
            default, never to a hardcoded city.
        generated_at: Aware generation instant.
        structure: ``auto`` (long-document apparatus by threshold) or ``plain``.

    Returns:
        The context, page size taken from settings.
    """
    return RenderContext(
        language=normalize_language(language),
        timezone=timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        page_size=settings.document_generation_page_size,
        generated_at=generated_at,
        structure=structure,
    )


def default_render_context() -> RenderContext:
    """The context of a caller that states nothing: deployment language and page, no date."""
    return RenderContext(
        language=normalize_language(settings.default_language),
        page_size=settings.document_generation_page_size,
    )
