"""Phone consent proposals are strict, private and side-effect free before HITL."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.infrastructure.phone_preferences import PhonePreferenceSnapshot, PhonePreferenceValues

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"rich_context_enabled": "false"},
        {"rich_context_enabled": None},
        {"disabled_domains": None},
        {"disabled_domains": ["secret"]},
        {"call_mode": "unknown"},
        {"phone_number": "+33612345678"},
        {"verified": True},
    ],
)
def test_native_patch_refuses_coercion_null_empty_unknown_and_identity_actions(
    payload: object,
) -> None:
    module = import_module("src.domains.agents.application.phone_preference_schemas")
    with pytest.raises(ValidationError):
        module.PhonePreferenceRequest.model_validate(payload)


async def test_single_consent_proposal_preserves_other_values_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.agents.application.phone_preference_operations")
    schemas = import_module("src.domains.agents.application.phone_preference_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(module, "load_actor", AsyncMock())
    before = PhonePreferenceSnapshot(
        values=PhonePreferenceValues(
            rich_context_enabled=True, disabled_domains=["email"], call_mode="delegated"
        ),
        stored_digest="a" * 64,
    )
    gateway = AsyncMock()
    gateway.read.return_value = before
    monkeypatch.setattr(module, "get_phone_preferences", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    draft = await module.prepare_phone_preferences(
        db, uuid4(), schemas.PhonePreferenceRequest(rich_context_enabled=False)
    )
    assert draft.operation_id == "phone_preferences.update"
    assert draft.intent["phone_preferences"]["values"] == {
        "rich_context_enabled": False,
        "disabled_domains": ["email"],
        "call_mode": "delegated",
    }
    assert draft.intent["phone_preferences"]["stored_digest"] == "a" * 64
    gateway.write.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("flag", ["application_tools_enabled", "telephony_enabled"])
async def test_disabled_management_precedes_phone_preference_port(
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
) -> None:
    module = import_module("src.domains.agents.application.phone_preference_operations")
    schemas = import_module("src.domains.agents.application.phone_preference_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(settings, flag, False)
    gateway = AsyncMock()
    monkeypatch.setattr(module, "get_phone_preferences", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    with pytest.raises(AuthorizationError):
        await module.prepare_phone_preferences(
            db, uuid4(), schemas.PhonePreferenceRequest(call_mode="direct")
        )
    gateway.read.assert_not_awaited()


def test_phone_action_is_registered_as_an_exact_confirmation_with_private_snapshot_hidden() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS
    from src.domains.agents.application.result_projection import public_application_values

    module = import_module("src.domains.agents.tools.application_phone_tools")
    assert set(
        module.update_lia_phone_preferences_tool.tool_call_schema.model_json_schema()["properties"]
    ) == {"change"}
    assert "update_lia_phone_preferences_tool" in APPLICATION_TOOL_NAMES
    spec = APPLICATION_OPERATIONS.get("phone_preferences.update")
    assert spec.kind == OperationKind.ACTION and spec.sections == ("telephony-identity",)
    snapshot = {
        "values": {
            "rich_context_enabled": True,
            "disabled_domains": ["email"],
            "call_mode": "delegated",
        },
        "stored_digest": "a" * 64,
    }
    changed = {**snapshot, "values": {**snapshot["values"], "rich_context_enabled": False}}
    from datetime import UTC, datetime, timedelta

    draft = ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=uuid4(),
        operation_id="phone_preferences.update",
        schema_fingerprint="b" * 64,
        expected_digest="c" * 64,
        intent={"phone_preferences": changed},
        before={"phone_preferences": snapshot},
        after={"phone_preferences": changed},
        title="Phone settings",
        user_timezone="UTC",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    labels = {
        "application_field_phone_preferences": "Phone settings",
        "application_before": "Before",
        "application_after": "After",
        "application_expiry": "Expires",
        "application_unavailable": "Unavailable",
        "application_phone_preferences": "Applies to future sessions and browser voice",
    }
    preview = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "direct")
    public = public_application_values(draft)
    assert "rich_context_enabled" in str(preview) and "rich_context_enabled" in str(prompt)
    assert "stored_digest" not in str(preview) + str(prompt) + str(public)
    assert "a" * 64 not in str(preview) + str(prompt) + str(public)
