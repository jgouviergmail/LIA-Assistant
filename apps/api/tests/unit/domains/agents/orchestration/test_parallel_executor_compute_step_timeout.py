"""Unit tests for `_compute_step_timeout` (parallel_executor timeout policy).

Validates the per-tool-family timeout policy in isolation:

- Sub-agent floor/ceiling come from Settings (tunable via `.env`).
- Browser floor/ceiling are dedicated module constants (higher than generic).
- Image / devops use a moderate fixed floor + generic ceiling.
- Regular tools use the generic floor/ceiling.
- High-latency tools enforce `max(planner_request, family_default)` so the
  planner cannot impose a too-short timeout that would kill the loop.
- Regular tools just `min(planner_request or default, ceiling)`.

The helper is intentionally pure (no side effects, no I/O beyond a single
`get_settings()` read) so it can be tested without mocking the parallel
executor's whole context.
"""

from __future__ import annotations

import pytest

from src.core.config import get_settings
from src.core.constants import (
    BROWSER_TOOL_TIMEOUT_SECONDS,
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    MAX_BROWSER_TOOL_TIMEOUT_SECONDS,
    MAX_TOOL_TIMEOUT_SECONDS,
)
from src.domains.agents.orchestration.parallel_executor import _compute_step_timeout


@pytest.mark.unit
class TestComputeStepTimeoutSubAgent:
    """`delegate_to_sub_agent_tool` uses Settings-tunable floor/ceiling."""

    def test_defaults_to_settings_floor_when_planner_unset(self):
        """No planner request → effective default = settings.subagent_tool_timeout_seconds."""
        expected = get_settings().subagent_tool_timeout_seconds
        assert _compute_step_timeout("delegate_to_sub_agent_tool", None) == expected

    def test_planner_request_below_floor_is_raised_to_floor(self):
        """High-latency policy: planner asked 60s → bumped to 180s floor."""
        floor = get_settings().subagent_tool_timeout_seconds
        assert _compute_step_timeout("delegate_to_sub_agent_tool", 60.0) == floor

    def test_planner_request_between_floor_and_ceiling_is_kept(self):
        """Planner asked 240s (between 180 floor and 300 ceiling) → 240s."""
        result = _compute_step_timeout("delegate_to_sub_agent_tool", 240.0)
        assert result == 240.0

    def test_planner_request_above_ceiling_is_capped(self):
        """Planner asked 999s → clamped to settings.subagent_tool_max_timeout_seconds."""
        ceiling = get_settings().subagent_tool_max_timeout_seconds
        assert _compute_step_timeout("delegate_to_sub_agent_tool", 999.0) == ceiling


@pytest.mark.unit
class TestComputeStepTimeoutBrowser:
    """`browser_task_tool` uses the highest dedicated floor/ceiling."""

    def test_defaults_to_browser_floor(self):
        assert _compute_step_timeout("browser_task_tool", None) == BROWSER_TOOL_TIMEOUT_SECONDS

    def test_planner_request_below_floor_is_raised(self):
        """Planner asked 60s, browser floor is 300s → 300s."""
        assert _compute_step_timeout("browser_task_tool", 60.0) == BROWSER_TOOL_TIMEOUT_SECONDS

    def test_planner_request_above_ceiling_is_capped_to_browser_max(self):
        """Browser ceiling (600s) is higher than the generic MAX_TOOL_TIMEOUT (120s)."""
        assert (
            _compute_step_timeout("browser_task_tool", 9999.0) == MAX_BROWSER_TOOL_TIMEOUT_SECONDS
        )


@pytest.mark.unit
class TestComputeStepTimeoutImage:
    """Image tools (generate_image, edit_image): 90s floor, generic ceiling."""

    @pytest.mark.parametrize("tool_name", ["generate_image", "edit_image"])
    def test_defaults_to_image_floor(self, tool_name: str):
        assert _compute_step_timeout(tool_name, None) == 90.0

    @pytest.mark.parametrize("tool_name", ["generate_image", "edit_image"])
    def test_planner_request_below_floor_is_raised(self, tool_name: str):
        """Planner asked 30s → bumped to 90s image floor."""
        assert _compute_step_timeout(tool_name, 30.0) == 90.0

    @pytest.mark.parametrize("tool_name", ["generate_image", "edit_image"])
    def test_ceiling_is_generic_max_tool_timeout(self, tool_name: str):
        """Image tools cap at the generic 120s, not at the browser 600s."""
        assert _compute_step_timeout(tool_name, 9999.0) == MAX_TOOL_TIMEOUT_SECONDS


@pytest.mark.unit
class TestComputeStepTimeoutDevops:
    """`claude_server_task_tool` uses a 120s floor + generic ceiling."""

    def test_defaults_to_devops_floor(self):
        assert _compute_step_timeout("claude_server_task_tool", None) == 120.0

    def test_floor_is_enforced(self):
        """Planner asked 10s → bumped to 120s devops floor."""
        assert _compute_step_timeout("claude_server_task_tool", 10.0) == 120.0


@pytest.mark.unit
class TestComputeStepTimeoutGeneric:
    """Regular tools: DEFAULT floor, MAX_TOOL_TIMEOUT ceiling. No floor enforcement."""

    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_emails_tool",
            "send_email_tool",
            "brave_search_tool",
            "fetch_web_page_tool",
            "get_events_tool",
        ],
    )
    def test_defaults_to_generic_default(self, tool_name: str):
        assert _compute_step_timeout(tool_name, None) == DEFAULT_TOOL_TIMEOUT_SECONDS

    def test_planner_can_request_below_default(self):
        """Regular tools: planner can ask for less than the default (no floor enforcement)."""
        # A regular tool with a 10s planner-requested timeout stays at 10s.
        assert _compute_step_timeout("brave_search_tool", 10.0) == 10.0

    def test_planner_request_capped_at_generic_max(self):
        """Regular tools cap at 120s — sub-agent ceiling (300s) does NOT apply."""
        assert _compute_step_timeout("brave_search_tool", 9999.0) == MAX_TOOL_TIMEOUT_SECONDS

    def test_unknown_tool_name_uses_generic_policy(self):
        """An unknown tool name falls back to generic floor / ceiling."""
        assert _compute_step_timeout("some_future_tool", None) == DEFAULT_TOOL_TIMEOUT_SECONDS

    def test_none_tool_name_uses_generic_policy(self):
        """`step.tool_name = None` (CONDITIONAL step) falls back to generic policy."""
        assert _compute_step_timeout(None, None) == DEFAULT_TOOL_TIMEOUT_SECONDS


@pytest.mark.unit
class TestComputeStepTimeoutIsolation:
    """Per-family policies do not bleed across each other."""

    def test_subagent_ceiling_does_not_apply_to_regular_tools(self):
        """A 250s planner request on a regular tool clamps to 120s, NOT 300s (sub-agent ceiling)."""
        result = _compute_step_timeout("brave_search_tool", 250.0)
        assert result == MAX_TOOL_TIMEOUT_SECONDS

    def test_browser_ceiling_does_not_apply_to_regular_tools(self):
        """A 500s planner request on a regular tool clamps to 120s, NOT 600s (browser ceiling)."""
        result = _compute_step_timeout("brave_search_tool", 500.0)
        assert result == MAX_TOOL_TIMEOUT_SECONDS

    def test_subagent_floor_does_not_apply_to_regular_tools(self):
        """A 5s planner request on a regular tool stays at 5s, NOT bumped to 180s."""
        result = _compute_step_timeout("brave_search_tool", 5.0)
        assert result == 5.0
