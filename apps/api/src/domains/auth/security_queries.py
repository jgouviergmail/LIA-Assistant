"""Reviewed security-state projections shared with the account UI."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.auth.models import WebAuthnCredential
from src.domains.auth.schemas import (
    AuthFeaturesResponse,
    StepUpStatusResponse,
    TOTPStatusResponse,
    WebAuthnCredentialResponse,
)
from src.domains.auth.totp_service import TOTPService
from src.domains.users.models import User


class AccountSecurityProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    features: AuthFeaturesResponse
    totp: TOTPStatusResponse | None = None
    passkeys: list[WebAuthnCredentialResponse] | None = None
    total: int = Field(default=0, ge=0)
    next_cursor: UUID | None = None
    unavailable_reason: str | None = None
    password_set: bool
    available_methods: list[str] | None = None
    step_up_freshness: Literal["unknown", "fresh", "stale"] = "unknown"
    step_up_valid_until: datetime | None = None


def effective_auth_features() -> AuthFeaturesResponse:
    return AuthFeaturesResponse(
        mfa_enabled=settings.mfa_enabled,
        terms_required=settings.demo_mode_enabled,
        terms_version=settings.demo_terms_version if settings.demo_mode_enabled else "",
        federated_signin_enabled=not settings.demo_mode_enabled,
    )


def methods_for_account(user: User, *, has_passkeys: bool, has_totp: bool) -> list[str]:
    methods: list[str] = []
    if user.hashed_password is not None:
        methods.append("password")
    if user.oauth_provider:
        methods.append(f"oauth_{user.oauth_provider}")
    if has_passkeys:
        methods.append("passkey")
    if has_totp:
        methods.append("totp")
    return methods


def assert_security_projection_coverage() -> None:
    shapes = (
        (
            AuthFeaturesResponse,
            {"mfa_enabled", "terms_required", "terms_version", "federated_signin_enabled"},
        ),
        (TOTPStatusResponse, {"active", "confirmed_at", "backup_codes_remaining"}),
        (StepUpStatusResponse, {"methods", "password_set", "step_up_valid_until"}),
        (
            WebAuthnCredentialResponse,
            {"id", "label", "device_type", "backed_up", "transports", "created_at", "last_used_at"},
        ),
    )
    if any(set(model.model_fields) != fields for model, fields in shapes):
        raise AssertionError("New security UI fields require explicit native projection review")


assert_security_projection_coverage()


async def read_passkey_page(
    db: AsyncSession, actor_id: UUID, *, cursor: UUID | None, limit: int
) -> tuple[list[WebAuthnCredentialResponse], int, UUID | None]:
    if not 1 <= limit <= 50:
        raise ValueError("Passkey page outside allowed bounds")
    query = select(WebAuthnCredential).where(WebAuthnCredential.user_id == actor_id)
    if cursor is not None:
        previous = await db.scalar(query.where(WebAuthnCredential.id == cursor))
        if previous is None:
            raise ValueError("Passkey cursor unavailable; restart at the first page")
        query = query.where(
            tuple_(WebAuthnCredential.created_at, WebAuthnCredential.id)
            > (previous.created_at, previous.id)
        )
    rows = await db.scalars(
        query.order_by(WebAuthnCredential.created_at.asc(), WebAuthnCredential.id.asc()).limit(
            limit + 1
        )
    )
    selected = list(rows.all())
    visible = [WebAuthnCredentialResponse.model_validate(row) for row in selected[:limit]]
    total = await db.scalar(
        select(func.count())
        .select_from(WebAuthnCredential)
        .where(WebAuthnCredential.user_id == actor_id)
    )
    return visible, int(total or 0), visible[-1].id if len(selected) > limit else None


async def read_account_security(
    db: AsyncSession, actor: User, *, section: str, cursor: UUID | None, limit: int
) -> AccountSecurityProjection:
    if section not in {"overview", "totp", "passkeys"}:
        raise ValueError("Unknown security read section")
    if not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    result = AccountSecurityProjection(
        features=effective_auth_features(), password_set=actor.hashed_password is not None
    )
    if not result.features.mfa_enabled:
        return result.model_copy(
            update={
                "unavailable_reason": "MFA_DISABLED",
                "available_methods": methods_for_account(actor, has_passkeys=False, has_totp=False),
            }
        )
    if section in {"overview", "totp"}:
        state = await TOTPService(db).get_status(actor)
        result.totp = TOTPStatusResponse(
            active=state.active,
            confirmed_at=state.confirmed_at,
            backup_codes_remaining=state.backup_codes_remaining,
        )
    if section in {"overview", "passkeys"}:
        result.passkeys, result.total, result.next_cursor = await read_passkey_page(
            db, actor.id, cursor=cursor, limit=limit
        )
    if section == "overview":
        result.available_methods = methods_for_account(
            actor,
            has_passkeys=result.total > 0,
            has_totp=result.totp is not None and result.totp.active,
        )
    return result
