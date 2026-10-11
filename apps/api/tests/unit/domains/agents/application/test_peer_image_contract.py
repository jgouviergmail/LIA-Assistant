"""Actual preview HTML escapes external words and editing omits frozen private evidence."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.peer_image_schemas import (
    PeerImageInput,
    PeerImagePatch,
    PeerImageSelection,
)
from src.domains.agents.application.peer_image_spec import PEER_IMAGE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.peers.schemas import ImageShareCreate

pytestmark = pytest.mark.unit


def test_image_source_request_growth_is_reviewed():
    assert set(ImageShareCreate.model_fields) == {"attachment_id", "comment"}
    with pytest.raises(ValidationError):
        PeerImageInput(connection_id=uuid4(), attachment_id=uuid4(), sender_id=uuid4())


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_literal_image_comment_and_private_editor(language):
    payload = PeerImageInput(
        connection_id=uuid4(), attachment_id=uuid4(), comment="<script>literal</script>"
    )
    selected = PeerImageSelection(
        request=payload,
        peer_id=uuid4(),
        display_name="<script>Alice</script>",
        email_hint="a***@example.com",
        title="<script>title</script>",
        state_digest="e" * 64,
        file_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        PEER_IMAGE_OPERATION,
        PeerImagePatch(peer_image=selected),
        {"peer_image": selected.public_scope()},
        {"peer_image": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    lines = render_application_preview(draft.model_dump(mode="json"), labels, lambda v: v or "")
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(lines)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert labels["application_peer_image_note"] in str(lines)
    assert "file_digest" not in str(lines) and "f" * 64 not in str(lines)
    editor = build_application_edit_prompt(draft.model_dump(mode="json"), "Change the comment")
    assert json.loads(editor[1]["content"])["intent"] == payload.model_dump(mode="json")
    assert "file_digest" not in str(editor) and "state_digest" not in str(editor)
