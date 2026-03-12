"""
Excalidraw overrides -- Constants and guidelines for the builder.

The LLM planner receives the full read_me from the Excalidraw MCP server.
When calling ``create_view``, it generates a structured INTENT describing the
diagram (components, connections, layout direction).  The builder in
``iterative_builder.py`` intercepts this intent and makes a single LLM call
to produce the complete set of Excalidraw elements.

Phase: evolution F2 -- Admin MCP Excalidraw
Created: 2026-03-07
"""

from src.core.constants import MCP_REFERENCE_TOOL_NAME

EXCALIDRAW_SERVER_NAME = "excalidraw"
EXCALIDRAW_CREATE_VIEW_TOOL = "create_view"
EXCALIDRAW_READ_ME_TOOL = MCP_REFERENCE_TOOL_NAME
# Normalized tool name used by the planner (mcp_{server}_{tool})
EXCALIDRAW_CREATE_VIEW_NORMALIZED = f"mcp_{EXCALIDRAW_SERVER_NAME}_{EXCALIDRAW_CREATE_VIEW_TOOL}"

# ---------------------------------------------------------------------------
# SPATIAL_SUFFIX: Appended to the create_view tool description in the catalogue.
# Instructs the planner LLM to generate a structured intent JSON instead of
# raw Excalidraw elements.  The builder uses this intent to drive a single
# dedicated LLM call that produces the complete diagram.
# ---------------------------------------------------------------------------
EXCALIDRAW_SPATIAL_SUFFIX = """

IMPORTANT — Iterative Rendering Mode:
Instead of generating raw Excalidraw elements directly, pass a JSON INTENT object
as the ``elements`` parameter. The rendering engine will use this intent to build
the diagram iteratively, one component at a time, for optimal layout quality.

Intent JSON format:
{
  "intent": true,
  "description": "Brief description of the diagram",
  "components": [
    {"name": "Component A", "shape": "rectangle", "color": "#a5d8ff"},
    {"name": "Component B", "shape": "ellipse", "color": "#b2f2bb"},
    {"name": "Component C", "shape": "diamond", "color": "#ffec99"}
  ],
  "connections": [
    {"from": "Component A", "to": "Component B", "label": "sends data"},
    {"from": "Component B", "to": "Component C"}
  ],
  "layout": "top-to-bottom"
}

RULES:
- "intent": true  (MANDATORY marker — the engine detects this to activate iterative mode)
- "description": short text describing the diagram purpose
- "components": list of nodes. Each has:
  - "name": display label (1-4 words)
  - "shape": "rectangle" | "ellipse" | "diamond"
  - "color": pastel hex — pick from: #a5d8ff (blue), #ffc9c9 (red), #b2f2bb (green),
    #ffec99 (yellow), #d0bfff (purple), #ffd8a8 (orange), #e9ecef (gray)
- "connections": list of directed edges.
  - "from"/"to": must match a component name exactly
  - "label": optional short text on the arrow
- "layout": "top-to-bottom" | "left-to-right" (flow direction)
- Order components logically: inputs first, processing middle, outputs last
- Keep it focused: 3-10 components for best results
- ALWAYS call read_me BEFORE create_view to learn the element format"""
