"""Serving one network run: register, key, render, reload — and undo (ADR-298).

The order is the contract:

- **enter**: the run's real keys are written into the shared volume FIRST
  (the file must exist before any ruleset names it), then the run is
  registered in Redis, then the ruleset of ALL live runs is rendered and the
  proxy reloaded. Any failure undoes everything and refuses the run;
- **exit**: the run is unregistered and the proxy reloaded WITHOUT it, and
  only then are its key files removed — a reload must never point at a file
  that is already gone.

Rendering happens under a Redis claim with an owner token, because two
workers may serve two runs in the same second and each must render the
other's rules too. A claim that stays busy past the wait is a refusal: a run
launched against a ruleset that may not hold its hosts is worse than a run
that did not start.

A hard-killed worker leaves a registry entry that expires by TTL and a
secrets directory nobody removes; :meth:`publish` prunes any directory older
than that TTL whose run is not live, so a leaked key outlives its run by at
most one TTL. A younger directory is left alone — it may belong to a run
between its key write and its registration.

The file writes here are synchronous on purpose: the config volume is a
tmpfs (compose declares it so), a ruleset is a few kilobytes, and handing a
microsecond write to a thread would cost more than the write.
"""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Protocol

import structlog

from src.domains.agents.python_sandbox.egress.proxy_client import EgressProxyUnavailable
from src.domains.agents.python_sandbox.egress.registry import (
    RULESET_CLAIM_KEY,
    LiveRun,
    LiveRunRegistry,
)
from src.domains.agents.python_sandbox.egress.ruleset import (
    SECRETS_DIRNAME,
    RulesetConfig,
    remove_run_secrets,
    render_ruleset,
    write_run_secrets,
)
from src.infrastructure.locks.redis_claim import acquire_claim, release_claim

logger = structlog.get_logger(__name__)

RULESET_FILENAME = "proxy.yaml"
CLAIM_POLL_SECONDS = 0.05


class ReloadableProxy(Protocol):
    """What the publisher needs of the management client."""

    async def reload(self) -> None: ...


class EgressPublisher:
    """The one writer of the proxy's ruleset in this process."""

    def __init__(
        self,
        *,
        redis: Any,
        registry: LiveRunRegistry,
        config_dir: Path,
        proxy: ReloadableProxy,
        ruleset_config: RulesetConfig,
        claim_ttl_seconds: int,
        claim_wait_seconds: float,
        orphan_secret_age_seconds: float,
    ) -> None:
        """
        Args:
            redis: The cache client the claim lives in.
            registry: The live-run registry (every worker's).
            config_dir: The shared config volume, as mounted in this container.
            proxy: The management client.
            ruleset_config: What the rendering reads from settings.
            claim_ttl_seconds: TTL of the writer claim.
            claim_wait_seconds: How long to wait for a busy claim before refusing.
            orphan_secret_age_seconds: A secrets directory older than this and
                not live is a leak from a killed worker, and is removed.
        """
        self._redis = redis
        self.registry = registry
        self._config_dir = config_dir
        self.proxy = proxy
        self._ruleset_config = ruleset_config
        self._claim_ttl = claim_ttl_seconds
        self._claim_wait = claim_wait_seconds
        self._orphan_age = orphan_secret_age_seconds

    async def publish(self) -> None:
        """Render every live run into the ruleset and reload the proxy.

        Raises:
            EgressProxyUnavailable: When the claim stays busy, the cache is
                unreachable, or the proxy refuses the reload.
        """
        try:
            token = await acquire_claim(
                self._redis,
                RULESET_CLAIM_KEY,
                ttl_seconds=self._claim_ttl,
                wait_seconds=self._claim_wait,
                poll_seconds=CLAIM_POLL_SECONDS,
            )
        except Exception as exc:
            raise EgressProxyUnavailable(f"ruleset claim failed: {type(exc).__name__}") from exc
        if token is None:
            raise EgressProxyUnavailable("ruleset claim busy beyond the wait budget")
        try:
            try:
                runs = await self.registry.live_runs()
            except Exception as exc:
                raise EgressProxyUnavailable(f"live runs unreadable: {type(exc).__name__}") from exc
            self._prune_orphan_secrets({run.run_id for run in runs})
            self._write_ruleset(render_ruleset(runs, self._ruleset_config))
            await self.proxy.reload()
        finally:
            await release_claim(self._redis, RULESET_CLAIM_KEY, token)

    @asynccontextmanager
    async def serve(self, run: LiveRun, secrets: Mapping[str, str]) -> AsyncIterator[None]:
        """Make the proxy serve ``run`` for the duration of the block.

        Args:
            run: The run, its hosts and credentials.
            secrets: ``{connector: real key}`` — the values the credentials'
                ``secret_path`` files must hold.

        Raises:
            EgressProxyUnavailable: When the run could not be published; nothing
                of it is left behind.
        """
        write_run_secrets(self._config_dir, run.run_id, secrets)
        try:
            try:
                await self.registry.register(run)
            except Exception as exc:
                raise EgressProxyUnavailable(f"registry failed: {type(exc).__name__}") from exc
            await self.publish()
        except BaseException:
            await self._withdraw(run.run_id, publish=False)
            raise
        try:
            yield
        finally:
            await self._withdraw(run.run_id, publish=True)

    async def _withdraw(self, run_id: str, *, publish: bool) -> None:
        """Unregister, reload without the run, then drop its keys — in that order."""
        with suppress(Exception):
            await self.registry.unregister(run_id)
        if publish:
            try:
                await self.publish()
            except EgressProxyUnavailable as exc:
                # The token stays in the proxy until the next publish by anyone;
                # its key file goes now, so the swap can no longer succeed.
                logger.warning("sandbox_egress_withdraw_publish_failed", reason=str(exc))
        remove_run_secrets(self._config_dir, run_id)

    def _write_ruleset(self, text: str) -> None:
        """Atomic replace, private from the first byte."""
        target = self._config_dir / RULESET_FILENAME
        tmp = target.with_suffix(".yaml.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, target)

    def _prune_orphan_secrets(self, live_ids: set[str]) -> None:
        """Remove secrets directories of runs that are neither live nor recent."""
        root = self._config_dir / SECRETS_DIRNAME
        if not root.is_dir():
            return
        cutoff = time.time() - self._orphan_age
        for entry in root.iterdir():
            if entry.name in live_ids or not entry.is_dir():
                continue
            if entry.stat().st_mtime > cutoff:
                continue
            logger.warning("sandbox_egress_orphan_secrets_removed", run_id=entry.name)
            shutil.rmtree(entry, ignore_errors=True)


__all__ = ["CLAIM_POLL_SECONDS", "RULESET_FILENAME", "EgressPublisher", "ReloadableProxy"]
