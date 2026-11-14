"""LangChain tool for interactive pages (ADR-370).

Mirrors ``document_generation_tools.py``: the capability's effective state,
validated inputs, the ``interactive_page`` slot through its service, honest
failures. What differs is the output: the page travels in the registry as a
``PAGE_APP`` widget, rendered post-LLM, and the model reads a sentence about it,
never the page. Its code would be retyped into the answer and paid for twice.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Final

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.constants import INTERACTIVE_PAGE_TOOL_NAME
from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.constants import AGENT_INTERACTIVE_PAGE, CONTEXT_DOMAIN_PAGE_APPS
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.interactive_page.catalogue_manifests import (
    PAGE_FILENAME_DESCRIPTION,
    PAGE_INSTRUCTIONS_DESCRIPTION,
    PAGE_MODE_DESCRIPTION,
    PAGE_SOURCE_DATA_DESCRIPTION,
    PAGE_TOOL_DESCRIPTION,
    PageModeName,
)
from src.domains.agents.interactive_page.page_sources import resolve_page_base
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import registered_tool
from src.domains.agents.utils.rate_limiting import rate_limit
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.interactive_pages.document import PageRefusal, page_frame
from src.domains.interactive_pages.schemas import PageMode
from src.domains.interactive_pages.service import (
    PageOutputTruncatedError,
    PageRefusedError,
    PageRequest,
    PageSourceNotFoundError,
    ProducedPage,
    produce_page,
)
from src.infrastructure.llm.structured_output import StructuredOutputCallError
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = get_logger(__name__)

_TOOL_NAME: Final = INTERACTIVE_PAGE_TOOL_NAME
#: What the widget opens on. The frontend reads these two values.
_VIEW_PAGE: Final = "page"
_VIEW_CODE: Final = "code"
#: Modes the writer works in, and which therefore need to be told what to do.
_WRITING_MODES: Final = frozenset({PageMode.CREATE, PageMode.REVISE})

_SHOWN_MESSAGE: Final = (
    "The page is displayed live in the LIA chat, below your answer, with its "
    "downloadable file; its source is behind the Code button of the page. Do NOT "
    "repeat its code and do NOT add a link: say in one or two sentences what it is."
)
_SOURCE_MESSAGE: Final = (
    "The exact source of the page is displayed in the LIA chat, below your answer. "
    "Do NOT retype it: announce it in one sentence."
)
_TRUNCATED_NOTE: Final = (
    " Note: the provided source data exceeded the configured limit and was truncated."
)
_REFUSAL_MESSAGES: Final[dict[PageRefusal, str]] = {
    PageRefusal.EMPTY: "No page was produced: the result held no HTML element.",
    PageRefusal.TOO_LARGE: (
        "No page was produced: the result exceeds the size limit of a page. Ask for a "
        "simpler page."
    ),
    PageRefusal.UNCLOSED_SCRIPT: (
        "No page was produced: its script never closes, so a browser would run none of it."
    ),
    PageRefusal.EXTERNAL_SCRIPT: (
        "No page was produced: it depends on an external script, which the sandbox "
        "blocks. A page holds all its code."
    ),
    PageRefusal.EMBEDDED_DOCUMENT: (
        "No page was produced: it embeds another document (iframe, embed or object), "
        "which the sandbox never shows. A page shows only what it holds: ask for the "
        "same page without an embedded document."
    ),
}


def _parsed_mode(raw: str) -> PageMode | None:
    """Read a mode, repairing its spelling only (ADR-184).

    Args:
        raw: The mode as received.

    Returns:
        The mode, or ``None`` when it names none.
    """
    try:
        return PageMode(raw.strip().lower())
    except ValueError:
        return None


def _page_output(page: ProducedPage, mode: PageMode) -> UnifiedToolOutput:
    """The tool's success: the widget for the chat, a sentence for the model.

    ``structured_data`` is never empty: a reader falls back on the registry
    payload when it is, which would hand the model the whole page.

    Args:
        page: The checked page.
        mode: The mode it answers.

    Returns:
        The output carrying one ``PAGE_APP`` item.
    """
    frame = page_frame(page.source)
    registry_id = generate_registry_id(RegistryItemType.PAGE_APP, f"page_{time.time_ns()}")
    item = RegistryItem(
        id=registry_id,
        type=RegistryItemType.PAGE_APP,
        payload={
            FIELD_REGISTRY_ID: registry_id,
            "title": page.title,
            "html_content": frame.document,
            "source_offset": frame.source_offset,
            "initial_view": _VIEW_CODE if mode is PageMode.CODE else _VIEW_PAGE,
        },
        meta=RegistryItemMeta(
            source="interactive_page",
            domain=CONTEXT_DOMAIN_PAGE_APPS,
            tool_name=_TOOL_NAME,
        ),
    )
    message = _SOURCE_MESSAGE if mode is PageMode.CODE else _SHOWN_MESSAGE
    return UnifiedToolOutput.data_success(
        message=message + (_TRUNCATED_NOTE if page.truncated_source else ""),
        registry_updates={registry_id: item},
        structured_data={
            CONTEXT_DOMAIN_PAGE_APPS: [
                {
                    "title": page.title,
                    "filename": page.stored.filename if page.stored else None,
                    FIELD_REGISTRY_ID: registry_id,
                }
            ],
        },
        metadata={"mode": mode.value, "page_bytes": len(page.source.encode("utf-8"))},
    )


def _failure_of(error: Exception) -> UnifiedToolOutput:
    """The honest output of a call that produced no page.

    Args:
        error: What stopped it.

    Returns:
        A failure the model can act on, never the error's own text.
    """
    if isinstance(error, PageSourceNotFoundError):
        return UnifiedToolOutput.failure(
            message=(
                "No page or HTML code was found in this conversation. Create a new page, "
                "or ask the person for the code."
            ),
            error_code=ToolErrorCode.NOT_FOUND.value,
        )
    if isinstance(error, PageOutputTruncatedError):
        return UnifiedToolOutput.failure(
            message=(
                "The page exceeded the output budget of the interactive_page slot "
                f"({error.budget_tokens} tokens). No page was produced. Ask for a simpler page."
            ),
            error_code="TOOL_ERROR",
        )
    if isinstance(error, PageRefusedError):
        return UnifiedToolOutput.failure(
            message=_REFUSAL_MESSAGES[error.refusal], error_code="TOOL_ERROR"
        )
    if isinstance(error, StructuredOutputCallError):
        return UnifiedToolOutput.failure(
            message="The page writer did not answer. No page was produced.",
            error_code=ToolErrorCode.EXTERNAL_API_ERROR.value,
        )
    return UnifiedToolOutput.failure(
        message="The page could not be finished. No page was produced.",
        error_code="TOOL_ERROR",
    )


@registered_tool
@track_tool_metrics(
    tool_name=_TOOL_NAME,
    agent_name=AGENT_INTERACTIVE_PAGE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.document_generation_rate_limit_calls,
    window_seconds=lambda: settings.document_generation_rate_limit_window,
    scope="user",
)
async def generate_interactive_page(
    instructions: Annotated[str, PAGE_INSTRUCTIONS_DESCRIPTION] = "",
    mode: Annotated[PageModeName, PAGE_MODE_DESCRIPTION] = "create",
    source_data: Annotated[str, PAGE_SOURCE_DATA_DESCRIPTION] = "",
    filename: Annotated[str, PAGE_FILENAME_DESCRIPTION] = "",
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Create an interactive web page and show it live (see ``PAGE_TOOL_DESCRIPTION``)."""
    context = tool_runtime_context(runtime)
    if context is None:
        logger.warning("interactive_page_no_context", has_runtime=runtime is not None)
        return UnifiedToolOutput.failure(
            message="Could not identify user. Please try again.", error_code="AUTH_ERROR"
        )
    if not await is_capability_enabled(PlatformCapability.INTERACTIVE_PAGES):
        return UnifiedToolOutput.failure(
            message="Interactive pages are currently disabled by the administrator.",
            error_code=ToolErrorCode.CONFIGURATION_ERROR.value,
        )
    parsed_mode = _parsed_mode(mode)
    if parsed_mode is None:
        accepted = ", ".join(page_mode.value for page_mode in PageMode)
        return UnifiedToolOutput.failure(
            message=f"Invalid mode '{mode}'. Must be one of: {accepted}",
            error_code=ToolErrorCode.INVALID_INPUT.value,
        )
    if parsed_mode in _WRITING_MODES and not instructions.strip():
        return UnifiedToolOutput.failure(
            message=f"The {parsed_mode.value} mode needs instructions.",
            error_code=ToolErrorCode.MISSING_REQUIRED_PARAM.value,
        )

    try:
        page = await produce_page(
            PageRequest(
                mode=parsed_mode,
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                delivery_runtime_id=context.delivery_runtime_id,
                instructions=instructions,
                source_data=source_data,
                base=await resolve_page_base(parsed_mode, source_data, context.conversation_id),
                requested_filename=filename,
                language=context.language,
                config=runtime.config if runtime else None,
            )
        )
    except Exception as exc:
        # Counts and types only: the page and its instructions are the person's.
        logger.warning(
            "interactive_page_failed", mode=parsed_mode.value, error_type=type(exc).__name__
        )
        return _failure_of(exc)

    logger.info(
        "interactive_page_tool_success",
        mode=parsed_mode.value,
        page_bytes=len(page.source.encode("utf-8")),
        filed=page.stored is not None,
    )
    return _page_output(page, parsed_mode)


# The loop binds this schema, never the manifest: one wording for both.
generate_interactive_page.description = PAGE_TOOL_DESCRIPTION
