"""Disk cache of tool embeddings: location, atomicity, and rejection rules.

Two production defects motivate this module.

**The cache never survived a deploy.** Its directory resolved inside the
container's writable layer, which ``docker compose up -d --force-recreate``
discards. Measured in production over 14 days: 108 ``cache_miss`` events and
**zero** ``cache_hit`` across 27 boots, each of the four uvicorn workers
re-embedding all 713 catalogue texts — 2 852 embeddings per deploy, for a payload
whose content hash had not changed in four days. The location is now settings
driven and anchored on the application root, so production can point it at a
mounted volume while the default keeps dev behaviour.

**The write was not atomic.** All four workers write the same multi-megabyte
document at boot; a plain ``write_text`` lets a reader observe a prefix of it,
and the reader's only recovery is to re-embed everything. Staging plus
``os.replace`` makes the swap atomic, and the pid in the staging name keeps two
workers from corrupting each other's temporary file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.config import settings
from src.core.constants import (
    TOOL_EMBEDDINGS_CACHE_DIR_DEFAULT,
    TOOL_EMBEDDINGS_CACHE_FILENAME,
)
from src.domains.agents.services import tool_selector as tool_selector_module
from src.domains.agents.services.tool_selector import (
    SemanticToolSelector,
    resolve_tool_embeddings_cache_dir,
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

    resolved = resolve_tool_embeddings_cache_dir()

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
    (run from ``/app``) pointing at the same file, and that stops a cache from
    silently going missing when a script is launched from the repository root.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        tmp_path: pytest temporary directory.
    """
    monkeypatch.setattr(settings, "tool_embeddings_cache_dir", "data/tool_cache", raising=False)

    before = resolve_tool_embeddings_cache_dir()
    monkeypatch.chdir(tmp_path)
    after = resolve_tool_embeddings_cache_dir()

    assert before == after


def test_absolute_path_is_honoured_verbatim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An absolute setting is the escape hatch for an arbitrary mount point.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        tmp_path: pytest temporary directory.
    """
    target = tmp_path / "elsewhere"
    monkeypatch.setattr(settings, "tool_embeddings_cache_dir", str(target), raising=False)

    assert resolve_tool_embeddings_cache_dir() == target


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

    assert resolve_tool_embeddings_cache_dir() == target
    assert not target.exists()


# ==========================================================================
# Round trip and rejection rules
# ==========================================================================


def test_save_then_load_returns_the_same_vectors(cache_path: Path) -> None:
    """The nominal path: what was written is what comes back.

    Args:
        cache_path: Target cache file.
    """
    SemanticToolSelector._save_embedding_cache(cache_path, HASH, VECTORS)

    assert SemanticToolSelector._load_embedding_cache(cache_path, HASH, len(VECTORS)) == VECTORS


def test_save_creates_missing_parent_directories(tmp_path: Path) -> None:
    """A fresh volume is an empty directory; deeper targets must still work.

    Args:
        tmp_path: pytest temporary directory.
    """
    nested = tmp_path / "a" / "b" / TOOL_EMBEDDINGS_CACHE_FILENAME

    SemanticToolSelector._save_embedding_cache(nested, HASH, VECTORS)

    assert nested.is_file()


def test_missing_file_is_a_miss(cache_path: Path) -> None:
    """An absent cache is a miss, not an error.

    Args:
        cache_path: Target cache file.
    """
    assert SemanticToolSelector._load_embedding_cache(cache_path, HASH, len(VECTORS)) is None


def test_stale_hash_is_rejected(cache_path: Path) -> None:
    """A changed catalogue must not be served from the previous vectors.

    Args:
        cache_path: Target cache file.
    """
    SemanticToolSelector._save_embedding_cache(cache_path, HASH, VECTORS)

    assert SemanticToolSelector._load_embedding_cache(cache_path, "b" * 64, len(VECTORS)) is None


def test_count_mismatch_is_rejected(cache_path: Path) -> None:
    """Fewer vectors than texts would index out of bounds downstream.

    Args:
        cache_path: Target cache file.
    """
    SemanticToolSelector._save_embedding_cache(cache_path, HASH, VECTORS)

    assert SemanticToolSelector._load_embedding_cache(cache_path, HASH, len(VECTORS) + 1) is None


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

    assert SemanticToolSelector._load_embedding_cache(cache_path, HASH, len(VECTORS)) is None


# ==========================================================================
# Atomicity
# ==========================================================================


def _patch_os(
    monkeypatch: pytest.MonkeyPatch,
    *,
    replace: Any,
    getpid: Any = os.getpid,
) -> None:
    """Swap the ``os`` handle the module under test uses.

    Replacing the attribute on the real ``os`` module would rewire the whole
    interpreter for the duration of the test — and a spy that calls
    ``os.replace`` would then call itself. A namespace exposing only what
    ``_save_embedding_cache`` consumes keeps the substitution local.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        replace: Stand-in for ``os.replace``.
        getpid: Stand-in for ``os.getpid``.
    """
    monkeypatch.setattr(tool_selector_module, "os", SimpleNamespace(replace=replace, getpid=getpid))


def test_save_leaves_no_staging_file_behind(cache_path: Path) -> None:
    """A stale staging file would weigh as much as the cache itself.

    Args:
        cache_path: Target cache file.
    """
    SemanticToolSelector._save_embedding_cache(cache_path, HASH, VECTORS)

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

    SemanticToolSelector._save_embedding_cache(cache_path, HASH, VECTORS)
    SemanticToolSelector._save_embedding_cache(cache_path, HASH, VECTORS)

    assert staged == [
        f"{TOOL_EMBEDDINGS_CACHE_FILENAME}.4242.tmp",
        f"{TOOL_EMBEDDINGS_CACHE_FILENAME}.4343.tmp",
    ]


def test_a_reader_never_observes_a_partial_document(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Until the rename, the visible file is still the previous one.

    The observable contract of ``os.replace``: content is swapped in one step, so
    a concurrent reader gets the old complete document or the new complete one.

    Args:
        cache_path: Target cache file.
        monkeypatch: pytest monkeypatch fixture.
    """
    SemanticToolSelector._save_embedding_cache(cache_path, HASH, VECTORS)
    previous = cache_path.read_text(encoding="utf-8")
    observed: list[str] = []

    def _observe_then_replace(src: Any, dst: Any) -> None:
        observed.append(Path(dst).read_text(encoding="utf-8"))
        os.replace(src, dst)

    _patch_os(monkeypatch, replace=_observe_then_replace)

    new_vectors = [[9.9, 9.9]]
    SemanticToolSelector._save_embedding_cache(cache_path, "c" * 64, new_vectors)

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
    SemanticToolSelector._save_embedding_cache(cache_path, HASH, VECTORS)

    def _boom(src: Any, dst: Any) -> None:
        raise OSError("no space left on device")

    _patch_os(monkeypatch, replace=_boom)

    SemanticToolSelector._save_embedding_cache(cache_path, "d" * 64, [[0.0]])

    assert SemanticToolSelector._load_embedding_cache(cache_path, HASH, len(VECTORS)) == VECTORS
    assert list(cache_path.parent.glob("*.tmp")) == []


def test_save_failure_is_swallowed_and_logged(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unwritable cache degrades cost, not availability — boot must continue.

    Args:
        cache_path: Target cache file.
        monkeypatch: pytest monkeypatch fixture.
    """
    warnings: list[tuple[str, dict[str, Any]]] = []

    def _warning(event: str, **kwargs: Any) -> None:
        warnings.append((event, kwargs))

    def _read_only_filesystem(src: Any, dst: Any) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(tool_selector_module.logger, "warning", _warning)
    _patch_os(monkeypatch, replace=_read_only_filesystem)

    SemanticToolSelector._save_embedding_cache(cache_path, HASH, VECTORS)

    assert [event for event, _ in warnings] == ["tool_embedding_cache_save_failed"]
    assert warnings[0][1]["error_type"] == "OSError"


# ==========================================================================
# The cache decision, end to end through initialize()
# ==========================================================================


def _manifest(name: str) -> Any:
    """A manifest carrying only what the selector reads at initialisation.

    Args:
        name: Tool name.

    Returns:
        The manifest.
    """
    from src.domains.agents.registry.catalogue import (
        CostProfile,
        OutputFieldSchema,
        PermissionProfile,
        ToolManifest,
    )

    return ToolManifest(
        name=name,
        agent="test_agent",
        description=f"Summary of {name}\nMODES: ignored by the embedding",
        parameters=[],
        outputs=[OutputFieldSchema(path="items[]", type="array", description="Items")],
        cost=CostProfile(est_tokens_in=10, est_tokens_out=10),
        permissions=PermissionProfile(required_scopes=[]),
        semantic_keywords=["first keyword", "second keyword"],
    )


@pytest.fixture
def cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the cache at a temporary directory.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        tmp_path: pytest temporary directory.

    Returns:
        The directory the selector will use.
    """
    target = tmp_path / "tool_cache"
    monkeypatch.setattr(settings, "tool_embeddings_cache_dir", str(target), raising=False)
    return target


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Stub the embedding provider the selector reaches for at initialisation.

    Args:
        monkeypatch: pytest monkeypatch fixture.

    Returns:
        The stub, whose ``calls`` records each batch it was given.
    """

    class _Stub:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
            self.calls.append(list(texts))
            return [[float(index), 0.0] for index, _ in enumerate(texts)]

    stub = _Stub()
    import src.infrastructure.llm.memory_embeddings as memory_embeddings_module

    monkeypatch.setattr(memory_embeddings_module, "get_memory_embeddings", lambda: stub)
    return stub


def _cache_counter(result: str) -> float:
    """Current value of the cache outcome counter.

    Args:
        result: Label value ("hit" or "miss").

    Returns:
        The counter value.
    """
    from src.infrastructure.observability.metrics_agents import tool_embeddings_cache_total

    return float(tool_embeddings_cache_total.labels(result=result)._value.get())


@pytest.mark.unit
class TestCacheOutcomeIsMeasured:
    """A 100% miss rate must be visible on a dashboard, not by grepping logs."""

    async def test_a_cold_cache_counts_a_miss_and_embeds(
        self, cache_dir: Path, provider: Any
    ) -> None:
        """First boot on an empty volume: one miss, one provider call.

        Args:
            cache_dir: Temporary cache directory.
            provider: Stubbed embedding provider.
        """
        before = _cache_counter("miss")

        await SemanticToolSelector().initialize([_manifest("alpha")])

        assert _cache_counter("miss") - before == 1
        assert len(provider.calls) == 1
        assert (cache_dir / TOOL_EMBEDDINGS_CACHE_FILENAME).is_file()

    async def test_a_warm_cache_counts_a_hit_and_embeds_nothing(
        self, cache_dir: Path, provider: Any
    ) -> None:
        """Second boot with the volume intact: no provider call at all.

        This is the property production never had — 27 boots, 108 misses, zero
        hits — because the cache lived in the container's writable layer.

        Args:
            cache_dir: Temporary cache directory.
            provider: Stubbed embedding provider.
        """
        await SemanticToolSelector().initialize([_manifest("alpha")])
        provider.calls.clear()
        before = _cache_counter("hit")

        await SemanticToolSelector().initialize([_manifest("alpha")])

        assert _cache_counter("hit") - before == 1
        assert provider.calls == []

    async def test_a_changed_catalogue_counts_a_miss(self, cache_dir: Path, provider: Any) -> None:
        """A different tool set must not be served from the previous vectors.

        Args:
            cache_dir: Temporary cache directory.
            provider: Stubbed embedding provider.
        """
        await SemanticToolSelector().initialize([_manifest("alpha")])
        before = _cache_counter("miss")

        await SemanticToolSelector().initialize([_manifest("beta")])

        assert _cache_counter("miss") - before == 1
