"""
Catalogue manifests for browser agent tools.

These manifests enable the SmartPlannerService to discover and select
browser tools during plan generation. Each manifest describes a tool's
capabilities, parameters, outputs, cost profile, and semantic keywords.

Phase: evolution F7 — Browser Control (Playwright)
Pattern: domains/agents/wikipedia/catalogue_manifests.py
"""

from __future__ import annotations

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# Browser Navigate Tool Manifest
# ============================================================================

# ============================================================================
# Browser Task Tool (PRIMARY — autonomous multi-step browsing)
# ============================================================================

browser_task_catalogue_manifest = ToolManifest(
    name="browser_task_tool",
    agent="browser_agent",
    description=(
        "Execute a complete browsing task autonomously: navigate to a website, "
        "search for content, click elements, fill forms, and extract results. "
        "The browser agent handles multi-step interaction internally. "
        "Use for ANY task requiring web interaction beyond simple page fetching."
    ),
    semantic_keywords=[
        "browse website",
        "go to website",
        "search on website",
        "navigate to URL",
        "visit page",
        "open browser",
        "interact with website",
        "fill form on website",
        "click on website",
        "find on website",
        "search for products",
        "check prices on website",
        "look up on site",
    ],
    parameters=[
        ParameterSchema(
            name="task",
            type="string",
            description="Natural language description of the browsing task",
            required=True,
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="content",
            type="string",
            description="Extracted content from the browsing session (text, data, results)",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=500,
        est_tokens_out=5000,
        est_cost_usd=0.02,
        est_latency_ms=15000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="browsers",
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="🌐",
        i18n_key="browser.navigate",
        visible=True,
        category="tool",
    ),
)

# ============================================================================
# Individual Browser Tools (used internally by browser agent ReAct loop)
# ============================================================================

browser_navigate_catalogue_manifest = ToolManifest(
    name="browser_navigate_tool",
    agent="browser_agent",
    description=(
        "Navigate to a specific URL. Used internally by the browser agent. "
        "For complete browsing tasks, use browser_task_tool instead."
    ),
    semantic_keywords=[
        "open URL",
        "navigate to specific page",
    ],
    parameters=[
        ParameterSchema(
            name="url",
            type="string",
            description="The URL to navigate to",
            required=True,
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="accessibility_tree",
            type="string",
            description="Page content as accessibility tree with [EN] element references",
        ),
        OutputFieldSchema(
            path="interactive_count",
            type="integer",
            description="Number of interactive elements found",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=200,
        est_tokens_out=2000,
        est_cost_usd=0.005,
        est_latency_ms=3000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="browsers",
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="🌐",
        i18n_key="browser.navigate",
        visible=True,
        category="tool",
    ),
)

# ============================================================================
# Browser Snapshot Tool Manifest
# ============================================================================

browser_snapshot_catalogue_manifest = ToolManifest(
    name="browser_snapshot_tool",
    agent="browser_agent",
    description=(
        "Get the current page's accessibility tree. "
        "Use before clicking or filling to get fresh element references."
    ),
    semantic_keywords=[
        "read page content",
        "get page state",
        "observe page",
        "page elements",
        "what is on the page",
    ],
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="accessibility_tree",
            type="string",
            description="Current page accessibility tree with [EN] references",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=100,
        est_tokens_out=2000,
        est_cost_usd=0.003,
        est_latency_ms=1500,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="browsers",
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="👁️",
        i18n_key="browser.snapshot",
        visible=True,
        category="tool",
    ),
)

# ============================================================================
# Browser Click Tool Manifest
# ============================================================================

browser_click_catalogue_manifest = ToolManifest(
    name="browser_click_tool",
    agent="browser_agent",
    description="Click an interactive element on the page by its [EN] reference.",
    semantic_keywords=[
        "click button",
        "click link",
        "press button",
        "select option",
        "click element",
    ],
    parameters=[
        ParameterSchema(
            name="ref",
            type="string",
            description="Element reference from accessibility tree (e.g., 'E3')",
            required=True,
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="accessibility_tree",
            type="string",
            description="Page state after click",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=100,
        est_tokens_out=2000,
        est_cost_usd=0.003,
        est_latency_ms=2000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="browsers",
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="👆",
        i18n_key="browser.click",
        visible=True,
        category="tool",
    ),
)

# ============================================================================
# Browser Fill Tool Manifest
# ============================================================================

browser_fill_catalogue_manifest = ToolManifest(
    name="browser_fill_tool",
    agent="browser_agent",
    description="Fill a form field on the page by its [EN] reference with a value.",
    semantic_keywords=[
        "fill form",
        "type text",
        "enter value",
        "fill field",
        "input text",
        "form submission",
    ],
    parameters=[
        ParameterSchema(
            name="ref",
            type="string",
            description="Element reference for the form field (e.g., 'E2')",
            required=True,
        ),
        ParameterSchema(
            name="value",
            type="string",
            description="The value to fill into the field",
            required=True,
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="accessibility_tree",
            type="string",
            description="Page state after filling the field",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=150,
        est_tokens_out=2000,
        est_cost_usd=0.003,
        est_latency_ms=1500,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="browsers",
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="✏️",
        i18n_key="browser.fill",
        visible=True,
        category="tool",
    ),
)

# ============================================================================
# Browser Press Key Tool Manifest
# ============================================================================

browser_press_key_catalogue_manifest = ToolManifest(
    name="browser_press_key_tool",
    agent="browser_agent",
    description="Press a keyboard key (Enter, Tab, Escape, Arrow keys, etc.).",
    semantic_keywords=[
        "press enter",
        "press key",
        "submit form",
        "keyboard input",
        "press tab",
    ],
    parameters=[
        ParameterSchema(
            name="key",
            type="string",
            description="Key to press (e.g., 'Enter', 'Tab', 'Escape')",
            required=True,
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="accessibility_tree",
            type="string",
            description="Page state after key press",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=100,
        est_tokens_out=2000,
        est_cost_usd=0.002,
        est_latency_ms=1000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="browsers",
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="⌨️",
        i18n_key="browser.press_key",
        visible=True,
        category="tool",
    ),
)

# ============================================================================
# Browser Screenshot Tool Manifest
# ============================================================================

browser_screenshot_catalogue_manifest = ToolManifest(
    name="browser_screenshot_tool",
    agent="browser_agent",
    description=(
        "Take a screenshot of the current page. "
        "Expensive operation — use only when visual verification is needed."
    ),
    semantic_keywords=[
        "screenshot page",
        "capture page",
        "page image",
        "visual check",
    ],
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="image_base64",
            type="string",
            description="JPEG screenshot encoded as base64",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=100,
        est_tokens_out=5000,
        est_cost_usd=0.02,
        est_latency_ms=2000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="browsers",
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="📸",
        i18n_key="browser.screenshot",
        visible=True,
        category="tool",
    ),
)
