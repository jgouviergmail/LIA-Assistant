"""Speech synthesis must go through the egress proxy when there is one.

The demonstrator's API container sits on no routed network: its only way to
the Internet is ``HTTPS_PROXY``. Every HTTP client in the stack honours that
variable — httpx and requests read it by default — but ``edge-tts`` opens a
WebSocket through aiohttp, and aiohttp reads no proxy from the environment
unless it is told to.

So speech synthesis was advertised as ON and could not connect: the flag said
yes, the allowlist said no (measured 2026-08-07: ``CONNECT
speech.platform.bing.com:443`` answered ``403 Forbidden``), and even with the
host opened the WebSocket would have bypassed the proxy and reached a network
that does not exist from inside that container.

``edge_tts.Communicate`` takes a ``proxy`` argument. Passing it is the whole
fix, and it is right for any proxied deployment, not only this one.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


class _Recorder:
    """Stands in for ``edge_tts.Communicate`` and remembers its arguments."""

    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        type(self).calls.append(kwargs)

    async def stream(self):  # type: ignore[no-untyped-def]
        yield {"type": "audio", "data": b"\x00\x01"}


@pytest.fixture(autouse=True)
def _clear_calls() -> None:
    _Recorder.calls = []


async def _synthesize(env: dict[str, str]) -> dict[str, object]:
    from src.domains.voice.client import EdgeTTSClient

    with (
        patch("src.domains.voice.client.edge_tts.Communicate", _Recorder),
        patch.dict("os.environ", env, clear=False),
    ):
        audio = await EdgeTTSClient().synthesize(text="bonjour", voice_name="fr-FR-DeniseNeural")

    assert audio == b"\x00\x01"
    return _Recorder.calls[-1]


class TestTheProxyReachesTheWebSocket:
    async def test_it_passes_the_configured_proxy(self) -> None:
        call = await _synthesize({"HTTPS_PROXY": "http://demo-instance-egress:3128"})

        assert call.get("proxy") == "http://demo-instance-egress:3128", (
            "without this the WebSocket goes straight out, and in an envelope "
            "whose API is on no routed network it goes nowhere"
        )

    async def test_no_proxy_configured_passes_none(self) -> None:
        """A direct deployment must keep behaving exactly as before."""
        call = await _synthesize({"HTTPS_PROXY": "", "https_proxy": ""})

        assert call.get("proxy") is None

    async def test_the_synthesis_arguments_are_unchanged(self) -> None:
        call = await _synthesize({"HTTPS_PROXY": "http://p:3128"})

        assert call["text"] == "bonjour"
        assert call["voice"] == "fr-FR-DeniseNeural"


class TestTheHelperIsReadable:
    """The environment is injected: ``os.environ`` is case-INSENSITIVE on
    Windows, so the two conventional spellings collapse there and the
    precedence between them cannot be observed through the real process
    environment."""

    def test_an_empty_variable_is_not_a_proxy(self) -> None:
        from src.domains.voice.client import _configured_proxy

        assert _configured_proxy({"HTTPS_PROXY": "   ", "https_proxy": ""}) is None

    def test_the_lowercase_spelling_is_honoured_too(self) -> None:
        from src.domains.voice.client import _configured_proxy

        assert (
            _configured_proxy({"https_proxy": "http://proxy.local:3128"})
            == "http://proxy.local:3128"
        )

    def test_the_uppercase_spelling_wins(self) -> None:
        from src.domains.voice.client import _configured_proxy

        assert (
            _configured_proxy(
                {"HTTPS_PROXY": "http://upper:3128", "https_proxy": "http://lower:3128"}
            )
            == "http://upper:3128"
        )

    def test_an_absent_variable_is_not_a_proxy(self) -> None:
        from src.domains.voice.client import _configured_proxy

        assert _configured_proxy({}) is None
