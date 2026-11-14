"""Document generation service: LLM structured content -> rendered attachment (ADR-226).

Pipeline: dedicated ``document_generation`` LLM slot (structured output typed
per format family) -> pure renderer -> attachments storage (TTL purge) ->
pending store for SSE card delivery. Failures propagate to the TOOL layer,
which translates them into honest UnifiedToolOutput failures — this module
never fakes a success and never queues a card for a document that does not
exist on disk.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import MappingProxyType

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import (
    DOCUMENT_GENERATION_COLUMN_CHOICES_MAX,
    DOCUMENT_GENERATION_FORMULA_MAX_CHARS,
    DOCUMENT_GENERATION_LLM_TYPE,
    DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN,
    DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX,
)
from src.core.document_preferences import DocumentIllustrations, DocumentPreferences
from src.core.i18n import get_language_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.attachments.file_contracts import UploadMetadata
from src.domains.attachments.generated_publication import publish_generated_files
from src.domains.attachments.models import (
    AttachmentContentType,
    AttachmentOrigin,
)
from src.domains.attachments.thread_id import conversation_uuid
from src.domains.attachments.urls import attachment_url
from src.domains.document_generation.context import build_render_context
from src.domains.document_generation.document_store import (
    PendingDocument,
    store_pending_document,
)
from src.domains.document_generation.illustrations import (
    PICTURE_REQUESTS,
    IllustrationReport,
    draw_illustrations,
)
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.pictures import illustration_budget
from src.domains.document_generation.prompts import (
    document_lines,
    document_prompt_template,
    format_label,
)
from src.domains.document_generation.renderers import (
    DOCUMENT_EXTENSIONS,
    DOCUMENT_MIME_TYPES,
    PICTURE_FORMATS,
    render_document,
)
from src.domains.document_generation.sanitize import sanitize_filename_stem
from src.domains.document_generation.schemas import (
    SCHEMA_BY_DOC_TYPE,
    DocumentContent,
    DocumentType,
    SectionedContent,
    SlideContent,
    TabularContent,
)
from src.domains.document_generation.typography import (
    CHART_MAX_SERIES,
    PPTX_AGENDA_MIN_PARTS,
    PPTX_FIGURES_PER_SLIDE,
)
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import (
    StructuredOutputTruncatedError,
    get_structured_output_with_retry,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class DocumentOutputTruncatedError(Exception):
    """The document LLM was cut at the slot's output budget (ADR-275).

    Nothing usable exists: a truncated payload is never rendered, and the tool
    turns this into an explicit failure naming the budget so the caller can ask
    for a shorter document instead of receiving a silently shortened one.
    """

    def __init__(self, budget_tokens: int) -> None:
        super().__init__(f"document output cut at the slot budget of {budget_tokens} tokens")
        self.budget_tokens = budget_tokens


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """A file on disk, its attachment row and its queued card."""

    attachment_id: str
    url: str
    filename: str
    size_bytes: int
    expires_at_iso: str | None


@dataclass
class GeneratedDocumentResult:
    """Outcome of a successful document generation."""

    attachment_id: str
    url: str
    filename: str
    doc_type: str
    size_bytes: int
    expires_at_iso: str | None
    truncated_source: bool
    #: What became of the pictures the writer asked for (none asked: all zero).
    illustrations: IllustrationReport = field(default_factory=IllustrationReport)


def _tabular_values() -> dict[str, str | int]:
    return {
        "formula_max_chars": DOCUMENT_GENERATION_FORMULA_MAX_CHARS,
        "column_choices_max": DOCUMENT_GENERATION_COLUMN_CHOICES_MAX,
        "workbook_figures_max": DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX,
    }


def _sectioned_values() -> dict[str, str | int]:
    return {
        "toc_min_headings": settings.document_generation_toc_min_headings,
        "formula_max_chars": DOCUMENT_GENERATION_FORMULA_MAX_CHARS,
    }


def _slides_values() -> dict[str, str | int]:
    return {
        "max_bullets_per_slide": settings.document_generation_slide_max_bullets,
        "max_bullet_chars": settings.document_generation_slide_max_bullet_chars,
        "formula_max_chars": DOCUMENT_GENERATION_FORMULA_MAX_CHARS,
        "figures_per_slide": PPTX_FIGURES_PER_SLIDE,
        "agenda_min_parts": PPTX_AGENDA_MIN_PARTS,
    }


#: The budgets each family's rules publish, read at call time (settings move).
_FAMILY_VALUES: dict[type, Callable[[], dict[str, str | int]]] = {
    TabularContent: _tabular_values,
    SectionedContent: _sectioned_values,
    SlideContent: _slides_values,
}

# Boot-time completeness (ADR-085): a family whose budgets nobody fills would
# reach the writer with an open placeholder.
assert set(_FAMILY_VALUES) == set(
    SCHEMA_BY_DOC_TYPE.values()
), "_FAMILY_VALUES must cover every content family"


#: Where each family's illustration rules are written: a deck places its
#: pictures on its cover and slides, a report on its cover and in its blocks.
_ILLUSTRATION_RULES: dict[type, str] = {
    SlideContent: "slides",
    SectionedContent: "sectioned",
}

# Boot-time completeness (ADR-085): a family that places pictures publishes its
# rules, and a format that places them belongs to such a family.
assert set(_ILLUSTRATION_RULES) == set(
    PICTURE_REQUESTS
), "_ILLUSTRATION_RULES must cover every family that places pictures"
assert all(
    SCHEMA_BY_DOC_TYPE[doc_type] in PICTURE_REQUESTS for doc_type in PICTURE_FORMATS
), "every format that places pictures belongs to a family that asks for them"


def _illustration_rules(family: type, preferences: DocumentPreferences) -> str:
    """The pictures the writer may ask for — the budget normalization enforces, published.

    A family that places no picture is told nothing; a document with no budget
    is told to leave the fields empty rather than spend its tokens on them.
    """
    rules = _ILLUSTRATION_RULES.get(family)
    if rules is None:
        return ""
    lines = document_lines()
    budget = illustration_budget(preferences)
    if budget == 0:
        return lines["illustrations.none"]
    asked_only = preferences.illustrations is DocumentIllustrations.ON_REQUEST
    mode = "on_request" if asked_only else "auto"
    return lines[f"illustrations.{mode}.{rules}"].format(illustrations_max=budget)


def _for_format(preferences: DocumentPreferences, doc_type: DocumentType) -> DocumentPreferences:
    """A format that places no picture is illustrated by nobody: its writer is told none."""
    if doc_type in PICTURE_FORMATS:
        return preferences
    return replace(preferences, illustrations=DocumentIllustrations.NEVER)


def prompt_values(
    *,
    doc_type: DocumentType,
    language: str,
    instructions: str,
    source_data: str,
    preferences: DocumentPreferences | None = None,
) -> dict[str, str | int]:
    """Every placeholder of the document prompt, budgets included.

    What the renderer ENFORCES, the prompt PUBLISHES (ADR-184): the slide
    density budgets, the long-document threshold and a length budget derived
    from the slot's effective ``max_tokens``. A number written in the prompt
    instead would be a number nobody could reconcile with the one applied.

    The length budget follows the FAMILY: a spreadsheet spends four times as
    many tokens per word as prose does (measured), so one factor for the three
    would hand a workbook a budget it cannot honour. The family's other budgets
    are the ones ITS rules publish, and only those: the template of a family
    asks for exactly these keys.

    Args:
        doc_type: Target format — it selects the family's rules and economics.
        language: Backend-canonical language code.
        instructions: What the document must contain.
        source_data: Raw material (already truncated by the caller).
        preferences: The person's document preferences: they decide the
            illustration rules in the request's tail. The defaults when absent.

    Returns:
        The ``str.format`` mapping the composed template expects.
    """
    family = SCHEMA_BY_DOC_TYPE[doc_type]
    slot = get_llm_config_for_agent(settings, DOCUMENT_GENERATION_LLM_TYPE)
    words_per_token = DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN[family.__name__]
    return {
        "doc_format": format_label(doc_type),
        "language": get_language_name(language),
        "instructions": instructions,
        "source_data": source_data,
        "length_budget_words": int(slot.max_tokens * words_per_token),
        "chart_max_series": CHART_MAX_SERIES,
        "illustrations": _illustration_rules(
            family, _for_format(preferences or DocumentPreferences(), doc_type)
        ),
        **_FAMILY_VALUES[family](),
    }


async def _call_document_llm(
    *,
    doc_type: DocumentType,
    instructions: str,
    source_data: str,
    language: str,
    config: RunnableConfig | None,
    user_id: uuid.UUID,
    preferences: DocumentPreferences | None = None,
) -> DocumentContent:
    """Produce structured document content with the dedicated LLM slot.

    Module-level seam (patched in unit tests). Mirrors
    ``telephony/return_synthesis.py``: get_llm + provider from the resolved
    config + retried structured output. Passing ``config`` through keeps the
    graph's token-tracking callbacks attached (node_name = the LLM type).

    Args:
        doc_type: Target format (selects the content schema BEFORE the call).
        instructions: What the document must contain.
        source_data: Raw material (already truncated by the caller).
        language: Backend-canonical language code for the document content.
        config: RunnableConfig carrying the run's callbacks, or ``None``.
        user_id: Account this call belongs to. Passed EXPLICITLY: the door
            resolves an owner from ``config.metadata``, which LangGraph never
            fills, so an inferred owner is no owner at all (ADR-272/ADR-275).
        preferences: The person's document preferences (the illustration rules).

    Returns:
        Validated content matching ``SCHEMA_BY_DOC_TYPE[doc_type]``.

    Raises:
        StructuredOutputTruncatedError: When the model was cut at its output
            budget — never retried, never rescued into a shorter document.
    """
    system = document_prompt_template(doc_type).format(
        **prompt_values(
            doc_type=doc_type,
            language=language,
            instructions=instructions,
            source_data=source_data,
            preferences=preferences,
        )
    )
    # The literal satisfies the LLMType Literal; the constant (same value,
    # asserted by a test) feeds the str-typed config-helper lookup.
    llm = get_llm("document_generation")
    provider = get_llm_config_for_agent(settings, DOCUMENT_GENERATION_LLM_TYPE).provider
    return await get_structured_output_with_retry(
        llm=llm,
        messages=[
            SystemMessage(content=system),
            HumanMessage(content="Produce the document now."),
        ],
        schema=SCHEMA_BY_DOC_TYPE[doc_type],
        provider=provider,
        node_name=DOCUMENT_GENERATION_LLM_TYPE,
        config=config,
        user_id=user_id,
    )


async def store_document(
    *,
    user_id: uuid.UUID,
    conversation_id: str | None,
    delivery_runtime_id: str | None = None,
    data: bytes,
    stem: str,
    extension: str,
    mime_type: str,
) -> StoredDocument:
    """Persist a generated file and queue its card. Nothing is queued unless it is on disk.

    Args:
        user_id: Owner of the resulting attachment.
        conversation_id: Stable business identity for the file's provenance.
        delivery_runtime_id: Root runtime receiving the card, absent outside a chat.
        data: The file's bytes.
        stem: Sanitized filename stem.
        extension: Filename extension, which is also what the card calls the format.
        mime_type: The attachment's media type.

    Returns:
        The stored file.
    """
    download_filename = f"{stem}.{extension}"
    async with get_db_context() as db:
        attachment = (
            await publish_generated_files(
                db,
                owner_id=user_id,
                files=[
                    (
                        UploadMetadata(
                            filename=download_filename,
                            mime_type=mime_type,
                            content_type=AttachmentContentType.DOCUMENT,
                            suffix=f".{extension}",
                            origin=AttachmentOrigin.GENERATED_DOCUMENT,
                            title=download_filename,
                            conversation_id=conversation_uuid(conversation_id),
                        ),
                        data,
                    )
                ],
            )
        )[0]
        expires_at_iso = attachment.expires_at.isoformat() if attachment.expires_at else None
        attachment_id = str(attachment.id)

    url = attachment_url(attachment_id)
    if delivery_runtime_id is not None:
        store_pending_document(
            delivery_runtime_id,
            PendingDocument(
                url=url,
                filename=download_filename,
                doc_type=extension,
                size_bytes=len(data),
                expires_at=expires_at_iso,
            ),
        )
    return StoredDocument(
        attachment_id=attachment_id,
        url=url,
        filename=download_filename,
        size_bytes=len(data),
        expires_at_iso=expires_at_iso,
    )


async def generate_document_for_user(
    *,
    user_id: uuid.UUID,
    conversation_id: str | None,
    delivery_runtime_id: str | None = None,
    doc_type: DocumentType,
    instructions: str,
    source_data: str,
    requested_filename: str,
    language: str,
    timezone: str,
    config: RunnableConfig | None,
    preferences: DocumentPreferences | None = None,
) -> GeneratedDocumentResult:
    """Generate, render and store one document; queue its card for delivery.

    Args:
        user_id: Owner of the resulting attachment.
        conversation_id: Stable business identity for the file's provenance.
        delivery_runtime_id: Root runtime receiving the card, absent outside a chat.
        doc_type: Target format.
        instructions: What the document must contain.
        source_data: Optional raw material (research results, prior steps).
        requested_filename: User-requested stem; wins over the LLM suggestion.
        language: Backend-canonical language code for the document content.
        timezone: The person's IANA timezone — the date on the title block is
            read in THEIR day, never the server's (ADR-274).
        config: RunnableConfig carrying the run's callbacks, or ``None``.
        preferences: What the person asked of their documents (illustrations,
            animations); the owner's defaults when absent.

    Returns:
        The stored document's metadata.

    Raises:
        Exception: LLM/renderer/storage failures propagate — the TOOL layer
            translates them into honest UnifiedToolOutput failures.
    """
    cap = settings.document_generation_max_source_chars
    truncated = len(source_data) > cap
    wanted = _for_format(preferences or DocumentPreferences(), doc_type)
    try:
        content = await _call_document_llm(
            doc_type=doc_type,
            instructions=instructions,
            source_data=source_data[:cap],
            language=language,
            config=config,
            user_id=user_id,
            preferences=wanted,
        )
    except StructuredOutputTruncatedError as exc:
        # The slot's output budget cut the document: nothing is rendered and
        # nothing is stored. The tool names the budget so the caller can ask
        # for a shorter document (ADR-275) — ADR-226 promised this honesty.
        budget = get_llm_config_for_agent(settings, DOCUMENT_GENERATION_LLM_TYPE).max_tokens
        logger.warning(
            "document_generation_output_truncated",
            user_id=str(user_id),
            doc_type=doc_type.value,
            budget_tokens=budget,
        )
        raise DocumentOutputTruncatedError(budget) from exc

    context = build_render_context(
        language=language,
        timezone=timezone,
        generated_at=datetime.now(UTC),
        preferences=wanted,
    )
    # The pictures are drawn for what the renderer will draw: the normalized
    # document, its pictures already within the person's budget.
    canonical = normalize_content(content, context)
    pictures, illustrations = await draw_illustrations(canonical, wanted, user_id=user_id)
    context = replace(context, pictures=MappingProxyType(pictures))
    data = await asyncio.to_thread(render_document, doc_type, canonical, context)

    stem = sanitize_filename_stem(requested_filename or content.filename_stem)
    stored = await store_document(
        user_id=user_id,
        conversation_id=conversation_id,
        delivery_runtime_id=delivery_runtime_id,
        data=data,
        stem=stem,
        extension=DOCUMENT_EXTENSIONS[doc_type],
        mime_type=DOCUMENT_MIME_TYPES[doc_type],
    )
    logger.info(
        "document_generation_attachment_saved",
        attachment_id=stored.attachment_id,
        user_id=str(user_id),
        doc_type=doc_type.value,
        file_size=stored.size_bytes,
        truncated_source=truncated,
        illustrations_requested=illustrations.requested,
        illustrations_drawn=illustrations.drawn,
    )
    return GeneratedDocumentResult(
        attachment_id=stored.attachment_id,
        url=stored.url,
        filename=stored.filename,
        doc_type=doc_type.value,
        size_bytes=stored.size_bytes,
        expires_at_iso=stored.expires_at_iso,
        truncated_source=truncated,
        illustrations=illustrations,
    )
