"""
Display Configuration for v3 Architecture.

Provides contextual display settings for responsive, warm responses.

PRINCIPLES:
1. CLEAR HIERARCHY (Respect user's brain)
   - Clickable title first
   - Essential metadata (compact)
   - Optional details (expandable/folding)

2. RESPONSIVE BY DEFAULT
   - Viewport injected by client
   - 1-2 lines max for info
   - Minimal separators
   - Emojis as SEMANTIC ICONS (not decoration)

3. CONTEXTUAL
   - Simple chat: natural, conversational
   - Mono-domain: compact structured list
   - Multi-domain: summary + sections per domain
   - HITL: focus on requested action

4. TOKEN ECONOMY
   - Only show relevant fields
   - Omit null/empty values
   - Group intelligently

5. GLANCEABILITY (At a glance)
   - Quantitative summary first
   - User knows instantly

6. WARMTH & CONNECTION
   - Structure serves clarity, tone serves RELATIONSHIP
   - Never orphan lists (always introduce)
   - Micro-comments in data
   - Varied vocabulary
   - Natural bounce (invite exchange)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.core.config import settings
from src.core.config.agents import V3DisplayConfig as V3DisplayConfigModel
from src.core.config.agents import get_v3_display_config


class Viewport(str, Enum):
    """Screen viewport sizes.

    Breakpoint defined in env:
    - V3_DISPLAY_VIEWPORT_MOBILE_MAX_WIDTH (default 430px)

    Mobile: <= 430px, Desktop: > 430px
    TABLET kept for backward compatibility but uses DESKTOP rendering.
    """

    MOBILE = "mobile"  # <= MOBILE_MAX_WIDTH (default 430px)
    TABLET = "tablet"  # Deprecated: uses DESKTOP rendering
    DESKTOP = "desktop"  # > MOBILE_MAX_WIDTH (default 430px)


class UserExpertise(str, Enum):
    """User expertise level for adaptive verbosity."""

    NOVICE = "novice"  # More verbose, explanatory
    INTERMEDIATE = "intermediate"  # Balanced
    EXPERT = "expert"  # Compact, icons only


class DisplayContext(str, Enum):
    """Display context types."""

    CHAT = "chat"  # Simple conversation
    MONO = "mono"  # Single domain results
    MULTI = "multi"  # Multi-domain results
    HITL = "hitl"  # Human-in-the-loop confirmation


# ============================================================================
# CSS CLASS CONSTANTS (DRY - Single Source of Truth)
# ============================================================================
# These constants ensure consistency between Python HTML generation and CSS
# Matches classes defined in apps/web/src/styles/lia-components.css

# Separator classes (bold vs simple)
CSS_CLASS_SEPARATOR_BOLD = "lia-response-separator"  # Bold line - boundaries
CSS_CLASS_SEPARATOR_SIMPLE = "lia-section-separator"  # Simple line - internal


def separator_bold() -> str:
    """Generate bold separator HR tag (used at response boundaries)."""
    return f'<hr class="{CSS_CLASS_SEPARATOR_BOLD}">'


def separator_simple() -> str:
    """Generate simple separator HR tag (used between sections/clusters)."""
    return f'<hr class="{CSS_CLASS_SEPARATOR_SIMPLE}">'


@dataclass
class DisplayConfig:
    """Configuration for response display.

    IMPORTANT: The template is selected by Python code,
    NOT by the LLM "guessing". The LLM receives the appropriate template.

    The conversational sandwich is MANDATORY for any response
    with structured data.

    Uses centralized constants from src.core.constants.
    """

    context: DisplayContext = DisplayContext.MONO
    viewport: Viewport = Viewport.DESKTOP
    user_expertise: UserExpertise = UserExpertise.INTERMEDIATE
    max_items_per_domain: int = settings.v3_display_max_items_per_domain
    show_secondary_metadata: bool = True
    enable_folding: bool = False  # For mobile mainly
    language: str = "fr"
    timezone: str = "Europe/Paris"  # User timezone for datetime formatting

    # Result display options
    show_relevance_explanation: bool = False
    group_by_date: bool = True
    show_proactive_suggestions: bool = True

    def for_mobile(self) -> DisplayConfig:
        """Return config adapted for mobile."""
        return DisplayConfig(
            context=self.context,
            viewport=Viewport.MOBILE,
            user_expertise=self.user_expertise,
            max_items_per_domain=self.max_items_per_domain,  # Use centralized config (respects user intent)
            show_secondary_metadata=False,  # Hide secondary on mobile
            enable_folding=True,  # Enable folding on mobile
            language=self.language,
            timezone=self.timezone,
            show_relevance_explanation=False,
            group_by_date=self.group_by_date,
            show_proactive_suggestions=True,
        )

    def for_hitl(self) -> DisplayConfig:
        """Return config for HITL confirmation."""
        return DisplayConfig(
            context=DisplayContext.HITL,
            viewport=self.viewport,
            user_expertise=self.user_expertise,
            max_items_per_domain=1,  # Focus on single item
            show_secondary_metadata=True,  # Show all details for confirmation
            enable_folding=False,
            language=self.language,
            timezone=self.timezone,
            show_relevance_explanation=False,
            group_by_date=False,
            show_proactive_suggestions=False,  # No distractions
        )

    def with_context(self, context: DisplayContext) -> DisplayConfig:
        """Return config with different context."""
        return DisplayConfig(
            context=context,
            viewport=self.viewport,
            user_expertise=self.user_expertise,
            max_items_per_domain=self.max_items_per_domain,
            show_secondary_metadata=self.show_secondary_metadata,
            enable_folding=self.enable_folding,
            language=self.language,
            timezone=self.timezone,
            show_relevance_explanation=self.show_relevance_explanation,
            group_by_date=self.group_by_date,
            show_proactive_suggestions=self.show_proactive_suggestions,
        )


def get_default_config(config: V3DisplayConfigModel | None = None) -> DisplayConfig:
    """Get default display configuration.

    Args:
        config: Optional V3DisplayConfigModel. If not provided, loaded from env.

    Returns:
        DisplayConfig with values from config.
    """
    v3_config = config or get_v3_display_config()

    return DisplayConfig(
        max_items_per_domain=v3_config.max_items_per_domain,
    )


def viewport_from_width(
    width: int,
    config: V3DisplayConfigModel | None = None,
) -> Viewport:
    """Determine viewport from screen width using config breakpoint.

    Uses V3_DISPLAY_VIEWPORT_MOBILE_MAX_WIDTH from environment configuration.
    <= mobile_max_width -> MOBILE, > mobile_max_width -> DESKTOP

    Args:
        width: Screen width in pixels.
        config: Optional V3DisplayConfigModel. If not provided, loaded from env.

    Returns:
        Viewport enum (MOBILE or DESKTOP).
    """
    v3_config = config or get_v3_display_config()

    if width <= v3_config.viewport_mobile_max_width:
        return Viewport.MOBILE
    return Viewport.DESKTOP


def config_for_viewport(
    viewport: str,
    config: V3DisplayConfigModel | None = None,
) -> DisplayConfig:
    """Get config for specific viewport.

    Args:
        viewport: Viewport string ('mobile', 'tablet', 'desktop').
        config: Optional V3DisplayConfigModel. If not provided, loaded from env.

    Returns:
        DisplayConfig adapted for the viewport.
    """
    v3_config = config or get_v3_display_config()
    viewport_enum = (
        Viewport(viewport) if viewport in Viewport._value2member_map_ else Viewport.DESKTOP
    )

    display_config = DisplayConfig(
        viewport=viewport_enum,
        max_items_per_domain=v3_config.max_items_per_domain,
    )

    if viewport_enum == Viewport.MOBILE:
        return display_config.for_mobile()

    return display_config


def config_for_width(
    width: int,
    config: V3DisplayConfigModel | None = None,
) -> DisplayConfig:
    """Get config for specific screen width.

    Combines viewport_from_width and config_for_viewport.
    Uses breakpoints from environment configuration.

    Args:
        width: Screen width in pixels.
        config: Optional V3DisplayConfigModel. If not provided, loaded from env.

    Returns:
        DisplayConfig adapted for the determined viewport.
    """
    v3_config = config or get_v3_display_config()
    viewport = viewport_from_width(width, v3_config)
    return config_for_viewport(viewport.value, v3_config)
