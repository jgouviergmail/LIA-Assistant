"""Native gallery input, bounded failures and model-visible identity remain strict."""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.gallery_read_schemas import GalleryReadQuery
from src.domains.agents.application.gallery_read_spec import GALLERY_READ_MANIFEST
from src.domains.agents.tools.application_gallery_tools import get_lia_generated_gallery_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"family": "upload"},
        {"user_id": str(uuid4())},
        {"file_path": "/private/key"},
        {"limit": 101},
        {"limit": True},
        {"offset": -1},
        {"q": "x" * 201},
        {"sort": "random"},
        {"created_after": datetime(2026, 1, 1)},
        {"created_after": "2026-10-10T00:00:00Z", "created_before": "2026-10-09T00:00:00Z"},
    ],
)
def test_gallery_filters_refuse_scope_widening_and_ambiguous_dates(extra):
    with pytest.raises(ValidationError):
        GalleryReadQuery.model_validate({"family": "images", **extra})


def test_actual_gallery_tool_schema_is_read_only_and_has_no_actor_parameter():
    schema = get_lia_generated_gallery_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"query"}
    assert GALLERY_READ_MANIFEST.mutation_policy == "read"
    assert not GALLERY_READ_MANIFEST.initiative_eligible
