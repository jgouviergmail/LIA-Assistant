"""
Where a connector authorization sends the user back to.

Ten callbacks each built this redirect with their own f-string, which is ten
places to remember when the destination changes — and the native shells made it
change. This module is the one place now.

Unlike sign-in, a connector callback needs no handoff: the flow is stateless,
the user id travels in the server-side OAuth state, and the connector is
already persisted by the time we get here. Nothing has to be transferred. All
the shell needs is to be brought back to the front, on the right page.

The query is deliberately IDENTICAL on both surfaces. The settings page reads
the same parameters whether it was reached in a browser or in a WebView; if the
two drifted, the shell would report a different outcome than the web for the
same event, and only one of them would ever be exercised by a test.
"""

from __future__ import annotations

from uuid import UUID

from fastapi.responses import RedirectResponse

from src.core.constants import REDIS_KEY_OAUTH_STATE_PREFIX
from src.core.native_deep_link import NativeDeepLinkHost
from src.core.oauth.native_return import make_native_flow_probe, oauth_return_redirect

#: Page both surfaces land on. The shell appends the query to its OWN server's
#: origin rather than receiving an absolute URL — carrying one would let
#: whoever intercepts the custom scheme choose where the WebView goes next.
_SETTINGS_PATH = "/dashboard/settings"


def _return_to(is_native: bool, params: dict[str, str]) -> RedirectResponse:
    """
    Build the redirect closing a connector flow, for whichever surface began it.

    Args:
        is_native: Whether a native shell started the flow.
        params: Query the settings page will read.

    Returns:
        A 302 to the app, or to the web settings page.
    """
    return oauth_return_redirect(
        is_native=is_native,
        host=NativeDeepLinkHost.CONNECTOR_CALLBACK,
        path=_SETTINGS_PATH,
        params=params,
    )


def connector_success_return(
    *,
    is_native: bool,
    connector_type: str,
    connector_id: UUID,
) -> RedirectResponse:
    """
    Send the user back after a connector was authorized.

    Args:
        is_native: Whether a native shell started the flow.
        connector_type: The connector's type, as the settings page names it.
        connector_id: The connector that was just created.

    Returns:
        A 302 the provider's browser will follow.
    """
    return _return_to(
        is_native,
        {
            "connector_added": "true",
            "connector_id": str(connector_id),
            "connector_type": connector_type,
        },
    )


def connector_error_return(*, is_native: bool, error_code: str) -> RedirectResponse:
    """
    Send the user back after a connector authorization failed.

    Branching here matters more than on the success path, not less: a shell
    user left in a browser after a failure has no connector to find later and
    nothing on screen explaining what went wrong.

    Args:
        is_native: Whether a native shell started the flow.
        error_code: Classified cause, which the settings page renders.

    Returns:
        A 302 the provider's browser will follow.
    """
    return _return_to(is_native, {"connector_error": error_code})


#: Did a native shell start this connector flow?
#:
#: Declared as a parameter on every connector callback so it runs BEFORE the
#: endpoint body — which matters, because the token exchange the body performs
#: SPENDS the state, and this reads it. The sign-in callback makes the same move
#: by hand, for the same reason.
oauth_return_is_native = make_native_flow_probe(REDIS_KEY_OAUTH_STATE_PREFIX)
