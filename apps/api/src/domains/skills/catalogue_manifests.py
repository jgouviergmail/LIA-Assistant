"""Catalogue manifests for Skills tools (agentskills.io standard).

The five tools are ONE affordance — a skill is activated, its script or its
commands run, its resources read, a library imported — so every manifest
declares the same ``binding_unit`` and the ReAct selector binds them whole or
not at all.
"""

from src.core.config import settings
from src.core.constants import SKILL_COMMAND_MAX_CHARS
from src.domains.agents.registry.catalogue import (
    REASON_INTERNAL_CONTEXT,
    REASON_SANDBOXED_CONTAINER,
    CostProfile,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.skills.command_bundle import COMMAND_DESCRIPTION, HOSTS_DESCRIPTION
from src.domains.skills.trust import ACTIVATION_REQUEST_DESCRIPTION

#: The binding unit every skills tool declares (read by the ReAct selector).
SKILLS_BINDING_UNIT = "skills"

# ============================================================================
# ACTIVATE SKILL TOOL — Load skill instructions (L2 activation)
# ============================================================================

activate_skill_catalogue_manifest = ToolManifest(
    name="activate_skill_tool",
    mutation_policy="reversible",
    mutation_policy_reason=REASON_INTERNAL_CONTEXT,
    # ADR-256: loads instructions into the turn. It mutates no user data, but
    # the read-only initiative phase must never activate a skill on its own.
    tool_category="system",
    agent="query_agent",
    binding_unit=SKILLS_BINDING_UNIT,
    description=(
        "**Tool: activate_skill_tool** - Load a skill's full instructions.\n"
        "**Use for**: Loading specialized instructions from available_skills catalogue.\n"
        "**Output**: Skill instructions wrapped in structured tags. A skill marked "
        "third-party runs on its own instead and returns its answer as external content."
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
        ParameterSchema(
            name="request",
            type="string",
            required=False,
            description=ACTIVATION_REQUEST_DESCRIPTION,
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
    mutation_policy="read",
    # ADR-256: reads a bundled resource.
    tool_category="readonly",
    agent="query_agent",
    binding_unit=SKILLS_BINDING_UNIT,
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

import_user_skill_catalogue_manifest = ToolManifest(
    name="import_user_skill",
    # The card under the answer IS the confirmation (ADR-327): the tool only
    # proposes, the person's click installs. Owner arbitration 2026-09-30.
    mutation_policy="draft",
    agent="query_agent",
    binding_unit=SKILLS_BINDING_UNIT,
    description=(
        "**Tool: import_user_skill** - Propose a finished skill to the user: it is "
        "validated and shown as a card with an Install button under your answer.\n"
        "**Use for**: Delivering a skill produced by the skill-generator (a new one, "
        "or the complete regenerated package of one of the user's own skills).\n"
        "**Output**: The proposed skill's name. NOTHING is installed until the user "
        "clicks Install on the card."
    ),
    semantic_keywords=[
        "skill",
        "import",
        "install",
        "generate",
        "create",
        "publish",
    ],
    parameters=[
        ParameterSchema(
            name="files",
            type="object",
            required=True,
            description=(
                "Map of relative path → text content. Must include a top-level "
                "'SKILL.md'; resources go under scripts/ or references/."
            ),
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message",
            type="string",
            description="What was proposed, and that the user installs it from the card",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=50,
        est_tokens_out=50,
        est_cost_usd=0.0,
        est_latency_ms=200,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="INTERNAL",
    ),
    # Declared explicitly: this leads to a WRITE — the card installs a skill in
    # the user's own skills. Without a declaration the category is inferred from
    # the name, which defaults unknown shapes to "readonly" and would make it
    # eligible for proactive execution while hiding it from the
    # invalid-mutation-plan safety net.
    tool_category="create",
    version="1.0.0",
)

run_skill_script_catalogue_manifest = ToolManifest(
    name="run_skill_script",
    mutation_policy="sandboxed",
    mutation_policy_reason=REASON_SANDBOXED_CONTAINER,
    agent="query_agent",
    binding_unit=SKILLS_BINDING_UNIT,
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
        #
        # The CONTAINER is declared before its members: `structured_data` groups
        # the payload under `skill_apps` as a LIST (see skills/output_builder),
        # and a planner told only about `skill_apps[].title` cannot know the
        # collection exists — the same gap that made other manifests advertise
        # unreachable paths (ADR-194).
        OutputFieldSchema(
            path="skill_apps",
            type="array",
            description="Interactive widgets produced by the script (empty when it only returns text)",
        ),
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
    # Declared explicitly: this EXECUTES a Python script from the skill's
    # scripts/ directory — arbitrary side effects. Name inference defaulted it
    # to "readonly", which is the most dangerous possible misclassification for
    # a tool the initiative node may run without the user asking.
    tool_category="update",
    version="1.1.0",
)


# ============================================================================
# RUN SKILL COMMAND TOOL: a skill's own shell commands — offline, or on the hosts it declares (ADR-327 lots 2-3)
# ============================================================================

run_skill_command_catalogue_manifest = ToolManifest(
    name="run_skill_command",
    mutation_policy="sandboxed",
    mutation_policy_reason=REASON_SANDBOXED_CONTAINER,
    agent="query_agent",
    binding_unit=SKILLS_BINDING_UNIT,
    description=(
        "**Tool: run_skill_command** - Run a shell command that a skill's instructions "
        "give (`python scripts/...`, `node ...`, `bash ...`), with bash in a copy of the "
        "skill's folder — offline, unless it declares the hosts it reaches.\n"
        "**Use for**: skills whose instructions say to run a command or a non-Python script.\n"
        "**Files**: the user's files attached to this turn are in ../input/; every file "
        "written under out/ is handed to the user as a card under the answer.\n"
        "**Output**: the exit code, standard output and standard error, and the files "
        "handed back."
    ),
    semantic_keywords=["skill", "command", "shell", "bash", "node", "convert", "run"],
    parameters=[
        ParameterSchema(
            name="skill_name",
            type="string",
            required=True,
            description="Name of the skill whose folder the command runs in",
        ),
        ParameterSchema(
            name="command",
            type="string",
            required=True,
            description=COMMAND_DESCRIPTION,
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=SKILL_COMMAND_MAX_CHARS),
            ],
        ),
        ParameterSchema(
            name="hosts",
            type="array",
            required=False,
            description=HOSTS_DESCRIPTION,
            # ADR-184: the bound the tool enforces is the bound the model reads.
            constraints=[
                ParameterConstraint(
                    kind="max_length", value=settings.python_sandbox_max_hosts_per_run
                )
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message",
            type="string",
            description="Exit code, standard output and error, and the files handed back",
        ),
        OutputFieldSchema(
            path="exit_code",
            type="integer",
            description="The command's exit status (null when unreadable)",
            nullable=True,
        ),
        OutputFieldSchema(
            path="files",
            type="array",
            description="Names of the files handed to the user",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=80,
        est_tokens_out=600,
        est_cost_usd=0.0,
        est_latency_ms=10000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="INTERNAL",
    ),
    # It EXECUTES code a skill ships: declared, never inferred from the name.
    tool_category="update",
    version="1.0.0",
)
