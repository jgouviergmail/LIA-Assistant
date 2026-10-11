"""Invitation preview/editor contains public target/note, never exact private proofs."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.peer_request_schemas import (
    PeerRequestInput,
    PeerRequestPatch,
    PeerRequestSelection,
)
from src.domains.agents.application.peer_request_spec import PEER_REQUEST_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"peer_id": "invalid"},
        {"peer_id": str(uuid4()), "user_id": "other"},
        {"peer_id": str(uuid4()), "context_message": 1},
        {"peer_id": str(uuid4()), "context_message": "X" * 501},
    ],
)
def test_invitation_cannot_override_source_scope(payload):
    with pytest.raises(ValidationError):
        PeerRequestInput.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_invitation_public_preview_and_editor_hide_proofs(language):
    selected = PeerRequestSelection(
        request=PeerRequestInput(peer_id=uuid4(), context_message="Bonjour"),
        display_name="Alice",
        email_hint="a***@example.com",
        before_status="pending",
        after_status="accepted",
        no_op=False,
        state_digest="a" * 64,
    )
    draft = build_action_content(
        uuid4(),
        PEER_REQUEST_OPERATION,
        PeerRequestPatch(peer_request=selected),
        {"peer_request": selected.public_scope()},
        {"peer_request": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda v: v or "")
    )
    assert (
        labels["application_peer_request_note"] in preview
        and "accepted" in preview
        and "Alice" in preview
    )
    assert "state_digest" not in preview and "a" * 64 not in preview
    editor = build_application_edit_prompt(draft.model_dump(mode="json"), "Invite someone else")
    assert json.loads(editor[1]["content"])["intent"] == selected.request.model_dump(mode="json")
    assert "state_digest" not in str(editor) and "a" * 64 not in str(editor)
