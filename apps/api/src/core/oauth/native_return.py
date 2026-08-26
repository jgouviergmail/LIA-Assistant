"""
Closing an OAuth flow on the surface that opened it.

Three flows now leave for a system browser and have to find their way back —
provider sign-in, connector authorization, and MCP server authorization. They
differ in where they land and what they say when they get there; they do not
differ in how the decision is made, so it is made once here.

Two pieces, and the second is the one that is easy to get wrong.

``oauth_return_redirect`` chooses between a deep link and a web URL. The query
is IDENTICAL either way: the destination page reads the same parameters whether
it was reached in a browser or a WebView, and letting the two drift would mean
the shell reports a different outcome than the web for the same event, with
only one of them ever exercised by a test.

``make_native_flow_probe`` builds the dependency that answers "did a shell start
this?". It reads the state WITHOUT consuming it, because it has to run before
the token exchange that spends it — and a FastAPI dependency is what guarantees
that ordering, rather than a line each callback must remember to put first.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import urlencode

from fastapi.responses import RedirectResponse

from src.core.config import settings
from src.core.native_deep_link import NativeDeepLinkHost, build_deep_link
from src.core.oauth.flow_handler import NATIVE_FLOW_METADATA_KEY
from src.core.oauth.state_peek import peek_oauth_state


def oauth_return_redirect(
    *,
    is_native: bool,
    host: NativeDeepLinkHost,
    path: str,
    params: Mapping[str, str],
) -> RedirectResponse:
    """
    Build the redirect closing an OAuth flow.

    Args:
        is_native: Whether a native shell started the flow.
        host: Deep-link host naming which flow is coming home.
        path: Web route the browser lands on, and that the shell opens on its
            OWN server's origin. Fixed by the caller, never carried in the
            link: a deep link that named its own destination would let whoever
            claims the custom scheme choose where the WebView goes next.
        params: Query the destination page reads. The same on both surfaces.

    Returns:
        A 302 the provider's browser will follow.
    """
    # `is True`, not truthiness. These endpoints are also called directly by
    # unit tests, where an unfilled `Depends(...)` default arrives as the
    # dependency OBJECT — which is truthy, and would have sent every such test,
    # and any future direct caller, down the deep-link path in a browser.
    # Caught by an existing MCP test doing exactly that.
    if is_native is True:
        return RedirectResponse(url=build_deep_link(host, params), status_code=302)
    return RedirectResponse(
        url=f"{settings.frontend_url}{path}?{urlencode(dict(params))}",
        status_code=302,
    )


def make_native_flow_probe(prefix: str) -> Callable[[str], Awaitable[bool]]:
    """
    Build the dependency answering "did a native shell start this flow?".

    Args:
        prefix: Redis key prefix the flow stores its state under. A parameter
            because the MCP flow keeps its own namespace.

    Returns:
        An async FastAPI dependency taking ``state`` from the query string.

        It returns False for a browser, an unknown or expired state, and a
        payload it cannot read. Doubt resolves towards the browser on purpose:
        a `lia://` redirect shows a desktop user nothing at all, while a web
        redirect merely inconveniences a shell.
    """

    async def probe(state: str = "") -> bool:
        payload = await peek_oauth_state(state, prefix=prefix)
        return bool(payload and payload.get(NATIVE_FLOW_METADATA_KEY) is True)

    return probe
