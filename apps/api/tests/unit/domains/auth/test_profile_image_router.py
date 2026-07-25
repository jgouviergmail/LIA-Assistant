"""Google profile-image proxy — redirect handling and response bounds (SEC-026).

The proxy exists for COEP compatibility: ``lh3.googleusercontent.com`` sends no
CORS headers, so the avatar is fetched server-side.

The route used to pass ``follow_redirects=True`` and inspect only the FINAL URL,
so a redirect to a forbidden host had already been contacted — and its body
buffered through the unbounded ``response.content`` — by the time it was
rejected. Redirects are now followed manually and every hop is validated before
it is requested.

Two properties are asserted together on purpose, because either one alone is
easy to satisfy wrongly:

- a disallowed hop is NEVER contacted (the security goal), and
- a Google→Google redirect still resolves (the nominal avatar path), which is
  what rules out "just stop following redirects" as a fix.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.constants import PROFILE_IMAGE_MAX_BYTES, PROFILE_IMAGE_MAX_REDIRECTS
from src.core.exceptions import ValidationError
from src.domains.auth.profile_image_router import proxy_profile_image

_ALLOWED_URL = "https://lh3.googleusercontent.com/a/avatar=s96-c"


def _make_user() -> MagicMock:
    """Build a mock authenticated user carrying only what the route reads."""
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _make_response(
    *,
    status_code: int = 200,
    content: bytes = b"\xff\xd8\xff\xe0JPEG",
    content_type: str = "image/jpeg",
    location: str | None = None,
    chunk_size: int | None = None,
) -> MagicMock:
    """Build a mock streaming ``httpx.Response``.

    Args:
        status_code: HTTP status returned by the upstream.
        content: Raw body bytes, yielded by ``aiter_bytes``.
        content_type: ``content-type`` header value.
        location: When set, the response is a redirect to this target.
        chunk_size: Split the body into chunks of this size (default: one chunk).

    Returns:
        MagicMock response with ``is_redirect``, ``headers`` and ``aiter_bytes``.
    """
    response = MagicMock()
    response.status_code = status_code
    response.is_redirect = location is not None
    headers = {"content-type": content_type}
    if location is not None:
        headers["location"] = location
    response.headers = headers

    size = chunk_size or max(len(content), 1)
    chunks = [content[i : i + size] for i in range(0, len(content), size)] or [b""]

    async def _aiter_bytes():
        for chunk in chunks:
            yield chunk

    response.aiter_bytes = _aiter_bytes
    return response


def _patch_client(*responses: MagicMock) -> tuple[MagicMock, MagicMock]:
    """Patch ``httpx.AsyncClient`` so no network call is ever made.

    Args:
        *responses: Responses returned by successive ``client.stream()`` calls,
            in order — one per redirect hop.

    Returns:
        Tuple of (patcher, stream_mock). ``stream_mock`` records every hop the
        route actually issued, which is what the SSRF assertions inspect.
    """
    stream_mock = MagicMock()
    queue = list(responses)

    def _stream(_method: str, url: str, **_kwargs):
        response = queue.pop(0) if queue else _make_response()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    stream_mock.side_effect = _stream

    client = MagicMock()
    client.stream = stream_mock

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    patcher = patch(
        "src.domains.auth.profile_image_router.httpx.AsyncClient",
        MagicMock(return_value=ctx),
    )
    return patcher, stream_mock


def _requested_urls(stream_mock: MagicMock) -> list[str]:
    """URLs the route actually contacted, in order."""
    return [call.args[1] for call in stream_mock.call_args_list]


class TestProfileImageProxyGuards:
    """Input validation performed before any outbound request."""

    @pytest.mark.asyncio
    async def test_disallowed_host_is_rejected(self):
        """A host outside the Google allowlist is refused."""
        patcher, stream_mock = _patch_client()
        with patcher, pytest.raises(ValidationError):
            await proxy_profile_image(url="https://evil.example/x.jpg", current_user=_make_user())
        stream_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_https_scheme_is_rejected(self):
        """An allowlisted host over plain HTTP is refused."""
        patcher, stream_mock = _patch_client()
        with patcher, pytest.raises(ValidationError):
            await proxy_profile_image(
                url="http://lh3.googleusercontent.com/a/avatar",
                current_user=_make_user(),
            )
        stream_mock.assert_not_called()


class TestProfileImageProxyNominalPath:
    """The path that must keep working — user avatars."""

    @pytest.mark.asyncio
    async def test_direct_fetch_returns_image(self):
        """An allowlisted URL is proxied with COEP-friendly headers."""
        patcher, _ = _patch_client(_make_response())
        with patcher:
            result = await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())

        assert result.status_code == 200
        assert result.media_type == "image/jpeg"
        assert result.headers["cross-origin-resource-policy"] == "cross-origin"

    @pytest.mark.asyncio
    async def test_redirect_between_google_hosts_succeeds(self):
        """Google→Google redirect is followed (guards the nominal avatar path).

        This is what makes SEC-026 non-trivial: the fix must keep following
        redirects *within* the allowlist, so it cannot simply stop following
        them. Google routinely redirects avatar URLs between lh3/lh4 hosts and
        between size variants — breaking this breaks every avatar.
        """
        patcher, stream_mock = _patch_client(
            _make_response(location="https://lh4.googleusercontent.com/a/avatar=s96-c"),
            _make_response(content=b"REDIRECTED-JPEG"),
        )
        with patcher:
            result = await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())

        assert result.status_code == 200
        assert _requested_urls(stream_mock) == [
            _ALLOWED_URL,
            "https://lh4.googleusercontent.com/a/avatar=s96-c",
        ]

    @pytest.mark.asyncio
    async def test_relative_redirect_is_resolved_against_the_current_url(self):
        """A `Location: /path` redirect stays on the same allowlisted host."""
        patcher, stream_mock = _patch_client(
            _make_response(location="/a/other=s96-c"),
            _make_response(),
        )
        with patcher:
            result = await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())

        assert result.status_code == 200
        assert _requested_urls(stream_mock)[1] == "https://lh3.googleusercontent.com/a/other=s96-c"

    @pytest.mark.asyncio
    async def test_upstream_error_status_is_surfaced(self):
        """A non-200 upstream response raises instead of proxying the body."""
        patcher, _ = _patch_client(_make_response(status_code=404))
        with patcher, pytest.raises(Exception) as exc_info:
            await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())
        assert not isinstance(exc_info.value, ValidationError)


class TestProfileImageProxyRedirectSsrf:
    """SEC-026 — a redirect is a destination we choose, so it is validated."""

    @pytest.mark.asyncio
    async def test_redirect_to_disallowed_host_is_never_contacted(self):
        """The disallowed hop must not be requested at all.

        This assertion was inverted: the route used to follow the whole chain
        with `follow_redirects=True` and only inspect the final URL afterwards,
        so the forbidden host had already been contacted and its body buffered
        (`response.content`, unbounded) by the time it was rejected.
        """
        patcher, stream_mock = _patch_client(
            _make_response(location="https://evil.example/payload"),
        )

        with patcher, pytest.raises(ValidationError):
            await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())

        assert _requested_urls(stream_mock) == [_ALLOWED_URL]
        assert not any("evil.example" in u for u in _requested_urls(stream_mock))

    @pytest.mark.asyncio
    async def test_redirect_to_private_address_is_never_contacted(self):
        """An internal address is refused like any other non-allowlisted host."""
        patcher, stream_mock = _patch_client(
            _make_response(location="http://169.254.169.254/latest/meta-data/"),
        )

        with patcher, pytest.raises(ValidationError):
            await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())

        assert _requested_urls(stream_mock) == [_ALLOWED_URL]

    @pytest.mark.asyncio
    async def test_redirect_loop_is_bounded(self):
        """A self-referencing redirect ends instead of spinning forever."""
        patcher, stream_mock = _patch_client(
            *[_make_response(location=_ALLOWED_URL) for _ in range(10)]
        )

        with patcher, pytest.raises(ValidationError):
            await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())

        assert len(_requested_urls(stream_mock)) <= PROFILE_IMAGE_MAX_REDIRECTS + 1

    @pytest.mark.asyncio
    async def test_redirect_without_location_is_refused(self):
        """A 302 with no Location cannot be followed — it is an error, not a loop."""
        response = _make_response()
        response.is_redirect = True  # redirect flag without a Location header

        patcher, _ = _patch_client(response)
        with patcher, pytest.raises(ValidationError):
            await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())


class TestProfileImageProxyResponseSize:
    """SEC-026 — an allowlisted host is not trusted to be finite."""

    @pytest.mark.asyncio
    async def test_oversized_body_is_refused(self):
        """A body past the ceiling is rejected instead of being buffered."""
        oversized = b"x" * (PROFILE_IMAGE_MAX_BYTES + 1024)

        patcher, _ = _patch_client(_make_response(content=oversized, chunk_size=64 * 1024))
        with patcher, pytest.raises(ValidationError):
            await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())

    @pytest.mark.asyncio
    async def test_body_under_the_ceiling_is_returned_whole(self):
        """A normal avatar delivered in several chunks is reassembled intact."""
        payload = b"a" * 200_000

        patcher, _ = _patch_client(_make_response(content=payload, chunk_size=8192))
        with patcher:
            result = await proxy_profile_image(url=_ALLOWED_URL, current_user=_make_user())

        # StreamingResponse wraps a sync iterator into an async one.
        streamed = b"".join([chunk async for chunk in result.body_iterator])
        assert streamed == payload
