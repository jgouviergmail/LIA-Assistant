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

import base64
import time
from datetime import UTC, datetime
from typing import Annotated, Any

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

# Debounce tracking for progressive screenshots (per-user, monotonic clock)
_screenshot_debounce: dict[str, float] = {}


async def _emit_progressive_screenshot(
    runtime: ToolRuntime | None,
    session: Any,
    url: str = "",
    title: str = "",
) -> None:
    """Emit a progressive screenshot to the SSE side-channel queue.

    Non-blocking, fire-and-forget. Never raises — failures are silently logged.
    Respects debounce interval to prevent flooding during rapid action sequences.

    Args:
        runtime: Tool runtime for accessing configurable queue.
        session: Browser session with screenshot_with_thumbnail() method.
        url: Current page URL (for frontend display).
        title: Current page title (for frontend display).
    """
    if not settings.browser_progressive_screenshots:
        return

    try:
        configurable = (runtime.config.get("configurable") or {}) if runtime else {}
        queue = configurable.get("__side_channel_queue")
        if queue is None:
            return

        # Debounce: skip if too soon after last emission for this user
        user_id = configurable.get("user_id", "unknown")
        now = time.monotonic()
        last_time = _screenshot_debounce.get(user_id, 0.0)
        if now - last_time < settings.browser_screenshot_debounce_seconds:
            return
        _screenshot_debounce[user_id] = now

        # Capture full-res + thumbnail in single Playwright call
        full_res_bytes, thumbnail_bytes = await session.screenshot_with_thumbnail()
        if thumbnail_bytes is None:
            return

        # SSE overlay: send lightweight thumbnail
        image_b64 = base64.b64encode(thumbnail_bytes).decode("ascii")

        from src.domains.agents.api.schemas import ChatStreamChunk

        queue.put_nowait(
            ChatStreamChunk(
                type="browser_screenshot",
                content={
                    "image_base64": image_b64,
                    "url": url,
                    "title": title,
                },
                metadata=None,
            ),
        )

        # Card finale: store full-res for Attachment saving (pattern: image_store.py)
        # Use __parent_thread_id (forwarded from parent graph) — NOT thread_id
        # which is a synthetic ID in ReAct nested_config (e.g., "browser_task_agent_xxx")
        conversation_id = configurable.get("__parent_thread_id") or configurable.get(
            "thread_id", ""
        )
        if conversation_id and full_res_bytes:
            from src.domains.agents.tools.browser_screenshot_store import (
                store_last_browser_screenshot,
            )

            store_last_browser_screenshot(str(conversation_id), full_res_bytes)

        logger.debug(
            "browser_progressive_screenshot_emitted",
            user_id=user_id,
            url=url[:100],
            thumbnail_kb=len(thumbnail_bytes) // 1024,
            full_res_kb=len(full_res_bytes) // 1024 if full_res_bytes else 0,
        )
    except Exception as e:
        logger.debug("browser_progressive_screenshot_failed", error=str(e))


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

        # Delegate to ReactSubAgentRunner (ADR-062: factorized ReAct pattern)
        from src.domains.agents.tools.react_runner import ReactSubAgentRunner

        runner = ReactSubAgentRunner("browser_agent", "browser_agent_prompt")
        react_result = await runner.run(
            task=task,
            tools=[
                browser_navigate_tool,
                browser_snapshot_tool,
                browser_click_tool,
                browser_fill_tool,
                browser_press_key_tool,
            ],
            prompt_vars={"context_instructions": ""},
            parent_runtime=runtime,
            thread_prefix="browser",
            recursion_limit=15,
        )
        final_message = react_result.final_message

        # Get current page info for registry
        current_url = session.page.url if session.page and not session.page.is_closed() else ""
        current_title = ""
        if session.page and not session.page.is_closed():
            try:
                current_title = await session.page.title()
            except Exception:
                pass  # Best-effort: page may be navigating or closed

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
        # Dashboard 20 browser errors metric (non-critical)
        try:
            from src.infrastructure.observability.metrics_browser import (
                browser_errors_total,
            )

            browser_errors_total.labels(
                error_type="timeout" if "Timeout" in type(e).__name__ else type(e).__name__
            ).inc()
        except Exception:
            pass
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

        # Progressive screenshot for SSE side-channel (fire-and-forget)
        await _emit_progressive_screenshot(runtime, session, snapshot.url, snapshot.title)

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

        # Progressive screenshot for SSE side-channel (fire-and-forget)
        await _emit_progressive_screenshot(runtime, session, snapshot.url, snapshot.title)

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

        # Progressive screenshot for SSE side-channel (fire-and-forget)
        await _emit_progressive_screenshot(runtime, session, snapshot.url, snapshot.title)

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

        # Progressive screenshot for SSE side-channel (fire-and-forget)
        await _emit_progressive_screenshot(runtime, session, snapshot.url, snapshot.title)

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

        # Progressive screenshot for SSE side-channel (fire-and-forget)
        await _emit_progressive_screenshot(runtime, session, snapshot.url, snapshot.title)

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
