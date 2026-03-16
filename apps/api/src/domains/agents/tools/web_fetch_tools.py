"""
Web Fetch Tool for LangGraph.

Fetches and extracts content from web pages, returning clean Markdown.
No OAuth or API key required — fetches public URLs directly with httpx.

Design Decision:
    Uses @tool + decorators instead of @connector_tool because:
    - Web Fetch is a standalone operation (no external OAuth/API key)
    - @connector_tool is designed for Google/external API connectors
    - Simpler pattern: @tool + @track_tool_metrics + @rate_limit

Security (CRITICAL — multi-tenant):
    - SSRF prevention via url_validator.py (private IP/hostname blacklists)
    - DNS resolution before fetch (prevents DNS rebinding)
    - Post-redirect SSRF check (re-validates response.url)
    - Content size limit (500KB HTTP response, streaming check)
    - Request timeout (15s)
    - Rate limiting (10 fetches/min per user)
    - HTTPS enforcement (HTTP → HTTPS upgrade)
    - Markdown sanitization (strip javascript:/data: URIs)

Architecture:
    fetch_web_page_tool (@tool)
        ├── validate_url()              → SSRF prevention (async DNS)
        ├── httpx.AsyncClient.stream()  → HTTP fetch (streaming for size control)
        ├── validate_resolved_url()     → Post-redirect SSRF check
        ├── readability.Document()      → Content extraction (article mode)
        ├── markdownify.markdownify()   → HTML → Markdown
        ├── _sanitize_markdown()        → Strip dangerous URIs
        ├── wrap_external_content()     → Prompt injection prevention (F2)
        └── UnifiedToolOutput           → Structured response
"""

import re
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse

import httpx
import markdownify
import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel
from readability import Document

from src.core.config import settings
from src.core.constants import (
    WEB_FETCH_ARTICLE_RATIO_THRESHOLD,
    WEB_FETCH_DEFAULT_EXTRACT_MODE,
    WEB_FETCH_MAX_CONTENT_LENGTH,
    WEB_FETCH_MAX_OUTPUT_LENGTH,
    WEB_FETCH_MAX_REDIRECTS,
    WEB_FETCH_MIN_ARTICLE_LENGTH,
    WEB_FETCH_MIN_ARTICLE_WORDS,
    WEB_FETCH_MIN_OUTPUT_LENGTH,
    WEB_FETCH_RATE_LIMIT_CALLS,
    WEB_FETCH_RATE_LIMIT_WINDOW,
    WEB_FETCH_TIMEOUT_SECONDS,
    WEB_FETCH_TRUNCATION_MARKER,
    WEB_FETCH_USER_AGENT,
)
from src.domains.agents.constants import (
    AGENT_WEB_FETCH,
    CONTEXT_DOMAIN_WEB_FETCH,
)
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
from src.domains.agents.web_fetch.url_validator import validate_resolved_url, validate_url
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.cache.web_search_cache import WebSearchCache
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)

# ============================================================================
# DATA REGISTRY INTEGRATION
# ============================================================================


class WebFetchItem(BaseModel):
    """Schema for web fetch data in context registry."""

    title: str
    url: str
    content: str = ""
    word_count: int = 0
    language: str | None = None


ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_WEB_FETCH,
        agent_name=AGENT_WEB_FETCH,
        item_schema=WebFetchItem,
        primary_id_field="url",
        display_name_field="title",
        reference_fields=["title", "url"],
        icon="🌐",
    )
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Regex to strip dangerous URIs from markdown links/images
_DANGEROUS_URI_PATTERN = re.compile(
    r"\[([^\]]*)\]\((javascript:|data:|vbscript:|file:|about:)[^)]*\)", re.IGNORECASE
)
# Regex to extract lang attribute from <html> tag
_HTML_LANG_PATTERN = re.compile(r"<html[^>]+lang=[\"']([^\"']+)[\"']", re.IGNORECASE)
# Regex to strip <script>, <style>, <noscript>, <iframe> blocks and their content.
# markdownify's `strip` param removes tags but leaves their TEXT content (e.g. JS code).
# This regex removes both the tags AND the content between them.
_REMOVABLE_BLOCKS_PATTERN = re.compile(
    r"<(script|style|noscript|iframe|svg)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
# Regex to also catch self-closing or unclosed script/style tags
_REMOVABLE_TAGS_PATTERN = re.compile(
    r"<(script|style|noscript|iframe|svg)[^>]*/?>",
    re.IGNORECASE,
)


def _extract_language(html: str) -> str | None:
    """Extract language from HTML lang attribute (lightweight, no external lib)."""
    match = _HTML_LANG_PATTERN.search(html[:2000])  # Only check head of document
    if match:
        lang = match.group(1).strip()
        return lang.split("-")[0].lower() if lang else None
    return None


def _clean_html(html: str) -> str:
    """Remove non-content HTML blocks (script, style, noscript, iframe, svg).

    markdownify's ``strip`` parameter removes tags but preserves their TEXT content,
    which means inline JavaScript (``<script>try{var t=...}</script>``) leaks into
    the Markdown output. This function removes both the tags AND their inner content
    before markdownify runs.

    Also extracts only the ``<body>`` content when present to avoid ``<head>`` metadata
    leaking into the output.
    """
    # 1. Extract <body> content if present (avoids <head> metadata, <link>, <meta>)
    body_match = re.search(r"<body[^>]*>(.*)</body>", html, re.IGNORECASE | re.DOTALL)
    cleaned = body_match.group(1) if body_match else html

    # 2. Remove <script>...</script>, <style>...</style>, etc. blocks
    cleaned = _REMOVABLE_BLOCKS_PATTERN.sub("", cleaned)

    # 3. Remove any remaining self-closing or orphaned opening tags
    cleaned = _REMOVABLE_TAGS_PATTERN.sub("", cleaned)

    return cleaned


def _estimate_text_word_count(html_content: str) -> int:
    """Estimate word count from HTML by stripping tags."""
    text = re.sub(r"<[^>]+>", " ", html_content)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text.split()) if text else 0


def _html_to_markdown(html: str, extract_mode: str) -> tuple[str, str]:
    """
    Convert HTML to clean Markdown.

    Args:
        html: Raw HTML content
        extract_mode: "article" uses readability, "full" converts entire page

    Returns:
        Tuple of (title, markdown_content)
    """
    if extract_mode == "article":
        doc = Document(html)
        title = doc.title() or ""
        article_html = doc.summary() or ""

        # Smart fallback: detect when readability captured too little content.
        # This happens on homepages, listing pages, and other non-article pages
        # where readability extracts only the featured item.
        should_fallback = False
        fallback_reason = ""

        if len(article_html) < WEB_FETCH_MIN_ARTICLE_LENGTH:
            should_fallback = True
            fallback_reason = "html_too_short"
        else:
            article_words = _estimate_text_word_count(article_html)
            if article_words < WEB_FETCH_MIN_ARTICLE_WORDS:
                full_words = _estimate_text_word_count(html)
                ratio = article_words / full_words if full_words > 0 else 1.0
                if ratio < WEB_FETCH_ARTICLE_RATIO_THRESHOLD:
                    should_fallback = True
                    fallback_reason = "low_extraction_ratio"
                    logger.info(
                        "readability_ratio_check",
                        article_words=article_words,
                        full_words=full_words,
                        ratio=round(ratio, 3),
                    )

        if should_fallback:
            logger.warning(
                "readability_fallback_to_full",
                article_length=len(article_html),
                reason=fallback_reason,
            )
            return _html_to_markdown(html, "full")
    else:
        # Full mode: extract title from <title> tag, use entire body
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""
        article_html = html

    # Pre-clean HTML: remove <script>/<style> blocks WITH their content.
    # markdownify's `strip` only removes tags but preserves inner text,
    # which leaks JS code into the output on real-world pages.
    article_html = _clean_html(article_html)

    md_content = markdownify.markdownify(
        article_html,
        heading_style="ATX",
        strip=["img"],
    )

    # Clean up excessive whitespace (3+ newlines → 2)
    md_content = re.sub(r"\n{3,}", "\n\n", md_content).strip()

    return title, md_content


def _sanitize_markdown(content: str) -> str:
    """Strip dangerous URIs (javascript:, data:) from markdown links."""
    return _DANGEROUS_URI_PATTERN.sub(r"\1", content)


def _truncate_content(content: str, max_length: int) -> tuple[str, bool]:
    """Truncate content to max_length with marker."""
    if len(content) <= max_length:
        return content, False
    truncated = content[:max_length] + WEB_FETCH_TRUNCATION_MARKER
    return truncated, True


# ============================================================================
# TOOL IMPLEMENTATION
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="web_fetch",
    agent_name=AGENT_WEB_FETCH,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
    log_execution=True,
)
@rate_limit(
    max_calls=WEB_FETCH_RATE_LIMIT_CALLS,
    window_seconds=WEB_FETCH_RATE_LIMIT_WINDOW,
    scope="user",
)
async def fetch_web_page_tool(
    url: Annotated[str, "The URL of the web page to fetch and read"],
    extract_mode: Annotated[
        str,
        "Content extraction mode: 'article' (main content only, recommended) "
        "or 'full' (entire page)",
    ] = "article",
    max_length: Annotated[
        int,
        "Maximum content length in characters (default 30000)",
    ] = WEB_FETCH_MAX_OUTPUT_LENGTH,
    force_refresh: Annotated[
        bool,
        "Force bypass cache and fetch fresh content (use when user asks to refresh/reload)",
    ] = False,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Fetch a web page and extract its content as clean Markdown.

    Use this tool when you need to read the full content of a specific web page.
    Unlike search tools (Brave, Perplexity) that return snippets, this tool
    fetches and reads the complete page content.

    WHEN TO USE:
    - User provides a URL and wants to know what's on the page
    - You found a URL via search and need the full article content
    - User asks to "read", "fetch", "open", or "get content from" a URL

    WHEN NOT TO USE:
    - Searching for information (use web_search or brave_search instead)
    - URL is not a public web page (e.g., file://, ftp://)

    Args:
        url: Complete URL to fetch (e.g., "https://example.com/article")
        extract_mode: "article" extracts main content (recommended), "full" gets everything
        max_length: Maximum output length in characters (default: 30000)
        runtime: Tool runtime (injected)

    Returns:
        Page content as clean Markdown with title and metadata
    """
    # 1. Validate runtime config
    config = validate_runtime_config(runtime, "fetch_web_page_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id_str = str(config.user_id)

    # 2. Cache check (before any external HTTP call)
    if not force_refresh:
        try:
            redis_client = await get_redis_cache()
            cache = WebSearchCache(redis_client)
            cache_result = await cache.get_fetch(config.user_id, url)
            if cache_result.from_cache and cache_result.data:
                logger.info(
                    "web_fetch_from_cache",
                    url=url[:50],
                    user_id=user_id_str[:8],
                    cache_age_seconds=cache_result.cache_age_seconds,
                )
                # Note: registry_updates not restored from cache (RegistryItem
                # objects cannot be reconstructed from plain dicts without loss).
                # The text message contains all information the agent needs.
                return UnifiedToolOutput.data_success(
                    message=cache_result.data.get("message", ""),
                    structured_data={
                        **cache_result.data.get("structured_data", {}),
                        "from_cache": True,
                        "cache_age_seconds": cache_result.cache_age_seconds,
                    },
                )
        except Exception as e:
            logger.warning("web_fetch_cache_check_failed", error=str(e))

    # 3. Validate extract_mode
    if extract_mode not in ("article", "full"):
        extract_mode = WEB_FETCH_DEFAULT_EXTRACT_MODE

    # 4. Clamp max_length
    effective_max_length = min(
        max(WEB_FETCH_MIN_OUTPUT_LENGTH, max_length), WEB_FETCH_MAX_OUTPUT_LENGTH
    )

    # 5. Validate URL (SSRF prevention with async DNS)
    validation = await validate_url(url)
    if not validation.valid:
        return UnifiedToolOutput.failure(
            message=f"URL rejected: {validation.error}",
            error_code="INVALID_INPUT",
        )
    safe_url = validation.url

    # 6. Fetch page with streaming (check headers before downloading body)
    try:
        async with httpx.AsyncClient(
            timeout=WEB_FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            max_redirects=WEB_FETCH_MAX_REDIRECTS,
            headers={"User-Agent": WEB_FETCH_USER_AGENT},
        ) as client:
            async with client.stream("GET", safe_url) as response:
                response.raise_for_status()

                # 6a. Post-redirect SSRF check
                final_url = str(response.url)
                if final_url != safe_url:
                    is_safe = await validate_resolved_url(final_url)
                    if not is_safe:
                        logger.warning(
                            "ssrf_redirect_blocked",
                            original_url=safe_url,
                            redirect_url=final_url,
                            user_id=user_id_str[:8],
                        )
                        return UnifiedToolOutput.failure(
                            message="URL redirected to a blocked destination",
                            error_code="INVALID_INPUT",
                        )

                # 6b. Check Content-Type before downloading body (case-insensitive per HTTP spec)
                content_type = response.headers.get("content-type", "").lower()
                if not any(ct in content_type for ct in ("text/html", "application/xhtml")):
                    return UnifiedToolOutput.failure(
                        message=f"Not an HTML page (content-type: {content_type})",
                        error_code="INVALID_RESPONSE_FORMAT",
                    )

                # 6c. Check Content-Length if available
                content_length_header = response.headers.get("content-length")
                if content_length_header:
                    try:
                        declared_length = int(content_length_header)
                        if declared_length > WEB_FETCH_MAX_CONTENT_LENGTH:
                            return UnifiedToolOutput.failure(
                                message=(
                                    f"Page too large ({declared_length:,} bytes, "
                                    f"max {WEB_FETCH_MAX_CONTENT_LENGTH:,})"
                                ),
                                error_code="CONSTRAINT_VIOLATION",
                            )
                    except ValueError:
                        pass  # Invalid Content-Length header, proceed with download

                # 6d. Read body (streaming already validated headers)
                await response.aread()
                body_bytes = response.content

                # Check actual body size
                if len(body_bytes) > WEB_FETCH_MAX_CONTENT_LENGTH:
                    return UnifiedToolOutput.failure(
                        message=(
                            f"Page too large ({len(body_bytes):,} bytes, "
                            f"max {WEB_FETCH_MAX_CONTENT_LENGTH:,})"
                        ),
                        error_code="CONSTRAINT_VIOLATION",
                    )

                html = response.text

    except httpx.TimeoutException:
        return UnifiedToolOutput.failure(
            message=f"Request timed out after {WEB_FETCH_TIMEOUT_SECONDS}s",
            error_code="TIMEOUT",
        )
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        error_code = "NOT_FOUND" if status_code == 404 else "EXTERNAL_API_ERROR"
        return UnifiedToolOutput.failure(
            message=f"HTTP error {status_code} fetching {safe_url}",
            error_code=error_code,
        )
    except httpx.RequestError as e:
        return UnifiedToolOutput.failure(
            message=f"Network error: {type(e).__name__}",
            error_code="EXTERNAL_API_ERROR",
        )

    # 7. Extract content (with article → full fallback)
    language = _extract_language(html)
    try:
        title, markdown_content = _html_to_markdown(html, extract_mode)
    except Exception as e:
        logger.warning("html_extraction_error", error=str(e), url=safe_url)
        return UnifiedToolOutput.failure(
            message="Failed to extract content from page",
            error_code="INVALID_RESPONSE_FORMAT",
        )

    # 8. Sanitize markdown (strip javascript:/data: URIs)
    markdown_content = _sanitize_markdown(markdown_content)

    # 9. Truncate if needed
    markdown_content, was_truncated = _truncate_content(markdown_content, effective_max_length)

    # 10. Calculate word count (before wrapping to avoid inflated count)
    word_count = len(markdown_content.split())

    # 11. Wrap external content (prompt injection prevention)
    if getattr(settings, "external_content_wrapping_enabled", True):
        markdown_content = wrap_external_content(
            content=markdown_content,
            source_url=safe_url,
            source_type="web_page",
        )

    # 12. Build registry item
    source_domain = urlparse(safe_url).netloc
    extracted_at = datetime.now(UTC).isoformat()

    item_id = generate_registry_id(RegistryItemType.WEB_PAGE, safe_url)
    registry_item = RegistryItem(
        id=item_id,
        type=RegistryItemType.WEB_PAGE,
        payload={
            "title": title,
            "url": safe_url,
            "content": markdown_content,
            "word_count": word_count,
            "language": language,
            "extracted_at": extracted_at,
            "source_domain": source_domain,
            "extract_mode": extract_mode,
            "was_truncated": was_truncated,
        },
        meta=RegistryItemMeta(
            source="web_fetch",
            domain=CONTEXT_DOMAIN_WEB_FETCH,
            tool_name="fetch_web_page_tool",
        ),
    )

    # 13. Build summary for LLM
    truncation_note = " [truncated]" if was_truncated else ""
    https_warning = " (upgraded to HTTPS)" if validation.https_upgraded else ""
    summary = (
        f"Article '{title}' ({word_count} words{truncation_note}) "
        f"— source: {source_domain}{https_warning}"
    )

    logger.info(
        "web_fetch_success",
        url=safe_url,
        title=title[:80],
        word_count=word_count,
        extract_mode=extract_mode,
        was_truncated=was_truncated,
        user_id=user_id_str[:8],
    )

    structured_data = {
        "title": title,
        "content": markdown_content,
        "url": safe_url,
        "word_count": word_count,
        "language": language,
        "extracted_at": extracted_at,
        "from_cache": False,
        "web_fetchs": [
            {
                "title": title,
                "url": safe_url,
                "word_count": word_count,
                "language": language,
            }
        ],
    }

    # Cache store (after successful extraction)
    try:
        redis_client = await get_redis_cache()
        cache = WebSearchCache(redis_client)
        await cache.set_fetch(
            user_id=config.user_id,
            url=url,
            data={
                "message": summary,
                "structured_data": structured_data,
            },
        )
    except Exception as e:
        logger.warning("web_fetch_cache_store_failed", error=str(e))

    return UnifiedToolOutput.data_success(
        message=summary,
        registry_updates={item_id: registry_item},
        structured_data=structured_data,
    )


__all__ = [
    "fetch_web_page_tool",
    "WebFetchItem",
]
