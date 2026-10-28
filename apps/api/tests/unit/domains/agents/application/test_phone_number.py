"""Number changes require exact HITL; public proposals cannot invent verification."""

from datetime import UTC, datetime
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.infrastructure.phone_number_preferences import PhoneNumberSnapshot, PhoneNumberValues

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"action": "set"},
        {"action": "set", "phone_number": None},
        {"action": "set", "phone_number": 33612345678},
        {"action": "set", "phone_number": ""},
        {"action": "clear", "phone_number": "+33612345678"},
        {"action": "clear", "phone_number": None},
        {"action": "set", "phone_number": "+33612345678", "verified": True},
        {"action": "verify"},
    ],
)
def test_number_request_refuses_missing_coerced_or_privileged_values(payload: object) -> None:
    model = import_module("src.domains.agents.application.phone_number_schemas").PhoneNumberRequest
    with pytest.raises(ValidationError):
        model.model_validate(payload)
    assert not Draft202012Validator(model.model_json_schema()).is_valid(payload)


@pytest.mark.parametrize("action,number", [("set", "+33 6 98 76 54 32"), ("clear", None)])
async def test_prepare_is_canonical_and_loses_verification_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    number: str | None,
) -> None:
    module = import_module("src.domains.agents.application.phone_number_operations")
    schemas = import_module("src.domains.agents.application.phone_number_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(module, "load_actor", AsyncMock())
    snapshot = PhoneNumberSnapshot(
        values=PhoneNumberValues(
            phone_number="+33612345678",
            number_status="available",
            verified=True,
            verified_at=datetime.now(UTC),
        ),
        stored_digest="a" * 64,
    )
    gateway = AsyncMock()
    gateway.read.return_value = snapshot
    monkeypatch.setattr(module, "get_phone_number_preferences", lambda: gateway)
    request = schemas.PhoneNumberRequest.model_validate(
        {"action": action, **({"phone_number": number} if number is not None else {})}
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    draft = await module.prepare_phone_number(db, uuid4(), request)
    assert draft.operation_id == "phone_number.update"
    patch = schemas.PhoneNumberPatch.model_validate(draft.intent).phone_number
    assert patch.expected == snapshot
    assert patch.number == ("+33698765432" if number else None)
    assert patch.public_values().verified is False
    gateway.write.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_source_number_fields_require_explicit_future_coverage_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.agents.application.phone_number_schemas")
    monkeypatch.setattr(
        module.TelephonyIdentityNumberRequest,
        "__pydantic_fields__",
        {
            **module.TelephonyIdentityNumberRequest.model_fields,
            "new_setting": module.TelephonyIdentityNumberRequest.model_fields["phone_number"],
        },
    )
    with pytest.raises(ValueError, match="Review new number settings"):
        module.assert_phone_number_schema_coverage()


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_unreadable_number_clear_has_a_complete_localized_before_and_after(language: str) -> None:
    from datetime import timedelta

    from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview

    schemas = import_module("src.domains.agents.application.phone_number_schemas")
    expected = PhoneNumberSnapshot(
        values=PhoneNumberValues(
            phone_number=None,
            number_status="unreadable",
            verified=False,
            verified_at=None,
        ),
        stored_digest="a" * 64,
    )
    clearing = schemas.PhoneNumberCommandValues(expected=expected, number=None).model_dump(
        mode="json"
    )
    draft = ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=uuid4(),
        operation_id="phone_number.update",
        schema_fingerprint="b" * 64,
        expected_digest="c" * 64,
        intent={"phone_number": clearing},
        before={"phone_number": clearing},
        after={"phone_number": clearing},
        title="Number",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    labels = DRAFT_PREVIEW_LABELS[language]
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_number_unreadable"] in preview
    assert labels["application_number_unset"] in preview
    assert labels["application_phone_number"] in preview
    assert "stored_digest" not in preview and "verified_at" not in preview


async def test_invalid_model_copy_is_refused_by_the_actual_tool_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langgraph.store.memory import InMemoryStore

    from src.domains.agents.effects.treatments import treatment_collector
    from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

    module = import_module("src.domains.agents.tools.application_phone_tools")
    schemas = import_module("src.domains.agents.application.phone_number_schemas")
    changed = schemas.PhoneNumberRequest(action="clear").model_copy(update={"action": "set"})
    door = AsyncMock()
    monkeypatch.setattr(module, "get_db_context", door)
    actor_id = uuid4()
    # A real turn publishes its consultation register; once a registration has
    # gated this tool, a call without one schedules a real database write.
    with (
        installed_runtime_context(user_id=actor_id),
        treatment_collector(run_id="phone-number-tool"),
    ):
        output = await module.update_lia_phone_number_tool.coroutine(
            change=changed,
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
    assert not output.success and output.error_code == "INVALID_INPUT"
    door.assert_not_called()


@pytest.mark.parametrize("flag", ["application_tools_enabled", "telephony_enabled"])
async def test_disabled_number_management_never_reads_the_port(
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
) -> None:
    module = import_module("src.domains.agents.application.phone_number_operations")
    schemas = import_module("src.domains.agents.application.phone_number_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(settings, flag, False)
    gateway = AsyncMock()
    monkeypatch.setattr(module, "get_phone_number_preferences", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    with pytest.raises(AuthorizationError):
        await module.prepare_phone_number(db, uuid4(), schemas.PhoneNumberRequest(action="clear"))
    gateway.read.assert_not_awaited()


def test_registered_number_tool_hides_private_state_from_preview_editor_and_result() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS
    from src.domains.agents.application.result_projection import public_application_values
    from src.domains.agents.tools.application_phone_tools import update_lia_phone_number_tool

    assert set(update_lia_phone_number_tool.tool_call_schema.model_fields) == {"change"}
    assert "update_lia_phone_number_tool" in APPLICATION_TOOL_NAMES
    assert APPLICATION_OPERATIONS.get("phone_number.update").sections == ("telephony-identity",)
    from datetime import timedelta

    from src.domains.agents.application.draft_models import ApplicationActionDraftContent

    schemas = import_module("src.domains.agents.application.phone_number_schemas")
    expected = PhoneNumberSnapshot(
        values=PhoneNumberValues(
            phone_number=None,
            number_status="unreadable",
            verified=False,
            verified_at=None,
        ),
        stored_digest="a" * 64,
    )
    before = schemas.PhoneNumberCommandValues(expected=expected, number=None)
    after = schemas.PhoneNumberCommandValues(expected=expected, number="+33612345678")
    draft = ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=uuid4(),
        operation_id="phone_number.update",
        schema_fingerprint="b" * 64,
        expected_digest="c" * 64,
        intent={"phone_number": after.model_dump(mode="json")},
        before={"phone_number": before.model_dump(mode="json")},
        after={"phone_number": after.model_dump(mode="json")},
        title="Number",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    labels = {
        "application_field_phone_number": "Declared phone number",
        "application_before": "Before",
        "application_after": "After",
        "application_expiry": "Expires",
        "application_unavailable": "Unavailable",
        "application_phone_number": "No call or verification; applies to future calls",
        "application_number_unreadable": "Stored number unreadable",
        "application_number_unset": "No declared number",
        "application_number_verified": "Verified",
        "application_number_unverified": "Not verified",
    }
    preview = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "clear it")
    public = public_application_values(draft)
    assert "unreadable" in str(preview) and "+33612345678" in str(preview)
    assert "number_status" not in str(preview) and "verified_at" not in str(preview)
    assert public["phone_number"]["verified"] is False
    assert "phone_number" in str(prompt) and '"action": "set"' in str(prompt)
    assert "expected" not in str(preview) + str(prompt) + str(public)
    assert "stored_digest" not in str(preview) + str(prompt) + str(public)
    assert "a" * 64 not in str(preview) + str(prompt) + str(public)


def test_same_declared_number_keeps_its_proven_verification_in_public_preview() -> None:
    schemas = import_module("src.domains.agents.application.phone_number_schemas")
    values = PhoneNumberValues(
        phone_number="+33612345678",
        number_status="available",
        verified=True,
        verified_at=datetime.now(UTC),
    )
    expected = PhoneNumberSnapshot(values=values, stored_digest="a" * 64)
    assert (
        schemas.PhoneNumberCommandValues(
            expected=expected, number=values.phone_number
        ).public_values()
        == values
    )


async def test_operator_withdrawal_during_number_read_refuses_the_entire_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.agents.application.phone_number_operations")
    schemas = import_module("src.domains.agents.application.phone_number_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(module, "load_actor", AsyncMock())
    gateway = AsyncMock()

    async def withdraw(db, actor_id):
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        return PhoneNumberSnapshot(
            values=PhoneNumberValues(
                phone_number=None,
                number_status="unset",
                verified=False,
                verified_at=None,
            ),
            stored_digest="a" * 64,
        )

    gateway.read.side_effect = withdraw
    monkeypatch.setattr(module, "get_phone_number_preferences", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    with pytest.raises(AuthorizationError):
        await module.prepare_phone_number(db, uuid4(), schemas.PhoneNumberRequest(action="clear"))
    gateway.write.assert_not_awaited()


def test_malformed_before_number_refuses_the_entire_confirmation_card() -> None:
    from datetime import timedelta

    from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview

    schemas = import_module("src.domains.agents.application.phone_number_schemas")
    expected = PhoneNumberSnapshot(
        values=PhoneNumberValues(
            phone_number=None,
            number_status="unset",
            verified=False,
            verified_at=None,
        ),
        stored_digest="a" * 64,
    )
    after = schemas.PhoneNumberCommandValues(expected=expected, number="+33612345678").model_dump(
        mode="json"
    )
    draft = ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=uuid4(),
        operation_id="phone_number.update",
        schema_fingerprint="b" * 64,
        expected_digest="c" * 64,
        intent={"phone_number": after},
        before={"phone_number": {**after, "number": "not-a-number"}},
        after={"phone_number": after},
        title="Number",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    preview = render_application_preview(
        draft.model_dump(mode="json"), DRAFT_PREVIEW_LABELS["fr"], lambda value: value or ""
    )
    assert (
        len(preview) == 1
        and preview[0].text == DRAFT_PREVIEW_LABELS["fr"]["application_unavailable"]
    )
