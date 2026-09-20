"""Unit tests for the person's own phone number — declared, stored encrypted, verified (lot 1).

The repository is faked at its two doors (``get_by_id`` / ``update``) so the
tests exercise the service's rules — E.164 or refusal, a changed number loses
its verification, the seam that hands the number to callers ONLY when verified
— and never a stubbed session's identity map.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.telephony.identity import TelephonyIdentityService


class _FakeUsers:
    """The two repository doors the service reads and writes."""

    def __init__(self, user: Any) -> None:
        self.user = user
        self.updates: list[dict[str, Any]] = []

    async def get_by_id(self, user_id, include_inactive: bool = False):  # noqa: ANN001
        return self.user if self.user is not None and self.user.id == user_id else None

    async def update(self, instance, data):  # noqa: ANN001
        self.updates.append(dict(data))
        for key, value in data.items():
            setattr(instance, key, value)
        return instance


class _FakeDb:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _user(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": uuid4(),
        "phone_number_encrypted": None,
        "phone_number_verified_at": None,
        "phone_rich_context_enabled": True,
        "phone_disabled_domains": [],
        "phone_call_mode": "delegated",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _service(user: Any) -> tuple[TelephonyIdentityService, _FakeUsers, _FakeDb]:
    db = _FakeDb()
    users = _FakeUsers(user)
    return TelephonyIdentityService(db, users=users), users, db  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _country_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telephony_default_country_code", "+33", raising=False)


@pytest.mark.unit
async def test_identity_of_a_person_with_no_number_is_empty() -> None:
    user = _user()
    service, _, _ = _service(user)
    identity = await service.get_identity(user.id)
    assert identity.phone_number is None
    assert identity.verified is False
    assert identity.rich_context_enabled is True


@pytest.mark.unit
async def test_unknown_account_is_refused() -> None:
    service, _, _ = _service(_user())
    with pytest.raises(ResourceNotFoundError):
        await service.get_identity(uuid4())


@pytest.mark.unit
async def test_set_number_stores_e164_encrypted_and_unverified() -> None:
    user = _user()
    service, users, db = _service(user)

    identity = await service.set_number(user.id, "06 12 34 56 78")

    assert identity.phone_number == "+33612345678"
    assert identity.verified is False
    assert decrypt_data(user.phone_number_encrypted) == "+33612345678"
    assert user.phone_number_verified_at is None
    assert db.commits == 1


@pytest.mark.unit
async def test_set_number_refuses_what_is_not_a_line() -> None:
    user = _user()
    service, users, _ = _service(user)
    with pytest.raises(ValidationError):
        await service.set_number(user.id, "Marie")
    assert users.updates == []


@pytest.mark.unit
async def test_changing_a_verified_number_loses_the_verification() -> None:
    user = _user(
        phone_number_encrypted=encrypt_data("+33612345678"),
        phone_number_verified_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    service, _, _ = _service(user)

    identity = await service.set_number(user.id, "+33698765432")

    assert identity.verified is False
    assert user.phone_number_verified_at is None


@pytest.mark.unit
async def test_setting_the_same_number_again_keeps_the_verification() -> None:
    verified_at = datetime(2026, 9, 1, tzinfo=UTC)
    user = _user(
        phone_number_encrypted=encrypt_data("+33612345678"),
        phone_number_verified_at=verified_at,
    )
    service, users, _ = _service(user)

    identity = await service.set_number(user.id, "06 12 34 56 78")

    assert identity.verified is True
    assert user.phone_number_verified_at == verified_at
    assert users.updates == []


@pytest.mark.unit
async def test_clear_number_drops_number_and_verification() -> None:
    user = _user(
        phone_number_encrypted=encrypt_data("+33612345678"),
        phone_number_verified_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    service, _, db = _service(user)

    await service.clear_number(user.id)

    assert user.phone_number_encrypted is None
    assert user.phone_number_verified_at is None
    assert db.commits == 1


@pytest.mark.unit
async def test_verified_number_is_handed_out_only_when_verified() -> None:
    unverified = _user(phone_number_encrypted=encrypt_data("+33612345678"))
    service, _, _ = _service(unverified)
    assert await service.verified_number(unverified.id) is None

    verified = _user(
        phone_number_encrypted=encrypt_data("+33612345678"),
        phone_number_verified_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    service, _, _ = _service(verified)
    assert await service.verified_number(verified.id) == "+33612345678"


@pytest.mark.unit
async def test_mark_verified_stamps_now() -> None:
    user = _user(phone_number_encrypted=encrypt_data("+33612345678"))
    service, _, db = _service(user)

    identity = await service.mark_verified(user.id)

    assert identity.verified is True
    assert user.phone_number_verified_at is not None
    assert user.phone_number_verified_at.tzinfo is not None
    assert db.commits == 1


@pytest.mark.unit
async def test_rich_context_switch_is_persisted() -> None:
    user = _user()
    service, _, db = _service(user)

    identity = await service.set_rich_context(user.id, False)

    assert identity.rich_context_enabled is False
    assert user.phone_rich_context_enabled is False
    assert db.commits == 1


@pytest.mark.unit
async def test_disabled_domains_are_persisted_as_a_sorted_set_and_read_back() -> None:
    """Lot 8: the DISABLED set is stored, so a domain the phone starts
    offering later is on by default."""
    user = _user()
    service, users, db = _service(user)

    identity = await service.set_disabled_domains(user.id, ["email", "event", "email"])

    assert identity.disabled_domains == ("email", "event")
    assert user.phone_disabled_domains == ["email", "event"]
    assert users.updates[-1] == {"phone_disabled_domains": ["email", "event"]}
    assert db.commits == 1
    # A value stored under an older vocabulary reads as nothing rather than as a switch.
    user.phone_disabled_domains = ["email", "not_a_domain"]
    assert (await service.get_identity(user.id)).disabled_domains == ("email",)


@pytest.mark.unit
async def test_disabled_domains_refuse_what_the_phone_does_not_offer() -> None:
    user = _user()
    service, users, db = _service(user)
    with pytest.raises(ValidationError):
        await service.set_disabled_domains(user.id, ["devops"], language="fr")
    assert users.updates == [] and db.commits == 0


@pytest.mark.unit
async def test_unreadable_ciphertext_reads_as_no_number() -> None:
    """A key rotation must not turn the settings page into a 500."""
    user = _user(
        phone_number_encrypted="not-a-token",
        phone_number_verified_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    service, _, _ = _service(user)

    identity = await service.get_identity(user.id)

    assert identity.phone_number is None
    assert identity.verified is False
    assert await service.verified_number(user.id) is None


@pytest.mark.unit
async def test_mark_verified_refuses_when_no_number_is_declared() -> None:
    """A verification stamp with no number under it would be a verified line
    nobody can read — refused, like a start without a number."""
    from src.core.exceptions import ResourceConflictError

    user = _user(phone_number_encrypted=None, phone_number_verified_at=None)
    service, users, _ = _service(user)
    with pytest.raises(ResourceConflictError):
        await service.mark_verified(user.id)
    assert users.updates == []


# --- the call mode (ADR-301): Live by default, Live direct on request ---------


@pytest.mark.unit
async def test_the_call_mode_is_live_by_default_and_read_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_url", "https://lia-back.example.com", raising=False)
    monkeypatch.setattr(settings, "telephony_callback_base_url", None, raising=False)
    user = _user()
    service, _, _ = _service(user)
    identity = await service.get_identity(user.id)
    assert identity.call_mode == "delegated"
    assert identity.live_available is True
    assert identity.live_unavailable_reason is None
    assert identity.call_mode_effective == "delegated"


@pytest.mark.unit
async def test_the_call_mode_is_persisted_and_refuses_an_unknown_value() -> None:
    user = _user()
    service, users, db = _service(user)
    identity = await service.set_call_mode(user.id, "direct")
    assert identity.call_mode == "direct"
    assert users.updates == [{"phone_call_mode": "direct"}]
    assert db.commits == 1
    with pytest.raises(ValidationError):
        await service.set_call_mode(user.id, "loud")


@pytest.mark.unit
async def test_live_is_unavailable_when_the_vendor_cannot_call_this_api_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A private callback host means the delegation webhook can never arrive:
    the choice stays stored, the EFFECTIVE mode says what a call will run."""
    monkeypatch.setattr(settings, "api_url", "https://localhost:8000", raising=False)
    monkeypatch.setattr(settings, "telephony_callback_base_url", None, raising=False)
    user = _user(phone_call_mode="delegated")
    service, _, _ = _service(user)
    identity = await service.get_identity(user.id)
    assert identity.call_mode == "delegated"
    assert identity.live_available is False
    assert identity.live_unavailable_reason == "callback_not_public"
    assert identity.call_mode_effective == "direct"


@pytest.mark.unit
async def test_a_declared_callback_base_url_wins_over_the_api_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_url", "https://localhost:8000", raising=False)
    monkeypatch.setattr(
        settings, "telephony_callback_base_url", "https://tunnel.example.org", raising=False
    )
    user = _user()
    service, _, _ = _service(user)
    identity = await service.get_identity(user.id)
    assert identity.live_available is True
    assert identity.call_mode_effective == "delegated"
