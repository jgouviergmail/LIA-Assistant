"""One page, written, checked and kept (ADR-370).

Pipeline: the writer of the ``interactive_page`` slot (structured output) when
a mode needs one, the checks of ``document.py``, then the attachments storage and
the document card, through the door generated documents use. Failures propagate
to the TOOL layer, which turns them into honest outputs: nothing here fakes a
success, and no card is queued for a page that does not exist on disk.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Final

from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import (
    INTERACTIVE_PAGE_BYTES_PER_OUTPUT_TOKEN,
    INTERACTIVE_PAGE_LLM_TYPE,
)
from src.core.i18n import get_language_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.prompt_layout import single_call_messages
from src.domains.document_generation.sanitize import sanitize_filename_stem
from src.domains.document_generation.service import StoredDocument, store_document
from src.domains.interactive_pages.document import (
    PageRefusal,
    clean_source,
    page_file,
    refusal_of,
)
from src.domains.interactive_pages.prompts import load_page_prompt
from src.domains.interactive_pages.schemas import PageContent, PageMode, PageSource
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import (
    StructuredOutputTruncatedError,
    get_structured_output_with_retry,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: What the page is called on disk, and how the chat card names its format.
PAGE_FILE_EXTENSION: Final = "html"
PAGE_MIME_TYPE: Final = "text/html"
#: The stem of a page that names itself nothing a filesystem accepts.
_FALLBACK_STEM: Final = "page"
#: A mode that shows what exists has no writer to pay.
_VERBATIM_MODES: Final = frozenset({PageMode.SHOW, PageMode.CODE})


class PageSourceNotFoundError(Exception):
    """A mode that works from an existing page found none in this conversation."""


class PageOutputTruncatedError(Exception):
    """The writer was cut at the slot's output budget: a cut page never runs (ADR-275)."""

    def __init__(self, budget_tokens: int) -> None:
        super().__init__(f"page output cut at the slot budget of {budget_tokens} tokens")
        self.budget_tokens = budget_tokens


class PageRefusedError(Exception):
    """A page that would load and do nothing is said, never shown."""

    def __init__(self, refusal: PageRefusal) -> None:
        super().__init__(f"page refused: {refusal.value}")
        self.refusal = refusal


@dataclass(frozen=True, slots=True)
class PageRequest:
    """One call, as the tool resolved it.

    Attributes:
        mode: What is asked.
        user_id: The account the file and the spend belong to.
        conversation_id: The conversation the card is delivered to.
        instructions: What the page must do, or the change to make.
        source_data: Facts the page must use.
        base: The existing page the mode works from, ``None`` for a new page.
        requested_filename: Stem the person asked for; wins over the writer's.
        language: Backend-canonical language of the page's text.
        config: RunnableConfig carrying the run's callbacks, or ``None``.
    """

    mode: PageMode
    user_id: uuid.UUID
    conversation_id: str
    instructions: str
    source_data: str
    base: PageSource | None
    requested_filename: str
    language: str
    config: RunnableConfig | None


@dataclass(frozen=True, slots=True)
class ProducedPage:
    """A page that passed every check.

    Attributes:
        title: Its title, empty when it has none.
        source: The page as written.
        stored: Its file; ``None`` for a mode that files nothing.
        truncated_source: The writer read less of ``source_data`` than it was
            given: a cut is stated, never silent.
    """

    title: str
    source: str
    stored: StoredDocument | None
    truncated_source: bool = False


def _slot_budget_bytes() -> int:
    """What the writer's slot can produce, in bytes of page.

    Returns:
        The slot's ``max_tokens`` read through the measured ratio.
    """
    slot = get_llm_config_for_agent(settings, INTERACTIVE_PAGE_LLM_TYPE)
    return int(slot.max_tokens * INTERACTIVE_PAGE_BYTES_PER_OUTPUT_TOKEN)


def prompt_values(request: PageRequest) -> dict[str, str | int]:
    """Every placeholder of the page prompt, its ceiling included.

    What the checks ENFORCE, the prompt PUBLISHES (ADR-184): the writer reads the
    tighter of the setting and of what its own output budget can hold.

    Args:
        request: The call.

    Returns:
        The ``str.format`` mapping the prompt file expects.
    """
    ceiling = min(settings.interactive_page_max_bytes, _slot_budget_bytes())
    return {
        "language": get_language_name(request.language),
        "instructions": request.instructions,
        "source_data": request.source_data[: settings.document_generation_max_source_chars],
        "current_page": request.base.html if request.base else "",
        "max_page_kb": ceiling // 1024,
    }


async def _call_page_llm(request: PageRequest) -> PageContent:
    """Have the page written. Module-level seam, patched in unit tests.

    Args:
        request: The call. ``user_id`` is passed EXPLICITLY: the door resolves an
            owner from ``config.metadata``, which LangGraph never fills.

    Returns:
        The writer's page.

    Raises:
        StructuredOutputTruncatedError: The writer was cut at its budget.
    """
    rendered = load_page_prompt().format(**prompt_values(request))
    # The literal satisfies the LLMType Literal; the constant feeds the
    # str-typed config-helper lookup (same value, as for documents).
    llm = get_llm("interactive_page")
    provider = get_llm_config_for_agent(settings, INTERACTIVE_PAGE_LLM_TYPE).provider
    return await get_structured_output_with_retry(
        llm=llm,
        messages=single_call_messages(rendered),
        schema=PageContent,
        provider=provider,
        node_name=INTERACTIVE_PAGE_LLM_TYPE,
        config=request.config,
        user_id=request.user_id,
    )


async def _written_page(request: PageRequest) -> PageContent:
    """The page a mode works with: what exists, or what the writer returns.

    Args:
        request: The call.

    Returns:
        The page, its name included.

    Raises:
        PageSourceNotFoundError: The mode works from a page, and there is none.
        PageOutputTruncatedError: The writer was cut at its budget.
    """
    base = request.base
    if base is None and request.mode is not PageMode.CREATE:
        raise PageSourceNotFoundError
    if base is not None and request.mode in _VERBATIM_MODES:
        return PageContent(filename_stem=base.title, title=base.title, html=base.html)
    try:
        return await _call_page_llm(request)
    except StructuredOutputTruncatedError as exc:
        budget = get_llm_config_for_agent(settings, INTERACTIVE_PAGE_LLM_TYPE).max_tokens
        logger.warning(
            "interactive_page_output_truncated",
            user_id=str(request.user_id),
            budget_tokens=budget,
        )
        raise PageOutputTruncatedError(budget) from exc


async def produce_page(request: PageRequest) -> ProducedPage:
    """Write or fetch one page, check it, and file it when the mode keeps one.

    Args:
        request: The call.

    Returns:
        The page and its file.

    Raises:
        PageSourceNotFoundError: The mode works from a page, and there is none.
        PageOutputTruncatedError: The writer was cut at its budget.
        PageRefusedError: The page could not work.
        Exception: Model and storage failures propagate: the TOOL layer turns
            them into honest outputs.
    """
    written = await _written_page(request)
    source = clean_source(written.html)
    refusal = await asyncio.to_thread(
        refusal_of, source, max_bytes=settings.interactive_page_max_bytes
    )
    if refusal is not None:
        logger.warning(
            "interactive_page_refused",
            user_id=str(request.user_id),
            refusal=refusal.value,
            mode=request.mode.value,
        )
        raise PageRefusedError(refusal)
    if request.mode is PageMode.CODE:
        return ProducedPage(title=written.title, source=source, stored=None)
    truncated = (
        request.mode not in _VERBATIM_MODES
        and len(request.source_data) > settings.document_generation_max_source_chars
    )

    stem = sanitize_filename_stem(
        request.requested_filename or written.filename_stem, fallback=_FALLBACK_STEM
    )
    stored = await store_document(
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        data=page_file(source),
        stem=stem,
        extension=PAGE_FILE_EXTENSION,
        mime_type=PAGE_MIME_TYPE,
    )
    return ProducedPage(
        title=written.title, source=source, stored=stored, truncated_source=truncated
    )
