"""
Browser session wrapper around a Playwright BrowserContext.

Provides high-level browser interaction methods (navigate, click, fill)
with security checks, accessibility tree extraction, content wrapping,
and resource limit enforcement.

Phase: evolution F7 — Browser Control (Playwright)
"""

from __future__ import annotations

import time
from io import BytesIO
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.constants import (
    BROWSER_SCREENSHOT_THUMBNAIL_QUALITY,
    BROWSER_SCREENSHOT_THUMBNAIL_WIDTH,
)
from src.infrastructure.browser.accessibility import AccessibilityTreeExtractor, AXNode
from src.infrastructure.browser.models import PageSnapshot
from src.infrastructure.browser.security import BrowserSecurityPolicy
from src.infrastructure.observability.metrics_browser import (
    browser_actions_total,
    browser_navigation_duration_seconds,
)

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

logger = structlog.get_logger(__name__)


class BrowserSession:
    """Manages a single user's browser session within a BrowserContext.

    Each session wraps a Playwright BrowserContext and provides high-level
    browser interaction methods (navigate, click, fill) with security checks,
    accessibility tree extraction, and content wrapping.

    Args:
        user_id: The user who owns this session.
        context: The Playwright BrowserContext for this session.
        security: Security policy for URL validation and input sanitization.
    """

    def __init__(
        self,
        user_id: str,
        context: BrowserContext,
        security: BrowserSecurityPolicy,
    ) -> None:
        self.user_id = user_id
        self.context = context
        self.page: Page | None = None
        self.created_at = time.monotonic()
        self.last_activity = time.monotonic()
        self.navigation_count = 0
        self._extractor = AccessibilityTreeExtractor()
        self._security = security
        self._popup_handler_registered = False

    def _register_popup_handler(self) -> None:
        """Register popup handler AFTER the main page is created.

        Must be called after the first new_page() to avoid closing
        the main page (context.on("page") fires for new_page() too).
        """
        if not self._popup_handler_registered:
            self.context.on("page", self._handle_new_page)
            self._popup_handler_registered = True

    async def _handle_new_page(self, new_page: Page) -> None:
        """Handle popup pages by closing them.

        Only closes pages that are NOT our main page.

        Args:
            new_page: The newly opened page (popup or tab).
        """
        if self.page is not None and new_page != self.page:
            logger.info("browser_popup_closed", url=new_page.url[:200])
            await new_page.close()

    async def navigate(self, url: str) -> PageSnapshot:
        """Navigate to a URL with SSRF check and request interception.

        Args:
            url: The URL to navigate to.

        Returns:
            PageSnapshot with accessibility tree of the loaded page.

        Raises:
            ValueError: If URL fails SSRF validation or limits exceeded.
            TimeoutError: If page load exceeds timeout.
        """
        self._check_limits()

        # SSRF validation
        is_valid, error = await self._security.validate_navigation_url(url)
        if not is_valid:
            raise ValueError(f"URL blocked: {error}")

        # Create or reuse page
        if self.page is None or self.page.is_closed():
            self.page = await self.context.new_page()
            await self._security.create_request_interceptor(self.page)
            # Register popup handler AFTER main page exists (avoids closing our own page)
            self._register_popup_handler()

        # Navigate with duration tracking
        timeout_ms = settings.browser_page_load_timeout_seconds * 1000
        nav_start = time.monotonic()
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Wait for JavaScript to finish rendering (SPAs, dynamic content)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass  # Some pages never reach networkidle (analytics, websockets)
            # Auto-dismiss cookie consent banners (blocks content on most sites)
            await self._dismiss_cookie_banner()
        except Exception as nav_error:
            # Page crashed or navigation failed — close corrupted page to prevent
            # subsequent operations from hanging on a dead page
            try:
                if self.page and not self.page.is_closed():
                    await self.page.close()
            except Exception:
                pass  # Best-effort cleanup: page may already be crashed
            self.page = None
            raise nav_error

        browser_navigation_duration_seconds.observe(time.monotonic() - nav_start)
        browser_actions_total.labels(action_type="navigate", status="success").inc()

        self.navigation_count += 1
        self.last_activity = time.monotonic()

        return await self.get_page_content()

    async def get_page_content(self) -> PageSnapshot:
        """Get visible text content of the current page.

        Extracts the visible text using page.inner_text() — this is what
        the user actually sees on screen. Ideal for content extraction
        (product listings, articles, search results).

        Tries semantic HTML5 content areas first (main, article), falls
        back to body if no semantic container found.

        Returns:
            PageSnapshot with visible text content.

        Raises:
            ValueError: If no page is currently open.
        """
        if self.page is None or self.page.is_closed():
            raise ValueError("No page is currently open")

        self.last_activity = time.monotonic()

        # Extract visible text — try semantic content areas first
        visible_text = ""
        for selector in ["main", "[role='main']", "article", "body"]:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() > 0:
                    visible_text = await locator.inner_text(timeout=5000)
                    if len(visible_text.strip()) > 100:
                        break
            except Exception:
                continue

        # Truncate to token budget
        max_chars = settings.browser_ax_tree_max_tokens * 4  # ~4 chars per token
        if len(visible_text) > max_chars:
            visible_text = (
                visible_text[:max_chars] + f"\n[... content truncated at {max_chars} chars]"
            )

        return PageSnapshot(
            url=self.page.url,
            title=await self.page.title(),
            content=visible_text,
        )

    async def get_snapshot(self) -> PageSnapshot:
        """Get accessibility tree with [EN] refs for interaction.

        Use this before clicking or filling elements — provides
        element references for targeted actions.

        Returns:
            PageSnapshot with formatted accessibility tree.

        Raises:
            ValueError: If no page is currently open.
        """
        if self.page is None or self.page.is_closed():
            raise ValueError("No page is currently open")

        self.last_activity = time.monotonic()

        # Extract and format accessibility tree with refs
        nodes = await self._extractor.extract(self.page)
        nodes = self._extractor.assign_refs(nodes)
        total_count = self._count_nodes(nodes)
        nodes = self._extractor.compact_tree(nodes)
        tree_text = self._extractor.format_for_llm(nodes)
        interactive_count = self._count_refs(nodes)

        return PageSnapshot(
            url=self.page.url,
            title=await self.page.title(),
            content=tree_text,
            interactive_count=interactive_count,
            total_count=total_count,
        )

    async def click(self, ref: str) -> PageSnapshot:
        """Click an interactive element by its [EN] reference.

        Args:
            ref: Element reference (e.g., 'E3').

        Returns:
            PageSnapshot after the click action.

        Raises:
            ValueError: If element not found or no page open.
        """
        if self.page is None or self.page.is_closed():
            raise ValueError("No page is currently open")

        locator = await self._extractor.find_element_by_ref(self.page, ref)
        if not locator:
            raise ValueError(f"Element [{ref}] not found on page")

        timeout_ms = settings.browser_action_timeout_seconds * 1000
        await locator.click(timeout=timeout_ms)
        browser_actions_total.labels(action_type="click", status="success").inc()
        self.last_activity = time.monotonic()

        # Wait briefly for page to settle after click (may not reload on SPAs)
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass  # SPA pages don't reload — timeout is expected

        return await self.get_snapshot()

    async def fill(self, ref: str, value: str) -> PageSnapshot:
        """Fill a form field by its [EN] reference with a sanitized value.

        Args:
            ref: Element reference (e.g., 'E2').
            value: The value to fill into the field.

        Returns:
            PageSnapshot after the fill action.

        Raises:
            ValueError: If element not found or no page open.
        """
        if self.page is None or self.page.is_closed():
            raise ValueError("No page is currently open")

        # Sanitize input
        safe_value = self._security.sanitize_fill_value(value)

        locator = await self._extractor.find_element_by_ref(self.page, ref)
        if not locator:
            raise ValueError(f"Element [{ref}] not found on page")

        timeout_ms = settings.browser_action_timeout_seconds * 1000
        await locator.fill(safe_value, timeout=timeout_ms)
        browser_actions_total.labels(action_type="fill", status="success").inc()
        self.last_activity = time.monotonic()

        return await self.get_snapshot()

    async def press_key(self, key: str) -> PageSnapshot:
        """Press a validated keyboard key.

        Args:
            key: The key to press (e.g., 'Enter', 'Tab').

        Returns:
            PageSnapshot after the key press.

        Raises:
            ValueError: If key not allowed or no page open.
        """
        if self.page is None or self.page.is_closed():
            raise ValueError("No page is currently open")

        if not self._security.validate_key(key):
            raise ValueError(f"Key '{key}' not allowed")

        await self.page.keyboard.press(key)
        browser_actions_total.labels(action_type="press_key", status="success").inc()
        self.last_activity = time.monotonic()

        # Wait briefly for page to settle (may not reload on SPAs)
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass  # SPA pages don't reload — timeout is expected

        return await self.get_snapshot()

    async def screenshot_with_thumbnail(
        self,
    ) -> tuple[bytes | None, bytes | None]:
        """Capture a full-res screenshot AND a reduced thumbnail in a single call.

        One Playwright screenshot call produces two outputs:
        - full_res: Original 1280x720 JPEG quality 80 (for persistent card, ~100-150KB)
        - thumbnail: 640px-wide JPEG quality 60 (for ephemeral SSE overlay, ~50-80KB)

        Never raises — returns (None, None) on any failure to avoid disrupting
        tool execution.

        Returns:
            Tuple of (full_res_bytes, thumbnail_bytes). Both None on error.
        """
        try:
            if self.page is None or self.page.is_closed():
                return None, None

            # Lazy import: Pillow is heavy and only needed for thumbnails
            from PIL import Image

            # Single Playwright call — reused for both outputs
            full_res = await self.page.screenshot(type="jpeg", quality=80, full_page=False)

            # Thumbnail: resize for SSE side-channel overlay
            img = Image.open(BytesIO(full_res))
            # thumbnail() like resize.py — in-place, preserves aspect ratio
            img.thumbnail(
                (BROWSER_SCREENSHOT_THUMBNAIL_WIDTH, BROWSER_SCREENSHOT_THUMBNAIL_WIDTH),
                Image.Resampling.LANCZOS,
            )

            buf = BytesIO()
            img.save(buf, format="JPEG", quality=BROWSER_SCREENSHOT_THUMBNAIL_QUALITY)
            thumbnail = buf.getvalue()

            return full_res, thumbnail
        except Exception:
            return None, None

    async def close(self) -> None:
        """Close the page and browser context, releasing all resources."""
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass  # Best-effort cleanup: page may already be closed or disconnected

        try:
            await self.context.close()
        except Exception:
            pass  # Best-effort cleanup: context may already be closed

        self.page = None
        logger.info("browser_session_closed", user_id=self.user_id[:8])

    # ========================================================================
    # Private helpers
    # ========================================================================

    async def _dismiss_cookie_banner(self) -> None:
        """Auto-dismiss cookie consent banners after navigation.

        Attempts to find and click common cookie accept buttons using
        multiple selector strategies. Runs silently — if no banner is
        found or the click fails, navigation continues normally.
        """
        if self.page is None or self.page.is_closed():
            return

        # Generic selectors for cookie accept buttons (ordered by frequency)
        # NO site-specific selectors — must work on any website.
        accept_selectors = [
            # Text-based (multi-language, covers 95% of cookie banners)
            'button:has-text("Accept all")',
            'button:has-text("Accept All")',
            'button:has-text("Tout accepter")',
            'button:has-text("Accepter")',
            'button:has-text("Accept")',
            'button:has-text("Alle akzeptieren")',
            'button:has-text("Akzeptieren")',
            'button:has-text("Aceptar todo")',
            'button:has-text("Aceptar")',
            'button:has-text("Accetta tutto")',
            'button:has-text("Accetta")',
            'button:has-text("Agree")',
            'button:has-text("Got it")',
            'button:has-text("OK")',
            'button:has-text("J\'ai compris")',
            'button:has-text("Continuer")',
            'input[type="submit"][value*="Accept" i]',
            'input[type="submit"][value*="ccept" i]',
            # Attribute-based (generic patterns across CMP frameworks)
            'button[id*="accept" i]',
            'button[class*="accept" i]',
            'button[data-testid*="accept" i]',
            '[id*="cookie" i] button',
            '[id*="consent" i] button',
            '[class*="cookie" i] button',
            '[class*="consent" i] button',
            '[role="dialog"] button:first-of-type',
        ]

        for selector in accept_selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.is_visible(timeout=500):
                    await locator.click(timeout=2000)
                    logger.info("browser_cookie_banner_dismissed", selector=selector[:50])
                    # Wait for page to reload after cookie acceptance
                    # Many sites reload content dynamically after consent
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        # Fallback: fixed wait if networkidle never reached
                        import asyncio

                        await asyncio.sleep(2)
                    return
            except Exception:
                continue  # Try next selector

    def _check_limits(self) -> None:
        """Check session resource limits before navigation.

        Raises:
            ValueError: If max navigations exceeded.
        """
        if self.navigation_count >= settings.browser_max_navigations_per_session:
            raise ValueError("Max navigations per session reached")

    def _count_nodes(self, nodes: list[AXNode]) -> int:
        """Count total nodes in tree."""
        count = len(nodes)
        for node in nodes:
            count += self._count_nodes(node.children)
        return count

    def _count_refs(self, nodes: list[AXNode]) -> int:
        """Count nodes with refs in tree."""
        count = sum(1 for n in nodes if n.ref)
        for node in nodes:
            count += self._count_refs(node.children)
        return count
