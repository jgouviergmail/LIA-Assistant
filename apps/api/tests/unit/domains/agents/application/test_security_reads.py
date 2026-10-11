"""Security state is owner-scoped and never includes enrollment or recovery material."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"section": "enroll"},
        {"section": "passkeys", "user_id": str(uuid4())},
        {"section": "passkeys", "limit": True},
        {"section": "passkeys", "limit": 51},
    ],
)
def test_security_read_schema_excludes_identity_secrets_and_unbounded_requests(
    payload: dict[str, object],
) -> None:
    module = import_module("src.domains.agents.application.security_schemas")
    with pytest.raises(ValidationError):
        module.SecurityRead.model_validate(payload)


async def test_disabled_tools_stop_security_read_before_loading_security_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.agents.application.security_operations")
    schema = import_module("src.domains.agents.application.security_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", False)
    read = AsyncMock()
    monkeypatch.setattr(module, "read_account_security", read)
    with pytest.raises(AuthorizationError):
        await module.read_security_settings(
            AsyncMock(spec=AsyncSession), uuid4(), schema.SecurityRead()
        )
    read.assert_not_awaited()


async def test_deactivated_owner_cannot_read_mfa_or_passkey_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.agents.application.security_operations")
    schema = import_module("src.domains.agents.application.security_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = User(id=uuid4(), is_active=False, deleted_at=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor]
    read = AsyncMock()
    monkeypatch.setattr(module, "read_account_security", read)
    with pytest.raises(AuthorizationError):
        await module.read_security_settings(db, actor.id, schema.SecurityRead())
    read.assert_not_awaited()


def test_security_tool_schema_offers_no_authentication_material() -> None:
    module = import_module("src.domains.agents.tools.application_security_tools")
    schema = module.get_lia_security_settings_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"query"}
    assert "actor_id" not in str(schema) and "session_id" not in str(schema)
    fields = schema["$defs"]["SecurityRead"]["properties"]
    assert set(fields) == {"section", "cursor", "limit"}


def test_passkey_budget_projection_cannot_skip_unshown_rows() -> None:
    import json

    from src.domains.agents.tools.output import UnifiedToolOutput
    from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm

    rows = [{"id": str(uuid4()), "label": "long " * 300} for _ in range(8)]
    output = UnifiedToolOutput.data_success(
        message="passkeys",
        structured_data={"passkeys": rows, "next_cursor": None, "total": 8},
        metadata={"application_passkey_cursor": True},
    )
    rendered = json.loads(extract_data_for_llm(output, budget_tokens=120))
    assert 0 < len(rendered["passkeys"]) < 8
    assert rendered["next_cursor"] == rendered["passkeys"][-1]["id"]
    assert output.structured_data["next_cursor"] is None


def test_security_read_is_consistently_declared_as_read_only() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    assert "get_lia_security_settings_tool" in APPLICATION_TOOL_NAMES
    manifest = next(
        row for row in APPLICATION_MANIFESTS if row.name == "get_lia_security_settings_tool"
    )
    assert manifest.mutation_policy == "read"
    spec = APPLICATION_OPERATIONS.get("security.read")
    assert spec.kind == OperationKind.READ and not spec.administrative
