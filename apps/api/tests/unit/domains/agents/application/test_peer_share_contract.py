"""Domain granularity is finite, explicit and always source-owned."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.peer_share_schemas import (
    PeerShareInput,
    PeerSharePatch,
    PeerShareSelection,
)
from src.domains.agents.application.peer_share_spec import PEER_SHARE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "changes",
    [
        {"domain": "calendar", "level": "titles"},
        {"domain": "task", "level": "details"},
        {"domain": "calendar"},
        {"domain": "unknown", "level": None},
        {"domain": "calendar", "level": "details", "owner_user_id": str(uuid4())},
    ],
)
def test_invalid_or_implicit_share_consent_refuses(changes):
    with pytest.raises(ValidationError):
        PeerShareInput.model_validate({"connection_id": str(uuid4()), **changes})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_share_preview_escapes_identity_and_editor_has_only_public_request(language):
    request = PeerShareInput(connection_id=uuid4(), domain="calendar", level="details")
    selected = PeerShareSelection(
        request=request,
        peer_id=uuid4(),
        display_name="<script>private-name</script>",
        email_hint="a***@example.com",
        before_level="availability",
        state_digest="c" * 64,
    )
    draft = build_action_content(
        uuid4(),
        PEER_SHARE_OPERATION,
        PeerSharePatch(peer_share=selected),
        {"peer_share": selected.public_scope()},
        {"peer_share": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    lines = render_application_preview(draft.model_dump(mode="json"), labels, lambda v: v or "")
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(lines)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert labels["application_peer_share_note"] in str(lines)
    assert "state_digest" not in str(lines) and "c" * 64 not in str(lines)
    editor = build_application_edit_prompt(draft.model_dump(mode="json"), "Revoke instead")
    assert json.loads(editor[1]["content"])["intent"] == request.model_dump(mode="json")
    assert "private-name" not in str(editor) and "state_digest" not in str(editor)
