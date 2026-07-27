"""The tool-embeddings cache: where it lives, how it is written, who computes it.

Three production defects are pinned here.

**The cache never survived a deploy** (v1.25.26). Its directory resolved inside
the container's writable layer, which ``--force-recreate`` discards: 108 misses
and **zero** hits across 27 boots, each of four workers re-embedding all 713
catalogue texts for a payload whose hash had not changed in four days.

**The write was not atomic** (v1.25.26). Several workers write the same
multi-megabyte document; a plain ``write_text`` lets a reader observe a prefix,
whose only recovery is to re-embed everything.

**Everyone computed at once** (v1.25.27). The first boot on the new volume had all
four workers miss together and embed simultaneously — 2 852 contents. The provider
answered a capacity ``429`` and **two workers died** (``Application startup
failed. Exiting.``); they only recovered because two survivors had written the
cache before uvicorn respawned them. A claim now makes one worker compute while
the others wait for its result, and the tests below pin the three properties that
make that safe: a dead holder cannot block a boot, a failing holder hands over,
and losing the coordination is never fatal.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.config import settings
from src.core.constants import (
    TOOL_EMBEDDINGS_CACHE_DIR_DEFAULT,
    TOOL_EMBEDDINGS_CACHE_FILENAME,
)
from src.domains.agents.services import tool_embeddings_cache as cache_module
from src.domains.agents.services.tool_embeddings_cache import (
    load,
    load_or_claim,
    lock_path_for,
    release,
    resolve_cache_dir,
    resolve_cache_path,
    save,
)

HASH = "a" * 64
VECTORS: list[list[float]] = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    """A cache file path inside an existing temporary directory.

    Args:
        tmp_path: pytest temporary directory.

    Returns:
        Path to the (not yet created) cache file.
    """
    return tmp_path / TOOL_EMBEDDINGS_CACHE_FILENAME


@pytest.fixture
def instant_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make waiting observable without making the suite slow.

    Args:
        monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.setattr(settings, "tool_embeddings_cache_claim_timeout_seconds", 1.0, raising=False)


def _counter(result: str) -> float:
    """Current value of the cache-outcome counter for one label.

    Args:
        result: Label value.

    Returns:
        The counter value.
    """
    from src.infrastructure.observability.metrics_agents import tool_embeddings_cache_total

    return float(tool_embeddings_cache_total.labels(result=result)._value.get())


# ==========================================================================
# Location
# ==========================================================================


def test_default_resolves_under_the_application_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default lands in ``<app root>/data/tool_cache``.

    In the image the application root is ``/app``, so the default resolves onto
    the ``tool_cache_data`` mount point without any environment variable.

    Args:
        monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.setattr(
        settings, "tool_embeddings_cache_dir", TOOL_EMBEDDINGS_CACHE_DIR_DEFAULT, raising=False
    )

    resolved = resolve_cache_dir()

    assert resolved.is_absolute()
    assert resolved.parts[-2:] == ("data", "tool_cache")
    # Identify the anchor by what it CONTAINS, not by re-deriving ``parents[4]``:
    # asserting the same expression the code uses could not catch a wrong index.
    app_root = resolved.parent.parent
    assert (app_root / "src" / "domains").is_dir(), f"{app_root} is not the API application root"
    assert (app_root / "pyproject.toml").is_file(), f"{app_root} is not the API application root"


def test_relative_path_ignores_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A relative setting is anchored on the app root, not on ``os.getcwd()``.

    This is the property that keeps pytest (run from ``apps/api``) and the image
    (run from ``/app``) pointing at the same file.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        tmp_path: pytest temporary directory.
    """
    monkeypatch.setattr(settings, "tool_embeddings_cache_dir", "data/tool_cache", raising=False)

    before = resolve_cache_dir()
    monkeypatch.chdir(tmp_path)
    after = resolve_cache_dir()

    assert before == after


def test_absolute_path_is_honoured_verbatim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An absolute setting is the escape hatch for an arbitrary mount point.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        tmp_path: pytest temporary directory.
    """
    monkeypatch.setattr(settings, "tool_embeddings_cache_dir", str(tmp_path), raising=False)

    assert resolve_cache_dir() == tmp_path
    assert resolve_cache_path() == tmp_path / TOOL_EMBEDDINGS_CACHE_FILENAME


def test_resolution_does_not_create_the_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Resolving is a pure computation — the writer creates, the reader misses.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        tmp_path: pytest temporary directory.
    """
    target = tmp_path / "not_yet"
    monkeypatch.setattr(settings, "tool_embeddings_cache_dir", str(target), raising=False)

    assert resolve_cache_dir() == target
    assert not target.exists()


# ==========================================================================
# Round trip and rejection rules
# ==========================================================================


def test_save_then_load_returns_the_same_vectors(cache_path: Path) -> None:
    """The nominal path: what was written is what comes back.

    Args:
        cache_path: Target cache file.
    """
    save(cache_path, HASH, VECTORS)

    assert load(cache_path, HASH, len(VECTORS)) == VECTORS


def test_save_creates_missing_parent_directories(tmp_path: Path) -> None:
    """A fresh volume is an empty directory; deeper targets must still work.

    Args:
        tmp_path: pytest temporary directory.
    """
    nested = tmp_path / "a" / "b" / TOOL_EMBEDDINGS_CACHE_FILENAME

    save(nested, HASH, VECTORS)

    assert nested.is_file()


def test_missing_file_is_a_miss(cache_path: Path) -> None:
    """An absent cache is a miss, not an error.

    Args:
        cache_path: Target cache file.
    """
    assert load(cache_path, HASH, len(VECTORS)) is None


def test_stale_hash_is_rejected(cache_path: Path) -> None:
    """A changed catalogue must not be served from the previous vectors.

    Args:
        cache_path: Target cache file.
    """
    save(cache_path, HASH, VECTORS)

    assert load(cache_path, "b" * 64, len(VECTORS)) is None


def test_count_mismatch_is_rejected(cache_path: Path) -> None:
    """Fewer vectors than texts would index out of bounds downstream.

    Args:
        cache_path: Target cache file.
    """
    save(cache_path, HASH, VECTORS)

    assert load(cache_path, HASH, len(VECTORS) + 1) is None


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("{not json", id="truncated_json"),
        pytest.param("[]", id="list_instead_of_object"),
        pytest.param("", id="empty_file"),
    ],
)
def test_corrupt_payload_is_a_miss(cache_path: Path, payload: str) -> None:
    """A corrupt file degrades to a recompute rather than crashing the boot.

    Args:
        cache_path: Target cache file.
        payload: Malformed file content.
    """
    cache_path.write_text(payload, encoding="utf-8")

    assert load(cache_path, HASH, len(VECTORS)) is None


# ==========================================================================
# Atomicity of the write
# ==========================================================================


def _patch_os(monkeypatch: pytest.MonkeyPatch, *, replace: Any, getpid: Any = os.getpid) -> None:
    """Swap the ``os`` handle the module uses.

    Replacing the attribute on the real ``os`` module would rewire the whole
    interpreter, and a spy that calls ``os.replace`` would call itself. A
    namespace exposing only what ``save`` consumes keeps the substitution local.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        replace: Stand-in for ``os.replace``.
        getpid: Stand-in for ``os.getpid``.
    """
    monkeypatch.setattr(
        cache_module,
        "os",
        SimpleNamespace(
            replace=replace,
            getpid=getpid,
            open=os.open,
            write=os.write,
            close=os.close,
            O_CREAT=os.O_CREAT,
            O_EXCL=os.O_EXCL,
            O_WRONLY=os.O_WRONLY,
        ),
    )


def test_save_leaves_no_staging_file_behind(cache_path: Path) -> None:
    """A stale staging file would weigh as much as the cache itself.

    Args:
        cache_path: Target cache file.
    """
    save(cache_path, HASH, VECTORS)

    assert list(cache_path.parent.glob("*.tmp")) == []


def test_staging_name_is_private_to_the_process(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two workers must not stage through the same temporary path.

    Without the pid, worker B's partial write is what worker A renames into
    place — the exact corruption the rename was meant to prevent.

    Args:
        cache_path: Target cache file.
        monkeypatch: pytest monkeypatch fixture.
    """
    staged: list[str] = []
    pids = iter([4242, 4343])

    def _capture(src: Any, dst: Any) -> None:
        staged.append(Path(src).name)
        os.replace(src, dst)

    _patch_os(monkeypatch, replace=_capture, getpid=lambda: next(pids))

    save(cache_path, HASH, VECTORS)
    save(cache_path, HASH, VECTORS)

    assert staged == [
        f"{TOOL_EMBEDDINGS_CACHE_FILENAME}.4242.tmp",
        f"{TOOL_EMBEDDINGS_CACHE_FILENAME}.4343.tmp",
    ]


def test_a_reader_never_observes_a_partial_document(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Until the rename, the visible file is still the previous one.

    Args:
        cache_path: Target cache file.
        monkeypatch: pytest monkeypatch fixture.
    """
    save(cache_path, HASH, VECTORS)
    previous = cache_path.read_text(encoding="utf-8")
    observed: list[str] = []

    def _observe_then_replace(src: Any, dst: Any) -> None:
        observed.append(Path(dst).read_text(encoding="utf-8"))
        os.replace(src, dst)

    _patch_os(monkeypatch, replace=_observe_then_replace)

    new_vectors = [[9.9, 9.9]]
    save(cache_path, "c" * 64, new_vectors)

    assert observed == [previous]
    assert json.loads(cache_path.read_text(encoding="utf-8"))["embeddings"] == new_vectors


def test_a_failed_write_preserves_the_previous_cache(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write that blows up must not destroy a usable cache.

    Args:
        cache_path: Target cache file.
        monkeypatch: pytest monkeypatch fixture.
    """
    save(cache_path, HASH, VECTORS)

    def _boom(src: Any, dst: Any) -> None:
        raise OSError("no space left on device")

    _patch_os(monkeypatch, replace=_boom)

    save(cache_path, "d" * 64, [[0.0]])

    assert load(cache_path, HASH, len(VECTORS)) == VECTORS
    assert list(cache_path.parent.glob("*.tmp")) == []


# ==========================================================================
# The claim — one writer, and no way for it to block a boot
# ==========================================================================


@pytest.mark.usefixtures("instant_timeout")
class TestClaim:
    """``O_CREAT | O_EXCL`` decides who computes; everyone else waits for them."""

    async def test_a_served_cache_takes_no_claim_at_all(self, cache_path: Path) -> None:
        """The common boot must not even touch the lock.

        Args:
            cache_path: Target cache file.
        """
        save(cache_path, HASH, VECTORS)
        before = _counter("hit")

        embeddings, claim = await load_or_claim(cache_path, HASH, len(VECTORS))

        assert embeddings == VECTORS
        assert claim is None
        assert not lock_path_for(cache_path).exists()
        assert _counter("hit") - before == 1

    async def test_the_first_worker_on_a_miss_takes_the_claim(self, cache_path: Path) -> None:
        """It must be told to compute, and hold the marker while it does.

        Args:
            cache_path: Target cache file.
        """
        before = _counter("miss")

        embeddings, claim = await load_or_claim(cache_path, HASH, len(VECTORS))

        assert embeddings is None
        assert claim == lock_path_for(cache_path)
        assert claim.exists()
        assert _counter("miss") - before == 1
        release(claim)

    async def test_a_second_worker_waits_and_is_served_the_result(
        self, cache_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """This is the burst removal: the loser embeds nothing.

        Args:
            cache_path: Target cache file.
            monkeypatch: pytest monkeypatch fixture.
        """
        lock = lock_path_for(cache_path)
        lock.write_text("1", encoding="utf-8")  # A peer is computing.
        before = _counter("hit_after_wait")

        real_sleep = asyncio.sleep

        async def _write_cache_then_sleep(seconds: float) -> None:
            # The peer finishes while we are between two polls.
            save(cache_path, HASH, VECTORS)
            await real_sleep(0)

        monkeypatch.setattr(cache_module.asyncio, "sleep", _write_cache_then_sleep)

        embeddings, claim = await load_or_claim(cache_path, HASH, len(VECTORS))

        assert embeddings == VECTORS
        assert claim is None, "a waiter that got the result must not hold the claim"
        assert _counter("hit_after_wait") - before == 1

    async def test_a_holder_that_never_finishes_does_not_hang_the_boot(
        self, cache_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Past the deadline the caller computes unclaimed rather than waiting on.

        Args:
            cache_path: Target cache file.
            monkeypatch: pytest monkeypatch fixture.
        """
        lock_path_for(cache_path).write_text("1", encoding="utf-8")
        before = _counter("miss_unclaimed")

        real_sleep = asyncio.sleep

        async def _fast_forward(seconds: float) -> None:
            await real_sleep(0)

        monkeypatch.setattr(cache_module.asyncio, "sleep", _fast_forward)
        monkeypatch.setattr(
            settings, "tool_embeddings_cache_claim_timeout_seconds", 0.05, raising=False
        )

        embeddings, claim = await load_or_claim(cache_path, HASH, len(VECTORS))

        assert embeddings is None
        assert claim is None, "no claim was taken, so nothing must be released"
        assert _counter("miss_unclaimed") - before == 1

    async def test_a_stale_claim_is_stolen(
        self, cache_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A crashed holder must not make every later boot wait out the timeout.

        Args:
            cache_path: Target cache file.
            monkeypatch: pytest monkeypatch fixture.
        """
        lock = lock_path_for(cache_path)
        lock.write_text("1", encoding="utf-8")
        # Older than the timeout: its holder cannot still be running.
        old = time.time() - 3600
        os.utime(lock, (old, old))
        monkeypatch.setattr(
            settings, "tool_embeddings_cache_claim_timeout_seconds", 30.0, raising=False
        )

        embeddings, claim = await load_or_claim(cache_path, HASH, len(VECTORS))

        assert embeddings is None
        assert claim == lock, "the stale claim must be taken over, not waited on"
        release(claim)

    async def test_a_fresh_claim_is_never_stolen(
        self, cache_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Stealing a live claim would restore the very burst this removes.

        Args:
            cache_path: Target cache file.
            monkeypatch: pytest monkeypatch fixture.
        """
        lock = lock_path_for(cache_path)
        lock.write_text("1", encoding="utf-8")
        real_sleep = asyncio.sleep

        async def _fast_forward(seconds: float) -> None:
            await real_sleep(0)

        monkeypatch.setattr(cache_module.asyncio, "sleep", _fast_forward)
        monkeypatch.setattr(
            settings, "tool_embeddings_cache_claim_timeout_seconds", 0.05, raising=False
        )

        _, claim = await load_or_claim(cache_path, HASH, len(VECTORS))

        assert claim is None, "a live holder's claim must survive"
        assert lock.exists()

    async def test_releasing_hands_the_claim_to_the_next_worker(self, cache_path: Path) -> None:
        """A holder whose embedding call fails must not deadlock its peers.

        Releasing on failure is what serialises the attempts (713 texts at a
        time) instead of parallelising them (2 852 at once).

        Args:
            cache_path: Target cache file.
        """
        _, first = await load_or_claim(cache_path, HASH, len(VECTORS))
        assert first is not None

        release(first)  # The computation raised; the caller released in `finally`.

        _, second = await load_or_claim(cache_path, HASH, len(VECTORS))

        assert second == first, "the next worker must be able to take over"
        release(second)

    async def test_release_is_idempotent(self, cache_path: Path) -> None:
        """Releasing twice, or releasing nothing, must never raise.

        Args:
            cache_path: Target cache file.
        """
        lock = lock_path_for(cache_path)

        release(lock)  # Never existed.
        lock.write_text("1", encoding="utf-8")
        release(lock)
        release(lock)  # Already gone.

        assert not lock.exists()

    async def test_a_fresh_volume_claims_immediately_instead_of_waiting(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The first-boot case this module exists for must not wait at all.

        On a brand new volume the cache directory does not exist yet, so
        ``os.open`` on the lock raises ``FileNotFoundError`` — an ``OSError``, not
        ``FileExistsError``. Treating that as a busy peer made every worker wait
        out the whole timeout and then embed anyway: worse than no coordination.

        Args:
            tmp_path: pytest temporary directory.
            monkeypatch: pytest monkeypatch fixture.
        """
        fresh = tmp_path / "tool_cache" / TOOL_EMBEDDINGS_CACHE_FILENAME
        assert not fresh.parent.exists()
        slept: list[float] = []

        async def _record(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr(cache_module.asyncio, "sleep", _record)

        embeddings, claim = await load_or_claim(fresh, HASH, len(VECTORS))

        assert embeddings is None
        assert claim == lock_path_for(fresh), "a fresh volume must yield the claim"
        assert slept == [], "nothing to wait for: no peer holds anything"
        release(claim)

    async def test_a_read_only_location_degrades_instead_of_waiting(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the claim genuinely cannot exist, compute now — do not poll.

        Waiting for a peer that can never appear would add the whole timeout to
        every boot. The caller computes unclaimed, exactly the pre-v1.25.27
        behaviour, and ``miss_unclaimed`` makes that visible.

        Args:
            tmp_path: pytest temporary directory.
            monkeypatch: pytest monkeypatch fixture.
        """
        cache = tmp_path / TOOL_EMBEDDINGS_CACHE_FILENAME
        before = _counter("miss_unclaimed")
        slept: list[float] = []

        async def _record(seconds: float) -> None:
            slept.append(seconds)

        def _read_only(*args: Any, **kwargs: Any) -> int:
            raise PermissionError("read-only file system")

        monkeypatch.setattr(cache_module.asyncio, "sleep", _record)
        _patch_os(monkeypatch, replace=os.replace)
        monkeypatch.setattr(cache_module.os, "open", _read_only)

        embeddings, claim = await load_or_claim(cache, HASH, len(VECTORS))

        assert (embeddings, claim) == (None, None)
        assert slept == [], "an impossible claim must not be waited on"
        assert _counter("miss_unclaimed") - before == 1

    async def test_a_zero_timeout_disables_waiting(
        self, cache_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The documented escape hatch back to "every worker computes".

        Args:
            cache_path: Target cache file.
            monkeypatch: pytest monkeypatch fixture.
        """
        lock_path_for(cache_path).write_text("1", encoding="utf-8")
        monkeypatch.setattr(
            settings, "tool_embeddings_cache_claim_timeout_seconds", 0.0, raising=False
        )
        slept: list[float] = []

        async def _record(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr(cache_module.asyncio, "sleep", _record)

        embeddings, claim = await load_or_claim(cache_path, HASH, len(VECTORS))

        assert (embeddings, claim) == (None, None)
        assert slept == [], "a zero timeout must not wait at all"

    async def test_a_cache_written_between_the_read_and_the_claim_is_used(
        self, cache_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Double-checked: holding the claim is not proof the work is still needed.

        A peer can write the cache and release the claim in the window between our
        last read and our acquisition — precisely the moment several workers are
        polling. Computing then would spend a full catalogue embedding on a result
        already sitting on disk.

        Args:
            cache_path: Target cache file.
            monkeypatch: pytest monkeypatch fixture.
        """
        # The cache appears exactly when we are about to take the claim.
        real_acquire = cache_module._acquire

        def _acquire_then_peer_finishes(lock_path: Path) -> Any:
            outcome = real_acquire(lock_path)
            save(cache_path, HASH, VECTORS)
            return outcome

        monkeypatch.setattr(cache_module, "_acquire", _acquire_then_peer_finishes)

        embeddings, claim = await load_or_claim(cache_path, HASH, len(VECTORS))

        assert embeddings == VECTORS, "the peer's result must be used, not recomputed"
        assert claim is None, "a claim we no longer need must be released"
        assert not lock_path_for(cache_path).exists()
