"""Per-user adaptive threshold controller (lot 7, audit 2026-08-19).

A fixed global similarity threshold is structurally wrong for per-user
distributions: prod showed journal-injection scores massed at 0.53–0.61 just
under the global 0.63, with an injection rate of 10%. The controller moves a
per-user threshold inside HARD bounds, one small step at a time, toward a
target injection-rate band — bounded, hysteretic, observable, fail-open.

Contract pinned here:
- pure math (``decide_adjustment``) separated from Redis IO;
- hard floor/ceiling always win;
- no adjustment below ``min_samples`` or before ``adjust_interval`` elapses;
- direction follows the observed rate vs the target band;
- IO is fail-open: Redis down → the static default, never an error;
- the perimeter registry is validated at import (ADR-085 boot-assert family).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.core.config import settings
from src.infrastructure.adaptive.threshold_controller import (
    PERIMETERS,
    ThresholdPerimeter,
    assert_perimeters_valid,
    decide_adjustment,
    effective_threshold,
    observe_score,
)

SPEC = ThresholdPerimeter(
    name="test_perimeter",
    floor=0.50,
    ceiling=0.70,
    target_rate_low=0.10,
    target_rate_high=0.35,
    default_getter=lambda: 0.63,
)

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
OLD = NOW - timedelta(hours=48)


def _cfg(**overrides: Any) -> dict[str, Any]:
    cfg = {
        "window_size": 50,
        "min_samples": 20,
        "step": 0.01,
        "adjust_interval_hours": 24.0,
    }
    cfg.update(overrides)
    return cfg


class TestDecideAdjustment:
    def test_rate_below_band_steps_down(self) -> None:
        samples = [0.55] * 30  # rate at 0.63 = 0% < 10%
        assert decide_adjustment(0.63, samples, NOW, OLD, SPEC, _cfg()) == 0.62

    def test_rate_above_band_steps_up(self) -> None:
        samples = [0.65] * 30  # rate at 0.60 = 100% > 35%
        assert decide_adjustment(0.60, samples, NOW, OLD, SPEC, _cfg()) == 0.61

    def test_rate_inside_band_holds(self) -> None:
        samples = [0.70] * 6 + [0.50] * 24  # 20% in [10%, 35%]
        assert decide_adjustment(0.63, samples, NOW, OLD, SPEC, _cfg()) is None

    def test_floor_is_hard(self) -> None:
        samples = [0.30] * 30
        assert decide_adjustment(SPEC.floor, samples, NOW, OLD, SPEC, _cfg()) is None

    def test_ceiling_is_hard(self) -> None:
        samples = [0.99] * 30
        assert decide_adjustment(SPEC.ceiling, samples, NOW, OLD, SPEC, _cfg()) is None

    def test_below_min_samples_never_adjusts(self) -> None:
        samples = [0.30] * 19
        assert decide_adjustment(0.63, samples, NOW, OLD, SPEC, _cfg()) is None

    def test_hysteresis_one_step_per_interval(self) -> None:
        samples = [0.30] * 30
        recent = NOW - timedelta(hours=2)
        assert decide_adjustment(0.63, samples, NOW, recent, SPEC, _cfg()) is None

    def test_never_adjusted_counts_as_due(self) -> None:
        samples = [0.30] * 30
        assert decide_adjustment(0.63, samples, NOW, None, SPEC, _cfg()) == 0.62

    def test_step_is_single_never_a_jump(self) -> None:
        """However far the rate is from the band, one interval = one step."""
        samples = [0.30] * 50
        assert decide_adjustment(0.68, samples, NOW, OLD, SPEC, _cfg()) == 0.67


class _FakeRedis:
    """Minimal async Redis double (repo _FakeRedis family)."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self.broken = False

    async def get(self, key: str) -> str | None:
        if self.broken:
            raise ConnectionError("redis down")
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        if self.broken:
            raise ConnectionError("redis down")
        self.data[key] = value
        self.ttls[key] = ex


def _patch_redis(monkeypatch: Any, fake: _FakeRedis) -> None:
    async def _get_redis() -> _FakeRedis:
        return fake

    monkeypatch.setattr(
        "src.infrastructure.adaptive.threshold_controller._get_redis",
        _get_redis,
    )


class TestEffectiveThreshold:
    async def test_defaults_when_no_state(self, monkeypatch: Any) -> None:
        _patch_redis(monkeypatch, _FakeRedis())
        value = await effective_threshold(uuid4(), "journal_injection")
        assert value == settings.journal_context_min_score

    async def test_redis_down_fails_open_to_default(self, monkeypatch: Any) -> None:
        fake = _FakeRedis()
        fake.broken = True
        _patch_redis(monkeypatch, fake)
        value = await effective_threshold(uuid4(), "journal_injection")
        assert value == settings.journal_context_min_score

    async def test_malformed_state_falls_back_to_default(self, monkeypatch: Any) -> None:
        fake = _FakeRedis()
        uid = uuid4()
        fake.data[f"adaptive:thr:journal_injection:{uid}"] = "{not json"
        _patch_redis(monkeypatch, fake)
        assert await effective_threshold(uid, "journal_injection") == (
            settings.journal_context_min_score
        )

    async def test_stored_threshold_is_clamped_into_bounds(self, monkeypatch: Any) -> None:
        """Defense in depth: a corrupt or stale value never escapes the bounds."""
        fake = _FakeRedis()
        uid = uuid4()
        fake.data[f"adaptive:thr:journal_injection:{uid}"] = json.dumps(
            {"t": 0.10, "s": [], "at": None}
        )
        _patch_redis(monkeypatch, fake)
        value = await effective_threshold(uid, "journal_injection")
        assert value == PERIMETERS["journal_injection"].floor


class TestObserveScore:
    async def test_appends_sample_and_bounds_window(self, monkeypatch: Any) -> None:
        fake = _FakeRedis()
        _patch_redis(monkeypatch, fake)
        uid = uuid4()
        for i in range(60):
            await observe_score(uid, "journal_injection", 0.50 + i * 0.001)
        state = json.loads(fake.data[f"adaptive:thr:journal_injection:{uid}"])
        assert len(state["s"]) == settings.adaptive_threshold_window_size

    async def test_adjustment_persists_and_is_visible(self, monkeypatch: Any) -> None:
        fake = _FakeRedis()
        _patch_redis(monkeypatch, fake)
        uid = uuid4()
        # Enough low samples to drive a step down once the interval is due
        # (state starts with adjusted_at=None → due immediately).
        for _ in range(settings.adaptive_threshold_min_samples + 1):
            await observe_score(uid, "journal_injection", 0.50)
        value = await effective_threshold(uid, "journal_injection")
        assert value == settings.journal_context_min_score - settings.adaptive_threshold_step

    async def test_redis_down_is_silent(self, monkeypatch: Any) -> None:
        fake = _FakeRedis()
        fake.broken = True
        _patch_redis(monkeypatch, fake)
        await observe_score(uuid4(), "journal_injection", 0.6)  # must not raise

    async def test_disabled_flag_freezes_everything(self, monkeypatch: Any) -> None:
        fake = _FakeRedis()
        _patch_redis(monkeypatch, fake)
        monkeypatch.setattr(settings, "adaptive_thresholds_enabled", False)
        uid = uuid4()
        await observe_score(uid, "journal_injection", 0.10)
        assert fake.data == {}
        assert await effective_threshold(uid, "journal_injection") == (
            settings.journal_context_min_score
        )


class TestStateTtl:
    async def test_state_carries_a_sliding_ttl(self, monkeypatch: Any) -> None:
        """Advisory state must expire: without a TTL, deleted or abandoned
        accounts leave orphan keys forever (the recurrence ledger expires —
        this store must too). Refreshed on every write (sliding)."""
        fake = _FakeRedis()
        _patch_redis(monkeypatch, fake)
        uid = uuid4()
        await observe_score(uid, "journal_injection", 0.6)
        key = f"adaptive:thr:journal_injection:{uid}"
        assert fake.ttls[key] == settings.adaptive_threshold_state_ttl_days * 86_400


class TestUnknownPerimeter:
    async def test_effective_threshold_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="unknown adaptive perimeter"):
            await effective_threshold(uuid4(), "no_such_perimeter")

    async def test_observe_score_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="unknown adaptive perimeter"):
            await observe_score(uuid4(), "no_such_perimeter", 0.5)


class TestPerimeterRegistry:
    def test_registry_is_valid_at_boot(self) -> None:
        assert_perimeters_valid()

    def test_journal_perimeter_registered_with_sane_bounds(self) -> None:
        spec = PERIMETERS["journal_injection"]
        assert spec.floor < spec.ceiling
        assert 0.0 < spec.target_rate_low < spec.target_rate_high < 1.0
        # The static default must sit inside the hard bounds.
        assert spec.floor <= spec.default_getter() <= spec.ceiling
