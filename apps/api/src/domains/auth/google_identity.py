"""What LIA trusts in Google's answer to a sign-in, and what it refuses.

A Google sign-in hands back two different things, and they deserve different
trust. The account ``id`` IS the identity: stable, Google's own, matched as-is.
The ``email`` is a CLAIM about an address, and it decides whether the sign-in
reaches an account somebody else registered — so it is trusted only when Google
vouches for it, and even then it grants nothing the account had not been granted.
"""

from collections.abc import Mapping
from typing import Literal

#: Why a sign-in was refused. Bounded on purpose: the value travels into the
#: redirect the browser follows and into a metric label, so it must never be
#: free text.
GoogleSignInRefusal = Literal["email_not_verified", "account_deleted"]


def google_email_is_verified(userinfo: Mapping[str, object]) -> bool:
    """Whether Google vouches for the address in a userinfo v2 answer.

    The v2 schema documents ``verified_email`` with a default of ``true``:
    "Always verified because we only return the user's primary email address"
    (discovery document, read 2026-09-23). An ABSENT flag is therefore the
    documented default and reads as verified. Only that default or an explicit
    ``true`` passes; ``false``, a string or a null is refused.

    Args:
        userinfo: The JSON object Google's userinfo endpoint returned.

    Returns:
        True when the address may be trusted.
    """
    return userinfo.get("verified_email", True) is True


class GoogleSignInRefusedError(Exception):
    """The account rules refuse this sign-in; the reason is safe to show."""

    def __init__(self, reason: GoogleSignInRefusal) -> None:
        """Carry the bounded reason the callback redirects with.

        Args:
            reason: Why the sign-in cannot proceed.
        """
        super().__init__(reason)
        self.reason: GoogleSignInRefusal = reason
