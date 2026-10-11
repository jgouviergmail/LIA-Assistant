"""Source canonical keys must fit their SQL column after folding expands Unicode."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.relation_debrief_build_schemas import (
    RelationDebriefBuildRequest,
)
from src.domains.agents.application.relation_debrief_read import RelationStoredDebriefQuery

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("model", [RelationStoredDebriefQuery, RelationDebriefBuildRequest])
def test_unicode_expansion_cannot_exceed_source_identity_column(model):
    with pytest.raises(ValidationError):
        model.model_validate({"name": "ﬀ" * 255})
