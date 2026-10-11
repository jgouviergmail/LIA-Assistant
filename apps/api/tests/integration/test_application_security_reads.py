"""Real owner-scoped security projections contain counts and metadata, never key material."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.security_operations import read_security_settings
from src.domains.agents.application.security_schemas import SecurityRead
from src.domains.auth.models import MFABackupCode, UserTOTP, WebAuthnCredential
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_security_projection_pages_tied_dates_and_hides_foreign_and_key_material(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mfa_enabled", True)
    now = datetime.now(UTC)
    foreign = User(id=uuid4(), email=f"foreign-security-{uuid4()}@example.test", is_active=True)
    async_session.add(foreign)
    await async_session.flush()
    rows = [
        WebAuthnCredential(
            id=uuid4(),
            user_id=test_user.id,
            credential_id=f"private-credential-{i}",
            public_key="private-key-material",
            sign_count=0,
            label=f"Device{i}",
            backed_up=False,
            created_at=now,
        )
        for i in range(4)
    ]
    foreign_passkey = WebAuthnCredential(
        id=uuid4(),
        user_id=foreign.id,
        credential_id="foreign-credential",
        public_key="foreign-key",
        sign_count=0,
        label="ForeignDevice",
        backed_up=False,
        created_at=now,
    )
    async_session.add_all(
        [
            *rows,
            foreign_passkey,
            UserTOTP(
                user_id=test_user.id, secret_encrypted="private-totp-secret", confirmed_at=now
            ),
            MFABackupCode(user_id=test_user.id, code_hash="private-backup-hash", used_at=None),
        ]
    )
    await async_session.commit()
    result = await read_security_settings(async_session, test_user.id, SecurityRead(limit=2))
    assert result.totp is not None and result.totp.active
    assert result.totp.backup_codes_remaining == 1
    assert result.total == 4 and len(result.passkeys) == 2
    assert result.next_cursor is not None
    second = await read_security_settings(
        async_session,
        test_user.id,
        SecurityRead(section="passkeys", limit=2, cursor=result.next_cursor),
    )
    assert second.next_cursor is None
    actual = [item.id for item in result.passkeys + second.passkeys]
    assert actual == sorted(row.id for row in rows)
    serialized = str(result.model_dump(mode="json"))
    assert "private" not in serialized and "ForeignDevice" not in serialized
    assert "public_key" not in serialized and "credential_id" not in serialized
    with pytest.raises(ValueError, match="cursor unavailable"):
        await read_security_settings(
            async_session, test_user.id, SecurityRead(section="passkeys", cursor=foreign_passkey.id)
        )
