"""A password-reset token is bound to its account and to that account's password (ADR-363).

Before, a link carried the address alone: a reset finished on one link left
every other link of the hour valid, and an account deleted then re-created with
the same address inherited the links of the one that left.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.core.security.utils import (
    create_password_reset_token,
    password_fingerprint,
    reset_token_matches_account,
    verify_token,
)

pytestmark = pytest.mark.unit

_EMAIL = "person@example.com"
#: Two bcrypt-shaped hashes: "$2b$12$" + a 22-character salt + a 31-character digest.
_HASH = "$2b$12$abcdefghijklmnopqrstuuTq3hS0Lr3o2TC3vC3x3D0e2wO8b3n7K"
_OTHER_HASH = "$2b$12$zyxwvutsrqponmlkjihgfeO0uVQq3l6W7mB0fF6aG1x9yY2kZq1Ue"


@pytest.fixture(autouse=True)
def _instance_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-secret-test-secret-test-secret-test-secret")
    monkeypatch.setattr(settings, "algorithm", "HS256")


def _issued(user_id: UUID, hashed_password: str | None) -> dict[str, Any]:
    token = create_password_reset_token(_EMAIL, user_id=user_id, hashed_password=hashed_password)
    payload = verify_token(token)
    assert payload is not None
    return payload


def test_a_token_matches_the_account_and_password_it_was_issued_for() -> None:
    user_id = uuid4()

    payload = _issued(user_id, _HASH)

    assert reset_token_matches_account(
        payload, user_id=user_id, email=_EMAIL, hashed_password=_HASH
    )


def test_a_password_changed_since_issue_makes_the_token_stale() -> None:
    user_id = uuid4()

    payload = _issued(user_id, _HASH)

    assert not reset_token_matches_account(
        payload, user_id=user_id, email=_EMAIL, hashed_password=_OTHER_HASH
    )


def test_a_first_password_set_on_a_passwordless_account_retires_its_tokens() -> None:
    user_id = uuid4()

    payload = _issued(user_id, None)

    assert reset_token_matches_account(payload, user_id=user_id, email=_EMAIL, hashed_password=None)
    assert not reset_token_matches_account(
        payload, user_id=user_id, email=_EMAIL, hashed_password=_HASH
    )


def test_another_account_at_the_same_address_does_not_match() -> None:
    payload = _issued(uuid4(), _HASH)

    assert not reset_token_matches_account(
        payload, user_id=uuid4(), email=_EMAIL, hashed_password=_HASH
    )


def test_another_address_does_not_match() -> None:
    user_id = uuid4()

    payload = _issued(user_id, _HASH)

    assert not reset_token_matches_account(
        payload, user_id=user_id, email="someone.else@example.com", hashed_password=_HASH
    )


@pytest.mark.parametrize("hashed_password", [_HASH, None], ids=["password", "passwordless"])
def test_a_token_minted_before_the_binding_matches_no_account(hashed_password: str | None) -> None:
    minted_before = {"sub": _EMAIL, "type": "password_reset", "exp": 4102444800, "iat": 1790928000}

    assert not reset_token_matches_account(
        minted_before, user_id=uuid4(), email=_EMAIL, hashed_password=hashed_password
    )


def test_the_token_never_carries_the_password_hash() -> None:
    serialized = repr(_issued(uuid4(), _HASH))

    assert _HASH not in serialized
    assert _HASH[7:29] not in serialized  # the salt alone


def test_the_fingerprint_is_keyed_by_the_instance_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    first = password_fingerprint(_HASH)

    monkeypatch.setattr(settings, "secret_key", "another-secret-0123456789abcdef-another")

    assert password_fingerprint(_HASH) != first
