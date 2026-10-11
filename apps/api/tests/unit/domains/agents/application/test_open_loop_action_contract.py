"""Native correction inherits source validators but never accepts invented authority."""

import json
from datetime import UTC, datetime
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.open_loop_action_schemas import (
    OpenLoopClosePatch,
    OpenLoopCloseRequest,
    OpenLoopCloseValues,
    OpenLoopUpdatePatch,
    OpenLoopUpdateRequest,
    OpenLoopUpdateValues,
)
from src.domains.agents.application.open_loop_spec import (
    OPEN_LOOP_CLOSE_OPERATION,
    OPEN_LOOP_UPDATE_OPERATION,
)
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.open_loops.management_commands import OpenLoopSnapshot, changed_open_loop
from src.domains.open_loops.schemas import CloseLoopRequest, OpenLoopResponse, UpdateLoopRequest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"subject": " "},
        {"subject": None},
        {"due_hint": None},
        {"due_hint": "2026-10-20T10:00:00"},
        {"due_hint": 123},
        {"clear_due_hint": "true"},
        {"status": "closed"},
        {"counterparty": "Other"},
        {"direction": "waiting_on_other"},
    ],
)
def test_corrections_refuse_ambiguous_or_privileged_payloads(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        OpenLoopUpdateRequest.model_validate({"loop_id": str(uuid4()), "changes": changes})


@pytest.mark.parametrize(
    "extra", ["actor_id", "expected", "source_ref", "closed_reason", "command_id"]
)
def test_close_never_accepts_model_selected_authority(extra: str) -> None:
    with pytest.raises(ValidationError):
        OpenLoopCloseRequest.model_validate({"loop_id": str(uuid4()), extra: "invented"})


def test_native_corrections_keep_the_source_field_set_and_normalization() -> None:
    parsed = OpenLoopUpdateRequest.model_validate(
        {
            "loop_id": str(uuid4()),
            "changes": {"subject": " Correct wording ", "due_hint": "2026-10-20T10:00:00+02:00"},
        }
    )
    assert parsed.changes.subject == "Correct wording"
    assert set(type(parsed.changes).model_fields) == set(UpdateLoopRequest.model_fields)
    assert set(UpdateLoopRequest.model_fields) == {"subject", "due_hint", "clear_due_hint"}
    assert set(get_args(CloseLoopRequest.model_fields["action"].annotation)) == {
        "done",
        "dismissed",
    }
    assert set(OpenLoopCloseRequest.model_fields) - {"loop_id"} == set(
        CloseLoopRequest.model_fields
    )
    assert set(OpenLoopSnapshot.model_fields) | {"nudge_count", "updated_at"} == set(
        OpenLoopResponse.model_fields
    )


@pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
@pytest.mark.parametrize("operation", ["update", "close"])
def test_complete_localized_confirmation_and_editor_keep_authority_server_owned(
    language: str, operation: str
) -> None:
    expected = OpenLoopSnapshot(
        id=uuid4(),
        subject="Source promise",
        counterparty="Alex",
        direction="user_owes",
        due_hint=None,
        status="open",
        closed_reason=None,
        created_at=datetime.now(UTC),
    )
    if operation == "update":
        changes = OpenLoopUpdateRequest.model_validate(
            {"loop_id": str(expected.id), "changes": {"subject": "Corrected promise"}}
        ).changes
        intent = OpenLoopUpdatePatch(
            open_loop=OpenLoopUpdateValues(expected=expected, changes=changes)
        )
        spec = OPEN_LOOP_UPDATE_OPERATION
    else:
        changes = CloseLoopRequest(action="dismissed")
        intent = OpenLoopClosePatch(
            open_loop=OpenLoopCloseValues(expected=expected, action=changes)
        )
        spec = OPEN_LOOP_CLOSE_OPERATION
    draft = build_action_content(
        uuid4(),
        spec,
        intent,
        {"open_loop": expected.model_dump(mode="json")},
        {"open_loop": changed_open_loop(expected, changes).model_dump(mode="json")},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert (
        labels["application_open_loop_note"] in preview
        and "Source promise" in preview
        and "Alex" in preview
    )
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Change the proposal")
    editable = json.loads(prompt[1]["content"])["intent"]
    assert editable["loop_id"] == str(expected.id)
    assert "expected" not in editable and "source_ref" not in json.dumps(prompt)
    corrupt = draft.model_copy(update={"after": {"open_loop": {"subject": "Unconfirmed result"}}})
    refused = str(
        render_application_preview(
            corrupt.model_dump(mode="json"), labels, lambda value: value or ""
        )
    )
    assert labels["application_unavailable"] in refused and "Unconfirmed result" not in refused
