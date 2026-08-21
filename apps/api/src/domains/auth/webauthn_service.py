"""WebAuthn passkey service (security program D1, Lot 1).

Orchestrates py_webauthn ceremonies around the domain concerns the library
does not cover: single-use challenge lifecycle in Redis, credential
persistence and caps, ownership, sign-count bookkeeping, and mapping of
ceremony failures onto the centralized error contract (generic 401 on the
anonymous login path — no credential enumeration).
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_WEBAUTHN_AUTH_CHALLENGE_PREFIX,
    REDIS_KEY_WEBAUTHN_REG_CHALLENGE_PREFIX,
    REDIS_KEY_WEBAUTHN_STEPUP_CHALLENGE_PREFIX,
    WEBAUTHN_LABEL_MAX_LENGTH,
)
from src.core.exceptions import (
    raise_invalid_credentials,
    raise_invalid_input,
    raise_not_found_or_unauthorized,
)
from src.domains.auth.models import WebAuthnCredential
from src.domains.auth.webauthn_repository import WebAuthnCredentialRepository
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.observability.metrics_mfa import track_webauthn_ceremony

logger = structlog.get_logger(__name__)


class WebAuthnService:
    """Passkey enrollment, login, and credential management."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with a database session.

        Args:
            db: SQLAlchemy async session.
        """
        self.db = db
        self.repository = WebAuthnCredentialRepository(db)

    # ------------------------------------------------------------------
    # Relying Party configuration
    # ------------------------------------------------------------------

    @staticmethod
    def _rp_id() -> str:
        """Relying Party ID: explicit setting, else the frontend hostname."""
        if settings.webauthn_rp_id:
            return settings.webauthn_rp_id
        return urlparse(settings.frontend_url).hostname or "localhost"

    @staticmethod
    def _expected_origin() -> str:
        """Expected browser origin: explicit setting, else the frontend URL."""
        return settings.webauthn_expected_origin or settings.frontend_url

    # ------------------------------------------------------------------
    # Registration (enrollment)
    # ------------------------------------------------------------------

    async def generate_registration_options(self, user: User) -> str:
        """Start a passkey enrollment ceremony for an authenticated user.

        Discoverable credentials are required (arbitration A1): resident key
        + user verification, so the passkey can drive conditional-UI login.

        Args:
            user: The authenticated user enrolling a new passkey.

        Returns:
            The ceremony options as JSON (client feeds them to
            ``navigator.credentials.create``).

        Raises:
            HTTPException: 400 when the per-account passkey cap is reached.
        """
        existing = await self.repository.list_for_user(user.id)
        if len(existing) >= settings.mfa_max_passkeys_per_user:
            raise_invalid_input(
                "Maximum number of passkeys reached for this account",
                max_passkeys=settings.mfa_max_passkeys_per_user,
            )

        options = generate_registration_options(
            rp_id=self._rp_id(),
            rp_name=settings.webauthn_rp_name,
            user_id=str(user.id).encode("utf-8"),
            user_name=user.email,
            user_display_name=user.full_name or user.email,
            timeout=settings.webauthn_challenge_ttl_seconds * 1000,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred.credential_id))
                for cred in existing
            ],
        )

        redis = await get_redis_session()
        await redis.set(
            f"{REDIS_KEY_WEBAUTHN_REG_CHALLENGE_PREFIX}{user.id}",
            bytes_to_base64url(options.challenge),
            ex=settings.webauthn_challenge_ttl_seconds,
        )

        logger.info("webauthn_registration_options_issued", user_id=str(user.id))
        return options_to_json(options)

    async def verify_registration(
        self,
        user: User,
        credential: dict[str, Any] | str,
        label: str | None,
    ) -> WebAuthnCredential:
        """Complete a passkey enrollment ceremony and persist the credential.

        Args:
            user: The authenticated user enrolling the passkey.
            credential: The ``navigator.credentials.create`` result (JSON
                string or already-parsed dict).
            label: Optional user-supplied display label.

        Returns:
            The persisted credential row.

        Raises:
            HTTPException: 400 on missing/expired challenge, invalid
                ceremony, duplicate credential, cap reached, or bad label.
        """
        label = self._validate_label(label)

        redis = await get_redis_session()
        challenge_raw = await redis.getdel(f"{REDIS_KEY_WEBAUTHN_REG_CHALLENGE_PREFIX}{user.id}")
        if not challenge_raw:
            raise_invalid_input(
                "No pending passkey registration challenge (expired or never issued)"
            )
        challenge_b64 = self._as_str(challenge_raw)

        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=base64url_to_bytes(challenge_b64),
                expected_rp_id=self._rp_id(),
                expected_origin=self._expected_origin(),
                require_user_verification=True,
            )
        except InvalidRegistrationResponse as exc:
            track_webauthn_ceremony("register", "failure")
            logger.warning(
                "webauthn_registration_rejected",
                user_id=str(user.id),
                error=str(exc),
            )
            raise_invalid_input("Invalid WebAuthn registration response")

        credential_id_b64 = bytes_to_base64url(verified.credential_id)
        if await self.repository.get_by_credential_id(credential_id_b64):
            track_webauthn_ceremony("register", "failure")
            raise_invalid_input("This passkey is already registered")

        existing = await self.repository.list_for_user(user.id)
        if len(existing) >= settings.mfa_max_passkeys_per_user:
            raise_invalid_input(
                "Maximum number of passkeys reached for this account",
                max_passkeys=settings.mfa_max_passkeys_per_user,
            )

        row = WebAuthnCredential(
            user_id=user.id,
            credential_id=credential_id_b64,
            public_key=bytes_to_base64url(verified.credential_public_key),
            sign_count=verified.sign_count,
            transports=self._extract_transports(credential),
            aaguid=verified.aaguid,
            device_type=verified.credential_device_type.value,
            backed_up=verified.credential_backed_up,
            label=label,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)

        track_webauthn_ceremony("register", "success")
        logger.info(
            "webauthn_credential_registered",
            user_id=str(user.id),
            credential_row_id=str(row.id),
            device_type=row.device_type,
            backed_up=row.backed_up,
        )
        return row

    # ------------------------------------------------------------------
    # Authentication (login)
    # ------------------------------------------------------------------

    async def generate_authentication_options(self) -> tuple[str, str]:
        """Start an anonymous passkey login ceremony.

        No ``allow_credentials`` list is sent (discoverable credentials,
        arbitration A1) so nothing about registered accounts leaks.

        Returns:
            Tuple of (challenge_id, options JSON). The client returns the
            challenge_id with the assertion so the server can retrieve the
            single-use challenge.
        """
        options = generate_authentication_options(
            rp_id=self._rp_id(),
            timeout=settings.webauthn_challenge_ttl_seconds * 1000,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        challenge_id = str(uuid.uuid4())
        redis = await get_redis_session()
        await redis.set(
            f"{REDIS_KEY_WEBAUTHN_AUTH_CHALLENGE_PREFIX}{challenge_id}",
            bytes_to_base64url(options.challenge),
            ex=settings.webauthn_challenge_ttl_seconds,
        )

        logger.debug("webauthn_authentication_options_issued", challenge_id=challenge_id)
        return challenge_id, options_to_json(options)

    async def verify_authentication(
        self,
        challenge_id: str,
        credential: dict[str, Any] | str,
    ) -> User:
        """Complete a passkey login ceremony and resolve the account.

        All failure modes on this anonymous path collapse to a generic 401
        (no credential/account enumeration). py_webauthn itself rejects
        sign-count regressions (clone detection) — surfaced here as the
        same generic 401 plus a WARN log and failure metric.

        Args:
            challenge_id: The id returned by ``generate_authentication_options``.
            credential: The ``navigator.credentials.get`` result (JSON
                string or already-parsed dict).

        Returns:
            The authenticated, active user.

        Raises:
            HTTPException: 401 on any ceremony or account failure.
        """
        redis = await get_redis_session()
        challenge_raw = await redis.getdel(
            f"{REDIS_KEY_WEBAUTHN_AUTH_CHALLENGE_PREFIX}{challenge_id}"
        )
        if not challenge_raw:
            track_webauthn_ceremony("authenticate", "failure")
            raise_invalid_credentials()
        challenge_b64 = self._as_str(challenge_raw)

        credential_id_b64 = self._extract_credential_id(credential)
        row = await self.repository.get_by_credential_id(credential_id_b64)
        if row is None:
            track_webauthn_ceremony("authenticate", "failure")
            logger.warning("webauthn_unknown_credential", challenge_id=challenge_id)
            raise_invalid_credentials()

        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=base64url_to_bytes(challenge_b64),
                expected_rp_id=self._rp_id(),
                expected_origin=self._expected_origin(),
                credential_public_key=base64url_to_bytes(row.public_key),
                credential_current_sign_count=row.sign_count,
                require_user_verification=True,
            )
        except InvalidAuthenticationResponse as exc:
            track_webauthn_ceremony("authenticate", "failure")
            logger.warning(
                "webauthn_authentication_rejected",
                user_id=str(row.user_id),
                credential_row_id=str(row.id),
                error=str(exc),
            )
            raise_invalid_credentials()

        user = await UserRepository(self.db).get_user_minimal_for_session(row.user_id)
        if user is None or not user.is_active or user.is_deleted:
            track_webauthn_ceremony("authenticate", "failure")
            logger.warning(
                "webauthn_login_inactive_account",
                user_id=str(row.user_id),
            )
            raise_invalid_credentials()

        row.sign_count = verified.new_sign_count
        row.last_used_at = datetime.now(UTC)
        await self.db.commit()

        track_webauthn_ceremony("authenticate", "success")
        logger.info(
            "webauthn_login_succeeded",
            user_id=str(user.id),
            credential_row_id=str(row.id),
        )
        return user

    # ------------------------------------------------------------------
    # Step-up re-authentication (authenticated ceremony)
    # ------------------------------------------------------------------

    async def generate_stepup_options(self, user: User) -> str:
        """Start a step-up passkey ceremony for an authenticated user.

        Unlike the anonymous login ceremony, the allow-list is restricted to
        the user's own credentials.

        Args:
            user: The authenticated user re-verifying.

        Returns:
            The ceremony options as JSON.

        Raises:
            HTTPException: 400 when the account has no passkeys.
        """
        credentials = await self.repository.list_for_user(user.id)
        if not credentials:
            raise_invalid_input("No passkeys registered on this account")

        options = generate_authentication_options(
            rp_id=self._rp_id(),
            timeout=settings.webauthn_challenge_ttl_seconds * 1000,
            user_verification=UserVerificationRequirement.REQUIRED,
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred.credential_id))
                for cred in credentials
            ],
        )

        redis = await get_redis_session()
        await redis.set(
            f"{REDIS_KEY_WEBAUTHN_STEPUP_CHALLENGE_PREFIX}{user.id}",
            bytes_to_base64url(options.challenge),
            ex=settings.webauthn_challenge_ttl_seconds,
        )
        return options_to_json(options)

    async def verify_stepup(self, user: User, credential: dict[str, Any] | str) -> None:
        """Complete a step-up passkey ceremony (ownership enforced).

        Args:
            user: The authenticated user re-verifying.
            credential: The ``navigator.credentials.get`` result.

        Raises:
            HTTPException: 400 on missing/expired challenge, foreign or
                unknown credential, or an invalid assertion.
        """
        redis = await get_redis_session()
        challenge_raw = await redis.getdel(f"{REDIS_KEY_WEBAUTHN_STEPUP_CHALLENGE_PREFIX}{user.id}")
        if not challenge_raw:
            raise_invalid_input("No pending step-up challenge (expired or never issued)")
        challenge_b64 = self._as_str(challenge_raw)

        credential_id_b64 = self._extract_credential_id(credential)
        row = await self.repository.get_by_credential_id(credential_id_b64)
        if row is None or row.user_id != user.id:
            track_webauthn_ceremony("step_up", "failure")
            raise_invalid_input("Unknown passkey for this account")

        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=base64url_to_bytes(challenge_b64),
                expected_rp_id=self._rp_id(),
                expected_origin=self._expected_origin(),
                credential_public_key=base64url_to_bytes(row.public_key),
                credential_current_sign_count=row.sign_count,
                require_user_verification=True,
            )
        except InvalidAuthenticationResponse as exc:
            track_webauthn_ceremony("step_up", "failure")
            logger.warning(
                "webauthn_stepup_rejected",
                user_id=str(user.id),
                credential_row_id=str(row.id),
                error=str(exc),
            )
            raise_invalid_input("Invalid passkey assertion")

        row.sign_count = verified.new_sign_count
        row.last_used_at = datetime.now(UTC)
        await self.db.commit()
        track_webauthn_ceremony("step_up", "success")

    # ------------------------------------------------------------------
    # Credential management
    # ------------------------------------------------------------------

    async def list_credentials(self, user: User) -> list[WebAuthnCredential]:
        """List the user's registered passkeys, oldest first.

        Args:
            user: The authenticated owner.

        Returns:
            The user's credential rows.
        """
        return await self.repository.list_for_user(user.id)

    async def rename_credential(
        self, user: User, row_id: uuid.UUID, label: str | None
    ) -> WebAuthnCredential:
        """Rename an owned passkey.

        Args:
            user: The authenticated owner.
            row_id: Credential row UUID.
            label: New label (validated, may be None to clear).

        Returns:
            The updated credential row.

        Raises:
            HTTPException: 404 when absent or not owned (hide existence).
        """
        label = self._validate_label(label)
        row = await self.repository.get_for_user(user.id, row_id)
        if row is None:
            raise_not_found_or_unauthorized("webauthn_credential", row_id)

        row.label = label
        await self.db.commit()
        await self.db.refresh(row)

        logger.info(
            "webauthn_credential_renamed",
            user_id=str(user.id),
            credential_row_id=str(row_id),
        )
        return row

    async def delete_credential(self, user: User, row_id: uuid.UUID) -> None:
        """Revoke (delete) an owned passkey.

        Args:
            user: The authenticated owner.
            row_id: Credential row UUID.

        Raises:
            HTTPException: 404 when absent or not owned (hide existence);
                400 when it is the last passkey of a password-less account
                (A8: the last strong method is never revocable).
        """
        row = await self.repository.get_for_user(user.id, row_id)
        if row is None:
            raise_not_found_or_unauthorized("webauthn_credential", row_id)

        if user.hashed_password is None:
            remaining = await self.repository.list_for_user(user.id)
            if len(remaining) <= 1:
                raise_invalid_input(
                    "Cannot revoke the last passkey while password sign-in is "
                    "disabled — re-enable a password first (email reset)"
                )

        await self.db.delete(row)
        await self.db.commit()

        logger.info(
            "webauthn_credential_revoked",
            user_id=str(user.id),
            credential_row_id=str(row_id),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _as_str(value: bytes | str) -> str:
        """Normalize a Redis payload to str (decode_responses yields str at
        runtime, but redis-py types GETDEL as bytes-capable)."""
        return value.decode("utf-8") if isinstance(value, bytes) else value

    @staticmethod
    def _validate_label(label: str | None) -> str | None:
        """Normalize and validate a user-supplied passkey label.

        Args:
            label: Raw label input.

        Returns:
            Stripped label, or None when empty.

        Raises:
            HTTPException: 400 when the label exceeds the length cap.
        """
        if label is None:
            return None
        label = label.strip()
        if not label:
            return None
        if len(label) > WEBAUTHN_LABEL_MAX_LENGTH:
            raise_invalid_input(
                "Passkey label too long",
                max_length=WEBAUTHN_LABEL_MAX_LENGTH,
            )
        return label

    @staticmethod
    def _extract_transports(credential: dict[str, Any] | str) -> list[str] | None:
        """Extract the transports hint from the raw client registration payload.

        py_webauthn's VerifiedRegistration does not surface transports; they
        only exist in the raw ``response.transports`` field.

        Args:
            credential: Raw client payload (dict or JSON string).

        Returns:
            The transports list, or None when absent/malformed.
        """
        try:
            data: Any = json.loads(credential) if isinstance(credential, str) else credential
            transports = data.get("response", {}).get("transports")
        except json.JSONDecodeError, AttributeError:
            return None
        if isinstance(transports, list) and all(isinstance(t, str) for t in transports):
            return transports
        return None

    @staticmethod
    def _extract_credential_id(credential: dict[str, Any] | str) -> str:
        """Extract the base64url credential id from an assertion payload.

        Args:
            credential: Raw client payload (dict or JSON string).

        Returns:
            The base64url credential id.

        Raises:
            HTTPException: 401 when the payload carries no credential id
                (generic — anonymous path).
        """
        try:
            data: Any = json.loads(credential) if isinstance(credential, str) else credential
            credential_id = data.get("rawId") or data.get("id")
        except json.JSONDecodeError, AttributeError:
            credential_id = None
        if not isinstance(credential_id, str) or not credential_id:
            raise_invalid_credentials()
        return credential_id
