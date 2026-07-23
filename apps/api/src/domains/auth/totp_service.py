"""TOTP second-factor service (security program D1, Lot 2).

Owns the enrollment lifecycle (draft → confirmed), login verification with
same-step anti-replay, single-use backup codes (revealed once, SHA-256
hashes persisted — the ``health_metric_tokens`` pattern), and the single-use
Redis pending token that bridges the two steps of a password+TOTP login.
"""

import asyncio
import base64
import hashlib
import io
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pyotp
import qrcode
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    MFA_BACKUP_CODE_HEX_CHARS,
    MFA_BACKUP_CODES_COUNT,
    REDIS_KEY_MFA_PENDING_PREFIX,
    TOTP_DIGITS,
    TOTP_INTERVAL_SECONDS,
    TOTP_VALID_WINDOW_STEPS,
)
from src.core.exceptions import raise_invalid_credentials, raise_invalid_input
from src.core.field_names import FIELD_USER_ID
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.auth.models import MFABackupCode, UserTOTP
from src.domains.auth.totp_repository import TOTPRepository
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.observability.metrics_mfa import track_totp_verification

logger = structlog.get_logger(__name__)


def hash_backup_code(raw_code: str) -> str:
    """SHA-256 hex digest of a normalized backup code.

    Args:
        raw_code: Code as typed by the user.

    Returns:
        Hex digest of the lowercased, stripped code.
    """
    return hashlib.sha256(raw_code.strip().lower().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TOTPStatus:
    """User-facing TOTP state for the Security settings."""

    active: bool
    confirmed_at: datetime | None
    backup_codes_remaining: int


@dataclass(frozen=True)
class PendingLogin:
    """Payload bridging the two steps of a password+TOTP login."""

    user_id: str
    remember_me: bool
    # A4 attestation outcome computed at step one, applied at step two.
    known_device: bool = False
    fcm_token_id: str | None = None


class TOTPService:
    """TOTP enrollment, verification, backup codes, pending-login tokens."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with a database session.

        Args:
            db: SQLAlchemy async session.
        """
        self.db = db
        self.repository = TOTPRepository(db)

    # ------------------------------------------------------------------
    # Enrollment lifecycle
    # ------------------------------------------------------------------

    async def enroll(self, user: User) -> tuple[str, str, str]:
        """Start a TOTP enrollment: fresh secret, provisioning URI, QR.

        The secret and QR are returned exactly once; only the Fernet-encrypted
        secret is persisted (unconfirmed draft — replaced by re-enrollment).

        Args:
            user: The authenticated user.

        Returns:
            Tuple (base32 secret, otpauth:// URI, PNG data-URI QR code).

        Raises:
            HTTPException: 400 when TOTP is already active.
        """
        existing = await self.repository.get_for_user(user.id)
        if existing and existing.confirmed_at is not None:
            raise_invalid_input("TOTP is already active — disable it before re-enrolling")
        if existing:
            await self.repository.delete_for_user(user.id)

        secret = pyotp.random_base32()
        uri = pyotp.TOTP(
            secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL_SECONDS
        ).provisioning_uri(name=user.email, issuer_name=settings.webauthn_rp_name)
        qr_data_uri = await asyncio.to_thread(self._render_qr_data_uri, uri)

        row = UserTOTP(user_id=user.id, secret_encrypted=encrypt_data(secret))
        self.db.add(row)
        await self.db.commit()

        logger.info("totp_enrollment_started", user_id=str(user.id))
        return secret, uri, qr_data_uri

    async def confirm(self, user: User, code: str) -> list[str]:
        """Confirm enrollment with a first valid code; generate backup codes.

        Args:
            user: The authenticated user.
            code: First TOTP code proving possession.

        Returns:
            The raw backup codes — revealed exactly once.

        Raises:
            HTTPException: 400 on missing draft, already-active TOTP, or
                invalid code.
        """
        row = await self.repository.get_for_user(user.id)
        if row is None:
            raise_invalid_input("No pending TOTP enrollment")
        if row.confirmed_at is not None:
            raise_invalid_input("TOTP is already active")

        if not self._verify_totp_code(row, code):
            track_totp_verification("confirm", "failure")
            raise_invalid_input("Invalid TOTP code")

        row.confirmed_at = datetime.now(UTC)
        codes = self._generate_backup_codes(user.id)
        await self.db.commit()

        track_totp_verification("confirm", "success")
        logger.info("totp_confirmed", user_id=str(user.id))
        return codes

    async def disable(self, user: User) -> None:
        """Disable TOTP: drop the secret and every backup code.

        Args:
            user: The authenticated user.

        Raises:
            HTTPException: 400 when TOTP is not enrolled.
        """
        row = await self.repository.get_for_user(user.id)
        if row is None:
            raise_invalid_input("TOTP is not enrolled")

        await self.repository.delete_for_user(user.id)
        await self.repository.delete_codes_for_user(user.id)
        await self.db.commit()

        logger.info("totp_disabled", user_id=str(user.id))

    async def regenerate_backup_codes(self, user: User) -> list[str]:
        """Invalidate every backup code and issue a fresh set.

        Args:
            user: The authenticated user.

        Returns:
            The raw new codes — revealed exactly once.

        Raises:
            HTTPException: 400 when TOTP is not active.
        """
        row = await self.repository.get_for_user(user.id)
        if row is None or row.confirmed_at is None:
            raise_invalid_input("TOTP is not active")

        await self.repository.delete_codes_for_user(user.id)
        codes = self._generate_backup_codes(user.id)
        await self.db.commit()

        logger.info("totp_backup_codes_regenerated", user_id=str(user.id))
        return codes

    async def get_status(self, user: User) -> TOTPStatus:
        """Report the user's TOTP state for the Security settings.

        Args:
            user: The authenticated user.

        Returns:
            Active flag, confirmation timestamp, unused backup code count.
        """
        row = await self.repository.get_for_user(user.id)
        active = row is not None and row.confirmed_at is not None
        remaining = await self.repository.count_unused_codes(user.id) if active else 0
        return TOTPStatus(
            active=active,
            confirmed_at=row.confirmed_at if row else None,
            backup_codes_remaining=remaining,
        )

    async def has_confirmed_totp(self, user_id: uuid.UUID) -> bool:
        """Whether the account requires a second login step.

        Args:
            user_id: Account UUID.

        Returns:
            True when a confirmed TOTP enrollment exists.
        """
        row = await self.repository.get_for_user(user_id)
        return row is not None and row.confirmed_at is not None

    # ------------------------------------------------------------------
    # Login verification
    # ------------------------------------------------------------------

    async def verify_for_login(self, user_id: uuid.UUID, code: str) -> None:
        """Verify the second login step: TOTP code or backup code.

        All failures collapse to a generic 401 (no oracle about which form
        was wrong).

        Args:
            user_id: Account UUID (from the consumed pending token).
            code: TOTP code or backup code.

        Raises:
            HTTPException: 401 on any failure.
        """
        row = await self.repository.get_for_user(user_id)
        if row is None or row.confirmed_at is None:
            track_totp_verification("login", "failure")
            raise_invalid_credentials()

        if self._verify_totp_code(row, code):
            await self.db.commit()  # persists last_used_step
            track_totp_verification("login", "success")
            logger.info("totp_login_verified", user_id=str(user_id), method="totp")
            return

        code_row = await self.repository.get_unused_code_by_hash(user_id, hash_backup_code(code))
        if code_row is not None:
            code_row.used_at = datetime.now(UTC)
            await self.db.commit()
            track_totp_verification("login", "success")
            logger.warning(
                "totp_backup_code_consumed",
                user_id=str(user_id),
            )
            return

        track_totp_verification("login", "failure")
        logger.warning("totp_login_rejected", user_id=str(user_id))
        raise_invalid_credentials()

    # ------------------------------------------------------------------
    # Pending-login tokens (two-step bridge)
    # ------------------------------------------------------------------

    async def create_pending_token(
        self,
        user_id: uuid.UUID,
        remember_me: bool,
        known_device: bool = False,
        fcm_token_id: str | None = None,
    ) -> str:
        """Issue the single-use token bridging password success → TOTP step.

        Args:
            user_id: Authenticated (first factor) account UUID.
            remember_me: Session duration preference carried to step two.
            known_device: A4 attestation outcome from step one.
            fcm_token_id: Attesting FCM token row id, when known.

        Returns:
            Opaque token to return to the client.
        """
        token = str(uuid.uuid4())
        redis = await get_redis_session()
        await redis.set(
            f"{REDIS_KEY_MFA_PENDING_PREFIX}{token}",
            json.dumps(
                {
                    FIELD_USER_ID: str(user_id),
                    "remember_me": remember_me,
                    "known_device": known_device,
                    "fcm_token_id": fcm_token_id,
                }
            ),
            ex=settings.mfa_pending_ttl_seconds,
        )
        return token

    async def consume_pending_token(self, token: str) -> PendingLogin | None:
        """Consume (single-use) a pending-login token.

        Args:
            token: Opaque token from the client.

        Returns:
            The pending payload, or None when unknown/expired/replayed.
        """
        redis = await get_redis_session()
        raw = await redis.getdel(f"{REDIS_KEY_MFA_PENDING_PREFIX}{token}")
        if not raw:
            return None
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        return PendingLogin(
            user_id=payload[FIELD_USER_ID],
            remember_me=bool(payload.get("remember_me", False)),
            known_device=bool(payload.get("known_device", False)),
            fcm_token_id=payload.get("fcm_token_id"),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _verify_totp_code(self, row: UserTOTP, code: str) -> bool:
        """Verify a TOTP code with window tolerance and step anti-replay.

        The matched timestep is resolved explicitly (pyotp does not report
        it) so an accepted code — or any older one — can never be replayed:
        acceptance requires ``matched_step > last_used_step``.

        Args:
            row: The user's TOTP row (mutated: ``last_used_step``).
            code: Submitted code.

        Returns:
            True when the code is valid and fresh.
        """
        code = code.strip().replace(" ", "")
        if len(code) != TOTP_DIGITS or not code.isdigit():
            return False

        secret = decrypt_data(row.secret_encrypted)
        totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL_SECONDS)
        now = datetime.now(UTC)
        current_step = int(now.timestamp()) // TOTP_INTERVAL_SECONDS

        for offset in range(-TOTP_VALID_WINDOW_STEPS, TOTP_VALID_WINDOW_STEPS + 1):
            candidate_step = current_step + offset
            at_time = datetime.fromtimestamp(candidate_step * TOTP_INTERVAL_SECONDS, tz=UTC)
            if secrets.compare_digest(totp.at(at_time), code):
                if row.last_used_step is not None and candidate_step <= row.last_used_step:
                    return False  # replay of an already-consumed (or older) step
                row.last_used_step = candidate_step
                return True
        return False

    def _generate_backup_codes(self, user_id: uuid.UUID) -> list[str]:
        """Create a fresh backup code set (hashes persisted, raws returned).

        Args:
            user_id: Owner UUID.

        Returns:
            The raw codes.
        """
        codes = [
            secrets.token_hex(MFA_BACKUP_CODE_HEX_CHARS // 2) for _ in range(MFA_BACKUP_CODES_COUNT)
        ]
        for raw in codes:
            self.db.add(MFABackupCode(user_id=user_id, code_hash=hash_backup_code(raw)))
        return codes

    @staticmethod
    def _render_qr_data_uri(uri: str) -> str:
        """Render the provisioning URI as a PNG data-URI (CPU-bound, threaded).

        Args:
            uri: otpauth:// provisioning URI.

        Returns:
            ``data:image/png;base64,...`` string.
        """
        image = qrcode.make(uri)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
