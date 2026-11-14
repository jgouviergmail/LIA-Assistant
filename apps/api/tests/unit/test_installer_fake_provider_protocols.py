"""The hermetic fake provider answers the clients a fresh install really uses.

The disposable qualification (ADR-215) installs LIA on a clean machine and has a
chat answered through ``scripts/install/tests/runtime/fake_provider.py``. The
reference configuration decides which wire formats that takes: the response and
the ReAct loop answer on an OpenAI-compatible provider, five core slots on
Anthropic. A fake that speaks only one of the two fails the qualification of
every release -- and the workflow that would say so runs on GitHub alone.

So the fake is driven here by the SAME client classes the provider adapter
builds, over a real loopback socket: a shape the SDK refuses fails this test.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from types import ModuleType

import anthropic
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

_MODEL = "claude-fable-5-2"


def _fake_module() -> ModuleType:
    path = repo_root_or_skip() / "scripts" / "install" / "tests" / "runtime" / "fake_provider.py"
    spec = importlib.util.spec_from_file_location("lia_fake_provider", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAKE = _fake_module()
KEY: str = FAKE.FIXTURE_KEY


@pytest.fixture(scope="module")
def fake_url() -> Iterator[str]:
    """The fake provider on a free loopback port, stopped and joined afterwards."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), FAKE._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _claude(base_url: str, key: str = KEY) -> ChatAnthropic:
    return ChatAnthropic(
        model=_MODEL, base_url=base_url, api_key=key, max_tokens=64, max_retries=0, timeout=10
    )


def test_a_plain_answer_reaches_the_anthropic_client(fake_url: str) -> None:
    answer = _claude(fake_url).invoke("Say OK.")

    assert answer.text == "Hermetic OK."
    assert answer.response_metadata["stop_reason"] == "end_turn"
    assert answer.usage_metadata is not None and answer.usage_metadata["output_tokens"] > 0


def test_a_streamed_answer_reaches_the_anthropic_client(fake_url: str) -> None:
    """The response node streams: the SDK reads NAMED server-sent events."""
    chunks = list(_claude(fake_url).stream("Say OK."))

    assert "".join(chunk.text for chunk in chunks) == "Hermetic OK."
    assert chunks, "the stream ended without a single event the client understood"


async def test_the_asynchronous_stream_is_the_one_a_chat_turn_uses(fake_url: str) -> None:
    text = ""
    async for chunk in _claude(fake_url).astream("Say OK."):
        text += chunk.text

    assert text == "Hermetic OK."


def test_a_wrong_key_is_refused_on_the_anthropic_wire(fake_url: str) -> None:
    with pytest.raises(anthropic.AuthenticationError):
        _claude(fake_url, key="sk-not-the-fixture").invoke("Say OK.")


def test_the_token_count_a_claude_slot_asks_for_is_answered(fake_url: str) -> None:
    """``token_counter`` asks the provider itself: a 404 there would be a path of
    the turn the qualification never took in production."""
    client = anthropic.Anthropic(base_url=fake_url, api_key=KEY, max_retries=0)
    try:
        counted = client.messages.count_tokens(
            model=_MODEL, messages=[{"role": "user", "content": "Say OK."}]
        )
    finally:
        client.close()

    assert counted.input_tokens >= 1


def test_the_openai_compatible_answer_is_unchanged(fake_url: str) -> None:
    """The response and the ReAct loop of a fresh install still answer this way."""
    llm = ChatOpenAI(
        model="fake-model", base_url=f"{fake_url}/v1", api_key=KEY, max_retries=0, timeout=10
    )

    assert llm.invoke("Say OK.").text == "Hermetic OK."


@pytest.mark.parametrize(
    ("provider", "suffix"), [("anthropic", ""), ("deepseek", "/v1")], ids=["anthropic", "deepseek"]
)
def test_the_installer_key_check_passes_and_fails_against_it(
    fake_url: str, provider: str, suffix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each required provider's own header: a fake reading one of them would
    call a valid key unverified."""
    root = str(repo_root_or_skip())
    if root not in sys.path:
        sys.path.insert(0, root)
    from scripts.install.model import VerifyOutcome
    from scripts.install.verify import verify_provider_key

    monkeypatch.setenv(f"{provider.upper()}_BASE_URL", f"{fake_url}{suffix}")

    assert verify_provider_key(provider, KEY, urllib.request.urlopen) is VerifyOutcome.VALID
    assert (
        verify_provider_key(provider, "sk-not-the-fixture", urllib.request.urlopen)
        is VerifyOutcome.INVALID
    )
