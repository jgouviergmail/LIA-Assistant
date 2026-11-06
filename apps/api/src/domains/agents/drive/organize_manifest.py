"""Catalogue manifest of the file-organising tool (ADR-369, lot 6, owner decision D2).

Beside ``catalogue_manifests.py``. What the clients gained for the « Tools » section reaches
the assistant in the same lot: each wording is ONE constant the planner's manifest and the
ReAct tool schema read (ADR-310). Every act is undone by one more call, so none asks first.
"""

from typing import Final

from src.core.constants import GOOGLE_DRIVE_SCOPES, ONEDRIVE_REFUSED_NAME_CHARACTERS
from src.domains.agents.registry.catalogue import (
    REASON_UNDONE_BY_ONE_CALL,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

#: What a drive can be asked to do.
FILE_ACTIONS: Final = ("create_folder", "upload", "rename", "move", "copy", "restore")

FILE_ACTION_DESCRIPTION: Final = (
    "create_folder (needs `name`); upload (needs `file_name`); rename (needs `file_id` and "
    "`name`); move (needs `file_id`); copy (needs `file_id`, a file: a folder is not copied); "
    "restore (needs `file_id`: takes it out of the trash)."
)
FILE_ID_DESCRIPTION: Final = "The file or folder's id (from get_files_tool or CONTEXT)."
FILE_FOLDER_DESCRIPTION: Final = (
    "The folder's id. For create_folder its parent, for upload, move and copy where it goes. "
    "Omitted: the top of the drive, or beside the original for a copy."
)
FILE_NAME_DESCRIPTION: Final = (
    "For create_folder and rename: the name, never a path. For copy and upload: the item's name "
    "on the drive, needed on OneDrive when the folder holds that name. "
    f"OneDrive refuses these characters in a name: {ONEDRIVE_REFUSED_NAME_CHARACTERS}"
)

FILE_SOURCE_DESCRIPTION: Final = (
    "For upload: the exact name of a file the person attached to the conversation or LIA "
    "generated (find_generated_files_tool gives it as `file_name`)."
)

manage_files_catalogue_manifest = ToolManifest(
    name="manage_files_tool",
    agent="file_agent",
    description=(
        "**Tool: manage_files_tool** - Organise the person's files (Google Drive or OneDrive): "
        "create a folder, send a file there, rename an item, move it to a folder, copy it. Asks "
        "no confirmation.\n"
        "- 'create a folder Invoices', 'rename this file', 'move the report to Archive', "
        "'put this PDF in my drive'\n"
        "- The ids come from get_files_tool or CONTEXT; a search is never done here\n"
        "- To put a file in the trash, use delete_file_tool; `restore` takes it back. Nothing "
        "here deletes for good: the person does that by hand\n"
        "**RETURNS**: `action`, `item` the item as it is now, or `copying` when the provider "
        "finishes the copy later."
    ),
    tool_category="update",
    mutation_policy="reversible",
    mutation_policy_reason=REASON_UNDONE_BY_ONE_CALL,
    semantic_keywords=[
        "create a new folder in my drive",
        "rename this file",
        "move this file to another folder",
        "copy this document to a folder",
        "organise my files into folders",
        "save this attachment to my drive",
        "put the generated report in my drive",
    ],
    parameters=[
        ParameterSchema(
            name="action",
            type="string",
            required=True,
            description=FILE_ACTION_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(FILE_ACTIONS))],
        ),
        ParameterSchema(
            name="file_id",
            type="string",
            required=False,
            description=FILE_ID_DESCRIPTION,
            semantic_type="file_id",
        ),
        ParameterSchema(
            name="folder_id",
            type="string",
            required=False,
            description=FILE_FOLDER_DESCRIPTION,
            semantic_type="file_id",
        ),
        ParameterSchema(
            name="name", type="string", required=False, description=FILE_NAME_DESCRIPTION
        ),
        ParameterSchema(
            name="file_name", type="string", required=False, description=FILE_SOURCE_DESCRIPTION
        ),
    ],
    outputs=[
        OutputFieldSchema(path="action", type="string", description="The act done"),
        OutputFieldSchema(path="item", type="object", description="The item as it is now"),
        OutputFieldSchema(path="copying", type="boolean", description="Finished by the provider"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=50, est_cost_usd=0.0, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_DRIVE_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    reference_examples=["action", "item"],
    display=DisplayMetadata(emoji="🗂️", i18n_key="manage_files", visible=True, category="tool"),
    version="1.0.0",
    maintainer="Team Agents",
)

__all__ = [
    "FILE_ACTIONS",
    "FILE_ACTION_DESCRIPTION",
    "FILE_FOLDER_DESCRIPTION",
    "FILE_ID_DESCRIPTION",
    "FILE_NAME_DESCRIPTION",
    "FILE_SOURCE_DESCRIPTION",
    "manage_files_catalogue_manifest",
]
