"""The application's own tokens survive the move from python-jose to PyJWT.

Dependency programme, lot 5. An e-mail verification or a password-reset link
carries an HS256 token signed with ``settings.secret_key``; a link sent before
the deploy must still open after it. The token below was minted by python-jose
3.5.0, with the claims the application writes, before the library changed.
"""

import pytest

from src.core.config import settings
from src.core.security.utils import create_password_reset_token, verify_token

pytestmark = pytest.mark.unit

_SECRET = "recorded-secret-0123456789abcdef-recorded-secret"
#: Minted by python-jose 3.5.0 (HS256, the secret above) on 2026-10-02; expires on 2100-01-01.
_MINTED_BY_PYTHON_JOSE = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwZXJzb25AZXhhbXBsZS5jb20iLCJ0eXBlIjoicGFz"
    "c3dvcmRfcmVzZXQiLCJleHAiOjQxMDI0NDQ4MDAsImlhdCI6MTc5MDkyODAwMCwianRpIjoibWludGVkLWJ5LXB5dGhv"
    "bi1qb3NlLTMuNS4wIn0.hoCsy1Ra-I7ZiLLmpaKPdiF-X3Okm1H_jHshy1snShs"
)


@pytest.fixture
def recorded_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", _SECRET)
    monkeypatch.setattr(settings, "algorithm", "HS256")


@pytest.mark.usefixtures("recorded_secret")
def test_a_link_sent_before_the_swap_still_opens() -> None:
    assert verify_token(_MINTED_BY_PYTHON_JOSE) == {
        "sub": "person@example.com",
        "type": "password_reset",
        "exp": 4102444800,
        "iat": 1790928000,
        "jti": "minted-by-python-jose-3.5.0",
    }


@pytest.mark.usefixtures("recorded_secret")
def test_a_token_minted_now_is_read_back() -> None:
    payload = verify_token(create_password_reset_token("person@example.com"))

    assert payload is not None
    assert (payload["sub"], payload["type"]) == ("person@example.com", "password_reset")


@pytest.mark.usefixtures("recorded_secret")
@pytest.mark.parametrize(
    "token",
    ["", "not.a.jwt", _MINTED_BY_PYTHON_JOSE[:-4] + "AAAA"],
    ids=["empty", "garbage", "altered signature"],
)
def test_a_token_that_is_not_ours_is_refused(token: str) -> None:
    assert verify_token(token) is None


def test_another_secret_refuses_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "another-secret-0123456789abcdef-another-secret")
    monkeypatch.setattr(settings, "algorithm", "HS256")

    assert verify_token(_MINTED_BY_PYTHON_JOSE) is None
