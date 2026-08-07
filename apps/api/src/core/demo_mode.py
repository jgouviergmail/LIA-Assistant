"""Guards that close real-account paths on a public demonstrator instance.

A demonstrator hands a throwaway account to a stranger. Every route that
would tie that account to a REAL identity — the visitor's mailbox, or their
Google account itself — must refuse, because the account is wiped nightly and
the person has no relationship with the operator.

Two paths do that, and they are siblings:

- **connector linking** (``/connectors/<service>/authorize|callback``): the
  visitor grants the instance access to their own data;
- **federated sign-in** (``/auth/<provider>/login|callback``): the visitor
  creates the account FROM their real identity — bypassing the terms, which
  are enforced on the registration path only (owner arbitration 6), and
  spending the operator's OAuth client on strangers.

Lot 2 closed the first and missed the second, because the guard lived in the
connectors domain and only ever watched ``/connectors``. It lives here now:
one module, one doctrine, and the network edge in front of both.

Both classify by SHAPE, never by a list of providers or services — the point
is that the next one is covered the day it is mounted, not the day someone
remembers this file.

Created: 2026-08-06 (live-demonstrator programme; lot 2 guard generalised in
lot 6 after the route census found federated sign-in wide open)
"""

from __future__ import annotations

from fastapi import Request

from src.core.config import settings
from src.core.exceptions import raise_permission_denied

#: Path segments that start, complete, or test an account link.
#:
#: Linking is not only OAuth — that was the lot-2 blind spot the lot-6 route
#: census exposed. Apple and API-key connectors are activated by TYPING
#: credentials ("tests credentials, then creates connectors"), and Philips Hue
#: pairs over the local network. Same risk as an authorize redirect, different
#: verb, and none of them were refused.
_LINKING_SEGMENTS = frozenset(
    {
        # OAuth redirect flow.
        "authorize",
        "callback",
        # Credentials typed into the instance.
        "activate",
        "validate",
        "rotate",
        # Local-network pairing, and the reachability probes around it.
        "pair",
        "discover",
        "test",
    }
)

#: Final path segments that start or complete a federated sign-in.
_SIGNIN_SEGMENTS = frozenset({"login", "callback"})

#: Path segment under which the authentication routes are mounted.
_AUTH_SEGMENT = "auth"

#: Path segment under which the connector routes are mounted.
_CONNECTORS_SEGMENT = "connectors"


def is_account_linking_path(path: str) -> bool:
    """Whether this path starts, completes, or tests an account link.

    Matches WHOLE SEGMENTS anywhere in the path, never substrings. Both halves
    matter and both were learned the hard way:

    - anywhere, because the verb is not always last —
      ``/philips-hue/activate/local`` is an activation;
    - whole segments, because ``/connectors/authorized-apps`` is a listing,
      not an authorize endpoint, and must keep working.

    Only the part AFTER ``/connectors`` is examined. ``test``, ``validate``
    and ``discover`` are ordinary words: a function living in ``core`` that
    matched them anywhere would bite the day someone mounts this guard on
    another router — and the bite would be a 403 nobody could explain.

    Args:
        path: Request path.

    Returns:
        True when the path would tie a real account to this instance.
    """
    segments = [segment for segment in path.strip("/").split("/") if segment]
    if _CONNECTORS_SEGMENT not in segments:
        return False
    after = segments[segments.index(_CONNECTORS_SEGMENT) + 1 :]
    return bool(set(after) & _LINKING_SEGMENTS)


def is_federated_signin_path(path: str) -> bool:
    """Whether this path signs in through an identity provider.

    Recognises the SHAPE ``…/auth/<provider>/<login|callback>``: exactly one
    segment between ``auth`` and the verb. That shape is what separates
    ``/auth/google/login`` (a provider) from ``/auth/login`` (the password
    form the demonstrator depends on) without naming either.

    Args:
        path: Request path.

    Returns:
        True when the path is a provider sign-in or its callback.
    """
    segments = [segment for segment in path.strip("/").split("/") if segment]
    if len(segments) < 3 or segments[-1] not in _SIGNIN_SEGMENTS:
        return False
    # <auth>/<provider>/<verb>: the provider is the only segment in between.
    return segments[-3] == _AUTH_SEGMENT


async def forbid_account_linking_in_demo(request: Request) -> None:
    """Refuse OAuth account linking when the instance is a demonstrator.

    Read-only connector endpoints are untouched: showing which categories
    exist and that they are unconfigured is part of what the demonstrator
    demonstrates.

    Args:
        request: Incoming request.

    Raises:
        AuthorizationError: 403 when a visitor tries to link a real account.
    """
    if not settings.demo_mode_enabled:
        return
    if not is_account_linking_path(request.url.path):
        return
    raise_permission_denied(
        action="link",
        resource_type="connector",
        details=(
            "Account linking is disabled on the public demonstrator: visitor "
            "accounts are wiped nightly and must never hold real credentials."
        ),
    )


async def forbid_federated_signin_in_demo(request: Request) -> None:
    """Refuse provider sign-in when the instance is a demonstrator.

    The demonstrator has exactly one way in — an email address and the terms
    — because that is what tells a visitor their account disappears tonight.
    A provider sign-in would create the account without ever showing it.

    Args:
        request: Incoming request.

    Raises:
        AuthorizationError: 403 when a visitor tries to sign in with a
            real identity provider.
    """
    if not settings.demo_mode_enabled:
        return
    if not is_federated_signin_path(request.url.path):
        return
    raise_permission_denied(
        action="sign_in",
        resource_type="identity_provider",
        details=(
            "Signing in with an identity provider is disabled on the public "
            "demonstrator: accounts are created with an email address and an "
            "explicit acceptance of the terms, which state that everything is "
            "wiped nightly."
        ),
    )
