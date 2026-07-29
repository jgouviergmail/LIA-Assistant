"""Product vocabulary + derivations (ADR-178) — bounded by construction.

What must hold:
- every derivation output belongs to its bounded vocabulary (an out-of-set
  value would create an unbounded Prometheus series);
- the channel derivation reuses the existing scheduled-action session prefix
  (never a re-hardcoded literal);
- the event-type registry completeness assert fails loudly on drift (ADR-085).
"""

from __future__ import annotations

import pytest

from src.core.constants import SCHEDULED_ACTIONS_SESSION_PREFIX
from src.domains.product.constants import (
    CHANNELS,
    DEVICE_CLASSES,
    PRODUCT_EVENT_DESCRIPTIONS,
    RESULT_TYPES,
    ProductEventType,
    assert_product_registries_complete,
    derive_channel,
    derive_device_class,
    derive_result_type,
)


class TestDeriveDeviceClass:
    """os_family (ADR-144 bounded families) → device class."""

    @pytest.mark.parametrize(
        ("os_family", "expected"),
        [
            ("android", "mobile"),
            ("ios", "mobile"),
            ("windows", "desktop"),
            ("macos", "desktop"),
            ("linux", "desktop"),
            ("unknown", "unknown"),
            (None, "unknown"),
            ("beos", "unknown"),
        ],
    )
    def test_mapping(self, os_family: str | None, expected: str) -> None:
        assert derive_device_class(os_family) == expected

    def test_output_always_bounded(self) -> None:
        for family in ("android", "ios", "windows", "macos", "linux", None, "x"):
            assert derive_device_class(family) in DEVICE_CLASSES


class TestDeriveChannel:
    """Session-prefix attribution, never a re-hardcoded literal."""

    def test_scheduler_prefix(self) -> None:
        assert derive_channel(f"{SCHEDULED_ACTIONS_SESSION_PREFIX}abc") == "scheduler"

    def test_web_default(self) -> None:
        assert derive_channel("session-123") == "web"

    def test_missing_session(self) -> None:
        assert derive_channel(None) == "unknown"
        assert derive_channel("") == "unknown"

    def test_output_always_bounded(self) -> None:
        for sid in (None, "", "abc", f"{SCHEDULED_ACTIONS_SESSION_PREFIX}x"):
            assert derive_channel(sid) in CHANNELS


class TestDeriveResultType:
    """v1 approximation: scheduler → automation_run, actionable → action."""

    @pytest.mark.parametrize(
        ("intention", "channel", "expected"),
        [
            (None, "scheduler", "automation_run"),
            ("actionable", "scheduler", "automation_run"),
            ("actionable", "web", "action"),
            ("conversation", "web", "answer"),
            (None, "web", "answer"),
            ("garbage", "unknown", "answer"),
        ],
    )
    def test_mapping(self, intention: str | None, channel: str, expected: str) -> None:
        assert derive_result_type(intention, channel) == expected

    def test_output_always_bounded(self) -> None:
        for intention in (None, "actionable", "conversation", "x"):
            for channel in CHANNELS:
                assert derive_result_type(intention, channel) in RESULT_TYPES


class TestEventRegistry:
    """ADR-085 doctrine: registry drift fails loudly at boot."""

    def test_completeness_holds(self) -> None:
        assert_product_registries_complete()

    def test_every_event_type_described(self) -> None:
        assert set(PRODUCT_EVENT_DESCRIPTIONS) == set(ProductEventType)

    def test_missing_entry_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delitem(PRODUCT_EVENT_DESCRIPTIONS, ProductEventType.OUTCOME_PRODUCED)
        with pytest.raises(RuntimeError, match="outcome_produced"):
            assert_product_registries_complete()
