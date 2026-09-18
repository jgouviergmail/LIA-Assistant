"""The publisher: one run served = registered, keyed, rendered, reloaded — and
undone in the order that never leaves the proxy pointing at a missing file."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import yaml

from src.domains.agents.python_sandbox.egress.proxy_client import EgressProxyUnavailable
from src.domains.agents.python_sandbox.egress.publisher import EgressPublisher
from src.domains.agents.python_sandbox.egress.registry import (
    RULESET_CLAIM_KEY,
    LiveRun,
    LiveRunRegistry,
    RunCredential,
)
from src.domains.agents.python_sandbox.egress.ruleset import RulesetConfig
from tests.unit.domains.agents.python_sandbox.egress.fakes import FakeRedis

pytestmark = pytest.mark.unit


class RecordingProxy:
    """Snapshots what the ruleset and the secrets dir looked like at each reload."""

    def __init__(self, config_dir: Path, *, fail: bool = False) -> None:
        self.config_dir = config_dir
        self.fail = fail
        self.reloads: list[tuple[list[str], list[str]]] = []

    async def reload(self) -> None:
        doc = yaml.safe_load((self.config_dir / "proxy.yaml").read_text(encoding="utf-8"))
        hosts = doc["transforms"][0]["config"]["domains"]
        secrets_dir = self.config_dir / "secrets"
        present = sorted(p.name for p in secrets_dir.iterdir()) if secrets_dir.exists() else []
        self.reloads.append((hosts, present))
        if self.fail:
            raise EgressProxyUnavailable("reload refused: HTTP 503")


def _run(run_id: str = "run-1") -> LiveRun:
    return LiveRun(
        run_id=run_id,
        user_id="user-1",
        hosts=("api.search.brave.com",),
        credentials=(
            RunCredential(
                connector="brave_search",
                host="api.search.brave.com",
                token="sbx_tok",
                auth_method="header",
                auth_name="X-Subscription-Token",
                secret_path=f"/etc/lia-egress/config/secrets/{run_id}/brave_search.key",
            ),
        ),
    )


def _publisher(
    tmp_path: Path, redis: FakeRedis, proxy: RecordingProxy, *, claim_wait: float = 0.2
) -> EgressPublisher:
    return EgressPublisher(
        redis=redis,
        registry=LiveRunRegistry(redis, ttl_seconds=90),
        config_dir=tmp_path,
        proxy=proxy,
        ruleset_config=RulesetConfig(max_body_bytes=1024),
        claim_ttl_seconds=5,
        claim_wait_seconds=claim_wait,
        orphan_secret_age_seconds=90,
    )


class TestServingARun:
    async def test_enter_registers_keys_renders_reloads_and_exit_undoes_in_order(
        self, tmp_path: Path
    ) -> None:
        redis, proxy = FakeRedis(), RecordingProxy(tmp_path)
        publisher = _publisher(tmp_path, redis, proxy)
        async with publisher.serve(_run(), {"brave_search": "REAL"}):
            assert (tmp_path / "secrets" / "run-1" / "brave_search.key").read_text() == "REAL"
            assert [r.run_id for r in await publisher.registry.live_runs()] == ["run-1"]
        assert await publisher.registry.live_runs() == []
        assert not (tmp_path / "secrets" / "run-1").exists()
        # First reload: the host is allowed and its key file EXISTS. Second
        # reload: the host is gone while the key file STILL exists — removed
        # only after the proxy stopped referencing it.
        assert proxy.reloads == [
            (["api.search.brave.com"], ["run-1"]),
            ([], ["run-1"]),
        ]
        assert RULESET_CLAIM_KEY not in redis.store, "the claim must be released"

    async def test_a_failing_reload_on_enter_refuses_and_leaves_nothing(
        self, tmp_path: Path
    ) -> None:
        redis, proxy = FakeRedis(), RecordingProxy(tmp_path, fail=True)
        publisher = _publisher(tmp_path, redis, proxy)
        with pytest.raises(EgressProxyUnavailable):
            async with publisher.serve(_run(), {"brave_search": "REAL"}):
                raise AssertionError("the run must not start")
        assert await publisher.registry.live_runs() == []
        assert not (tmp_path / "secrets" / "run-1").exists()
        assert RULESET_CLAIM_KEY not in redis.store

    async def test_a_busy_claim_beyond_the_wait_refuses(self, tmp_path: Path) -> None:
        redis, proxy = FakeRedis(), RecordingProxy(tmp_path)
        redis.store[RULESET_CLAIM_KEY] = "another-worker"
        publisher = _publisher(tmp_path, redis, proxy, claim_wait=0.05)
        with pytest.raises(EgressProxyUnavailable, match="busy"):
            async with publisher.serve(_run(), {"brave_search": "REAL"}):
                raise AssertionError("the run must not start")
        assert proxy.reloads == []
        assert not (tmp_path / "secrets" / "run-1").exists()
        assert redis.store[RULESET_CLAIM_KEY] == "another-worker"

    async def test_a_cache_failure_refuses_before_any_secret_is_written(
        self, tmp_path: Path
    ) -> None:
        redis, proxy = FakeRedis(broken=True), RecordingProxy(tmp_path)
        publisher = _publisher(tmp_path, redis, proxy)
        with pytest.raises(EgressProxyUnavailable, match="ConnectionError"):
            async with publisher.serve(_run(), {"brave_search": "REAL"}):
                raise AssertionError("the run must not start")
        assert not (tmp_path / "secrets").exists() or not any((tmp_path / "secrets").iterdir())


class TestPublishAlone:
    async def test_an_empty_registry_renders_the_bootstrap_and_prunes_old_orphans(
        self, tmp_path: Path
    ) -> None:
        redis, proxy = FakeRedis(), RecordingProxy(tmp_path)
        publisher = _publisher(tmp_path, redis, proxy)
        old = tmp_path / "secrets" / "killed-worker-run"
        old.mkdir(parents=True)
        (old / "brave_search.key").write_text("LEAKED")
        stale = time.time() - 600
        os.utime(old, (stale, stale))
        fresh = tmp_path / "secrets" / "just-written"
        fresh.mkdir(parents=True)
        await publisher.publish()
        assert not old.exists(), "an orphan older than the registry TTL is a leaked key"
        assert (
            fresh.exists()
        ), "a directory younger than the TTL may belong to a run being registered"
        assert proxy.reloads == [([], ["just-written"])]
        assert (tmp_path / "proxy.yaml").exists()
