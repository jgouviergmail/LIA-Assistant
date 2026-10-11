"""Native revocation accepts a displayed identity, never a cookie or claimed actor."""

import json
from datetime import UTC, datetime
from importlib import import_module
from uuid import uuid4

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"display_id": "a" * 16},
        {"display_id": "a" * 16, "user_id": "claimed-owner"},
        {"display_id": "a" * 16, "session_cookie": "private-cookie"},
        {"display_id": "a" * 32},
        {"display_id": None},
        {"display_id": 1234567890123456},
        {"display_id": "../auth/sessions"},
    ],
)
def test_public_request_is_strict_and_uses_only_the_ui_display_identity(
    payload: dict[str, object],
) -> None:
    request = import_module(
        "src.domains.agents.application.session_revocation_schemas"
    ).DeviceSessionRevokeRequest
    if payload == {"display_id": "a" * 16}:
        assert request.model_validate(payload).model_dump() == payload
    else:
        with pytest.raises(ValidationError):
            request.model_validate(payload)


def test_copied_request_cannot_bypass_display_identity_validation() -> None:
    request = import_module(
        "src.domains.agents.application.session_revocation_schemas"
    ).DeviceSessionRevokeRequest
    copied = request(display_id="a" * 16).model_copy(update={"display_id": "private-cookie"})
    with pytest.raises(ValidationError):
        request.model_validate(copied)


def prepared_content() -> dict[str, object]:
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokePatch
    from src.domains.auth.session_queries import ListedDeviceSession

    session = ListedDeviceSession(
        id="a" * 16,
        ua_family="chrome",
        os_family="windows",
        ip_trunc=None,
        auth_methods=["password"],
        created_at=datetime.now(UTC),
        last_seen_at=None,
        device_name="My laptop",
        current=False,
    )
    patch = DeviceSessionRevokePatch(session_to_revoke=session)
    draft: ApplicationActionDraftContent = _preference_content(
        uuid4(), patch, patch.model_dump(mode="json")
    )
    return draft.model_dump(mode="json")


def test_modifier_exposes_only_the_selectable_display_identity() -> None:
    from src.domains.agents.application.prompts import build_application_edit_prompt

    prompt = build_application_edit_prompt(prepared_content(), "use another session")
    message = json.loads(prompt[1]["content"])
    assert message["intent"] == {"display_id": "a" * 16}
    assert "created_at" not in prompt[0]["content"]
    assert "auth_methods" not in prompt[0]["content"]


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_confirmation_identifies_the_device_and_consequence_in_every_locale(language: str) -> None:
    from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.drafts.card_spec import Note, Row

    labels = DRAFT_PREVIEW_LABELS[language]
    preview = render_application_preview(prepared_content(), labels, lambda value: value or "")
    assert any(
        isinstance(line, Note) and line.text == labels["application_session_revoke"]
        for line in preview
    )
    assert any(
        isinstance(line, Row) and "My laptop" in str(line.value) and "a" * 16 in str(line.value)
        for line in preview
    )
    assert labels["application_session_closed"] in str(preview)
    assert "auth_methods" not in str(preview) and "session_to_revoke" not in str(preview)
