"""Unit tests for `compute_step_timeout` (step_timeouts — executor timeout policy).

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
from src.domains.agents.orchestration.step_timeouts import compute_step_timeout


@pytest.mark.unit
class TestComputeStepTimeoutSubAgent:
    """`delegate_to_sub_agent_tool` uses Settings-tunable floor/ceiling."""

    def test_defaults_to_settings_floor_when_planner_unset(self):
        """No planner request → effective default = settings.subagent_tool_timeout_seconds."""
        expected = get_settings().subagent_tool_timeout_seconds
        assert compute_step_timeout("delegate_to_sub_agent_tool", None) == expected

    def test_planner_request_below_floor_is_raised_to_floor(self):
        """High-latency policy: planner asked 60s → bumped to 180s floor."""
        floor = get_settings().subagent_tool_timeout_seconds
        assert compute_step_timeout("delegate_to_sub_agent_tool", 60.0) == floor

    def test_planner_request_between_floor_and_ceiling_is_kept(self):
        """A planner request strictly between the floor and ceiling is preserved.

        Floor and ceiling are read from Settings (never hardcoded — operators
        can override the defaults via SUBAGENT_TOOL_TIMEOUT_SECONDS and
        SUBAGENT_TOOL_MAX_TIMEOUT_SECONDS). The midpoint is the only value
        guaranteed to fall strictly inside any (floor, ceiling) interval.
        Skipped when floor == ceiling (no value exists strictly between).
        """
        s = get_settings()
        floor = s.subagent_tool_timeout_seconds
        ceiling = s.subagent_tool_max_timeout_seconds
        if floor >= ceiling:
            pytest.skip(
                f"Operator collapsed sub-agent floor/ceiling to {floor}/{ceiling}; "
                "no value exists strictly between them to test the kept-as-is path."
            )
        midpoint = (floor + ceiling) / 2
        assert compute_step_timeout("delegate_to_sub_agent_tool", midpoint) == midpoint

    def test_planner_request_above_ceiling_is_capped(self):
        """Planner asked 999s → clamped to settings.subagent_tool_max_timeout_seconds."""
        ceiling = get_settings().subagent_tool_max_timeout_seconds
        assert compute_step_timeout("delegate_to_sub_agent_tool", 999.0) == ceiling


@pytest.mark.unit
class TestComputeStepTimeoutBrowser:
    """`browser_task_tool` uses the highest dedicated floor/ceiling."""

    def test_defaults_to_browser_floor(self):
        assert compute_step_timeout("browser_task_tool", None) == BROWSER_TOOL_TIMEOUT_SECONDS

    def test_planner_request_below_floor_is_raised(self):
        """Planner asked 60s, browser floor is 300s → 300s."""
        assert compute_step_timeout("browser_task_tool", 60.0) == BROWSER_TOOL_TIMEOUT_SECONDS

    def test_planner_request_above_ceiling_is_capped_to_browser_max(self):
        """Browser ceiling (600s) is higher than the generic MAX_TOOL_TIMEOUT (120s)."""
        assert compute_step_timeout("browser_task_tool", 9999.0) == MAX_BROWSER_TOOL_TIMEOUT_SECONDS


@pytest.mark.unit
class TestComputeStepTimeoutImage:
    """Image tools get a dedicated floor AND a dedicated ceiling.

    Measured against gpt-image-2 in production on 2026-07-27:

    ==========================  =========
    Parameters                  Latency
    ==========================  =========
    ``medium`` ``1024x1536``      47.2 s
    ``high`` ``1024x1536``       138.3 s
    ==========================  =========

    The old policy was a 90 s floor under the *generic* 120 s ceiling, so
    ``quality=high`` could not succeed at any setting — 138.3 s exceeds the
    ceiling itself, which is why raising ``IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS``
    in ``.env`` would not have helped. Production 2026-07-27 05:18: the step was
    killed at exactly 90 s, no image, and the replanner's ``retry_same`` is not
    wired, so the failure was final.
    """

    @pytest.mark.parametrize("tool_name", ["generate_image", "edit_image"])
    def test_default_floor_covers_the_measured_high_quality_latency(self, tool_name: str):
        """The floor must sit above 138.3 s, or `high` fails by construction."""
        assert compute_step_timeout(tool_name, None) > 138.3

    @pytest.mark.parametrize("tool_name", ["generate_image", "edit_image"])
    def test_planner_request_below_floor_is_raised(self, tool_name: str):
        """A planner asking for 30 s must not undercut the family floor."""
        floor = compute_step_timeout(tool_name, None)
        assert compute_step_timeout(tool_name, 30.0) == floor

    @pytest.mark.parametrize("tool_name", ["generate_image", "edit_image"])
    def test_ceiling_is_dedicated_not_the_generic_one(self, tool_name: str):
        """Image tools no longer cap at the generic 120 s — below the measurement."""
        ceiling = compute_step_timeout(tool_name, 9999.0)
        assert ceiling > MAX_TOOL_TIMEOUT_SECONDS
        assert ceiling == get_settings().max_image_generation_tool_timeout_seconds

    @pytest.mark.parametrize("tool_name", ["generate_image", "edit_image"])
    def test_floor_stays_under_the_ceiling(self, tool_name: str):
        """A floor above its own ceiling would silently clamp back down."""
        assert compute_step_timeout(tool_name, None) <= compute_step_timeout(tool_name, 9999.0)


@pytest.mark.unit
class TestComputeStepTimeoutDevops:
    """`claude_server_task_tool` uses a 120s floor + generic ceiling."""

    def test_defaults_to_devops_floor(self):
        assert compute_step_timeout("claude_server_task_tool", None) == 120.0

    def test_floor_is_enforced(self):
        """Planner asked 10s → bumped to 120s devops floor."""
        assert compute_step_timeout("claude_server_task_tool", 10.0) == 120.0


@pytest.mark.unit
class TestComputeStepTimeoutMcpReactTask:
    """MCP iterative task tools (`{server}_task`) use their own Settings pair (audit D1)."""

    def test_defaults_to_mcp_react_floor(self):
        floor = float(get_settings().mcp_react_step_timeout_seconds)
        assert compute_step_timeout("excalidraw_task", None) == floor

    def test_planner_request_below_floor_is_raised(self):
        """Planner asked 60s but the MCP react floor (300s default) wins."""
        floor = float(get_settings().mcp_react_step_timeout_seconds)
        assert compute_step_timeout("excalidraw_task", 60.0) == floor

    def test_planner_request_above_ceiling_is_capped_to_mcp_react_max(self):
        """MCP react ceiling (600s default) is higher than the generic 120s."""
        ceiling = float(get_settings().mcp_react_step_max_timeout_seconds)
        assert compute_step_timeout("excalidraw_task", 9999.0) == ceiling

    def test_generic_max_does_not_clamp_mcp_react_task(self):
        """The 120s generic ceiling must NOT apply — this is the exact D1 bug.

        Pick a planner request strictly between the MCP-react floor and ceiling
        (read from settings, never hard-coded) so it is neither raised to the
        floor nor capped to the ceiling: it must pass through unchanged and, in
        particular, exceed the generic ``MAX_TOOL_TIMEOUT_SECONDS`` (120 s).
        """
        cfg = get_settings()
        floor = float(cfg.mcp_react_step_timeout_seconds)
        ceiling = float(cfg.mcp_react_step_max_timeout_seconds)
        request = (floor + ceiling) / 2  # strictly inside (floor, ceiling)
        result = compute_step_timeout("notion_task", request)
        assert result == request
        assert result > MAX_TOOL_TIMEOUT_SECONDS

    def test_browser_task_tool_is_not_treated_as_mcp_react(self):
        """`browser_task_tool` ends in `_tool`, not the bare `_task` suffix → browser family."""
        assert compute_step_timeout("browser_task_tool", None) == BROWSER_TOOL_TIMEOUT_SECONDS

    def test_subagent_tool_is_not_treated_as_mcp_react(self):
        """`delegate_to_sub_agent_tool` ends in `_tool` → sub-agent family, not MCP react."""
        sub_floor = float(get_settings().subagent_tool_timeout_seconds)
        assert compute_step_timeout("delegate_to_sub_agent_tool", None) == sub_floor


@pytest.mark.unit
class TestComputeStepTimeoutWebResearch:
    """Web-research tools (Perplexity-backed) get their own Settings pair.

    Production 2026-08-14→20: ``unified_web_search_tool`` steps were killed at
    exactly 30 s (the generic floor the planner requested) while the Perplexity
    synthesis legitimately takes longer — 6 ``step_execution_timeout`` in 7
    days, each one a final failure for the user's research.
    """

    @pytest.mark.parametrize(
        "tool_name",
        ["unified_web_search_tool", "perplexity_search_tool", "perplexity_ask_tool"],
    )
    def test_defaults_to_web_research_floor(self, tool_name: str):
        floor = float(get_settings().web_research_tool_timeout_seconds)
        assert compute_step_timeout(tool_name, None) == floor
        assert floor > DEFAULT_TOOL_TIMEOUT_SECONDS

    def test_planner_request_below_floor_is_raised(self):
        """The measured failure: planner asked 30 s → family floor wins."""
        floor = float(get_settings().web_research_tool_timeout_seconds)
        assert compute_step_timeout("unified_web_search_tool", 30.0) == floor

    def test_planner_request_above_ceiling_is_capped(self):
        ceiling = float(get_settings().max_web_research_tool_timeout_seconds)
        assert compute_step_timeout("unified_web_search_tool", 9999.0) == ceiling

    def test_floor_stays_under_the_ceiling(self):
        assert compute_step_timeout("unified_web_search_tool", None) <= compute_step_timeout(
            "unified_web_search_tool", 9999.0
        )

    def test_brave_stays_generic(self):
        """Direct Brave calls are fast (5 s HTTP timeout) — not in this family."""
        assert compute_step_timeout("brave_search_tool", None) == DEFAULT_TOOL_TIMEOUT_SECONDS


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
        assert compute_step_timeout(tool_name, None) == DEFAULT_TOOL_TIMEOUT_SECONDS

    def test_planner_can_request_below_default(self):
        """Regular tools: planner can ask for less than the default (no floor enforcement)."""
        # A regular tool with a 10s planner-requested timeout stays at 10s.
        assert compute_step_timeout("brave_search_tool", 10.0) == 10.0

    def test_planner_request_capped_at_generic_max(self):
        """Regular tools cap at 120s — sub-agent ceiling (300s) does NOT apply."""
        assert compute_step_timeout("brave_search_tool", 9999.0) == MAX_TOOL_TIMEOUT_SECONDS

    def test_unknown_tool_name_uses_generic_policy(self):
        """An unknown tool name falls back to generic floor / ceiling."""
        assert compute_step_timeout("some_future_tool", None) == DEFAULT_TOOL_TIMEOUT_SECONDS

    def test_none_tool_name_uses_generic_policy(self):
        """`step.tool_name = None` (CONDITIONAL step) falls back to generic policy."""
        assert compute_step_timeout(None, None) == DEFAULT_TOOL_TIMEOUT_SECONDS


@pytest.mark.unit
class TestComputeStepTimeoutIsolation:
    """Per-family policies do not bleed across each other."""

    def test_subagent_ceiling_does_not_apply_to_regular_tools(self):
        """A 250s planner request on a regular tool clamps to 120s, NOT 300s (sub-agent ceiling)."""
        result = compute_step_timeout("brave_search_tool", 250.0)
        assert result == MAX_TOOL_TIMEOUT_SECONDS

    def test_browser_ceiling_does_not_apply_to_regular_tools(self):
        """A 500s planner request on a regular tool clamps to 120s, NOT 600s (browser ceiling)."""
        result = compute_step_timeout("brave_search_tool", 500.0)
        assert result == MAX_TOOL_TIMEOUT_SECONDS

    def test_subagent_floor_does_not_apply_to_regular_tools(self):
        """A 5s planner request on a regular tool stays at 5s, NOT bumped to 180s."""
        result = compute_step_timeout("brave_search_tool", 5.0)
        assert result == 5.0
