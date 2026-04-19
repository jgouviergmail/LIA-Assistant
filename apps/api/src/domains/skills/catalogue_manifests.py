"""Catalogue manifests for Skills tools (agentskills.io standard)."""

from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# ACTIVATE SKILL TOOL — Load skill instructions (L2 activation)
# ============================================================================

activate_skill_catalogue_manifest = ToolManifest(
    name="activate_skill_tool",
    agent="query_agent",
    description=(
        "**Tool: activate_skill_tool** - Load a skill's full instructions.\n"
        "**Use for**: Loading specialized instructions from available_skills catalogue.\n"
        "**Output**: Skill instructions wrapped in structured tags."
    ),
    semantic_keywords=[
        "skill",
        "activate",
        "instructions",
        "specialized",
        "expert",
    ],
    parameters=[
        ParameterSchema(
            name="name",
            type="string",
            required=True,
            description="Name of the skill to activate (from available_skills catalogue)",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message",
            type="string",
            description="Skill instructions with structured wrapping",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=50,
        est_tokens_out=2000,
        est_cost_usd=0.0,
        est_latency_ms=10,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="INTERNAL",
    ),
    version="1.0.0",
)

# ============================================================================
# RUN SKILL SCRIPT TOOL — Execute Python scripts from skills
# ============================================================================

# ============================================================================
# READ SKILL RESOURCE TOOL — L3 on-demand resource loading
# ============================================================================

read_skill_resource_catalogue_manifest = ToolManifest(
    name="read_skill_resource",
    agent="query_agent",
    description=(
        "**Tool: read_skill_resource** - Read a bundled resource from a skill.\n"
        "**Use for**: Loading templates, examples, references, or assets "
        "listed in <skill_resources> after activating a skill.\n"
        "**Output**: File content as text."
    ),
    semantic_keywords=[
        "skill",
        "resource",
        "read",
        "template",
        "reference",
        "example",
    ],
    parameters=[
        ParameterSchema(
            name="skill_name",
            type="string",
            required=True,
            description="Name of the skill containing the resource",
        ),
        ParameterSchema(
            name="path",
            type="string",
            required=True,
            description="Relative path to the resource (e.g., 'template.md')",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message",
            type="string",
            description="File content as text",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=50,
        est_tokens_out=2000,
        est_cost_usd=0.0,
        est_latency_ms=10,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="INTERNAL",
    ),
    version="1.0.0",
)

run_skill_script_catalogue_manifest = ToolManifest(
    name="run_skill_script",
    agent="query_agent",
    description=(
        "**Tool: run_skill_script** - Execute a Python script from a skill.\n"
        "**Use for**: Running scripts in a skill's scripts/ directory.\n"
        "**Output**: Textual message always present. When the script emits the\n"
        "``SkillScriptOutput`` JSON contract on stdout with a ``frame`` or\n"
        "``image`` field, a ``SKILL_APP`` registry item is also produced and\n"
        "the widget renders as an interactive frame/image card in the chat.\n"
        "Runtime auto-injects ``_lang`` (user language) and ``_tz`` (user\n"
        "timezone) into ``parameters`` — scripts should read those for\n"
        "localization rather than calling ``strftime``/``setlocale``."
    ),
    semantic_keywords=[
        "skill",
        "script",
        "execute",
        "run",
        "python",
    ],
    parameters=[
        ParameterSchema(
            name="skill_name",
            type="string",
            required=True,
            description="Name of the skill containing the script",
        ),
        ParameterSchema(
            name="script",
            type="string",
            required=True,
            description="Script filename (e.g., 'extract.py')",
        ),
        ParameterSchema(
            name="parameters",
            type="object",
            required=False,
            description=(
                "Parameters passed to the script via stdin JSON. Accepts either a "
                "JSON object (preferred) or a JSON string — both are normalized."
            ),
        ),
    ],
    outputs=[
        # Always emitted: textual message (used by the LLM reformulator).
        OutputFieldSchema(
            path="message",
            type="string",
            description="Text response (always present — from SkillScriptOutput.text)",
        ),
        # Rich outputs (v1.16.8, ADR-075): emitted only when the script returns
        # a SkillScriptOutput JSON with frame or image. The SKILL_APP registry
        # item is rendered as an interactive widget (iframe + optional image).
        OutputFieldSchema(
            path="skill_apps[].skill_name",
            type="string",
            description="Emitting skill name (only when frame/image is produced)",
            nullable=True,
        ),
        OutputFieldSchema(
            path="skill_apps[]._registry_id",
            type="string",
            description=(
                "Registry identifier of the SKILL_APP widget — chainable via "
                "$steps.<step_id>.skill_apps[]._registry_id"
            ),
            nullable=True,
        ),
        OutputFieldSchema(
            path="skill_apps[].title",
            type="string",
            description="Display title (frame header / image alt fallback)",
            nullable=True,
        ),
    ],
    cost=CostProfile(
        est_tokens_in=50,
        est_tokens_out=500,
        est_cost_usd=0.0,
        est_latency_ms=5000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="INTERNAL",
    ),
    version="1.1.0",
)
