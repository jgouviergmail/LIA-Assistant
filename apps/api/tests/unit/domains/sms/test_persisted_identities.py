"""An SMS sender is resolved once, independently of the reading surface."""

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.sms.identity import ContactIdentity, IdentityBook, SenderIdentity


@pytest.fixture(autouse=True)
def local_metadata(monkeypatch):
    from src.domains.sms import identity_resolution

    monkeypatch.setattr(
        identity_resolution, "load_relation_book", AsyncMock(return_value=IdentityBook())
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("known", [True, False])
async def test_repeated_sms_reads_reuse_even_a_negative_resolution(monkeypatch, known):
    from src.domains.sms import identity_resolution as module

    owner = uuid4()
    scope = module.ResolutionScope(owner, uuid4(), "contacts-account", 7, b"k" * 32)
    saved: dict[str, SenderIdentity] = {}

    async def read(*args):
        return scope, dict(saved)

    async def publish(selected, values, *, assistant):
        saved.update(values)

    monkeypatch.setattr(module, "read_resolutions", read)
    monkeypatch.setattr(module, "publish_resolutions", publish)
    book = IdentityBook(
        contacts=(ContactIdentity("Alice", numbers=("12345",)),) if known else (),
        complete=True,
    )
    load = AsyncMock(return_value=book)
    monkeypatch.setattr(module, "load_identity_book", load)

    async def flight(key, *, build, read_shared, **kwargs):
        from src.infrastructure.utils.shared_flight import SharedFlightResult

        return SharedFlightResult(await build(), True, False)

    monkeypatch.setattr(module, "run_shared_flight", flight)
    for _ in range(6):
        result = await module.resolve_senders(
            owner, ["12345", "12345"], revision=7, assistant=False
        )
        assert result.identities["12345"].display_name == ("Alice" if known else "12345")
    load.assert_awaited_once_with(owner, cache_scope=f"{scope.authority}:{scope.generation}")
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_explicit_generation_change_resolves_again(monkeypatch):
    from src.domains.sms import identity_resolution as module

    owner = uuid4()
    scope = module.ResolutionScope(owner, uuid4(), "contacts-account", 7, b"k" * 32)
    saved = {"12345": SenderIdentity("Old", "contact", "resolved")}

    async def read(*args):
        return scope, dict(saved)

    async def publish(selected, values, *, assistant):
        saved.update(values)

    monkeypatch.setattr(module, "read_resolutions", read)
    monkeypatch.setattr(module, "publish_resolutions", publish)
    load = AsyncMock(return_value=IdentityBook(complete=True))
    monkeypatch.setattr(module, "load_identity_book", load)
    result = await module.resolve_senders(owner, ["12345"], revision=7, assistant=False)
    assert result.identities["12345"].display_name == "Old"
    load.assert_not_awaited()
    scope = replace(scope, generation=uuid4())
    saved.clear()

    async def flight(key, *, build, read_shared, **kwargs):
        from src.infrastructure.utils.shared_flight import SharedFlightResult

        return SharedFlightResult(await build(), True, False)

    monkeypatch.setattr(module, "run_shared_flight", flight)
    result = await module.resolve_senders(owner, ["12345"], revision=7, assistant=False)
    assert result.identities["12345"].state == "unresolved"
    load.assert_awaited_once_with(owner, cache_scope=f"{scope.authority}:{scope.generation}")
