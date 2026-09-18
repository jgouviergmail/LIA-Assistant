"""The live-run registry (ADR-298): every worker sees every network run."""

from __future__ import annotations

import pytest

from src.domains.agents.python_sandbox.egress.registry import (
    LiveRun,
    LiveRunRegistry,
    RunCredential,
    run_key,
)
from tests.unit.domains.agents.python_sandbox.egress.fakes import FakeRedis

pytestmark = pytest.mark.unit


def _run(run_id: str = "run-1", *, hosts: tuple[str, ...] = ("api.search.brave.com",)) -> LiveRun:
    return LiveRun(
        run_id=run_id,
        user_id="7c1b1c2e-0000-4000-8000-000000000001",
        hosts=hosts,
        credentials=(
            RunCredential(
                connector="brave_search",
                host="api.search.brave.com",
                token="sbx_run1_abc",
                auth_method="header",
                auth_name="X-Subscription-Token",
                secret_path="/etc/lia-egress/config/secrets/run-1/brave_search.key",
            ),
        ),
    )


class TestRoundTrip:
    def test_every_field_survives_serialisation(self) -> None:
        run = _run()
        assert LiveRun.from_serializable_dict(run.to_serializable_dict()) == run


class TestTheRegistryIsShared:
    async def test_a_registered_run_is_listed_with_its_ttl(self) -> None:
        redis = FakeRedis()
        registry = LiveRunRegistry(redis, ttl_seconds=90)
        await registry.register(_run())
        assert await registry.live_runs() == [_run()]
        assert redis.ttls[run_key("run-1")] == 90

    async def test_two_workers_see_each_others_runs(self) -> None:
        redis = FakeRedis()
        await LiveRunRegistry(redis, ttl_seconds=90).register(_run("a"))
        await LiveRunRegistry(redis, ttl_seconds=90).register(_run("b", hosts=("example.org",)))
        listed = await LiveRunRegistry(redis, ttl_seconds=90).live_runs()
        assert {r.run_id for r in listed} == {"a", "b"}

    async def test_unregister_removes_the_run(self) -> None:
        redis = FakeRedis()
        registry = LiveRunRegistry(redis, ttl_seconds=90)
        await registry.register(_run())
        await registry.unregister("run-1")
        assert await registry.live_runs() == []
        assert run_key("run-1") not in redis.store

    async def test_an_expired_entry_is_pruned_from_the_index(self) -> None:
        """A worker killed mid-run leaves an index member whose entry expired
        by TTL; listing must neither fail nor keep the ghost."""
        redis = FakeRedis()
        registry = LiveRunRegistry(redis, ttl_seconds=90)
        await registry.register(_run("dead"))
        await registry.register(_run("alive"))
        redis.expire_now(run_key("dead"))
        listed = await registry.live_runs()
        assert [r.run_id for r in listed] == ["alive"]
        assert await redis.smembers(registry.index_key) == {"alive"}

    async def test_a_cache_failure_propagates(self) -> None:
        """The ruleset writer must REFUSE a run it cannot register — never
        launch a network container the proxy knows nothing about."""
        with pytest.raises(ConnectionError):
            await LiveRunRegistry(FakeRedis(broken=True), ttl_seconds=90).register(_run())
