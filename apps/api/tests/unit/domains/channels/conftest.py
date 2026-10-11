"""Channel tests use the real injected assistant adapter with their existing service doubles."""

from collections.abc import Iterator

import pytest

from src.domains.agents.api.channel_gateway import build_channel_gateway
from src.infrastructure.channels.assistant_gateway import configure_channel_gateway


@pytest.fixture(autouse=True)
def configured_channel_gateway() -> Iterator[None]:
    previous = configure_channel_gateway(build_channel_gateway())
    try:
        yield
    finally:
        configure_channel_gateway(previous)
