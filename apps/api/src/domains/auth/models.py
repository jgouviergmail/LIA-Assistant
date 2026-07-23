"""Authentication domain models (WebAuthn passkeys, TOTP, backup codes).

Security program D1 — ADR-143 (program doc:
``docs/superpowers/specs/2026-07-23-security-account-program.md``).
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class WebAuthnCredential(BaseModel):
    """A registered WebAuthn passkey bound to a user account.

    Only public material is persisted (credential id, COSE public key,
    signature counter): the private key never leaves the user's
    authenticator. ``label`` follows the ``health_metric_tokens`` display
    convention — user-supplied name ("iPhone", "PC bureau") shown in the
    Security settings list.
    """

    __tablename__ = "webauthn_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    credential_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        comment="Base64url-encoded WebAuthn credential ID (public identifier).",
    )

    public_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Base64url-encoded COSE public key (verification material, not secret-usable).",
    )

    sign_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Last verified signature counter (clone detection; 0 for synced passkeys).",
    )

    transports: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Authenticator transports reported at registration (internal, hybrid, usb…).",
    )

    aaguid: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="Authenticator AAGUID (model identifier, may be zeroed by the platform).",
    )

    device_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="py_webauthn credential_device_type: single_device | multi_device.",
    )

    backed_up: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the credential is synced/backed up (multi-device passkey).",
    )

    label: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Optional user-supplied label (e.g. 'iPhone', 'PC bureau').",
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Updated on each successful authentication.",
    )

    __table_args__ = (Index("ix_webauthn_credentials_user", "user_id"),)

    def __repr__(self) -> str:
        """Concise representation for logging (no key material)."""
        return (
            f"<WebAuthnCredential(user_id={self.user_id}, "
            f"label={self.label}, device_type={self.device_type})>"
        )


class UserTOTP(BaseModel):
    """TOTP second factor for one user (security program D1, Lot 2).

    The shared secret is Fernet-encrypted at rest (it must stay reversible
    to verify codes). ``last_used_step`` stores the last ACCEPTED 30-second
    timestep so the same code can never be replayed within its window.
    Unconfirmed rows (``confirmed_at`` NULL) are enrollment drafts and are
    replaced by a new enrollment.
    """

    __tablename__ = "user_totp"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    secret_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Fernet-encrypted base32 TOTP secret (reversible by design).",
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when the user proves possession with a first valid code.",
    )

    last_used_step: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Last accepted TOTP timestep (anti-replay within the validity window).",
    )

    def __repr__(self) -> str:
        """Concise representation for logging (never the secret)."""
        return f"<UserTOTP(user_id={self.user_id}, confirmed={self.confirmed_at is not None})>"


class MFABackupCode(BaseModel):
    """One single-use MFA backup code (security program D1, Lot 2).

    Only the SHA-256 hash is persisted — the raw codes are shown to the
    user exactly once at generation (``health_metric_tokens`` pattern).
    """

    __tablename__ = "mfa_backup_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    code_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="SHA-256 hex digest of the raw backup code (never the raw code).",
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set on consumption — a backup code is strictly single-use.",
    )

    __table_args__ = (Index("ix_mfa_backup_codes_user", "user_id"),)

    def __repr__(self) -> str:
        """Concise representation for logging (never code material)."""
        return f"<MFABackupCode(user_id={self.user_id}, used={self.used_at is not None})>"
