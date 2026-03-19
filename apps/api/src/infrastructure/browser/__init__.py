"""
Browser automation infrastructure.

Provides Playwright-based headless browser management with:
- Session pool with cross-worker recovery via Redis
- Accessibility tree extraction via Chrome DevTools Protocol (CDP)
- Security policy (SSRF prevention, input sanitization, request interception)

Phase: evolution F7 — Browser Control (Playwright)
Reference: docs/technical/BROWSER_CONTROL.md
"""

from src.infrastructure.browser.models import (
    BrowserAction,
    BrowserSessionInfo,
    PageSnapshot,
)
from src.infrastructure.browser.pool import close_browser_pool, get_browser_pool

__all__ = [
    "BrowserAction",
    "BrowserSessionInfo",
    "PageSnapshot",
    "close_browser_pool",
    "get_browser_pool",
]
