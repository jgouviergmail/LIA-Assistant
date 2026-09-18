"""The live network runs, in Redis (ADR-298).

The proxy holds ONE ruleset for the whole deployment, and production runs
four uvicorn workers: a registry kept in a worker's memory would render a
ruleset that forgets the other three workers' runs — and revoke their tokens
mid-flight (ADR-271's lesson, applied to a lock instead of a cache). So every
live run is an entry here, with a TTL that outlives the run's own budget, and
the ruleset is always rendered from ALL of them.

What an entry holds is what the proxy needs to write its rule: the hosts, the
opaque token and WHERE the real key is (a path in the shared tmpfs volume).
The real key itself is never in Redis.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

import structlog

from src.core.constants import REDIS_KEY_SANDBOX_EGRESS_PREFIX

logger = structlog.get_logger(__name__)

AuthMethod = Literal["header", "query"]


@dataclass(frozen=True)
class RunCredential:
    """One of the person's API keys, reachable from the run through a token.

    Attributes:
        connector: The ``ConnectorType`` value the key belongs to.
        host: The upstream host the proxy swaps the token on — that one only.
        token: The opaque value the sandbox holds (``LIA_KEY_<CONNECTOR>``).
        auth_method: Where the client class says the key travels.
        auth_name: The header name or the query parameter name.
        secret_path: Where the proxy reads the real key, in the shared volume.
    """

    connector: str
    host: str
    token: str
    auth_method: AuthMethod
    auth_name: str
    secret_path: str


@dataclass(frozen=True)
class LiveRun:
    """A network run the proxy must currently serve.

    Attributes:
        run_id: The run's identity (also the name of its secrets directory).
        user_id: The account the run belongs to.
        hosts: Every host the run may reach — declared by the model, permitted
            by a connector, the operator or a grant.
        credentials: The tokens the run holds, one per connector host.
    """

    run_id: str
    user_id: str
    hosts: tuple[str, ...]
    credentials: tuple[RunCredential, ...]

    def to_serializable_dict(self) -> dict[str, Any]:
        """The msgpack/JSON-safe shape stored in Redis."""
        payload = asdict(self)
        payload["hosts"] = list(self.hosts)
        payload["credentials"] = [asdict(c) for c in self.credentials]
        return payload

    @classmethod
    def from_serializable_dict(cls, payload: dict[str, Any]) -> LiveRun:
        """Rebuild a run from :meth:`to_serializable_dict`'s output.

        Raises:
            ValueError: On an auth method outside the closed vocabulary — an
                entry another version wrote is refused rather than guessed.
        """
        return cls(
            run_id=str(payload["run_id"]),
            user_id=str(payload["user_id"]),
            hosts=tuple(str(h) for h in payload.get("hosts", [])),
            credentials=tuple(_credential_from(c) for c in payload.get("credentials", [])),
        )


def _credential_from(payload: dict[str, Any]) -> RunCredential:
    """One credential from its stored shape, the auth method validated."""
    method = str(payload["auth_method"])
    if method not in ("header", "query"):
        raise ValueError(f"unknown auth method in egress registry: {method!r}")
    auth_method: AuthMethod = "header" if method == "header" else "query"
    return RunCredential(
        connector=str(payload["connector"]),
        host=str(payload["host"]),
        token=str(payload["token"]),
        auth_method=auth_method,
        auth_name=str(payload["auth_name"]),
        secret_path=str(payload["secret_path"]),
    )


def run_key(run_id: str) -> str:
    """The Redis key of one run's entry."""
    return f"{REDIS_KEY_SANDBOX_EGRESS_PREFIX}run:{run_id}"


INDEX_KEY = f"{REDIS_KEY_SANDBOX_EGRESS_PREFIX}runs"
RULESET_CLAIM_KEY = f"{REDIS_KEY_SANDBOX_EGRESS_PREFIX}ruleset_claim"


class LiveRunRegistry:
    """Register, drop and list the live runs of the whole deployment."""

    index_key = INDEX_KEY

    def __init__(self, redis: Any, *, ttl_seconds: int) -> None:
        """
        Args:
            redis: The cache client.
            ttl_seconds: How long an entry survives a worker that never
                unregisters it (a hard kill). Longer than any run's budget.
        """
        self._redis = redis
        self._ttl = ttl_seconds

    async def register(self, run: LiveRun) -> None:
        """Add a run. Propagates a cache failure: a run the proxy cannot be
        told about must be refused, never launched blind."""
        await self._redis.set(
            run_key(run.run_id), json.dumps(run.to_serializable_dict()), ex=self._ttl
        )
        await self._redis.sadd(self.index_key, run.run_id)

    async def unregister(self, run_id: str) -> None:
        """Drop a run's entry and its index member."""
        await self._redis.delete(run_key(run_id))
        await self._redis.srem(self.index_key, run_id)

    async def live_runs(self) -> list[LiveRun]:
        """Every run whose entry still exists, index ghosts pruned.

        A worker killed mid-run leaves an index member whose entry expired by
        TTL; it is dropped here so the ruleset never carries a dead token.
        """
        members = sorted(await self._redis.smembers(self.index_key))
        if not members:
            return []
        entries = await self._redis.mget([run_key(m) for m in members])
        runs: list[LiveRun] = []
        ghosts: list[str] = []
        for run_id, raw in zip(members, entries, strict=True):
            if raw is None:
                ghosts.append(run_id)
                continue
            runs.append(LiveRun.from_serializable_dict(json.loads(raw)))
        if ghosts:
            logger.info("sandbox_egress_ghost_runs_pruned", count=len(ghosts))
            await self._redis.srem(self.index_key, *ghosts)
        return runs


__all__ = [
    "INDEX_KEY",
    "RULESET_CLAIM_KEY",
    "AuthMethod",
    "LiveRun",
    "LiveRunRegistry",
    "RunCredential",
    "run_key",
]
