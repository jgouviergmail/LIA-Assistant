"""
Browser automation configuration module.

Contains settings for:
- Browser feature toggle (enabled/disabled)
- ReAct loop (max iterations of the browser agent)
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

from src.core.constants import (
    BROWSER_AX_TREE_MAX_TOKENS_DEFAULT,
    BROWSER_DEFAULT_TIMEOUT_MS,
    BROWSER_REACT_MAX_ITERATIONS_DEFAULT,
    BROWSER_SSRF_CACHE_MAX_HOSTS_DEFAULT,
    BROWSER_SSRF_CACHE_TTL_SECONDS_DEFAULT,
    BROWSER_SSRF_ENFORCE_DEFAULT,
)


class BrowserSettings(BaseSettings):
    """Browser automation settings for Playwright-based web interaction."""

    # ========================================================================
    # ReAct Loop
    # ========================================================================

    browser_react_max_iterations: int = Field(
        default=BROWSER_REACT_MAX_ITERATIONS_DEFAULT,
        ge=1,
        le=50,
        description=(
            "Max ReAct iterations for the browser agent loop "
            "(create_react_agent recursion_limit). Each iteration is one "
            "LLM call plus the resulting browser tool execution."
        ),
    )

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

    browser_default_timeout_ms: int = Field(
        default=BROWSER_DEFAULT_TIMEOUT_MS,
        ge=30_000,
        le=600_000,
        description=(
            "Default timeout (milliseconds) embedded in the ``browser_agent`` "
            "manifest by ``catalogue_loader`` and surfaced to the planner. "
            "Catalogue manifests use ms to match the frontend display contract. "
            "Independent from ``browser_tool_timeout_seconds`` which is the "
            "actual ``asyncio.wait_for`` value applied by the parallel executor."
        ),
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
        default=BROWSER_AX_TREE_MAX_TOKENS_DEFAULT,
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

    browser_ssrf_enforce: bool = Field(
        default=BROWSER_SSRF_ENFORCE_DEFAULT,
        description=(
            "SEC-032. When true, the request interceptor ABORTS every navigation, "
            "redirect, sub-resource or click that resolves to a non-public address. "
            "When false it only logs what it would have blocked (report-only), so "
            "the block rate can be measured on real traffic before enforcing — a "
            "wrongly-blocked CDN would otherwise break page rendering silently."
        ),
    )

    browser_ssrf_cache_ttl_seconds: int = Field(
        default=BROWSER_SSRF_CACHE_TTL_SECONDS_DEFAULT,
        ge=1,
        le=300,
        description=(
            "How long a per-host SSRF verdict is reused. The check resolves DNS, "
            "and a page pulls dozens to hundreds of sub-resources — without a "
            "cache the interceptor would add one lookup per request. Kept short: "
            "the cache is also the DNS-rebinding window."
        ),
    )

    browser_ssrf_cache_max_hosts: int = Field(
        default=BROWSER_SSRF_CACHE_MAX_HOSTS_DEFAULT,
        ge=16,
        description="Maximum hosts held in the SSRF verdict cache (bounded memory).",
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
