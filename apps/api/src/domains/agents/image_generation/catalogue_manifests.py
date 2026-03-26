"""Catalogue manifests for Image Generation tools.

Defines the ToolManifest for the generate_image tool,
used by the SmartCatalogueService for domain detection and tool selection.

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

from src.domains.agents.constants import AGENT_IMAGE
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# AGENT MANIFEST
# ============================================================================

image_agent_manifest = AgentManifest(
    name=AGENT_IMAGE,
    description="Agent for AI image generation and editing from text descriptions.",
    tools=["generate_image", "edit_image"],
    max_parallel_runs=1,
    default_timeout_ms=120000,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
)

# ============================================================================
# GENERATE IMAGE TOOL
# ============================================================================
_desc = (
    "**Tool: generate_image** - Generate an image from a text description using AI.\n"
    "The generated image is displayed as a card below the assistant response.\n"
    "**Use for**: 'Create an image of...', 'Generate a picture of...', "
    "'Draw me a...', 'Make an illustration of...', 'Design a logo for...'.\n"
    "**IMPORTANT**: This tool generates images using AI and has a cost per image. "
    "Use only when user explicitly requests image creation.\n"
    "**Output**: Generated image displayed as a card below the response."
)

generate_image_catalogue_manifest = ToolManifest(
    name="generate_image",
    agent=AGENT_IMAGE,
    description=_desc,
    semantic_keywords=[
        "create an image from text description",
        "generate a picture or illustration",
        "draw or paint something for me",
        "make a visual representation",
        "AI art generation from prompt",
        "create a logo or design",
    ],
    parameters=[
        ParameterSchema(
            name="prompt",
            type="string",
            required=True,
            description=(
                "Detailed text description of the image to generate. "
                "Be specific about style, content, colors, and composition. "
                "Quality and size are controlled by the user's preferences."
            ),
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message",
            type="string",
            description="Confirmation message with prompt summary",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=0,
        est_tokens_out=0,
        est_cost_usd=0.042,  # medium quality 1024x1024
        est_latency_ms=90000,  # high quality can take 60-90s on OpenAI API
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    tool_category="create",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="\U0001f3a8",
        i18n_key="generate_image",
        visible=True,
        category="tool",
    ),
)

# ============================================================================
# EDIT IMAGE TOOL
# ============================================================================
_edit_desc = (
    "**Tool: edit_image** - Edit an existing image based on a text description.\n"
    "Takes an existing image (generated or uploaded attachment) and modifies it.\n"
    "**Use for**: 'Modify this image to...', 'Change the background of this image', "
    "'Add a hat to the cat in this image', 'Make this photo look like a painting'.\n"
    "**IMPORTANT**: Requires a source_attachment_id referencing an existing image.\n"
    "**Output**: Edited image displayed as a card below the response."
)

edit_image_catalogue_manifest = ToolManifest(
    name="edit_image",
    agent=AGENT_IMAGE,
    description=_edit_desc,
    semantic_keywords=[
        "modify or change an existing image",
        "edit a photo or picture",
        "transform or alter an image",
        "add or remove elements from an image",
        "change the style of an image",
        "make an image look different",
    ],
    parameters=[
        ParameterSchema(
            name="prompt",
            type="string",
            required=True,
            description=(
                "Detailed text description of the desired modification. "
                "Be specific about what to change, add, or remove."
            ),
        ),
        ParameterSchema(
            name="source_attachment_id",
            type="string",
            required=False,
            description=(
                "Optional UUID of a specific image to edit. "
                "If omitted, the most recent image (generated or uploaded) is used."
            ),
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message",
            type="string",
            description="Confirmation message",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=0,
        est_tokens_out=0,
        est_cost_usd=0.042,
        est_latency_ms=90000,  # high quality can take 60-90s on OpenAI API
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    tool_category="create",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="\u270f\ufe0f",  # pencil
        i18n_key="edit_image",
        visible=True,
        category="tool",
    ),
)
