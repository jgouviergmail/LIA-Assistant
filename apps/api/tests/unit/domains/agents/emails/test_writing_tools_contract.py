"""Every writing tool tells the model who writes its words, the same way in both modes.

The ReAct loop binds the tool's SCHEMA, the planner reads its MANIFEST: one sentence
per field, from one constant, or a mode that reads the other's contract writes the
e-mail itself (measured 2026-11-15: 14 of 18 requests of intent on the schema of the
time, ADR-383 amendment).
"""

from __future__ import annotations

import pytest
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.domains.agents.emails.authorship import WRITING_TOOLS
from src.domains.agents.emails.catalogue_manifests import (
    DICTATED_WORDS,
    reply_email_catalogue_manifest,
    send_email_catalogue_manifest,
)
from src.domains.agents.emails.mailbox_drafts_manifests import (
    create_mailbox_draft_catalogue_manifest,
    create_mailbox_reply_draft_catalogue_manifest,
    update_mailbox_draft_catalogue_manifest,
)
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.tools.emails_tools import reply_email_tool, send_email_tool
from src.domains.agents.tools.mailbox_draft_edit_tools import update_mailbox_draft_tool
from src.domains.agents.tools.mailbox_drafts_tools import (
    create_mailbox_draft_tool,
    create_mailbox_reply_draft_tool,
)

pytestmark = pytest.mark.unit


def _structured(tool: object) -> StructuredTool:
    """A writing tool as what it is once decorated: its decorator types it as its function."""
    assert isinstance(tool, StructuredTool)
    return tool


#: Each writing tool, as the loop binds it and as the planner reads it.
SURFACES: dict[str, tuple[StructuredTool, ToolManifest]] = {
    "send_email_tool": (_structured(send_email_tool), send_email_catalogue_manifest),
    "reply_email_tool": (_structured(reply_email_tool), reply_email_catalogue_manifest),
    "create_mailbox_draft_tool": (
        _structured(create_mailbox_draft_tool),
        create_mailbox_draft_catalogue_manifest,
    ),
    "create_mailbox_reply_draft_tool": (
        _structured(create_mailbox_reply_draft_tool),
        create_mailbox_reply_draft_catalogue_manifest,
    ),
    "update_mailbox_draft_tool": (
        _structured(update_mailbox_draft_tool),
        update_mailbox_draft_catalogue_manifest,
    ),
}
#: The fields that say who writes the words.
WHO_WRITES = ("body", "content_instruction", "instructions")


def _bound(tool: StructuredTool) -> dict[str, str]:
    properties = convert_to_openai_tool(tool)["function"]["parameters"]["properties"]
    return {name: str(spec.get("description")) for name, spec in properties.items()}


def _published(manifest: ToolManifest) -> dict[str, str]:
    return {parameter.name: parameter.description for parameter in manifest.parameters}


def test_every_writing_tool_is_held_here() -> None:
    assert set(SURFACES) == WRITING_TOOLS


@pytest.mark.parametrize("name", sorted(WRITING_TOOLS))
def test_both_modes_read_the_same_sentence(name: str) -> None:
    tool, manifest = SURFACES[name]
    bound, published = _bound(tool), _published(manifest)

    for field in WHO_WRITES:
        if field in published:
            assert bound[field] == published[field], field


@pytest.mark.parametrize("name", sorted(WRITING_TOOLS))
def test_the_text_field_says_only_dictated_words_go_in_it(name: str) -> None:
    tool, _manifest = SURFACES[name]

    assert DICTATED_WORDS in _bound(tool)["body"]


@pytest.mark.parametrize("name", sorted(WRITING_TOOLS))
def test_the_bound_description_names_who_writes(name: str) -> None:
    """The loop reads the tool's description (its docstring) beside its fields."""
    tool, _manifest = SURFACES[name]

    assert DICTATED_WORDS in tool.description
