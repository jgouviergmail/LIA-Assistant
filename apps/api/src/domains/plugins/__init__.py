"""Agent Plugins domain (agent-plugins.org standard v1.0.0, ADR-225).

LIA is a conformant Agent Plugins client under the incremental-adoption
profile (§11.2): skills + streamable-http MCP servers. This bounded context
owns plugin package validation, the import pipeline and the installed-plugin
lifecycle; skills and MCP servers materialized from a plugin are then handled
by their own domains (``domains/skills``, ``domains/user_mcp``) exactly like
their manually-created counterparts.
"""
