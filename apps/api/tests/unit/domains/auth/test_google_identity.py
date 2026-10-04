"""The profile picture a Google sign-in leaves on an account.

The service's two doors (a returning account, an account linked by its address)
are proven on PostgreSQL in ``tests/integration/test_auth_service_refactored.py``;
this module pins the rule they share, inside the fast gate.
"""

import pytest

from src.domains.auth.google_identity import google_picture_after_sign_in

pytestmark = pytest.mark.unit

_STORED = "https://lh3.googleusercontent.com/a/stored"
_SENT = "https://lh3.googleusercontent.com/a/today"


@pytest.mark.parametrize(
    ("stored", "sent", "expected"),
    [
        pytest.param(_STORED, _SENT, _SENT, id="the-url-google-sends-wins"),
        pytest.param(_STORED, _STORED, _STORED, id="the-same-url-stays"),
        pytest.param(None, _SENT, _SENT, id="a-first-picture-is-taken"),
        pytest.param(_STORED, None, _STORED, id="no-claim-erases-nothing"),
        pytest.param(_STORED, "", _STORED, id="an-empty-claim-erases-nothing"),
        pytest.param(None, None, None, id="nothing-stays-nothing"),
    ],
)
def test_the_picture_after_a_google_sign_in(
    stored: str | None, sent: str | None, expected: str | None
) -> None:
    """Google's URL is a snapshot: the one a sign-in sends replaces the stored one."""
    assert google_picture_after_sign_in(stored, sent) == expected
