"""
Browser automation configuration module.

Contains settings for:
- Browser feature toggle (enabled/disabled)
- Session management (timeout, max sessions, max navigations)
- Accessibility tree extraction (max tokens, max depth)
- Rate limiting (read/write/expensive tool calls)
- Resource limits (memory, screenshots)
- Security (blocked domains, user agent)

Phase: evolution F7 — Browser Control (Playwright)
Created: 2026-03-18
Reference: docs/technical/BROWSER_CONTROL.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class BrowserSettings(BaseSettings):
    """Browser automation settings for Playwright-based web interaction."""

    # ========================================================================
    # Session Management
    # ========================================================================

    browser_max_concurrent_sessions: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Maximum concurrent browser sessions globally (coordinated via Redis).",
    )

    browser_session_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=1800,
        description="Idle timeout before a browser session is automatically closed.",
    )

    browser_max_pages_per_session: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum pages per browser session.",
    )

    browser_max_navigations_per_session: int = Field(
        default=30,
        ge=5,
        le=100,
        description="Maximum navigations per session before forced close.",
    )

    # ========================================================================
    # Timeouts
    # ========================================================================

    browser_page_load_timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Maximum wait time for page load completion.",
    )

    browser_action_timeout_seconds: int = Field(
        default=10,
        ge=3,
        le=60,
        description="Maximum wait time for individual browser actions (click, fill).",
    )

    # ========================================================================
    # Accessibility Tree
    # ========================================================================

    browser_accessibility_max_depth: int = Field(
        default=8,
        ge=3,
        le=15,
        description="Maximum depth for accessibility tree extraction.",
    )

    browser_ax_tree_max_tokens: int = Field(
        default=5000,
        ge=500,
        le=50000,
        description="Maximum tokens for accessibility tree output. Hard-truncated if exceeded.",
    )

    # ========================================================================
    # Resource Limits
    # ========================================================================

    browser_memory_limit_mb: int = Field(
        default=512,
        ge=128,
        le=2048,
        description="Memory limit per browser instance (MB). Navigation refused if exceeded.",
    )

    browser_progressive_screenshots: bool = Field(
        default=True,
        description=(
            "Enable progressive screenshot streaming via SSE during browser actions. "
            "Side-channel only (not processed by LLM)."
        ),
    )

    browser_screenshot_debounce_seconds: float = Field(
        default=0.1,
        ge=0.0,
        le=10.0,
        description=(
            "Minimum interval in seconds between progressive screenshots for the same user. "
            "Prevents flooding during rapid browser action sequences."
        ),
    )

    # ========================================================================
    # Security
    # ========================================================================

    browser_blocked_domains: str = Field(
        default="",
        description="Additional blocked domains (CSV). Combined with SSRF protection.",
    )

    browser_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        description="User-Agent string for browser requests.",
    )

    # ========================================================================
    # Rate Limiting
    # ========================================================================

    browser_rate_limit_read_calls: int = Field(
        default=20,
        ge=5,
        le=100,
        description="Max read tool calls (navigate, snapshot) per window.",
    )

    browser_rate_limit_read_window: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Rate limit window (seconds) for read tools.",
    )

    browser_rate_limit_write_calls: int = Field(
        default=20,
        ge=5,
        le=100,
        description="Max write tool calls (click, fill, press_key) per window.",
    )

    browser_rate_limit_write_window: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Rate limit window (seconds) for write tools.",
    )

    browser_rate_limit_expensive_calls: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Max expensive tool calls (screenshot) per window.",
    )

    browser_rate_limit_expensive_window: int = Field(
        default=300,
        ge=60,
        le=1800,
        description="Rate limit window (seconds) for expensive tools.",
    )
