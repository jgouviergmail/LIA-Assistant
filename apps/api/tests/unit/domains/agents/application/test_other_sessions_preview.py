"""An exact complete fleet stays durable; approval and editing prompts stay bounded."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.session_bulk_operations import (
    SESSION_FLEET_OPERATION,
    OtherSessionsRevokePatch,
)
from src.domains.agents.drafts.card_spec import Note, Row
from src.domains.auth.session_bulk_schemas import OtherDeviceSessionsSelection
from src.domains.auth.session_queries import ListedDeviceSession

pytestmark = pytest.mark.unit


def fleet_content(size: int) -> dict[str, object]:
    selection = OtherDeviceSessionsSelection(
        current_display_id="f" * 16,
        sessions=tuple(
            ListedDeviceSession(
                id=f"{index:016x}",
                current=False,
                ua_family="private-user-agent",
                os_family=None,
                ip_trunc=None,
                auth_methods=[],
                created_at=datetime(2026, 10, 7, tzinfo=UTC),
                last_seen_at=None,
                device_name="private-device-label",
            )
            for index in range(size)
        ),
    )
    intent = OtherSessionsRevokePatch(other_sessions_to_revoke=selection)
    return build_action_content(
        uuid4(),
        SESSION_FLEET_OPERATION,
        intent,
        intent.model_dump(mode="json"),
        {"other_sessions_to_revoke": None},
    ).model_dump(mode="json")


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
@pytest.mark.parametrize("size", [0, 1000])
def test_complete_fleet_confirmation_is_exact_localized_and_bounded(
    language: str, size: int
) -> None:
    content = fleet_content(size)
    labels = get_draft_preview_labels(language)
    with patch.dict(
        APPLICATION_OPERATIONS._operations,
        {
            SESSION_FLEET_OPERATION.operation_id: SESSION_FLEET_OPERATION,
        },
    ):
        lines = render_application_preview(content, labels, lambda value: value or "")
    assert len(lines) == 4
    assert isinstance(lines[0], Note) and lines[0].text != labels["application_unavailable"]
    assert isinstance(lines[1], Row) and lines[1].value == str(size)
    assert isinstance(lines[2], Row) and lines[2].value == "f" * 16
    rendered = str(lines)
    assert len(rendered) < 1600
    assert "private-user-agent" not in rendered and "private-device-label" not in rendered
    assert content["intent"] == content["before"]
    assert (
        len(
            OtherSessionsRevokePatch.model_validate(
                content["intent"]
            ).other_sessions_to_revoke.sessions
        )
        == size
    )


@pytest.mark.parametrize("change", ["after", "before", "current"])
def test_tampered_fleet_never_presents_a_confirmable_summary(change: str) -> None:
    content = fleet_content(1)
    if change == "after":
        content["after"] = content["intent"]
    elif change == "before":
        content["before"] = {}
    else:
        original = OtherSessionsRevokePatch.model_validate(content["intent"])
        content["intent"] = {
            "other_sessions_to_revoke": {
                **original.other_sessions_to_revoke.model_dump(mode="json"),
                "current_display_id": original.other_sessions_to_revoke.sessions[0].id,
            }
        }
    labels = get_draft_preview_labels("en")
    with patch.dict(
        APPLICATION_OPERATIONS._operations,
        {
            SESSION_FLEET_OPERATION.operation_id: SESSION_FLEET_OPERATION,
        },
    ):
        assert render_application_preview(content, labels, lambda value: value or "") == [
            Note(text=labels["application_unavailable"])
        ]


def test_modifier_refreshes_the_selection_without_leaking_or_editing_snapshot_fields() -> None:
    from src.domains.agents.application.prompts import build_application_edit_prompt

    content = fleet_content(1000)
    with patch.dict(
        APPLICATION_OPERATIONS._operations,
        {
            SESSION_FLEET_OPERATION.operation_id: SESSION_FLEET_OPERATION,
        },
    ):
        prompt = build_application_edit_prompt(content, "refresh the other sessions")
    assert json.loads(prompt[1]["content"])["intent"] == {}
    assert '"additionalProperties": false' in prompt[0]["content"]
    assert "other_sessions_to_revoke" not in str(prompt)
    assert "private-user-agent" not in str(prompt) and "private-device-label" not in str(prompt)
    assert len(str(prompt)) < 6000


@pytest.mark.parametrize("surface", ["preview", "editor"])
def test_a_read_operation_cannot_be_rendered_or_edited_as_an_action(surface: str) -> None:
    from src.domains.agents.application.prompts import build_application_edit_prompt

    labels = get_draft_preview_labels("en")
    with patch.dict(
        APPLICATION_OPERATIONS._operations,
        {
            SESSION_FLEET_OPERATION.operation_id: replace(
                SESSION_FLEET_OPERATION, kind=OperationKind.READ
            ),
        },
    ):
        if surface == "editor":
            with pytest.raises(ValueError):
                build_application_edit_prompt(fleet_content(1), "refresh")
        else:
            assert render_application_preview(
                fleet_content(1), labels, lambda value: value or ""
            ) == [Note(text=labels["application_unavailable"])]
