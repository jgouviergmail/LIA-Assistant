"""Saved-answer reads expose strict UI bounds and honest bounded content windows."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.bookmark_read import _window
from src.domains.agents.application.bookmark_read_schemas import BookmarkReadQuery
from src.domains.agents.application.bookmark_read_spec import BOOKMARK_READ_MANIFEST
from src.domains.agents.tools.application_bookmark_tools import get_lia_saved_answers_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": "foreign"},
        {"limit": True},
        {"limit": 101},
        {"limit": 0},
        {"offset": -1},
        {"content_limit": 0},
        {"content_limit": 10001},
        {"content_offset": True},
        {"q": "X" * 201},
    ],
)
def test_bookmark_scope_and_window_bounds_are_strict(extra):
    with pytest.raises(ValidationError):
        BookmarkReadQuery.model_validate(extra)


def test_multibyte_content_is_windowed_by_characters_with_exact_continuation():
    query = BookmarkReadQuery(content_offset=2, content_limit=3)
    result, window = _window("界界界界界界", query)
    assert result == "界界界" and window.total_chars == 6 and window.next_offset == 5
    empty, tail = _window("abc", query.model_copy(update={"content_offset": 9}))
    assert empty == "" and tail.next_offset is None and tail.total_chars == 3


def test_both_modes_share_read_schema_without_initiative_or_mutation():
    assert BOOKMARK_READ_MANIFEST.parameters[0].schema == BookmarkReadQuery.model_json_schema()
    assert set(get_lia_saved_answers_tool.tool_call_schema.model_json_schema()["properties"]) == {
        "query"
    }
    assert (
        BOOKMARK_READ_MANIFEST.mutation_policy == "read"
        and not BOOKMARK_READ_MANIFEST.initiative_eligible
    )
