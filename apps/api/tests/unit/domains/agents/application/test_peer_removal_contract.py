"""Severance previews expose source grants and policy, never private state proofs or work."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.peer_removal_schemas import (
    PeerRemovalInput,
    PeerRemovalPatch,
    PeerRemovalSelection,
)
from src.domains.agents.application.peer_removal_spec import PEER_REMOVAL_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.peers.schemas import ShareItem

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_removal_preview_and_editor_respect_private_scope(language):
    request = PeerRemovalInput(connection_id=uuid4())
    selected = PeerRemovalSelection(
        request=request,
        peer_id=uuid4(),
        display_name="<script>private-name</script>",
        email_hint="a***@example.com",
        my_shares=[ShareItem(domain="calendar", level="details")],
        their_shares=[ShareItem(domain="task", level="titles")],
        state_digest="d" * 64,
    )
    draft = build_action_content(
        uuid4(),
        PEER_REMOVAL_OPERATION,
        PeerRemovalPatch(peer_removal=selected),
        {"peer_removal": selected.public_scope()},
        {"peer_removal": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    lines = render_application_preview(draft.model_dump(mode="json"), labels, lambda v: v or "")
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(lines)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert labels["application_peer_removal_note"] in str(lines)
    assert "state_digest" not in str(lines) and "d" * 64 not in str(lines)
    assert "calendar" in html and "task" in html
    editor = build_application_edit_prompt(
        draft.model_dump(mode="json"), "Remove another connection"
    )
    assert json.loads(editor[1]["content"])["intent"] == request.model_dump(mode="json")
    assert "private-name" not in str(editor) and "state_digest" not in str(editor)


def test_removal_input_cannot_choose_another_actor_or_pending_state():
    with pytest.raises(ValidationError):
        PeerRemovalInput.model_validate(
            {"connection_id": str(uuid4()), "actor_id": str(uuid4()), "status": "pending"}
        )
