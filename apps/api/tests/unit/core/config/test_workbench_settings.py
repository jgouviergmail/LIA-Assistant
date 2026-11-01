"""WorkbenchSettings: every bound is a setting, every default a constant (ADR-369).

The workbench publishes what it enforces (ADR-184): page sizes, the bulk
selection, the download ceiling, the calendar window and the per-account rate
windows. Pinned here: the class reaches the composed ``Settings``, each default
is its ``core.constants`` entry, and the bounds refuse what would disable a
limit (a zero window) or make one meaningless.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core import constants
from src.core.config import settings
from src.core.config.workbench import WorkbenchSettings

pytestmark = pytest.mark.unit

_DEFAULTS = [
    ("workbench_read_rate_limit_calls", "WORKBENCH_READ_RATE_LIMIT_CALLS_DEFAULT", 120),
    (
        "workbench_read_rate_limit_window_seconds",
        "WORKBENCH_READ_RATE_LIMIT_WINDOW_SECONDS_DEFAULT",
        60,
    ),
    ("workbench_write_rate_limit_calls", "WORKBENCH_WRITE_RATE_LIMIT_CALLS_DEFAULT", 30),
    (
        "workbench_write_rate_limit_window_seconds",
        "WORKBENCH_WRITE_RATE_LIMIT_WINDOW_SECONDS_DEFAULT",
        60,
    ),
    ("workbench_send_rate_limit_calls", "WORKBENCH_SEND_RATE_LIMIT_CALLS_DEFAULT", 10),
    (
        "workbench_send_rate_limit_window_seconds",
        "WORKBENCH_SEND_RATE_LIMIT_WINDOW_SECONDS_DEFAULT",
        60,
    ),
    ("workbench_bulk_rate_limit_calls", "WORKBENCH_BULK_RATE_LIMIT_CALLS_DEFAULT", 6),
    (
        "workbench_bulk_rate_limit_window_seconds",
        "WORKBENCH_BULK_RATE_LIMIT_WINDOW_SECONDS_DEFAULT",
        60,
    ),
    ("workbench_download_rate_limit_calls", "WORKBENCH_DOWNLOAD_RATE_LIMIT_CALLS_DEFAULT", 10),
    (
        "workbench_download_rate_limit_window_seconds",
        "WORKBENCH_DOWNLOAD_RATE_LIMIT_WINDOW_SECONDS_DEFAULT",
        60,
    ),
    ("workbench_page_size", "WORKBENCH_PAGE_SIZE_DEFAULT", 25),
    ("workbench_bulk_max_items", "WORKBENCH_BULK_MAX_ITEMS_DEFAULT", 50),
    (
        "workbench_calendar_window_max_events",
        "WORKBENCH_CALENDAR_WINDOW_MAX_EVENTS_DEFAULT",
        500,
    ),
    ("workbench_download_max_bytes", "WORKBENCH_DOWNLOAD_MAX_BYTES_DEFAULT", 25 * 1024 * 1024),
    ("workbench_idempotency_ttl_seconds", "WORKBENCH_IDEMPOTENCY_TTL_SECONDS_DEFAULT", 86_400),
]


class TestComposition:
    def test_flag_defaults_to_enabled(self) -> None:
        """A fresh instance offers the section; the demonstrator closes it in its env."""
        assert WorkbenchSettings.model_fields["workbench_enabled"].default is True

    def test_every_field_is_reachable_from_the_composed_settings(self) -> None:
        for field in WorkbenchSettings.model_fields:
            assert hasattr(settings, field), f"{field} missing from the Settings MRO"


class TestDefaults:
    @pytest.mark.parametrize(("field", "constant", "value"), _DEFAULTS)
    def test_default_is_the_constant(self, field: str, constant: str, value: int) -> None:
        assert getattr(constants, constant) == value
        assert WorkbenchSettings.model_fields[field].default == value


class TestBounds:
    @pytest.mark.parametrize("field", [field for field, _, _ in _DEFAULTS])
    def test_zero_is_refused(self, field: str) -> None:
        with pytest.raises(ValidationError):
            WorkbenchSettings(**{field: 0})

    def test_page_size_cannot_exceed_the_provider_ceiling_range(self) -> None:
        """The provider clients cap a listing at 50 (``api_max_items_per_request``)."""
        with pytest.raises(ValidationError):
            WorkbenchSettings(workbench_page_size=51)

    def test_an_operator_value_inside_the_bounds_is_kept(self) -> None:
        tuned = WorkbenchSettings(workbench_send_rate_limit_calls=20, workbench_page_size=50)
        assert tuned.workbench_send_rate_limit_calls == 20
        assert tuned.workbench_page_size == 50
