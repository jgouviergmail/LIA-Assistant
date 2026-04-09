"""
Authentication domain schemas (Pydantic models for API).
"""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

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


class UserLoginRequest(BaseModel):
    """Schema for user login with email/password."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")
    remember_me: bool = Field(
        default=False,
        description="Remember me - extends session to 30 days instead of 7",
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
    """Schema for updating user voice mode preference (wake word + STT input)."""

    voice_mode_enabled: bool = Field(
        ..., description="Enable or disable voice mode (wake word detection + STT input)"
    )


class VoiceModePreferenceResponse(BaseModel):
    """Schema for voice mode preference update response."""

    voice_mode_enabled: bool = Field(..., description="Current voice mode preference state")
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


class SubAgentsPreferenceRequest(BaseModel):
    """Schema for updating user sub-agents delegation preference."""

    sub_agents_enabled: bool = Field(
        ..., description="Enable or disable delegation to specialized sub-agents"
    )


class SubAgentsPreferenceResponse(BaseModel):
    """Schema for sub-agents preference update response."""

    sub_agents_enabled: bool = Field(
        ..., description="Current sub-agents delegation preference state"
    )
    message: str = Field(
        default="Sub-agents preference updated",
        description="Confirmation message",
    )


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
