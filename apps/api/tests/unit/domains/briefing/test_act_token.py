"""A dashboard act token is honoured for its account, its context and its lifetime only."""

from __future__ import annotations

import base64
import string
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from src.domains.briefing.act_token import (
    briefing_context_digest,
    new_act_id,
    sign_act,
    verify_act,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)
TODAY = date(2026, 10, 28)


def _digest(
    *,
    hidden: frozenset[str] = frozenset({"health"}),
    language: str = "fr",
    timezone: str = "Europe/Paris",
    local_day: date = TODAY,
) -> str:
    return briefing_context_digest(
        hidden=hidden, language=language, timezone=timezone, local_day=local_day
    )


def test_act_roundtrip_and_tamper() -> None:
    owner, act_id, digest = uuid4(), new_act_id(), _digest()
    token = sign_act(
        act_id=act_id, user_id=owner, context_digest=digest, expires_at=NOW + timedelta(minutes=5)
    )

    assert verify_act(token, user_id=owner, context_digest=digest, now=NOW) == ("valid", act_id)
    assert verify_act(token, user_id=uuid4(), context_digest=digest, now=NOW).check == "foreign"
    later = NOW + timedelta(minutes=5)
    assert verify_act(token, user_id=owner, context_digest=digest, now=later).check == "expired"
    other_day = _digest(local_day=date(2026, 10, 29))
    verdict = verify_act(token, user_id=owner, context_digest=other_day, now=NOW)
    assert verdict == ("context_changed", None)

    payload, _, signature = token.rpartition(".")
    middle = len(payload) // 2
    flipped = payload[:middle] + ("A" if payload[middle] != "A" else "B") + payload[middle + 1 :]
    # The last character carries padding bits a lenient decoder ignores: toggling one
    # spells the SAME payload differently.
    alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + "-_"
    respelled = payload[:-1] + alphabet[alphabet.index(payload[-1]) ^ 1]
    assert base64.urlsafe_b64decode(respelled + "==") == base64.urlsafe_b64decode(payload + "==")
    for forged in (flipped, respelled, payload + "!"):
        verdict = verify_act(f"{forged}.{signature}", user_id=owner, context_digest=digest, now=NOW)
        assert verdict == ("malformed", None)
    for garbage in ("", ".", "not-a-token", f"{payload}."):
        verdict = verify_act(garbage, user_id=owner, context_digest=digest, now=NOW)
        assert verdict == ("malformed", None)


@pytest.mark.parametrize(
    "changed",
    [
        _digest(hidden=frozenset()),
        _digest(language="en"),
        _digest(timezone="America/New_York"),
        _digest(local_day=date(2026, 10, 29)),
    ],
    ids=["hidden", "language", "timezone", "local_day"],
)
def test_every_context_field_changes_the_digest(changed: str) -> None:
    assert changed != _digest()


def test_hidden_order_does_not_change_the_digest() -> None:
    assert _digest(hidden=frozenset({"a", "b"})) == _digest(hidden=frozenset({"b", "a"}))


def test_a_signed_payload_of_another_shape_is_malformed() -> None:
    """The signature vouches for the bytes, never for their shape."""
    from src.domains.briefing.act_token import _encode, _signature

    owner, digest = uuid4(), _digest()
    dotted = sign_act(
        act_id="act.with-a-dot",
        user_id=owner,
        context_digest=digest,
        expires_at=NOW + timedelta(minutes=5),
    )
    payload = f"{new_act_id()}.{owner}.{digest}.soon".encode()
    undated = f"{_encode(payload)}.{_signature(payload)}"

    for token in (dotted, undated):
        verdict = verify_act(token, user_id=owner, context_digest=digest, now=NOW)
        assert verdict == ("malformed", None)
