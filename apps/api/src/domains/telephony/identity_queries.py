"""The UI and native phone reader share the source identity projection."""

from typing import get_args

from src.domains.shared.phone_domains import PHONE_DOMAINS
from src.domains.telephony.identity import PhoneIdentity
from src.domains.telephony.schemas import TelephonyIdentityResponse
from src.domains.users.models import User
from src.infrastructure.phone_identity import (
    NativePhoneCallMode,
    PhoneIdentityData,
    PhoneIdentityProjection,
)


def assert_identity_projection_coverage() -> None:
    if set(TelephonyIdentityResponse.model_fields) != set(PhoneIdentityData.model_fields):
        raise AssertionError("New phone identity fields require native projection review")
    for name in ("call_mode", "call_mode_effective"):
        if set(get_args(TelephonyIdentityResponse.model_fields[name].annotation)) != set(
            get_args(NativePhoneCallMode)
        ):
            raise AssertionError("New phone call modes require native projection review")


assert_identity_projection_coverage()


def project_identity(
    identity: PhoneIdentity, *, verification_pending: bool = False
) -> TelephonyIdentityResponse:
    return TelephonyIdentityResponse(
        phone_number=identity.phone_number,
        verified=identity.verified,
        verified_at=identity.verified_at,
        rich_context_enabled=identity.rich_context_enabled,
        disabled_domains=list(identity.disabled_domains),
        call_mode=identity.call_mode,
        call_mode_effective=identity.call_mode_effective,
        live_available=identity.live_available,
        live_unavailable_reason=identity.live_unavailable_reason,
        available_domains=list(PHONE_DOMAINS),
        verification_pending=verification_pending,
    )


def native_identity_projection(
    user: User, identity: TelephonyIdentityResponse
) -> PhoneIdentityProjection:
    status = "available" if identity.phone_number is not None else "unset"
    if user.phone_number_encrypted and identity.phone_number is None:
        status = "unreadable"
    return PhoneIdentityProjection(
        identity=PhoneIdentityData.model_validate(identity.model_dump(mode="json")),
        number_status=status,
    )
