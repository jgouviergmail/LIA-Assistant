"""Studio creation is strict, including nested conditions and approval intent."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.routine_create_schemas import (
    RoutineCreatePatch,
    RoutineCreateRequest,
    RoutineCreationValues,
)
from src.domains.agents.application.routine_spec import ROUTINE_CREATE_OPERATION

pytestmark = pytest.mark.unit


def test_native_condition_creation_carries_every_studio_setting() -> None:
    request = RoutineCreateRequest.model_validate(
        {
            "title": "Inbox",
            "action_prompt": "Summarize receipts",
            "trigger_kind": "condition",
            "condition_config": {"type": "mail_match", "query": "receipt"},
            "requires_approval": True,
            "execution_mode": "pipeline",
        }
    )
    assert request.requires_approval is True and request.execution_mode == "pipeline"
    assert request.recurrence is None


@pytest.mark.parametrize(
    "extra",
    [
        {"owner_id": "foreign"},
        {"requires_approval": "false"},
        {"condition_config": {"type": "mail_match", "query": "receipt", "secret": "injected"}},
        {"recurrence": {}},
    ],
)
def test_native_creation_refuses_implicit_approval_and_unknown_fields(
    extra: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RoutineCreateRequest.model_validate(
            {
                "title": "Inbox",
                "action_prompt": "Summarize receipts",
                "trigger_kind": "condition",
                "condition_config": {"type": "mail_match", "query": "receipt"},
                **extra,
            }
        )


@pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
def test_creation_preview_keeps_all_configuration_and_editor_cannot_choose_identity(
    language: str,
) -> None:
    identity = uuid4()
    request = RoutineCreateRequest.model_validate(
        {
            "title": "Inbox",
            "action_prompt": "Summarize receipts",
            "trigger_kind": "condition",
            "condition_config": {"type": "mail_match", "query": "receipt"},
            "requires_approval": True,
            "execution_mode": "pipeline",
        }
    )
    patch = RoutineCreatePatch(
        routine_to_create=RoutineCreationValues(
            id=identity, user_timezone="Europe/Paris", configuration=request
        )
    )
    content = build_action_content(
        uuid4(),
        ROUTINE_CREATE_OPERATION,
        patch,
        {"routine_to_create": None},
        patch.model_dump(mode="json", exclude_unset=True),
        command_id=identity,
    ).model_dump(mode="json")
    lines = render_application_preview(
        content, DRAFT_PREVIEW_LABELS[language], lambda value: value or ""
    )
    assert len(lines) == 3 and "Summarize receipts" in str(lines) and "receipt" in str(lines)
    assert "Europe/Paris" in str(lines) and "requires_approval" in str(lines)
    prompt = build_application_edit_prompt(content, "Change title")
    assert str(identity) not in str(prompt)
    assert "user_timezone" not in str(prompt)
