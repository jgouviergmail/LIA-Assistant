"""Application-visible security data comes from reviewed public DTOs only."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import create_model
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.users.models import User

pytestmark = pytest.mark.unit


async def test_unmounted_mfa_has_no_invented_inactive_totp_or_passkey_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.auth.security_queries")
    monkeypatch.setattr(settings, "mfa_enabled", False)
    db = AsyncMock(spec=AsyncSession)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    result = await module.read_account_security(
        db, actor, section="overview", cursor=None, limit=25
    )
    assert result.features.mfa_enabled is False
    assert result.totp is None and result.passkeys is None
    assert result.unavailable_reason == "MFA_DISABLED"
    assert result.password_set is False and result.available_methods == []
    assert result.step_up_freshness == "unknown"
    db.execute.assert_not_awaited()


def test_available_reauthentication_methods_do_not_claim_session_freshness() -> None:
    module = import_module("src.domains.auth.security_queries")
    actor = User(id=uuid4(), hashed_password="private-hash", oauth_provider="google")
    assert module.methods_for_account(actor, has_passkeys=True, has_totp=True) == [
        "password",
        "oauth_google",
        "passkey",
        "totp",
    ]
    assert module.methods_for_account(actor, has_passkeys=False, has_totp=False) == [
        "password",
        "oauth_google",
    ]


def test_new_security_public_fields_require_explicit_native_projection_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.auth.security_queries")
    module.assert_security_projection_coverage()
    future = create_model(
        "FutureCredential",
        __base__=module.WebAuthnCredentialResponse,
        key_material=(str, "private"),
    )
    monkeypatch.setattr(module, "WebAuthnCredentialResponse", future)
    with pytest.raises(AssertionError, match="projection review"):
        module.assert_security_projection_coverage()
