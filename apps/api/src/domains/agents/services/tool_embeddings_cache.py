"""Disk cache of the tool-catalogue embeddings, and the right to compute it.

Extracted from ``tool_selector`` because it is a distinct concern with distinct
failure modes, and because it grew one: **who** computes the cache when several
workers find it missing at the same time.

Production, 2026-07-27, first boot after the cache was given a volume: the volume
was empty, all four uvicorn workers missed, and all four embedded the same 713
catalogue texts at once. The provider answered ``429 RESOURCE_EXHAUSTED`` —
capacity, not quota — and **two workers died** (``Application startup failed.
Exiting.``). They recovered only because the two survivors had written the cache
by the time uvicorn respawned them: had all four failed together there would have
been nothing to recover from.

So the burst is removed rather than survived. On a miss, a worker takes an
exclusive claim (``O_CREAT | O_EXCL`` — atomic on every filesystem this runs on,
no Redis, no database) and the others wait for its result instead of duplicating
it. Three properties make that safe rather than merely clever:

* **A dead holder cannot block a boot.** A claim old enough that no live holder
  could still own it is stolen, because otherwise one crash would make every later
  boot wait out the whole timeout and then embed anyway — worse than no
  coordination at all. That age is ``max(timeout, 30 s)`` and never the timeout
  alone: the two thresholds fail in opposite directions, and judging a *live*
  claim stale would restore the very burst this module removes.
* **A failing holder hands over.** The claim is released even when the
  computation raises, so a waiter takes it next: attempts are serialised (713
  texts at a time) instead of parallelised (2 852 at once).
* **Losing the coordination is never fatal.** If the deadline passes or the lock
  cannot be created, the caller computes unclaimed — exactly today's behaviour —
  and ``result="miss_unclaimed"`` says so on a dashboard.

Note the failure of ``initialize()`` stays fatal to the worker on purpose. Making
it non-fatal was considered and rejected: a worker that survives with an
uninitialised selector skips semantic tool scoring for the rest of its life
(``router_node_v3`` guards on ``is_initialized()``), whereas a worker that exits
is respawned and comes back fully functional. Dying is the better degradation
here — measured in production: 4 successful initialisations, 2 failures, 4 healthy
workers ~48 s later.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import suppress
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.core.constants import TOOL_EMBEDDINGS_CACHE_FILENAME
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import tool_embeddings_cache_total

logger = get_logger(__name__)

# Application root (apps/api, /app in the image): the anchor for a relative cache
# directory, so the resolved location never depends on the working directory.
_APP_ROOT = Path(__file__).resolve().parents[4]

# How often a waiter re-checks. Not a setting: it is bounded by the claim timeout
# above it, and a second knob would only allow combinations neither value wants.
_POLL_INTERVAL_SECONDS = 0.5

# Floor on the age at which a claim is presumed abandoned. The wait timeout alone
# cannot serve as that threshold: the two have opposite failure directions. Waiting
# too briefly merely costs an unclaimed computation, whereas judging a *live* claim
# stale makes two workers compute at once — the exact burst this module removes. A
# small timeout must therefore never shorten the staleness rule below a duration no
# legitimate holder can exceed (measured: 713 texts embed in ~14 s).
_MIN_STALE_SECONDS = 30.0


def resolve_cache_dir() -> Path:
    """Resolve the directory holding the tool-embeddings disk cache.

    An absolute setting is honoured verbatim; a relative one is anchored on the
    application root rather than the working directory, which is what makes the
    cache land in the same place whether the process was started from
    ``apps/api`` (pytest, dev server) or from ``/app`` (image).

    Returns:
        Absolute path to the cache directory. Not created here — the writer
        creates it, the reader treats its absence as a cache miss.
    """
    configured = Path(settings.tool_embeddings_cache_dir)
    return configured if configured.is_absolute() else _APP_ROOT / configured


def resolve_cache_path() -> Path:
    """Absolute path of the cache document itself.

    Returns:
        ``<cache dir>/tool_embeddings_cache.json``.
    """
    return resolve_cache_dir() / TOOL_EMBEDDINGS_CACHE_FILENAME


def load(cache_path: Path, expected_hash: str, expected_count: int) -> list[list[float]] | None:
    """Load cached embeddings from disk if they match what the caller needs.

    Args:
        cache_path: Path to the JSON cache file.
        expected_hash: Hash of the current tool texts — must match the cached one.
        expected_count: Expected number of vectors. A truncated or mismatched
            file would otherwise index out of bounds downstream.

    Returns:
        The vectors, or None when the cache is missing, stale or corrupt.
    """
    if not cache_path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(cache_path.read_text(encoding="utf-8"))
        if data.get("content_hash") != expected_hash:
            return None
        embeddings: list[list[float]] = data.get("embeddings", [])
        if len(embeddings) != expected_count:
            logger.warning(
                "tool_embedding_cache_count_mismatch",
                cached=len(embeddings),
                expected=expected_count,
            )
            return None
        return embeddings
    except Exception:
        return None


def save(cache_path: Path, content_hash: str, embeddings: list[list[float]]) -> None:
    """Persist embeddings to disk alongside their content hash.

    Written to a private temporary sibling and renamed into place. Several workers
    can write this same path, and the document is tens of megabytes: a plain
    ``write_text`` lets a concurrent reader observe a half-written file, whose
    only recovery is to re-embed the whole catalogue. ``os.replace`` is atomic, so
    a reader sees either the previous file or the complete new one — never a
    prefix of it. The temporary name carries the pid so two writers cannot corrupt
    each other's staging file.

    Args:
        cache_path: Path to write the JSON cache file.
        content_hash: Hash of the texts that produced these embeddings.
        embeddings: Vectors, in the caller's text order.
    """
    data = {"content_hash": content_hash, "embeddings": embeddings}
    tmp_path = cache_path.with_name(f"{cache_path.name}.{os.getpid()}.tmp")
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp_path, cache_path)
    except Exception as e:
        # A staging file left behind would be dead weight on the volume, and its
        # size is that of the cache itself.
        with suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        logger.warning(
            "tool_embedding_cache_save_failed",
            error=str(e),
            error_type=type(e).__name__,
            cache_path=str(cache_path),
        )


def lock_path_for(cache_path: Path) -> Path:
    """Path of the claim marker for a cache file.

    Args:
        cache_path: Cache document the claim protects.

    Returns:
        The sibling lock path.
    """
    return cache_path.with_name(f"{cache_path.name}.lock")


class _Claim(Enum):
    """Outcome of one attempt at taking the claim.

    Three outcomes, not two: "someone else holds it" is the only one worth
    waiting on. Collapsing it with "I cannot create it" made a fresh volume — no
    cache directory yet, so ``os.open`` raises ``FileNotFoundError`` — look like a
    busy peer, and every worker then waited out the whole timeout before embedding
    anyway. That is worse than not coordinating at all, and it is precisely the
    first-boot case this module exists for.
    """

    TAKEN = "taken"
    HELD_BY_OTHER = "held_by_other"
    UNAVAILABLE = "unavailable"


def _acquire(lock_path: Path) -> _Claim:
    """One atomic attempt at taking the claim.

    ``O_CREAT | O_EXCL`` is the whole mechanism: the filesystem decides the
    winner, so no lock service is involved and the claim works between processes
    that share nothing but the volume.

    Args:
        lock_path: Claim marker to create.

    Returns:
        Which of the three outcomes occurred.
    """
    try:
        # The volume can be empty on a first boot; the writer creates the
        # directory anyway, so create it here too rather than mistaking its
        # absence for a busy peer.
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return _Claim.HELD_BY_OTHER
    except OSError as exc:
        # Genuinely unable to coordinate (read-only mount, permissions). Say so
        # and let the caller compute immediately rather than wait for a peer that
        # will never appear, or fail the boot.
        logger.warning(
            "tool_embedding_cache_claim_unavailable",
            error=str(exc),
            error_type=type(exc).__name__,
            lock_path=str(lock_path),
        )
        return _Claim.UNAVAILABLE
    try:
        os.write(descriptor, str(os.getpid()).encode())
    finally:
        os.close(descriptor)
    return _Claim.TAKEN


def _is_stale(lock_path: Path, ttl_seconds: float) -> bool:
    """Whether a claim is old enough that its holder cannot still be working.

    A file mtime is wall clock, so this comparison cannot use a monotonic source.
    A forward clock step larger than the TTL — NTP settling on the production
    host, which happens around boot — can therefore make a *live* claim look
    abandoned. What makes the heuristic acceptable is that **both** of its errors
    are bounded by the behaviour that preceded the claim:

    * stealing a live claim ⇒ two workers compute at once, which is exactly what
      every boot did before v1.25.27;
    * failing to steal a dead one ⇒ waiters spend the timeout, then compute
      unclaimed, which is that same pre-v1.25.27 behaviour plus a bounded delay.

    Neither error creates a failure mode that did not already exist; they only
    forfeit the optimisation for one boot. That is why no process-liveness check
    (``os.kill(pid, 0)``, an advisory ``flock``) is worth the platform-specific
    branch it would need here.

    Args:
        lock_path: Claim marker to inspect.
        ttl_seconds: Age past which the holder is presumed gone.

    Returns:
        True when the claim should be stolen.
    """
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return False  # Vanished between the failed acquire and now: not stale.
    return age > ttl_seconds


def release(lock_path: Path) -> None:
    """Give up a claim, whether the computation succeeded or not.

    Releasing on failure is what turns four simultaneous attempts into a relay:
    the next waiter takes the claim and tries alone.

    Args:
        lock_path: Claim marker to remove.
    """
    with suppress(OSError):
        lock_path.unlink(missing_ok=True)


async def load_or_claim(
    cache_path: Path, expected_hash: str, expected_count: int
) -> tuple[list[list[float]] | None, Path | None]:
    """Serve the cache, or take the exclusive right to compute it.

    Args:
        cache_path: Cache document.
        expected_hash: Hash the cache must carry to be usable.
        expected_count: Number of vectors the caller needs.

    Returns:
        ``(embeddings, None)`` — serve these, nothing to release.
        ``(None, lock_path)`` — compute, then ``release(lock_path)``.
        ``(None, None)`` — compute unclaimed; coordination was unavailable.
    """
    cached = load(cache_path, expected_hash, expected_count)
    if cached is not None:
        tool_embeddings_cache_total.labels(result="hit").inc()
        return cached, None

    timeout = float(settings.tool_embeddings_cache_claim_timeout_seconds)
    lock_path = lock_path_for(cache_path)
    deadline = time.monotonic() + timeout
    stolen_once = False
    waited = False

    while True:
        outcome = _acquire(lock_path)
        if outcome is _Claim.TAKEN:
            # Double-checked: a peer can have written the cache and released the
            # claim in the window between our last read and this acquisition —
            # precisely the moment several workers are polling. Computing here
            # would spend a full catalogue embedding on a result already on disk.
            cached = load(cache_path, expected_hash, expected_count)
            if cached is not None:
                release(lock_path)
                tool_embeddings_cache_total.labels(result="hit_after_wait").inc()
                return cached, None
            tool_embeddings_cache_total.labels(result="miss").inc()
            return None, lock_path
        if outcome is _Claim.UNAVAILABLE:
            tool_embeddings_cache_total.labels(result="miss_unclaimed").inc()
            return None, None

        # Someone else is computing the very same thing. Waiting for their
        # result is the entire point: this is the burst that killed two workers.
        if not stolen_once and _is_stale(lock_path, max(timeout, _MIN_STALE_SECONDS)):
            stolen_once = True
            logger.warning(
                "tool_embedding_cache_claim_stale",
                lock_path=str(lock_path),
                ttl_seconds=max(timeout, _MIN_STALE_SECONDS),
                remediation="stealing the claim — its holder cannot still be running",
            )
            release(lock_path)
            continue

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            tool_embeddings_cache_total.labels(result="miss_unclaimed").inc()
            logger.warning(
                "tool_embedding_cache_claim_timeout",
                lock_path=str(lock_path),
                timeout_seconds=timeout,
                remediation="computing unclaimed — the concurrent burst may recur",
            )
            return None, None

        if not waited:
            waited = True
            logger.info(
                "tool_embedding_cache_claim_waiting",
                lock_path=str(lock_path),
                timeout_seconds=timeout,
            )
        await asyncio.sleep(min(_POLL_INTERVAL_SECONDS, remaining))

        cached = load(cache_path, expected_hash, expected_count)
        if cached is not None:
            tool_embeddings_cache_total.labels(result="hit_after_wait").inc()
            return cached, None
