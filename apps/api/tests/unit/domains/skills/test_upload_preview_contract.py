"""New public upload metadata requires explicit typed/native coverage review."""

import pytest

from src.domains.skills.ui_projection import parsed_skill_metadata
from src.domains.skills.upload_preview import SkillPackagePreview

pytestmark = pytest.mark.unit


def test_upload_metadata_cannot_grow_without_preview_contract_review():
    metadata = parsed_skill_metadata({"name": "card", "description": "public"}, "user")
    assert set(metadata) == set(SkillPackagePreview.model_fields) - {"files"}
    preview = SkillPackagePreview(**metadata, files=())
    assert SkillPackagePreview.model_validate(preview.model_dump(mode="json")) == preview
