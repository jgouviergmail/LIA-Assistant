"""The cache decision, exercised end to end through ``initialize()``.

The cache primitives themselves (location, atomic write, rejection rules, and the
claim that decides who computes) live in ``tool_embeddings_cache`` and are tested
in ``test_tool_embeddings_cache.py``. What only this path can prove is that the
selector actually consults them: production ran 27 boots with 108 misses and zero
hits, and no test noticed because none went through ``initialize()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.core.config import settings
from src.core.constants import TOOL_EMBEDDINGS_CACHE_FILENAME
from src.domains.agents.services.tool_selector import SemanticToolSelector

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


@pytest.mark.unit
class TestTheClaimIsAlwaysReleased:
    """The selector must never leave a claim behind — success or failure."""

    @staticmethod
    def _lock(cache_dir: Path) -> Path:
        """Claim marker the selector would use.

        Args:
            cache_dir: Temporary cache directory.

        Returns:
            The lock path.
        """
        return cache_dir / f"{TOOL_EMBEDDINGS_CACHE_FILENAME}.lock"

    async def test_released_after_a_successful_initialisation(
        self, cache_dir: Path, provider: Any
    ) -> None:
        """A leaked claim would make the next boot wait out the whole timeout.

        Args:
            cache_dir: Temporary cache directory.
            provider: Stubbed embedding provider.
        """
        await SemanticToolSelector().initialize([_manifest("alpha")])

        assert not self._lock(cache_dir).exists()

    async def test_released_when_the_embedding_call_fails(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch, provider: Any
    ) -> None:
        """This is what turns four simultaneous attempts into a relay.

        A holder whose provider call is rejected must hand the claim over, so the
        next worker tries alone — instead of every worker either deadlocking or
        embedding at once, which is what killed two workers in production.

        Args:
            cache_dir: Temporary cache directory.
            monkeypatch: pytest monkeypatch fixture.
            provider: Stubbed embedding provider.
        """

        working = provider.aembed_documents

        async def _rejected(texts: list[str]) -> list[list[float]]:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

        monkeypatch.setattr(provider, "aembed_documents", _rejected)

        with pytest.raises(RuntimeError):
            await SemanticToolSelector().initialize([_manifest("alpha")])

        assert not self._lock(cache_dir).exists(), "a failed holder must release its claim"

        # And the relay works: the next worker takes the freed claim and succeeds.
        monkeypatch.setattr(provider, "aembed_documents", working)
        await SemanticToolSelector().initialize([_manifest("alpha")])

        assert (cache_dir / TOOL_EMBEDDINGS_CACHE_FILENAME).is_file()
        assert not self._lock(cache_dir).exists()
