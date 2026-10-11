"""Authority changes and corrupted proposals fail before claim or cached serving."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import encrypt_data
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.draft_execution import authorized_application_executor
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.outcomes import ApplicationPhase
from src.domains.agents.application.preparation import preference_schema_fingerprint
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.effects.digest import draft_digest, payload_digest
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("capability", "CAPABILITY_DISABLED"),
        ("inactive", "FORBIDDEN"),
        ("deleted", "FORBIDDEN"),
        ("ownership", "FORBIDDEN"),
        ("corrupt", "INVALID_DRAFT"),
        ("expired", "EXPIRED"),
        ("schema", "SCHEMA_CHANGED"),
        ("cancelled", "CANCELLED"),
        ("ordinary_admin", "FORBIDDEN"),
        ("waiting_corrupt", "INVALID_DRAFT"),
    ],
)
async def test_current_authority_refuses_a_previously_prepared_or_recorded_action(
    fault: str, expected: str
) -> None:
    actor = User(
        id=uuid4(),
        is_active=fault != "inactive",
        is_superuser=False,
        deleted_at=datetime.now(UTC) if fault == "deleted" else None,
    )
    before = {"font_size": 16}
    content = ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=uuid4() if fault == "ownership" else actor.id,
        operation_id="preferences.update",
        schema_fingerprint="c" * 64 if fault == "schema" else preference_schema_fingerprint(),
        expected_digest=payload_digest(before),
        before=before,
        after={"font_size": 17},
        intent={"font_size": 17},
        title="Preferences",
        expires_at=datetime.now(UTC) + timedelta(minutes=-1 if fault == "expired" else 15),
    )
    raw = content.model_dump(mode="json")
    command = ApplicationCommand(
        id=content.command_id,
        actor_id=actor.id,
        draft_id="d-1",
        operation_id=content.operation_id,
        content_digest=draft_digest(raw),
        content_encrypted=(
            "corrupt" if fault == "corrupt" else encrypt_data(content.model_dump_json())
        ),
        phase=(
            ApplicationPhase.WAITING
            if fault == "waiting_corrupt"
            else ApplicationPhase.CANCELLED if fault == "cancelled" else ApplicationPhase.PENDING
        ),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        result_encrypted="broken encrypted interaction" if fault == "waiting_corrupt" else None,
    )
    db = AsyncMock()
    db.scalar.side_effect = ["false" if fault == "capability" else "true", actor, command]

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    execute = AsyncMock(return_value={"success": True, "restricted_details": "must-not-serve"})
    spec = APPLICATION_OPERATIONS.get("preferences.update")
    scope = EffectScope(
        run_id="r-1",
        idempotency_key="draft:d-1",
        approved=True,
        approval_kind="draft_critique",
        approval_ref="d-1",
        draft_digest=draft_digest(raw),
    )
    with (
        installed_runtime_context(user_id=actor.id),
        effect_scope(scope),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch.object(
            APPLICATION_OPERATIONS,
            "get",
            return_value=replace(spec, administrative=fault == "ordinary_admin"),
        ),
    ):
        result = await authorized_application_executor(execute)(raw, actor.id, None)
    assert result == {"success": False, "error_code": expected}
    execute.assert_not_awaited()
