"""The model cannot choose file material or smuggle an unbounded browser continuation."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.document_upload_schemas import (
    DocumentUploadInput,
    DocumentUploadSelection,
)


@pytest.mark.parametrize("extra", ["filename", "file", "file_path", "url", "content_base64"])
def test_upload_request_refuses_model_selected_file_material(extra):
    with pytest.raises(ValidationError):
        DocumentUploadInput.model_validate({"space_id": str(uuid4()), extra: "untrusted"})


def test_upload_scope_survives_json_round_trip_without_private_proof_in_browser():
    selected = DocumentUploadSelection.model_validate(
        {
            "space": {
                "id": str(uuid4()),
                "name": "<Literal name>",
                "description": None,
                "is_active": True,
                "kind": None,
            },
            "document_count": 0,
            "max_documents": 200,
            "max_file_size_bytes": 20 * 1024 * 1024,
            "allowed_content_types": ["text/plain"],
            "state_digest": "1" * 64,
        }
    )
    restored = DocumentUploadSelection.model_validate_json(selected.model_dump_json())
    assert restored == selected
    assert "state_digest" not in restored.public_scope()
    assert restored.public_scope()["browser_file_confirmation_required"] is True
    with pytest.raises(ValidationError, match="64,000"):
        DocumentUploadSelection.model_validate(
            {**selected.model_dump(), "allowed_content_types": ["x" * 64_000]}
        )
