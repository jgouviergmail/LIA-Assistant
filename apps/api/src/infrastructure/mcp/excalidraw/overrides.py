"""
Excalidraw overrides -- Constants for the Excalidraw MCP server.

With ADR-062 (iterative_mode), the Excalidraw server delegates to a ReAct
sub-agent that follows the native MCP workflow: read_me first, then
create_view with correct elements. The SPATIAL_SUFFIX and iterative_builder
are no longer needed.

Phase: evolution F2 -- Admin MCP Excalidraw
Created: 2026-03-07
Updated: 2026-03-24 -- ADR-062: Replaced intent builder with ReAct sub-agent
"""

from src.core.constants import MCP_REFERENCE_TOOL_NAME

EXCALIDRAW_SERVER_NAME = "excalidraw"
EXCALIDRAW_CREATE_VIEW_TOOL = "create_view"
EXCALIDRAW_READ_ME_TOOL = MCP_REFERENCE_TOOL_NAME
# Normalized tool name used by the planner (mcp_{server}_{tool})
EXCALIDRAW_CREATE_VIEW_NORMALIZED = f"mcp_{EXCALIDRAW_SERVER_NAME}_{EXCALIDRAW_CREATE_VIEW_TOOL}"
