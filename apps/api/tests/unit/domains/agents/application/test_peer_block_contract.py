"""Directional block previews explain severance and never leak proof to the editor."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.peer_block_schemas import (
    PeerBlockInput,
    PeerBlockPatch,
    PeerBlockSelection,
)
from src.domains.agents.application.peer_block_spec import PEER_BLOCK_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"peer_id": str(uuid4()), "blocked": "true"},
        {"peer_id": str(uuid4()), "blocked": 1},
        {"peer_id": str(uuid4()), "blocked": True, "blocker_id": str(uuid4())},
        {"peer_id": str(uuid4())},
    ],
)
def test_block_choice_is_explicit_and_cannot_override_actor(payload):
    with pytest.raises(ValidationError):
        PeerBlockInput.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_block_preview_escapes_identity_and_editor_omits_private_proof(language):
    request = PeerBlockInput(peer_id=uuid4(), blocked=True)
    selected = PeerBlockSelection(
        request=request,
        display_name="<script>private-name</script>",
        email_hint=None,
        before_blocked=False,
        pair_status="accepted",
        state_digest="e" * 64,
        share_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        PEER_BLOCK_OPERATION,
        PeerBlockPatch(peer_block=selected),
        {"peer_block": selected.public_scope()},
        {"peer_block": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    lines = render_application_preview(draft.model_dump(mode="json"), labels, lambda v: v or "")
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(lines)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert labels["application_peer_block_note"] in str(lines)
    assert "state_digest" not in str(lines) and "e" * 64 not in str(lines)
    editor = build_application_edit_prompt(draft.model_dump(mode="json"), "Unblock instead")
    assert json.loads(editor[1]["content"])["intent"] == request.model_dump(mode="json")
    assert "private-name" not in str(editor) and "state_digest" not in str(editor)
