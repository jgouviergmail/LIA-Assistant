"""Importing an export attached in the chat: an exact, confirmed proposal (R5).

The settings could import a memories export (wave 2, lot 24); the assistant could not. Its proposal
names the attached file and the exact counts of what it holds, renders the file's name literally,
never lets an edit retarget another file, and changes the « memories » resource once committed.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.memory_import import import_draft
from src.domains.agents.application.memory_import_manifest import MEMORY_IMPORT_MANIFEST
from src.domains.agents.application.memory_import_schemas import (
    MemoryImportInput,
    MemoryImportSnapshot,
    canonical_memory_import,
)
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_memory_tools import import_lia_memories_tool

pytestmark = pytest.mark.unit


def _snapshot(name: str = "memories.csv") -> MemoryImportSnapshot:
    return MemoryImportSnapshot(
        request=MemoryImportInput(file_name=name),
        attachment_id=uuid4(),
        file_name=name,
        total=12,
        new=9,
        already_present=2,
        duplicates=1,
        invalid=0,
        file_digest="d" * 64,
    )


@pytest.mark.parametrize(
    "extra",
    [{"attachment_id": str(uuid4())}, {"content": "x"}, {"user_id": str(uuid4())}, {"path": "x"}],
)
def test_the_request_names_a_file_and_never_an_id(extra: dict[str, object]) -> None:
    """The model never copies an id: the server finds the file in this discussion."""
    with pytest.raises(ValidationError):
        MemoryImportInput.model_validate({"file_name": "memories.csv", **extra})


@pytest.mark.parametrize("name", ["", "x" * 256])
def test_a_file_name_is_a_name(name: str) -> None:
    with pytest.raises(ValidationError):
        MemoryImportInput(file_name=name)


def test_no_name_means_the_latest_export_of_the_discussion() -> None:
    assert MemoryImportInput().file_name is None


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_the_proposal_is_literal_canonical_and_hides_its_witness(language: str) -> None:
    draft = import_draft(uuid4(), _snapshot("<script>literal</script>.csv"))

    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_memory_import(draft)
    labels = get_draft_preview_labels(language)
    assert labels["application_memory_import_note"]
    assert labels["application_field_memories_import"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Same file"))
    assert "d" * 64 not in prompt and "d" * 64 not in html
    sealed = str(draft.intent["memories_import"]["attachment_id"])
    assert sealed not in html, "the card names the file, never its id"
    assert changed_resources(draft) == ["memories"]


def test_a_draft_that_says_another_after_is_not_canonical() -> None:
    draft = import_draft(uuid4(), _snapshot())
    tampered = draft.model_copy(update={"after": {"memories_import": {"memories_to_create": 99}}})

    assert not canonical_memory_import(tampered)


def test_the_model_reads_the_request_schema_it_is_held_to() -> None:
    assert MEMORY_IMPORT_MANIFEST.parameters[0].schema == MemoryImportInput.model_json_schema()
    assert MEMORY_IMPORT_MANIFEST.mutation_policy == "draft"
    schema = import_lia_memories_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"request"}
