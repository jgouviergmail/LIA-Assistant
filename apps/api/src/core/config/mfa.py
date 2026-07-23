"""MFA configuration module (security program D1).

Settings for strong authentication: WebAuthn passkeys (Lot 1) and, from
Lot 2 on, TOTP + backup codes. Composed into the main ``Settings`` class
via multiple inheritance (see ``src/core/config/__init__.py``).
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    MFA_MAX_PASSKEYS_PER_USER_DEFAULT,
    MFA_PENDING_TTL_SECONDS_DEFAULT,
    STEP_UP_WINDOW_SECONDS_DEFAULT,
    WEBAUTHN_CHALLENGE_TTL_SECONDS_DEFAULT,
    WEBAUTHN_RP_NAME_DEFAULT,
)


class MFASettings(BaseSettings):
    """Strong-authentication (MFA / passkeys) settings."""

    mfa_enabled: bool = Field(
        default=False,
        description="Master switch for strong-auth features (passkeys, TOTP). "
        "The WebAuthn/TOTP routers are not mounted when disabled.",
    )

    webauthn_rp_id: str = Field(
        default="",
        description="WebAuthn Relying Party ID (registrable domain seen by the browser). "
        "Empty = derived from the frontend_url hostname.",
    )

    webauthn_rp_name: str = Field(
        default=WEBAUTHN_RP_NAME_DEFAULT,
        description="Human-readable Relying Party name shown by authenticators.",
    )

    webauthn_expected_origin: str = Field(
        default="",
        description="Expected WebAuthn client origin for ceremony verification. "
        "Empty = frontend_url.",
    )

    webauthn_challenge_ttl_seconds: int = Field(
        default=WEBAUTHN_CHALLENGE_TTL_SECONDS_DEFAULT,
        gt=0,
        description="TTL of pending WebAuthn challenges in Redis (single-use).",
    )

    mfa_max_passkeys_per_user: int = Field(
        default=MFA_MAX_PASSKEYS_PER_USER_DEFAULT,
        gt=0,
        description="Maximum number of registered passkeys per account.",
    )

    mfa_pending_ttl_seconds: int = Field(
        default=MFA_PENDING_TTL_SECONDS_DEFAULT,
        gt=0,
        description="Lifetime of the single-use pending token bridging the two "
        "steps of a password+TOTP login.",
    )

    step_up_window_seconds: int = Field(
        default=STEP_UP_WINDOW_SECONDS_DEFAULT,
        gt=0,
        description="How long a successful step-up re-authentication stays fresh "
        "for sensitive actions (revocations, exports, MFA management).",
    )

    @field_validator("webauthn_rp_id", "webauthn_expected_origin", mode="before")
    @classmethod
    def _reject_leaked_env_comments(cls, v: object) -> object:
        """Fail fast on .env inline-comment leakage (boot, not first ceremony).

        Docker compose does NOT strip inline comments when the value before
        ``#`` is empty: ``KEY=   # comment`` reaches the process as
        ``# comment``. A Relying Party ID or origin can never legitimately
        contain ``#`` or whitespace, so such a value is always a leaked
        comment — refuse to boot with a clear message.
        """
        if not isinstance(v, str):
            return v
        stripped = v.strip()
        if "#" in stripped or " " in stripped:
            raise ValueError(
                "leaked .env inline comment detected — remove the inline comment "
                "from the empty-valued WEBAUTHN_* variable in your .env"
            )
        return stripped
