"""Phone consent changes are one owned, atomic, expected-state operation."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError, ValidationError
from src.domains.telephony.schemas import TelephonyIdentityUpdateRequest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


async def test_clearing_obsolete_domains_materializes_the_explicit_empty_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.preference_commands")
    user = actor()
    user.phone_disabled_domains = ["removed_domain"]
    monkeypatch.setattr(
        module.UserRepository, "get_by_id_for_preference_update", AsyncMock(return_value=user)
    )
    db = AsyncMock(spec=AsyncSession)
    receipt = PreferenceWriteReceipt()
    await module.update_phone_preferences(
        db,
        user.id,
        TelephonyIdentityUpdateRequest(disabled_domains=[]),
        receipt=receipt,
    )
    assert user.phone_disabled_domains == [] and receipt.committed and not receipt.no_op
    db.commit.assert_awaited_once()


async def test_authority_recheck_after_lock_wait_precedes_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.preference_commands")
    user = actor()
    order: list[str] = []

    async def lock(repository: object, identity: object) -> User:
        order.append("lock")
        return user

    async def check() -> None:
        order.append("check")
        raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})

    monkeypatch.setattr(module.UserRepository, "get_by_id_for_preference_update", lock)
    db = AsyncMock(spec=AsyncSession)
    with pytest.raises(AuthorizationError):
        await module.update_phone_preferences(
            db, user.id, TelephonyIdentityUpdateRequest(rich_context_enabled=False), check=check
        )
    assert order == ["lock", "check"] and user.phone_rich_context_enabled is True
    db.commit.assert_not_awaited()


def test_future_source_field_requires_an_explicit_native_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.preference_commands")
    monkeypatch.setattr(
        module.TelephonyIdentityUpdateRequest,
        "__pydantic_fields__",
        {**module.TelephonyIdentityUpdateRequest.model_fields, "future_switch": object()},
    )
    with pytest.raises(AssertionError, match="projection review"):
        module.assert_phone_preference_coverage()


def actor() -> User:
    return User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        phone_rich_context_enabled=True,
        phone_disabled_domains=["email"],
        phone_call_mode="delegated",
    )


async def test_complete_patch_is_validated_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.preference_commands")
    user = actor()
    lock = AsyncMock(return_value=user)
    monkeypatch.setattr(module.UserRepository, "get_by_id_for_preference_update", lock)
    db = AsyncMock(spec=AsyncSession)
    with pytest.raises(ValidationError):
        await module.update_phone_preferences(
            db,
            user.id,
            TelephonyIdentityUpdateRequest(rich_context_enabled=False, disabled_domains=["secret"]),
        )
    assert user.phone_rich_context_enabled is True
    db.commit.assert_not_awaited()


async def test_owned_patch_preserves_number_and_commits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.preference_commands")
    user = actor()
    user.phone_number_encrypted = "private-cipher"
    monkeypatch.setattr(
        module.UserRepository, "get_by_id_for_preference_update", AsyncMock(return_value=user)
    )
    expected = module.phone_preference_snapshot(user)
    db = AsyncMock(spec=AsyncSession)
    receipt = PreferenceWriteReceipt()
    result = await module.update_phone_preferences(
        db,
        user.id,
        TelephonyIdentityUpdateRequest(
            rich_context_enabled=False, disabled_domains=["event", "event"], call_mode="direct"
        ),
        expected=expected,
        receipt=receipt,
    )
    assert result.disabled_domains == ["event"] and result.rich_context_enabled is False
    assert user.phone_call_mode == "direct" and user.phone_number_encrypted == "private-cipher"
    assert receipt.committed and not receipt.no_op
    db.commit.assert_awaited_once()


@pytest.mark.parametrize("intervention", ["consent", "number", "verification"])
async def test_changed_approved_state_refuses_without_commit(
    monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    from datetime import UTC, datetime

    module = import_module("src.domains.telephony.preference_commands")
    user = actor()
    expected = module.phone_preference_snapshot(user)
    if intervention == "consent":
        user.phone_rich_context_enabled = False
    elif intervention == "number":
        user.phone_number_encrypted = "other-private-cipher"
    else:
        user.phone_number_verified_at = datetime.now(UTC)
    monkeypatch.setattr(
        module.UserRepository, "get_by_id_for_preference_update", AsyncMock(return_value=user)
    )
    db = AsyncMock(spec=AsyncSession)
    with pytest.raises(ResourceConflictError):
        await module.update_phone_preferences(
            db,
            user.id,
            TelephonyIdentityUpdateRequest(call_mode="direct"),
            expected=expected,
        )
    db.commit.assert_not_awaited()


async def test_identical_saved_state_is_verified_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    module = import_module("src.domains.telephony.preference_commands")
    user = actor()
    monkeypatch.setattr(
        module.UserRepository, "get_by_id_for_preference_update", AsyncMock(return_value=user)
    )
    db = AsyncMock(spec=AsyncSession)
    receipt = PreferenceWriteReceipt()
    await module.update_phone_preferences(
        db,
        user.id,
        TelephonyIdentityUpdateRequest(disabled_domains=["email"]),
        expected=module.phone_preference_snapshot(user),
        receipt=receipt,
    )
    assert receipt.committed and receipt.no_op
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("unavailable", ["foreign", "inactive", "deleted", "absent"])
async def test_current_owner_required_before_state_or_writes(
    monkeypatch: pytest.MonkeyPatch, unavailable: str
) -> None:
    from datetime import UTC, datetime

    module = import_module("src.domains.telephony.preference_commands")
    user = actor()
    identity = user.id
    if unavailable == "foreign":
        identity = uuid4()
    elif unavailable == "inactive":
        user.is_active = False
    elif unavailable == "deleted":
        user.deleted_at = datetime.now(UTC)
    monkeypatch.setattr(
        module.UserRepository,
        "get_by_id_for_preference_update",
        AsyncMock(return_value=None if unavailable == "absent" else user),
    )
    db = AsyncMock(spec=AsyncSession)
    with pytest.raises(AuthorizationError):
        await module.update_phone_preferences(
            db,
            identity,
            TelephonyIdentityUpdateRequest(call_mode="direct"),
        )
    db.commit.assert_not_awaited()
