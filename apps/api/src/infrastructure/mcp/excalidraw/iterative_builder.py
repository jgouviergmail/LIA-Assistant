"""
Excalidraw Iterative Builder — LLM-driven diagram construction.

The core principle: the LLM is the creative engine.  It decides positions, sizes,
colors, and layout.  Python code ONLY orchestrates the LLM call and parses the result.
No coordinate computation in this module — non-intent elements are passed through
unchanged to the MCP server.

Flow:
    1. Receive structured intent (components, connections, layout) from planner
    2. Use the ``read_me`` cheat sheet from the Excalidraw MCP server
    3. Single LLM call: generate ALL elements (camera + background + shapes + labels + arrows)
    4. Return final JSON array

Phase: evolution F2 — Admin MCP Excalidraw
Created: 2026-03-07
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Maximum total components in a diagram
_MAX_COMPONENTS = 15
# Maximum elements the LLM can generate per call (safety limit)
_MAX_ELEMENTS_PER_CALL = 60


async def build_from_intent(
    intent: dict[str, Any],
    cheat_sheet: str,
) -> str:
    """Build Excalidraw elements from a structured intent via a single LLM call.

    The LLM is the creative engine — it decides ALL positions, layout, and
    connections in one pass.

    Args:
        intent: Structured diagram intent with components, connections, layout.
        cheat_sheet: Full read_me content from the Excalidraw MCP server.

    Returns:
        JSON string of the complete Excalidraw elements array.

    Raises:
        ValueError: If intent has no components.
    """
    components = intent.get("components", [])
    connections = intent.get("connections", [])
    description = intent.get("description", "Diagram")
    layout = intent.get("layout", "top-to-bottom")

    if not components:
        raise ValueError("Intent must contain at least one component")

    # Cap components to prevent excessive output
    if len(components) > _MAX_COMPONENTS:
        components = components[:_MAX_COMPONENTS]
        logger.warning(
            "excalidraw_intent_components_capped",
            original_count=len(intent.get("components", [])),
            capped_to=_MAX_COMPONENTS,
        )

    logger.info(
        "excalidraw_build_start",
        description=description,
        component_count=len(components),
        connection_count=len(connections),
        layout=layout,
    )

    llm = _get_excalidraw_llm()
    invoke_config = _build_invoke_config()

    elements = await _generate_diagram(
        llm,
        components,
        connections,
        layout,
        description,
        cheat_sheet,
        invoke_config,
    )

    logger.info(
        "excalidraw_build_complete",
        total_elements=len(elements),
        component_count=len(components),
        connection_count=len(connections),
    )

    return json.dumps(elements)


def is_intent(elements_str: str) -> dict[str, Any] | None:
    """Check if the elements string is a structured intent (not raw elements).

    Returns the parsed intent dict if it's an intent, None otherwise.
    """
    try:
        data = json.loads(elements_str)
    except (json.JSONDecodeError, TypeError):
        return None

    if isinstance(data, dict) and data.get("intent") is True and "components" in data:
        return data

    return None


# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------


def _get_excalidraw_llm() -> Any:
    """Get a dedicated LLM instance for Excalidraw diagram generation.

    Uses LLM_DEFAULTS["mcp_excalidraw"] + DB overrides via admin config.
    """
    from src.infrastructure.llm.factory import get_llm

    return get_llm("mcp_excalidraw")


_EXCALIDRAW_NODE_NAME = "excalidraw_builder"


def _build_invoke_config() -> RunnableConfig:
    """Build a RunnableConfig with metrics callbacks for token/cost tracking.

    Ensures Excalidraw LLM calls are tracked in both:
    - **Prometheus** (MetricsCallbackHandler) via ``enrich_config_with_node_metadata``
    - **DB cost aggregation** (TokenTrackingCallback) via ``current_tracker`` ContextVar

    The ``current_tracker`` ContextVar is set by ``TrackingContext.__aenter__()``
    at graph start and remains available throughout the async call stack.
    Without it, Excalidraw LLM costs are missing from the user-facing cost total.
    """
    from src.core.context import current_tracker
    from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

    # Build base config with TokenTrackingCallback if tracker is available
    base_config: RunnableConfig | None = None
    tracker = current_tracker.get()
    if tracker is not None:
        from src.infrastructure.observability.callbacks import TokenTrackingCallback

        token_callback = TokenTrackingCallback(tracker=tracker, run_id=tracker.run_id)
        base_config = RunnableConfig(callbacks=[token_callback])

    # Enrich with MetricsCallbackHandler (Prometheus) — preserves existing callbacks
    return enrich_config_with_node_metadata(base_config, _EXCALIDRAW_NODE_NAME)


# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------

_SYSTEM_PREFIX = """You are an expert Excalidraw diagram generator.
You generate ONLY valid Excalidraw JSON element arrays — no explanations, no markdown.
Follow the cheat sheet EXACTLY for element format, color usage, and coordinate system.

CRITICAL RULES:
- Output ONLY a valid JSON array [...] — no text before or after
- Use separate text elements with containerId for labels (no label shorthand)
- Center text precisely: text.x = shape.x + (shape.width - text.width) / 2
- Center text vertically: text.y = shape.y + (shape.height - text.height) / 2
- All shapes must have: type, id, x, y, width, height, backgroundColor, strokeColor
- All text must have: type, id, x, y, width, height, text, fontSize, fontFamily, containerId
- All arrows must have: type, id, x, y, width, height, points, strokeColor, endArrowhead, startBinding, endBinding
- Minimum fontSize: 16 for body text, 20 for titles
- Use strokeColor "#1e3a5f" for all shapes and arrows (dark blue)
- Element order: cameraUpdate, background, shapes with labels, then arrows with optional labels
"""


async def _generate_diagram(
    llm: Any,
    components: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    layout: str,
    description: str,
    cheat_sheet: str,
    invoke_config: RunnableConfig | None = None,
) -> list[dict[str, Any]]:
    """Generate the COMPLETE Excalidraw diagram in a single LLM call.

    The LLM receives the full intent and cheat sheet and produces all elements:
    camera, background, shapes, labels, arrows, and arrow labels.
    """
    # Build component descriptions
    comp_lines = []
    for i, c in enumerate(components):
        name = c.get("name", f"Component {i + 1}")
        shape = c.get("shape", "rectangle")
        color = c.get("color", "#a5d8ff")
        comp_lines.append(f'  {i + 1}. "{name}" — shape: {shape}, color: {color}')

    components_desc = "\n".join(comp_lines)

    # Build connection descriptions
    conn_section = ""
    if connections:
        conn_lines = []
        for c in connections:
            line = f'  - "{c.get("from", "?")}" → "{c.get("to", "?")}"'
            if c.get("label"):
                line += f' (label: "{c["label"]}")'
            conn_lines.append(line)
        conn_desc = "\n".join(conn_lines)
        conn_section = f"""
CONNECTIONS:
{conn_desc}
"""

    prompt = f"""Generate the COMPLETE Excalidraw diagram with all elements.

DIAGRAM DESCRIPTION: "{description}"
LAYOUT DIRECTION: {layout}

COMPONENTS:
{components_desc}
{conn_section}
INSTRUCTIONS:
1. Start with a cameraUpdate element (4:3 aspect ratio) that fits ALL content with padding
2. Add a background rectangle with backgroundColor "#f0f4ff", strokeColor "transparent", roundness type 3
3. For EACH component, generate:
   a. A shape element (rectangle/ellipse/diamond) with the specified color and strokeColor "#1e3a5f"
   b. A text label element with containerId pointing to the shape, fontSize 20, fontFamily 1
4. Arrange components in a clean "{layout}" layout with generous spacing (at least 100px gap between shapes)
5. Each shape should be approximately 200×80 pixels (adjust for long names)
6. Center text precisely inside each shape using the centering formula
7. For EACH connection, generate:
   a. An arrow element connecting the source shape to the target shape
      - Use startBinding and endBinding with the shape IDs
      - Arrows should exit from the appropriate edge based on the layout
      - Use points: [[0, 0], [dx, dy]] where dx/dy go from source edge to target edge
      - strokeColor "#1e3a5f", endArrowhead "arrow"
   b. If the connection has a label, add a text element at the arrow midpoint
      - fontSize 16, fontFamily 1, no containerId

Use unique IDs for each element (e.g., lowercase component name with underscores).

Output ONLY the JSON array with ALL elements (camera + background + shapes + labels + arrows)."""

    return await _call_llm_for_elements(llm, prompt, cheat_sheet, invoke_config)


async def _call_llm_for_elements(
    llm: Any,
    prompt: str,
    cheat_sheet: str,
    invoke_config: RunnableConfig | None = None,
) -> list[dict[str, Any]]:
    """Call the LLM and parse the response as a JSON element array."""
    from langchain_core.messages import HumanMessage, SystemMessage

    system_msg = _SYSTEM_PREFIX + "\n\n--- EXCALIDRAW CHEAT SHEET ---\n" + cheat_sheet
    messages = [SystemMessage(content=system_msg), HumanMessage(content=prompt)]

    try:
        import asyncio

        excalidraw_timeout = getattr(
            __import__("src.core.config", fromlist=["settings"]).settings,
            "mcp_excalidraw_step_timeout_seconds",
            60,
        )
        response = await asyncio.wait_for(
            llm.ainvoke(messages, config=invoke_config),
            timeout=excalidraw_timeout,
        )
        content = response.content if hasattr(response, "content") else str(response)

        # Extract JSON array from response (handle markdown code blocks)
        json_str = _extract_json_array(content)
        if json_str is None:
            logger.warning(
                "excalidraw_llm_no_json_array",
                response_preview=content[:200],
            )
            return []

        elements = json.loads(json_str)
        if not isinstance(elements, list):
            logger.warning("excalidraw_llm_not_array", type=type(elements).__name__)
            return []

        # Safety cap
        if len(elements) > _MAX_ELEMENTS_PER_CALL:
            elements = elements[:_MAX_ELEMENTS_PER_CALL]

        return elements

    except Exception as exc:
        logger.error(
            "excalidraw_llm_call_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return []


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _extract_json_array(text: str) -> str | None:
    """Extract a JSON array from LLM response text.

    Handles responses wrapped in markdown code blocks or with extra text.
    Correctly skips brackets inside JSON string literals.
    """
    text = text.strip()

    # Strip markdown code blocks
    if text.startswith("```"):
        # Remove opening ```json or ```
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    # Find the JSON array
    start = text.find("[")
    if start == -1:
        return None

    # Find matching closing bracket, skipping brackets inside strings
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None
