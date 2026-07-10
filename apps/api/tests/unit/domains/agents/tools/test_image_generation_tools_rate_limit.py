"""Rate limiting contract for the image generation tools.

``generate_image`` / ``edit_image`` hit a paid external API (gpt-image-1 &
co.) with no client-layer rate limiter (``ImageGenerationClient`` is a
standalone ABC, unlike the connector clients built on ``BaseAPIKeyClient``).
The ``@rate_limit`` decorator is therefore the only technical anti-runaway
ceiling: these tests prove that exceeding the settings-driven threshold
short-circuits the tool with the standard ``rate_limit_exceeded`` payload
(the tool-layer materialization of ``ToolErrorCode.RATE_LIMIT_EXCEEDED``).

No DB / network: the fake settings disable the feature flag so the tool body
returns immediately — the rate limiter records the call *before* executing
the body, so blocked/allowed transitions are still fully exercised.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.tools import image_generation_tools
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.utils.rate_limiting import _rate_limit_tracker

# Patch path for get_settings (imported inside the rate_limit wrapper)
SETTINGS_PATCH_PATH = "src.core.config.get_settings"


@pytest.fixture(autouse=True)
def reset_tracker():
    """Isolate the in-memory sliding-window tracker between tests."""
    _rate_limit_tracker.clear()
    yield
    _rate_limit_tracker.clear()


@pytest.fixture
def mock_runtime() -> MagicMock:
    """ToolRuntime carrying the user_id the limiter keys on."""
    runtime = MagicMock()
    runtime.config = {"configurable": {"user_id": "rate-limit-test-user"}}
    return runtime


@pytest.fixture
def fake_settings() -> MagicMock:
    """Module-level settings double.

    ``image_generation_enabled=False`` short-circuits the tool body before
    any DB access. The rate-limit values are deliberately small so the test
    stays fast; the invocation loop below derives its count from this object
    (never a duplicated literal), proving the decorator lambdas read the
    settings at call time.
    """
    settings = MagicMock()
    settings.image_generation_enabled = False
    settings.image_generation_rate_limit_calls = 3
    settings.image_generation_rate_limit_window = 60
    return settings


@pytest.fixture
def wrapper_settings() -> MagicMock:
    """Settings returned by get_settings() inside the rate_limit wrapper."""
    settings = MagicMock()
    settings.rate_limit_enabled = True
    return settings


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_obj", [image_generation_tools.generate_image, image_generation_tools.edit_image]
)
async def test_exceeding_threshold_returns_rate_limit_exceeded(
    tool_obj, mock_runtime, fake_settings, wrapper_settings
) -> None:
    """Call N+1 within the window is blocked with the standard payload."""
    max_calls = fake_settings.image_generation_rate_limit_calls

    with (
        patch.object(image_generation_tools, "settings", fake_settings),
        patch(SETTINGS_PATCH_PATH, return_value=wrapper_settings),
        patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits") as mock_metric,
    ):
        # Under the threshold: the limiter lets every call through to the
        # tool body (which returns a structured failure — feature disabled).
        for _ in range(max_calls):
            result = await tool_obj.coroutine(prompt="test", runtime=mock_runtime)
            assert isinstance(result, UnifiedToolOutput)

        # Call N+1: blocked by the limiter before the body runs.
        blocked = await tool_obj.coroutine(prompt="test", runtime=mock_runtime)

        assert isinstance(blocked, str), "rate-limited call must not reach the body"
        payload = json.loads(blocked)
        assert payload["error"] == ToolErrorCode.RATE_LIMIT_EXCEEDED.value.lower()
        assert payload["retry_after_seconds"] > 0
        assert str(max_calls) in payload["limit"]

        # Prometheus hit counter incremented exactly once.
        mock_metric.labels.assert_called_once()
        mock_metric.labels().inc.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tools_have_independent_rate_limit_pools(
    mock_runtime, fake_settings, wrapper_settings
) -> None:
    """Exhausting generate_image's pool must not block edit_image.

    The limiter keys on (tool_name, user_id): both tools share the same
    settings values but each has its own sliding window.
    """
    max_calls = fake_settings.image_generation_rate_limit_calls

    with (
        patch.object(image_generation_tools, "settings", fake_settings),
        patch(SETTINGS_PATCH_PATH, return_value=wrapper_settings),
        patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"),
    ):
        for _ in range(max_calls):
            await image_generation_tools.generate_image.coroutine(
                prompt="test", runtime=mock_runtime
            )
        blocked = await image_generation_tools.generate_image.coroutine(
            prompt="test", runtime=mock_runtime
        )
        assert isinstance(blocked, str)

        # edit_image still goes through to the tool body.
        result = await image_generation_tools.edit_image.coroutine(
            prompt="test", runtime=mock_runtime
        )
        assert isinstance(result, UnifiedToolOutput)
