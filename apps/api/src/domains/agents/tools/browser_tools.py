"""
Browser Control Tools for LangGraph.

Interactive web browsing: navigate pages, click elements, fill forms,
press keys, take screenshots. Uses Playwright + accessibility tree (CDP).

Design Decision:
    Uses @tool + decorators instead of @connector_tool because:
    - Browser control is a standalone operation (no external OAuth/API key)
    - @connector_tool is designed for Google/external API connectors
    - Simpler pattern: @tool + @track_tool_metrics + @rate_limit
    - Same pattern as web_fetch_tools.py

Security (CRITICAL — multi-tenant):
    - SSRF prevention via BrowserSecurityPolicy (reuses url_validator.py)
    - Input sanitization (fill values, key whitelist)
    - Request interception (blocks dangerous schemes, private IPs)
    - Content wrapping (prompt injection prevention via wrap_external_content)
    - Session isolation per user (separate BrowserContext per user)
    - Global session coordination via Redis (prevents resource exhaustion)

Phase: evolution F7 — Browser Control (Playwright)
Reference: docs/technical/BROWSER_CONTROL.md
"""

from datetime import UTC, datetime
from typing import Annotated

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel, Field

from src.core.config import settings
from src.domains.agents.constants import AGENT_BROWSER, CONTEXT_DOMAIN_BROWSERS
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.agents.utils.rate_limiting import rate_limit
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA REGISTRY INTEGRATION
# ============================================================================


class BrowserPageItem(BaseModel):
    """Schema for browser page data in context registry."""

    url: str = Field(..., description="Page URL.")
    title: str = Field(..., description="Page title.")
    interactive_count: int = Field(default=0, description="Number of interactive elements.")
    content_summary: str = Field(default="", description="Brief content summary.")


ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_BROWSERS,
        agent_name=AGENT_BROWSER,
        item_schema=BrowserPageItem,
        primary_id_field="url",
        display_name_field="title",
        reference_fields=["title", "url"],
        icon="🌐",
    )
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def _get_session(runtime: ToolRuntime, user_id: str) -> tuple[object, object]:
    """Get browser pool and session for the current user.

    Extracts user language/timezone from runtime config for browser locale.

    Args:
        runtime: The tool runtime (for user preferences).
        user_id: The user ID from validated runtime config.

    Returns:
        Tuple of (pool, session) or raises ValueError.

    Raises:
        ValueError: If browser disabled, pool unhealthy, or session limit reached.
    """
    from src.infrastructure.browser.pool import get_browser_pool

    pool = await get_browser_pool()
    if pool is None:
        raise ValueError("Browser not enabled")

    # Extract user preferences from runtime config for browser locale/timezone
    configurable = (runtime.config.get("configurable") or {}) if runtime else {}
    user_language = configurable.get("user_language", "fr")
    user_timezone = configurable.get("user_timezone", "Europe/Paris")

    session = await pool.acquire_session(user_id, user_language, user_timezone)
    return pool, session


def _make_registry_item(url: str, title: str, interactive_count: int, content: str = "") -> dict:
    """Create a registry update dict for a browser page snapshot.

    Follows the web_fetch pattern: {item_id: RegistryItem}.
    The content (accessibility tree) is included in the payload so that
    generate_data_for_filtering() can serialize it for the response LLM.

    Args:
        url: Page URL.
        title: Page title.
        interactive_count: Number of interactive elements.
        content: The accessibility tree content (for LLM consumption via data_for_filtering).

    Returns:
        Registry updates dict for UnifiedToolOutput.
    """
    item_id = generate_registry_id(RegistryItemType.BROWSER_PAGE, url)
    registry_item = RegistryItem(
        id=item_id,
        type=RegistryItemType.BROWSER_PAGE,
        payload=BrowserPageItem(
            url=url,
            title=title,
            interactive_count=interactive_count,
            content_summary=content,
        ).model_dump(),
        meta=RegistryItemMeta(
            source="browser_agent",
            domain="browsers",
            timestamp=datetime.now(UTC),
            tool_name="browser_navigate",
        ),
    )
    return {item_id: registry_item}


# ============================================================================
# BROWSER TASK TOOL (primary — delegates to browser agent ReAct loop)
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="browser_task",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_read_calls,
    window_seconds=lambda: settings.browser_rate_limit_read_window,
    scope="user",
)
async def browser_task_tool(
    task: Annotated[str, "Natural language description of the browsing task to accomplish"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Execute a complete browsing task autonomously using the browser agent.

    This tool launches the browser agent's ReAct loop which can navigate pages,
    click elements, fill forms, search, and extract content — all autonomously
    based on the task description. Use this for any task requiring web interaction
    beyond simple page fetching.

    Examples:
        - "Go to nike.com, search for white Nike Air for men, and list prices"
        - "Go to leboncoin.fr, search for MacBook Pro M4, show first 5 results"
        - "Fill out the contact form on example.com with name John and email john@test.com"
    """
    config = validate_runtime_config(runtime, "browser_task")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        user_id = str(config.user_id)

        # Ensure browser session exists
        pool, session = await _get_session(runtime, user_id)

        # Build a lightweight ReAct agent for this task
        from langchain_core.messages import HumanMessage
        from langchain_core.runnables import RunnableConfig
        from langgraph.prebuilt import create_react_agent

        from src.core.time_utils import get_prompt_datetime_formatted
        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.infrastructure.llm.factory import get_llm

        llm = get_llm("browser_agent")
        prompt = load_prompt("browser_agent_prompt", version="v1").format(
            current_datetime=get_prompt_datetime_formatted(),
            context_instructions="",
        )

        # ReAct agent with browser tools (navigate, snapshot, click, fill, press_key)
        react_agent = create_react_agent(
            llm,
            tools=[
                browser_navigate_tool,
                browser_snapshot_tool,
                browser_click_tool,
                browser_fill_tool,
                browser_press_key_tool,
            ],
            prompt=prompt,
        )

        # Build clean config for nested agent (avoid LangGraph internal state conflicts)
        parent_config = runtime.config if runtime else {}
        parent_configurable = parent_config.get("configurable", {})
        nested_config = RunnableConfig(
            configurable={
                "user_id": parent_configurable.get("user_id"),
                "thread_id": f"browser_{user_id}",
                "__deps": parent_configurable.get("__deps"),
                "user_timezone": parent_configurable.get("user_timezone", "UTC"),
                "user_language": parent_configurable.get("user_language", "fr"),
            },
            callbacks=parent_config.get("callbacks"),
            recursion_limit=15,
        )

        result = await react_agent.ainvoke(
            {"messages": [HumanMessage(content=task)]},
            config=nested_config,
        )

        # Extract the final response from the agent
        messages = result.get("messages", [])
        final_message = ""
        if messages:
            last_msg = messages[-1]
            final_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        # Get current page info for registry
        current_url = session.page.url if session.page and not session.page.is_closed() else ""
        current_title = ""
        if session.page and not session.page.is_closed():
            try:
                current_title = await session.page.title()
            except Exception:
                pass

        # Update Redis with final page state
        if current_url:
            await pool.update_session_redis(user_id, current_url, current_title)

        # Wrap content for prompt injection prevention
        wrapped_content = wrap_external_content(
            final_message,
            current_url or "browser_agent",
            source_type="browser_page",
        )

        return UnifiedToolOutput.data_success(
            message=wrapped_content,
            structured_data={
                "url": current_url,
                "title": current_title,
                "task": task,
            },
            registry_updates=_make_registry_item(
                current_url or "about:blank",
                current_title or "Browser Task",
                0,
                final_message,
            ),
        )

    except ValueError as e:
        logger.warning("browser_task_error", task=task[:100], error=str(e))
        error_code = "RATE_LIMIT_EXCEEDED" if "Max" in str(e) else "CONFIGURATION_ERROR"
        return UnifiedToolOutput.failure(message=str(e), error_code=error_code)

    except Exception as e:
        if "Timeout" in type(e).__name__:
            logger.error("browser_task_timeout", task=task[:100])
            return UnifiedToolOutput.failure(
                message=f"Browser task timed out: {task[:100]}",
                error_code="TIMEOUT",
            )
        logger.error("browser_task_error", task=task[:100], error=str(e))
        return UnifiedToolOutput.failure(
            message=f"Browser task failed: {type(e).__name__}: {str(e)[:200]}",
            error_code="EXTERNAL_API_ERROR",
        )


# ============================================================================
# BROWSER TOOLS (used internally by browser agent ReAct loop)
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="browser_navigate",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_read_calls,
    window_seconds=lambda: settings.browser_rate_limit_read_window,
    scope="user",
)
async def browser_navigate_tool(
    url: Annotated[str, "The URL to navigate to"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Navigate to a web page and return its accessibility tree structure.

    Use this tool to open a URL in the browser. Returns the page's
    accessibility tree with [EN] element references for interaction.
    """
    config = validate_runtime_config(runtime, "browser_navigate")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        user_id = str(config.user_id)
        pool, session = await _get_session(runtime, user_id)

        snapshot = await session.navigate(url)

        # Update Redis with current URL for cross-worker recovery
        await pool.update_session_redis(user_id, snapshot.url, snapshot.title)

        # Wrap content for prompt injection prevention
        wrapped_tree = wrap_external_content(
            snapshot.content,
            snapshot.url,
            source_type="browser_page",
        )

        return UnifiedToolOutput.data_success(
            message=(
                f"**{snapshot.title}**\n\n"
                f"Source: {snapshot.url}\n"
                f"Interactive elements: {snapshot.interactive_count}\n\n"
                f"{wrapped_tree}"
            ),
            structured_data={
                "url": snapshot.url,
                "title": snapshot.title,
                "interactive_count": snapshot.interactive_count,
                "total_nodes": snapshot.total_count,
            },
            registry_updates=_make_registry_item(
                snapshot.url, snapshot.title, snapshot.interactive_count, wrapped_tree
            ),
        )

    except ValueError as e:
        logger.warning("browser_navigate_validation_error", url=url[:200], error=str(e))
        error_code = "INVALID_INPUT" if "URL blocked" in str(e) else "CONFIGURATION_ERROR"
        if "Max concurrent" in str(e) or "Max navigations" in str(e):
            error_code = "RATE_LIMIT_EXCEEDED"
        return UnifiedToolOutput.failure(message=str(e), error_code=error_code)

    except Exception as e:
        # Detect timeout (Playwright's TimeoutError does NOT inherit from
        # Python's builtin TimeoutError — it inherits from playwright.Error)
        if "Timeout" in type(e).__name__:
            logger.error("browser_navigate_timeout", url=url[:200])
            return UnifiedToolOutput.failure(
                message=f"Page load timeout after {settings.browser_page_load_timeout_seconds}s",
                error_code="TIMEOUT",
            )
        logger.error("browser_navigate_error", url=url[:200], error=str(e))
        return UnifiedToolOutput.failure(
            message=f"Navigation failed: {type(e).__name__}",
            error_code="EXTERNAL_API_ERROR",
        )


@tool
@track_tool_metrics(
    tool_name="browser_snapshot",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_read_calls,
    window_seconds=lambda: settings.browser_rate_limit_read_window,
    scope="user",
)
async def browser_snapshot_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Get current page accessibility tree (observe page state before acting).

    Use this tool to read the current page state. Always call this before
    clicking or filling elements to get fresh [EN] references.
    """
    config = validate_runtime_config(runtime, "browser_snapshot")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        _, session = await _get_session(runtime, str(config.user_id))
        snapshot = await session.get_snapshot()

        wrapped_tree = wrap_external_content(
            snapshot.content,
            snapshot.url,
            source_type="browser_page",
        )

        return UnifiedToolOutput.data_success(
            message=(
                f"**{snapshot.title}**\n\n"
                f"Source: {snapshot.url}\n"
                f"Interactive elements: {snapshot.interactive_count}\n\n"
                f"{wrapped_tree}"
            ),
            structured_data={
                "url": snapshot.url,
                "title": snapshot.title,
                "interactive_count": snapshot.interactive_count,
            },
        )

    except ValueError as e:
        logger.warning("browser_snapshot_error", error=str(e))
        return UnifiedToolOutput.failure(
            message=str(e),
            error_code="DEPENDENCY_ERROR" if "No page" in str(e) else "CONFIGURATION_ERROR",
        )

    except Exception as e:
        logger.error("browser_snapshot_error", error=str(e))
        return UnifiedToolOutput.failure(
            message=f"Snapshot failed: {type(e).__name__}",
            error_code="EXTERNAL_API_ERROR",
        )


@tool
@track_tool_metrics(
    tool_name="browser_click",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_write_calls,
    window_seconds=lambda: settings.browser_rate_limit_write_window,
    scope="user",
)
async def browser_click_tool(
    ref: Annotated[str, "Element reference from accessibility tree (e.g., 'E3')"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Click an interactive element by its reference from the accessibility tree.

    Use the [EN] references from browser_snapshot_tool output to identify
    which element to click.
    """
    config = validate_runtime_config(runtime, "browser_click")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        _, session = await _get_session(runtime, str(config.user_id))
        snapshot = await session.click(ref)

        wrapped_tree = wrap_external_content(
            snapshot.content,
            snapshot.url,
            source_type="browser_page",
        )

        return UnifiedToolOutput.data_success(
            message=(
                f"Clicked [{ref}] on **{snapshot.title}**\n\n"
                f"Source: {snapshot.url}\n"
                f"Interactive elements: {snapshot.interactive_count}\n\n"
                f"{wrapped_tree}"
            ),
            structured_data={
                "url": snapshot.url,
                "title": snapshot.title,
                "interactive_count": snapshot.interactive_count,
            },
        )

    except ValueError as e:
        error_code = "NOT_FOUND" if "not found" in str(e) else "CONFIGURATION_ERROR"
        logger.warning("browser_click_error", ref=ref, error=str(e))
        return UnifiedToolOutput.failure(message=str(e), error_code=error_code)

    except Exception as e:
        logger.error("browser_click_error", ref=ref, error=str(e))
        return UnifiedToolOutput.failure(
            message=f"Click failed: {type(e).__name__}",
            error_code="EXTERNAL_API_ERROR",
        )


@tool
@track_tool_metrics(
    tool_name="browser_fill",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_write_calls,
    window_seconds=lambda: settings.browser_rate_limit_write_window,
    scope="user",
)
async def browser_fill_tool(
    ref: Annotated[str, "Element reference for the form field (e.g., 'E2')"],
    value: Annotated[str, "The value to fill into the form field"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Fill a form field by its reference with the given value.

    Use the [EN] references from browser_snapshot_tool output to identify
    which field to fill. Values are automatically sanitized.
    """
    config = validate_runtime_config(runtime, "browser_fill")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        _, session = await _get_session(runtime, str(config.user_id))
        snapshot = await session.fill(ref, value)

        wrapped_tree = wrap_external_content(
            snapshot.content,
            snapshot.url,
            source_type="browser_page",
        )

        return UnifiedToolOutput.data_success(
            message=(
                f"Filled [{ref}] on **{snapshot.title}**\n\n"
                f"Source: {snapshot.url}\n"
                f"Interactive elements: {snapshot.interactive_count}\n\n"
                f"{wrapped_tree}"
            ),
            structured_data={
                "url": snapshot.url,
                "title": snapshot.title,
                "interactive_count": snapshot.interactive_count,
            },
        )

    except ValueError as e:
        error_code = "NOT_FOUND" if "not found" in str(e) else "INVALID_INPUT"
        logger.warning("browser_fill_error", ref=ref, error=str(e))
        return UnifiedToolOutput.failure(message=str(e), error_code=error_code)

    except Exception as e:
        logger.error("browser_fill_error", ref=ref, error=str(e))
        return UnifiedToolOutput.failure(
            message=f"Fill failed: {type(e).__name__}",
            error_code="EXTERNAL_API_ERROR",
        )


@tool
@track_tool_metrics(
    tool_name="browser_press_key",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_write_calls,
    window_seconds=lambda: settings.browser_rate_limit_write_window,
    scope="user",
)
async def browser_press_key_tool(
    key: Annotated[str, "Keyboard key to press (e.g., 'Enter', 'Tab', 'Escape')"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Press a keyboard key (Enter, Tab, Escape, Arrow keys, etc.).

    Only whitelisted keys are allowed for security.
    """
    config = validate_runtime_config(runtime, "browser_press_key")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        _, session = await _get_session(runtime, str(config.user_id))
        snapshot = await session.press_key(key)

        wrapped_tree = wrap_external_content(
            snapshot.content,
            snapshot.url,
            source_type="browser_page",
        )

        return UnifiedToolOutput.data_success(
            message=(
                f"Pressed {key} on **{snapshot.title}**\n\n"
                f"Source: {snapshot.url}\n"
                f"Interactive elements: {snapshot.interactive_count}\n\n"
                f"{wrapped_tree}"
            ),
            structured_data={
                "url": snapshot.url,
                "title": snapshot.title,
                "interactive_count": snapshot.interactive_count,
            },
        )

    except ValueError as e:
        error_code = "INVALID_INPUT" if "not allowed" in str(e) else "CONFIGURATION_ERROR"
        logger.warning("browser_press_key_error", key=key, error=str(e))
        return UnifiedToolOutput.failure(message=str(e), error_code=error_code)

    except Exception as e:
        logger.error("browser_press_key_error", key=key, error=str(e))
        return UnifiedToolOutput.failure(
            message=f"Key press failed: {type(e).__name__}",
            error_code="EXTERNAL_API_ERROR",
        )


@tool
@track_tool_metrics(
    tool_name="browser_screenshot",
    agent_name=AGENT_BROWSER,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.browser_rate_limit_expensive_calls,
    window_seconds=lambda: settings.browser_rate_limit_expensive_window,
    scope="user",
)
async def browser_screenshot_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Take a screenshot of the current page (requires browser_screenshot_enabled).

    Returns a JPEG screenshot of the visible viewport.
    Useful for visual verification when the accessibility tree is insufficient.
    """
    config = validate_runtime_config(runtime, "browser_screenshot")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        _, session = await _get_session(runtime, str(config.user_id))
        image_bytes = await session.screenshot()

        import base64

        image_b64 = base64.b64encode(image_bytes).decode("ascii")

        return UnifiedToolOutput.data_success(
            message="Screenshot captured.",
            structured_data={
                "image_base64": image_b64,
                "format": "jpeg",
                "width": 1280,
            },
        )

    except ValueError as e:
        error_code = "CONFIGURATION_ERROR" if "disabled" in str(e) else "DEPENDENCY_ERROR"
        logger.warning("browser_screenshot_error", error=str(e))
        return UnifiedToolOutput.failure(message=str(e), error_code=error_code)

    except Exception as e:
        logger.error("browser_screenshot_error", error=str(e))
        return UnifiedToolOutput.failure(
            message=f"Screenshot failed: {type(e).__name__}",
            error_code="EXTERNAL_API_ERROR",
        )
