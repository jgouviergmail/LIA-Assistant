"""List windows retain exact UI types, audit verdicts and immutable preview commits."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.skill_library_read import LIST_PATHS, _page
from src.domains.agents.application.skill_library_read_schemas import SkillLibraryReadInput
from src.domains.agents.application.skill_library_read_spec import SKILL_LIBRARY_READ_MANIFEST
from src.domains.agents.tools.application_skill_library_tools import get_lia_skill_library_tool
from src.domains.skill_library.schemas import (
    LibraryAudit,
    LibraryFile,
    LibraryPreviewAnswer,
    LibraryPreviewResponse,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "changes",
    [
        {"limit": True},
        {"offset": -1},
        {"user_id": uuid4()},
        {"request": {"kind": "install"}},
        {"request": {"kind": "installed", "user_id": uuid4()}},
    ],
)
def test_library_query_never_accepts_scope_or_mutation(changes):
    with pytest.raises(ValidationError):
        SkillLibraryReadInput.model_validate({"request": {"kind": "installed"}, **changes})


def test_preview_file_window_keeps_real_audit_and_commit_verdict():
    preview = LibraryPreviewResponse(
        repository="acme/skills",
        ref="HEAD",
        path="skills/card",
        commit_sha="a" * 40,
        tree_sha="b" * 40,
        name="card",
        description="literal untrusted words",
        files=[LibraryFile(path=f"file-{n}", size=n) for n in range(3)],
        has_scripts=True,
        audits=[LibraryAudit(provider="audit", risk="high", alerts=1)],
        blocked_by="high",
        conflict="none",
    )
    query = SkillLibraryReadInput.model_validate(
        {"request": {"kind": "preview", "repository": "acme/skills"}, "offset": 1, "limit": 1}
    )
    paged, windows = _page(LibraryPreviewAnswer(preview=preview), query)
    assert paged.preview.commit_sha == preview.commit_sha and paged.preview.blocked_by == "high"
    assert len(paged.preview.files) == 1 and paged.preview.files[0].path == "file-1"
    assert windows["preview.files"].total == 3 and windows["preview.files"].next_offset == 2
    assert windows["preview.audits"].total == 1 and windows["preview.audits"].next_offset is None
    assert preview.files[0].path == "file-0" and len(preview.files) == 3


def test_manifest_and_bound_tool_share_the_four_read_kinds():
    assert (
        SKILL_LIBRARY_READ_MANIFEST.parameters[0].schema
        == SkillLibraryReadInput.model_json_schema()
    )
    assert set(get_lia_skill_library_tool.tool_call_schema.model_json_schema()["properties"]) == {
        "query"
    }
    assert (
        SKILL_LIBRARY_READ_MANIFEST.mutation_policy == "read"
        and not SKILL_LIBRARY_READ_MANIFEST.initiative_eligible
    )


def test_added_ui_list_requires_an_explicit_native_window():
    from src.domains.skill_library.schemas import (
        LibraryInstalledResponse,
        LibrarySearchResponse,
        LibraryUpdatePreviewResponse,
    )

    def lists(node, definitions, prefix=""):
        if "$ref" in node:
            return lists(definitions[node["$ref"].split("/")[-1]], definitions, prefix)
        if node.get("type") == "array":
            return {prefix}
        found = set()
        for branch in node.get("anyOf", []):
            found.update(lists(branch, definitions, prefix))
        for name, value in node.get("properties", {}).items():
            found.update(lists(value, definitions, f"{prefix}.{name}" if prefix else name))
        return found

    actual = set()
    for model in (
        LibraryInstalledResponse,
        LibrarySearchResponse,
        LibraryPreviewAnswer,
        LibraryUpdatePreviewResponse,
    ):
        schema = model.model_json_schema()
        actual.update(lists(schema, schema.get("$defs", {})))
    assert actual == set(LIST_PATHS)
