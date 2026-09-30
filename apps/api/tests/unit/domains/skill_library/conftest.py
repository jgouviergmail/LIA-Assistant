"""The library's unit tests run against the fake hub, never the network (ADR-327).

Names resolve to a public address (the SSRF check still runs, on what the
fake answers), the shared Redis cache reads as empty and keeps nothing — each
test sees the hub as it built it — and every client the service opens is the
hub's.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.domains.agents.web_fetch import url_validator
from src.domains.skill_library import cache, service
from tests.unit.domains.skill_library.fakes import FakeHub


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_validator, "_resolve_dns_sync", lambda _host: ["93.184.216.34"])


@pytest.fixture(autouse=True)
def _no_shared_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    async def nothing(_key: str) -> None:
        return None

    async def keep_nothing(_key: str, _value: object, _ttl: int) -> None:
        return None

    monkeypatch.setattr(cache, "cached", nothing)
    monkeypatch.setattr(cache, "store", keep_nothing)


@pytest.fixture()
def hub(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeHub]:
    """The fake portal and GitHub every client of the service talks to."""
    fake = FakeHub()
    monkeypatch.setattr(service, "_client", fake.client)
    yield fake
