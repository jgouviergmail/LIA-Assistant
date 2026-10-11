"""The model selects an entry, never provenance ownership or source URLs."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.journal_provenance_schemas import JournalProvenanceRequest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("field", ["actor_id", "user_id", "conversation_id", "url", "scope"])
def test_provenance_request_cannot_override_source_authority(field: str) -> None:
    with pytest.raises(ValidationError):
        JournalProvenanceRequest.model_validate({"entry_id": str(uuid4()), field: "injected"})
