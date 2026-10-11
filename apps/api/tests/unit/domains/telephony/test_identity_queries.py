"""UI/native phone identity shares the same source projection and hides verification material."""

from importlib import import_module
from uuid import uuid4

import pytest
from pydantic import create_model

from src.domains.telephony.identity import PhoneIdentity
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def test_native_projection_distinguishes_unreadable_number_from_absence() -> None:
    module = import_module("src.domains.telephony.identity_queries")
    identity = PhoneIdentity(
        phone_number=None,
        verified=False,
        verified_at=None,
        rich_context_enabled=True,
        live_available=False,
        live_unavailable_reason="callback_not_public",
    )
    user = User(id=uuid4(), is_active=True, phone_number_encrypted="private-broken-cipher")
    result = module.project_identity(identity, verification_pending=False)
    native = module.native_identity_projection(user, result)
    assert native.number_status == "unreadable"
    assert native.identity.phone_number is None and native.identity.call_mode_effective == "direct"
    assert "private-broken-cipher" not in native.model_dump_json()
    user.phone_number_encrypted = None
    assert module.native_identity_projection(user, result).number_status == "unset"


def test_new_phone_identity_fields_require_explicit_projection_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.identity_queries")
    module.assert_identity_projection_coverage()
    future = create_model(
        "FuturePhoneIdentity",
        __base__=module.TelephonyIdentityResponse,
        verification_code=(str, "private"),
    )
    monkeypatch.setattr(module, "TelephonyIdentityResponse", future)
    with pytest.raises(AssertionError, match="review"):
        module.assert_identity_projection_coverage()
