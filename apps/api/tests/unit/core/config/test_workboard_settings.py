"""WorkboardSettings: every bound is a setting, every default a constant (ADR-276).

Two things are pinned here, and they fail for different reasons:

- the module composes into the ``Settings`` MRO (the peers precedent) — a
  settings class nobody added to the composition is a flag nothing reads;
- every default equals its ``core.constants`` entry — the repository rule that
  a magic value never lives in a config module, so an operator reading the
  constants file sees what the deployment actually ships.
"""

import pytest

from src.core import constants
from src.core.config import settings
from src.core.config.workboard import WorkboardSettings

pytestmark = pytest.mark.unit


class TestComposition:
    """The class reached the composed Settings object."""

    def test_flag_defaults_to_enabled(self) -> None:
        """Owner arbitration 2026-09-08: the board ships ON."""
        assert settings.workboard_enabled is True

    def test_every_field_is_reachable_from_the_composed_settings(self) -> None:
        for field in WorkboardSettings.model_fields:
            assert hasattr(settings, field), f"{field} missing from the Settings MRO"


class TestDefaults:
    """Each default is the constant, and the constant is the only literal."""

    @pytest.mark.parametrize(
        ("field", "constant"),
        [
            ("workboard_run_sweep_seconds", "WORKBOARD_RUN_SWEEP_SECONDS_DEFAULT"),
            ("workboard_run_timeout_seconds", "WORKBOARD_RUN_TIMEOUT_SECONDS_DEFAULT"),
            ("workboard_run_max_attempts", "WORKBOARD_RUN_MAX_ATTEMPTS_DEFAULT"),
            ("workboard_quota_retry_minutes", "WORKBOARD_QUOTA_RETRY_MINUTES_DEFAULT"),
            ("workboard_max_tickets_per_user", "WORKBOARD_MAX_TICKETS_PER_USER_DEFAULT"),
            (
                "workboard_max_children_per_ticket",
                "WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT",
            ),
            ("workboard_max_runs_per_ticket", "WORKBOARD_MAX_RUNS_PER_TICKET_DEFAULT"),
            (
                "workboard_hidden_rows_retention_days",
                "WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS_DEFAULT",
            ),
            ("workboard_title_max_chars", "WORKBOARD_TITLE_MAX_CHARS_DEFAULT"),
            ("workboard_description_max_chars", "WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT"),
            ("workboard_comment_max_chars", "WORKBOARD_COMMENT_MAX_CHARS_DEFAULT"),
            ("workboard_closed_hide_days_default", "WORKBOARD_CLOSED_HIDE_DAYS_DEFAULT"),
            ("workboard_nudge_due_hours", "WORKBOARD_NUDGE_DUE_HOURS_DEFAULT"),
            ("workboard_nudge_waiting_hours", "WORKBOARD_NUDGE_WAITING_HOURS_DEFAULT"),
            ("workboard_nudge_cooldown_days", "WORKBOARD_NUDGE_COOLDOWN_DAYS_DEFAULT"),
            ("workboard_brief_max_notes", "WORKBOARD_BRIEF_MAX_NOTES_DEFAULT"),
        ],
    )
    def test_every_default_is_a_constant(self, field: str, constant: str) -> None:
        assert getattr(WorkboardSettings(), field) == getattr(constants, constant)

    def test_a_run_timeout_shorter_than_the_sweep_would_reap_live_runs(self) -> None:
        """The reaper releases a claim older than the timeout; a timeout below
        the sweep interval would release a run still in flight."""
        defaults = WorkboardSettings()
        assert defaults.workboard_run_timeout_seconds >= defaults.workboard_run_sweep_seconds


class TestOverrides:
    """An operator may retune every bound without a code change."""

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORKBOARD_MAX_RUNS_PER_TICKET", "3")
        assert WorkboardSettings().workboard_max_runs_per_ticket == 3

    def test_flag_can_be_switched_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORKBOARD_ENABLED", "false")
        assert WorkboardSettings().workboard_enabled is False

    @pytest.mark.parametrize(
        ("variable", "value"),
        [
            ("WORKBOARD_MAX_RUNS_PER_TICKET", "0"),
            ("WORKBOARD_RUN_SWEEP_SECONDS", "5"),
            ("WORKBOARD_MAX_TICKETS_PER_USER", "0"),
            ("WORKBOARD_TITLE_MAX_CHARS", "1"),
        ],
    )
    def test_out_of_range_values_are_refused_at_boot(
        self, monkeypatch: pytest.MonkeyPatch, variable: str, value: str
    ) -> None:
        """A nonsensical bound fails to start rather than silently applying."""
        monkeypatch.setenv(variable, value)
        with pytest.raises(ValueError):
            WorkboardSettings()
