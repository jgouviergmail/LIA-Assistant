"""Catalogue manifests for DevOps tools (Claude CLI remote server management)."""

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

claude_server_task_catalogue_manifest = ToolManifest(
    name="claude_server_task_tool",
    agent="devops_agent",
    description=(
        "**Tool: claude_server_task_tool** - Execute a task on a remote server using"
        " Claude Code CLI.\n"
        "Claude will independently inspect, diagnose, and report on the server.\n"
        "**Use for**: Log inspection, Docker container management, system health checks, "
        "deployment status, error diagnosis, service restart.\n"
        "**IMPORTANT**: This tool must be called EVERY TIME the user asks about server state. "
        "Results are NOT cached — server state changes constantly. Always invoke for fresh data.\n"
        "**Output**: Claude CLI's analysis and findings, with session ID for follow-up."
    ),
    parameters=[
        ParameterSchema(
            name="task",
            type="string",
            required=True,
            description=(
                "Natural language description of the task to perform on the server. "
                "Be specific: 'Check the last 100 lines of lia-api-prod logs for errors' "
                "is better than 'check logs'."
            ),
        ),
        ParameterSchema(
            name="server",
            type="string",
            required=False,
            description="Target server name. Leave empty to use the default (first configured) server.",
        ),
        ParameterSchema(
            name="context",
            type="string",
            required=False,
            description=(
                "Additional context or constraints for Claude CLI "
                "(e.g. 'focus on 500 errors since 14:00')."
            ),
        ),
        ParameterSchema(
            name="resume_session",
            type="string",
            required=False,
            description=(
                "Previous Claude CLI session ID to resume an investigation. "
                "Use when the user wants to continue a previous analysis."
            ),
        ),
    ],
    outputs=[
        OutputFieldSchema(path="result", type="string", description="Claude CLI analysis output"),
        OutputFieldSchema(path="server", type="string", description="Server name used"),
        OutputFieldSchema(
            path="session_id",
            type="string",
            description="Claude session ID for follow-up",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=500,
        est_tokens_out=2000,
        est_cost_usd=0.0,  # Uses Claude Max/Pro subscription, no API cost
        est_latency_ms=30000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        allowed_roles=[],  # Access controlled by DEVOPS_ENABLED feature flag (admin-only env)
        hitl_required=False,
        data_classification="RESTRICTED",
    ),
    semantic_keywords=[
        "check server logs",
        "inspect docker containers",
        "restart service",
        "server health check",
        "diagnose production issue",
        "check deployment status",
        "analyze error logs",
        "server monitoring",
        "container status",
        "system disk space memory",
        "check server uptime",
        "relancer le container",
        "vérifier les logs",
        "état du serveur",
        "problème en production",
        "diagnostiquer une erreur",
        "inspecter le serveur",
        "redémarrer le service",
    ],
    tool_category="readonly",
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="🖥️",
        i18n_key="claude_server_task",
        visible=True,
        category="tool",
    ),
)
