"""
Authentication domain schemas (Pydantic models for API).
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.domains.shared.schemas import (
    LanguageValidatorMixin,
    PasswordValidatorMixin,
    TimezoneValidatorMixin,
    UserBase,
    password_field,
)


# Request schemas
class UserRegisterRequest(
    BaseModel, TimezoneValidatorMixin, LanguageValidatorMixin, PasswordValidatorMixin
):
    """Schema for user registration with email/password."""

    email: EmailStr = Field(..., description="User email address")
    password: str = password_field()
    full_name: str | None = Field(None, description="User full name")
    timezone: str | None = Field(None, description="User's IANA timezone")
    language: str | None = Field(
        None,
        description="User's preferred language (fr, en, es, de, it, zh-CN)",
    )
    remember_me: bool = Field(
        default=False,
        description="Remember me - extends session to 30 days instead of 7",
    )
    terms_accepted: bool = Field(
        default=False,
        description=(
            "Whether the user accepted the terms of use. Required on an "
            "instance that asks for them (public demonstrator); the rule "
            "lives in the service, not in this schema, because it depends "
            "on the deployment rather than on the payload."
        ),
    )


class UserLoginRequest(BaseModel):
    """Schema for user login with email/password."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")
    remember_me: bool = Field(
        default=False,
        description="Remember me - extends session to 30 days instead of 7",
    )
    fcm_token: str | None = Field(
        default=None,
        description="This device's FCM token, if push is enabled — attests a known "
        "device and suppresses the new-login notification (A4)",
    )


class TokenRefreshRequest(BaseModel):
    """Schema for token refresh request."""

    refresh_token: str = Field(..., description="Refresh token")


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""

    email: EmailStr = Field(..., description="User email address")


class PasswordResetConfirm(BaseModel, PasswordValidatorMixin):
    """Schema for password reset confirmation."""

    token: str = Field(..., description="Password reset token")
    new_password: str = password_field("New password")


# Response schemas
class TokenResponse(BaseModel):
    """Schema for authentication token response."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")


class UserResponse(UserBase):
    """Schema for user response in authentication flows."""

    pass  # All fields and validators inherited from UserBase


class AuthResponse(BaseModel):
    """Schema for authentication response with user info."""

    user: UserResponse = Field(..., description="User information")
    tokens: TokenResponse = Field(..., description="Authentication tokens")


class AuthResponseBFF(BaseModel):
    """Schema for BFF authentication response (session-based, no tokens exposed)."""

    user: UserResponse = Field(..., description="User information")
    message: str = Field(
        default="Authentication successful",
        description="Success message",
    )


class GoogleOAuthCallback(BaseModel):
    """Schema for Google OAuth callback data."""

    code: str = Field(..., description="Authorization code from Google")
    state: str = Field(..., description="CSRF state token")


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str = Field(..., description="Response message")
    detail: str | None = Field(default=None, description="Additional details")


# ============================================================================
# WebAuthn passkeys (security program D1, Lot 1)
# ============================================================================


class LoginResponseBFF(BaseModel):
    """Two-state login response (BFF Pattern, security program D1 Lot 2).

    Either the session was created (``user`` set, cookie sent) or a second
    factor is required (``mfa_required`` + single-use ``mfa_token`` to
    present to ``/auth/mfa/verify``). Never both.
    """

    user: UserResponse | None = Field(
        default=None, description="User information (present when the session was created)"
    )
    mfa_required: bool = Field(
        default=False, description="True when a TOTP/backup code step is required"
    )
    mfa_token: str | None = Field(
        default=None,
        description="Single-use pending token for /auth/mfa/verify (5 min TTL)",
    )
    message: str = Field(..., description="Localized status message")


class MFAVerifyRequest(BaseModel):
    """Second login step: pending token + TOTP or backup code."""

    mfa_token: str = Field(..., description="Pending token returned by /auth/login")
    code: str = Field(
        ...,
        min_length=6,
        max_length=16,
        description="6-digit TOTP code or 10-char backup code",
    )


class TOTPEnrollResponse(BaseModel):
    """TOTP enrollment material — revealed exactly once."""

    secret: str = Field(..., description="Base32 secret (shown once, for manual entry)")
    otpauth_uri: str = Field(..., description="otpauth:// provisioning URI")
    qr_data_uri: str = Field(..., description="QR code as PNG data-URI")


class TOTPConfirmRequest(BaseModel):
    """First valid code proving authenticator possession."""

    code: str = Field(..., min_length=6, max_length=8, description="6-digit TOTP code")


class TOTPBackupCodesResponse(BaseModel):
    """Backup codes — revealed exactly once."""

    backup_codes: list[str] = Field(
        ..., description="Single-use backup codes (shown once, store them safely)"
    )
    message: str = Field(..., description="Localized confirmation message")


class TOTPStatusResponse(BaseModel):
    """TOTP state for the Security settings."""

    active: bool = Field(..., description="Whether TOTP is enrolled and confirmed")
    confirmed_at: datetime | None = Field(
        default=None, description="Confirmation timestamp (null when inactive)"
    )
    backup_codes_remaining: int = Field(..., description="Number of unused backup codes")


class DeviceSessionResponse(BaseModel):
    """One live session in the "My devices" list (bounded metadata only)."""

    id: str = Field(..., description="Opaque display id (sha256 prefix — never the session id)")
    current: bool = Field(..., description="Whether this row is the caller's own session")
    ua_family: str | None = Field(default=None, description="Coarse browser family")
    os_family: str | None = Field(default=None, description="Coarse OS family")
    ip_trunc: str | None = Field(default=None, description="Truncated IP (never the full address)")
    auth_methods: list[str] = Field(..., description="How this session was authenticated")
    created_at: datetime = Field(..., description="Session creation timestamp")
    last_seen_at: datetime | None = Field(
        default=None, description="Coarse last activity (>= 15 min grain)"
    )
    device_name: str | None = Field(
        default=None, description="Real device name when the login was FCM-attested (A4)"
    )


class RevokeOthersResponse(BaseModel):
    """Result of signing out every other device."""

    revoked: int = Field(..., description="Number of sessions revoked")


class LoginNotificationsPreferenceRequest(BaseModel):
    """Toggle the new-login FCM notification (A4)."""

    enabled: bool = Field(..., description="Notify my devices on unrecognized logins")


class LoginNotificationsPreferenceResponse(BaseModel):
    """Current new-login notification preference."""

    enabled: bool = Field(..., description="Current preference state")
    message: str = Field(..., description="Localized confirmation message")


class StepUpStatusResponse(BaseModel):
    """Which re-authentication methods this account can use, and freshness."""

    methods: list[str] = Field(
        ..., description="Available step-up methods: password, passkey, totp"
    )
    password_set: bool = Field(..., description="Whether password sign-in is enabled")
    step_up_valid_until: datetime | None = Field(
        default=None, description="Until when the current session's step-up stays fresh"
    )


class StepUpPasswordRequest(BaseModel):
    """Step-up re-authentication with the account password."""

    password: str = Field(..., min_length=1, description="Current account password")


class StepUpTotpRequest(BaseModel):
    """Step-up re-authentication with a TOTP or backup code."""

    code: str = Field(
        ..., min_length=6, max_length=16, description="6-digit TOTP code or backup code"
    )


class StepUpWebAuthnVerifyRequest(BaseModel):
    """Step-up re-authentication with a passkey assertion."""

    credential: dict[str, Any] = Field(
        ..., description="navigator.credentials.get result, JSON-serialized by the client"
    )


class StepUpVerifiedResponse(BaseModel):
    """Successful step-up: freshness horizon for the session."""

    step_up_valid_until: datetime = Field(
        ..., description="Until when sensitive actions are allowed without re-verifying"
    )


class AuthFeaturesResponse(BaseModel):
    """Publicly visible authentication capabilities of this instance.

    Lets the frontend show/hide strong-auth UI without probing flag-gated
    routers (which are unmounted when disabled). Reveals nothing sensitive.
    """

    mfa_enabled: bool = Field(
        ..., description="Whether passkeys/TOTP endpoints are mounted on this instance"
    )
    terms_required: bool = Field(
        default=False,
        description=(
            "Whether registration requires accepting the terms. True on a "
            "public demonstrator: the terms are what tell a visitor the "
            "instance is wiped nightly, so the form must show them."
        ),
    )
    terms_version: str = Field(
        default="",
        description="Version of the terms the visitor is accepting.",
    )
    federated_signin_enabled: bool = Field(
        default=True,
        description=(
            "Whether signing in with an identity provider is offered. False on a "
            "public demonstrator, where the only way in is an email address and an "
            "explicit acceptance of the terms."
        ),
    )


class WebAuthnOptionsResponse(BaseModel):
    """Ceremony options for ``navigator.credentials.create`` (registration)."""

    options: str = Field(
        ..., description="PublicKeyCredentialCreationOptions as JSON (py_webauthn format)"
    )


class WebAuthnAuthOptionsResponse(BaseModel):
    """Ceremony options for ``navigator.credentials.get`` (authentication)."""

    challenge_id: str = Field(..., description="Opaque id of the single-use server-side challenge")
    options: str = Field(
        ..., description="PublicKeyCredentialRequestOptions as JSON (py_webauthn format)"
    )


class WebAuthnRegisterVerifyRequest(BaseModel):
    """Client result of a registration ceremony."""

    credential: dict[str, Any] = Field(
        ..., description="navigator.credentials.create result, JSON-serialized by the client"
    )
    label: str | None = Field(
        default=None,
        max_length=64,
        description="Optional display label for this passkey (e.g. 'iPhone')",
    )


class WebAuthnAuthenticateVerifyRequest(BaseModel):
    """Client result of an authentication ceremony."""

    challenge_id: str = Field(..., description="Challenge id from /authenticate/options")
    credential: dict[str, Any] = Field(
        ..., description="navigator.credentials.get result, JSON-serialized by the client"
    )


class WebAuthnRenameRequest(BaseModel):
    """Rename a registered passkey."""

    label: str | None = Field(
        default=None,
        max_length=64,
        description="New display label (null/empty clears the label)",
    )


class WebAuthnCredentialResponse(BaseModel):
    """A registered passkey as shown in the Security settings list.

    Never exposes key material (credential id, public key).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Credential row id (management identifier)")
    label: str | None = Field(default=None, description="User-supplied display label")
    device_type: str | None = Field(
        default=None, description="single_device or multi_device (synced passkey)"
    )
    backed_up: bool = Field(..., description="Whether the passkey is synced/backed up")
    transports: list[str] | None = Field(
        default=None, description="Authenticator transports reported at registration"
    )
    created_at: datetime = Field(..., description="Registration timestamp")
    last_used_at: datetime | None = Field(
        default=None, description="Last successful authentication timestamp"
    )


class MemoryPreferenceRequest(BaseModel):
    """Schema for updating user memory preference."""

    memory_enabled: bool = Field(..., description="Enable or disable long-term memory")


class MemoryPreferenceResponse(BaseModel):
    """Schema for memory preference update response."""

    memory_enabled: bool = Field(..., description="Current memory preference state")
    message: str = Field(
        default="Memory preference updated",
        description="Confirmation message",
    )


class HealthMetricsAgentsPreferenceRequest(BaseModel):
    """Schema for updating the Health Metrics assistant toggle (v1.17.2).

    When enabled, the assistant is allowed to read the user's health
    samples and to feed the four gated integrations (agents, Heartbeat,
    journal extractor, memory extractor).
    """

    health_metrics_agents_enabled: bool = Field(
        ...,
        description=(
            "Enable or disable assistant-level access to Health Metrics data "
            "(agents, Heartbeat source, memory/journal context)."
        ),
    )


class HealthMetricsAgentsPreferenceResponse(BaseModel):
    """Schema for Health Metrics assistant toggle update response."""

    health_metrics_agents_enabled: bool = Field(
        ..., description="Current Health Metrics assistant preference state."
    )
    message: str = Field(
        default="Health Metrics assistant preference updated",
        description="Confirmation message",
    )


class ExecutionModePreferenceRequest(BaseModel):
    """Schema for updating user execution mode preference (pipeline vs react)."""

    execution_mode: Literal["pipeline", "react"] = Field(
        ...,
        description="Execution mode: 'pipeline' (classic planner) or 'react' (ReAct agent loop)",
    )


class ExecutionModePreferenceResponse(BaseModel):
    """Schema for execution mode preference update response."""

    execution_mode: str = Field(..., description="Current execution mode preference")
    message: str = Field(
        default="Execution mode preference updated",
        description="Confirmation message",
    )


class WeatherLocationPreferenceRequest(BaseModel):
    """Schema for updating the weather last-known location opt-in flag."""

    enabled: bool = Field(
        ...,
        description=(
            "Enable or disable use of the persisted browser geolocation for "
            "proactive weather notifications. Disabling wipes any stored location."
        ),
    )


class WeatherLocationPreferenceResponse(BaseModel):
    """Schema for weather location preference update response."""

    enabled: bool = Field(..., description="Current weather location preference state")
    message: str = Field(
        default="Weather location preference updated",
        description="Confirmation message",
    )


class LastLocationUpdateRequest(BaseModel):
    """Schema for pushing a new browser geolocation sample."""

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")
    accuracy: float | None = Field(
        default=None,
        ge=0.0,
        description="Optional accuracy in meters (non-negative)",
    )


class LastLocationUpdateResponse(BaseModel):
    """Schema for last-location update response."""

    updated: bool = Field(..., description="True if a new row was written")
    throttled: bool = Field(
        ...,
        description="True if the call was throttled (< throttle window since last update)",
    )


class LastLocationViewResponse(BaseModel):
    """Schema for the read-only view of the user's stored last-known location.

    When no location is stored, all fields except ``stored`` are None.
    """

    stored: bool = Field(..., description="True if a location is currently stored")
    lat: float | None = Field(default=None, description="Latitude (only if stored)")
    lon: float | None = Field(default=None, description="Longitude (only if stored)")
    accuracy: float | None = Field(default=None, description="Accuracy in meters (only if stored)")
    updated_at: datetime | None = Field(
        default=None, description="UTC timestamp of last update (only if stored)"
    )
    stale: bool = Field(
        default=False,
        description="True if the stored location is past the configured TTL",
    )


class VoicePreferenceRequest(BaseModel):
    """Schema for updating user voice preference (TTS)."""

    voice_enabled: bool = Field(..., description="Enable or disable voice comments (TTS)")


class VoicePreferenceResponse(BaseModel):
    """Schema for voice preference update response."""

    voice_enabled: bool = Field(..., description="Current voice preference state")
    message: str = Field(
        default="Voice preference updated",
        description="Confirmation message",
    )


class VoiceModePreferenceRequest(BaseModel):
    """Schema for updating user voice mode preference (wake word + STT input).

    Both fields are optional so the same endpoint can patch the on/off
    switch and the STT backend independently.
    """

    voice_mode_enabled: bool | None = Field(
        default=None,
        description="Enable or disable voice mode (wake word detection + STT input)",
    )
    voice_stt_mode: Literal["local", "remote"] | None = Field(
        default=None,
        description=(
            "STT backend choice when voice mode is enabled: 'local' (Sherpa, free) "
            "or 'remote' (ElevenLabs Scribe, billed per audio duration)."
        ),
    )


class VoiceModePreferenceResponse(BaseModel):
    """Schema for voice mode preference update response."""

    voice_mode_enabled: bool = Field(..., description="Current voice mode preference state")
    voice_stt_mode: Literal["local", "remote"] = Field(
        ...,
        description="Current STT backend choice ('local' or 'remote').",
    )
    stt_remote_available: bool = Field(
        ...,
        description=(
            "True when the remote provider (ElevenLabs) has an API key configured "
            "and the user can opt into 'remote' STT."
        ),
    )
    message: str = Field(
        default="Voice mode preference updated",
        description="Confirmation message",
    )


class TokensDisplayPreferenceRequest(BaseModel):
    """Schema for updating user tokens display preference."""

    tokens_display_enabled: bool = Field(
        ..., description="Enable or disable token usage and costs display"
    )


class TokensDisplayPreferenceResponse(BaseModel):
    """Schema for tokens display preference update response."""

    tokens_display_enabled: bool = Field(..., description="Current tokens display preference state")
    message: str = Field(
        default="Tokens display preference updated",
        description="Confirmation message",
    )


class OnboardingPreferenceRequest(BaseModel):
    """Schema for updating user onboarding completed status."""

    onboarding_completed: bool = Field(..., description="Mark onboarding tutorial as completed")


class OnboardingPreferenceResponse(BaseModel):
    """Schema for onboarding preference update response."""

    onboarding_completed: bool = Field(..., description="Current onboarding completed status")
    message: str = Field(
        default="Onboarding preference updated",
        description="Confirmation message",
    )


class OnboardingChecklistRequest(BaseModel):
    """Update the starter checklist card state (UXR Lot 6, A10).

    True values stamp the matching ISO-UTC timestamp server-side; False/None
    leave it untouched (the card is designed to never resurface once
    dismissed or celebrated — no unset path in v1).
    """

    dismissed: bool | None = Field(
        None, description="True stamps dismissed_at — the card never renders again"
    )
    celebrated: bool | None = Field(
        None, description="True stamps celebrated_at — 100% reached (or pre-completed)"
    )


class OnboardingChecklistResponse(BaseModel):
    """Current starter checklist card state."""

    onboarding_checklist: dict[str, Any] = Field(
        ..., description="{dismissed_at, celebrated_at} ISO-UTC (possibly empty)"
    )
    message: str = Field(
        default="Checklist state updated",
        description="Confirmation message",
    )


class DebugPanelPreferenceRequest(BaseModel):
    """Schema for updating user debug panel preference."""

    debug_panel_enabled: bool = Field(
        ..., description="Enable or disable the debug panel for this user"
    )


class DebugPanelPreferenceResponse(BaseModel):
    """Schema for debug panel preference update response."""

    debug_panel_enabled: bool = Field(..., description="Current debug panel preference state")
    message: str = Field(
        default="Debug panel preference updated",
        description="Confirmation message",
    )


# ADR-083 Phase 2 cleanup: SubAgentsPreferenceRequest/Response were removed
# along with the PATCH /me/sub-agents-preference endpoint (Option B).


class DisplayModePreferenceRequest(BaseModel):
    """Schema for updating user response display mode."""

    response_display_mode: str = Field(
        ...,
        description="Response display mode: 'cards' (HTML data cards), 'html' (rich formatting), 'markdown' (plain text)",
    )


class DisplayModePreferenceResponse(BaseModel):
    """Schema for display mode preference update response."""

    response_display_mode: str = Field(..., description="Current response display mode")
    message: str = Field(
        default="Display mode preference updated",
        description="Confirmation message",
    )
