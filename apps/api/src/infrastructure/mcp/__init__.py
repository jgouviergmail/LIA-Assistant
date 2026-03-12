"""
MCP (Model Context Protocol) Infrastructure Package.

Provides integration with external MCP tool servers:
- schemas: Data models (MCPServerConfig, MCPDiscoveredTool, MCPServerStatus)
- security: Server validation, SSRF prevention, HITL resolution
- tool_adapter: MCPToolAdapter (MCP → LangChain BaseTool wrapper)
- client_manager: MCPClientManager (lifecycle, connections, health)
- registration: Bridge between MCP discovery and AgentRegistry + tool_registry

Phase: evolution F2 — MCP Support
Created: 2026-02-28
Reference: docs/technical/MCP_INTEGRATION.md
"""

from src.infrastructure.mcp.schemas import (
    MCPDiscoveredTool,
    MCPServerConfig,
    MCPServerStatus,
    MCPTransportType,
)

__all__ = [
    "MCPDiscoveredTool",
    "MCPServerConfig",
    "MCPServerStatus",
    "MCPTransportType",
]
