"""A tool logs through the logging configuration in force when it LOGS.

Tool classes are instantiated at module import (module-level singletons such
as ``_search_events_tool_instance``), which ``main.py`` used to reach before
``configure_logging()`` ran. A logger BOUND at construction froze structlog's
defaults for the life of the process: DEBUG lines emitted at
``LOG_LEVEL=INFO``, rendered for a console Promtail cannot parse, and never
passed through the PII filter — measured 2026-09-23, tool parameters in the
production logs. These tests build nothing: they use the real instances the
import created, then swap the configuration, as ``configure_logging()`` does.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

import pytest
import structlog.testing

from src.domains.agents.tools import base
from src.domains.agents.tools.calendar_tools import _search_events_tool_instance
from src.domains.agents.tools.weather_tools import _get_current_weather_tool_impl
from tests.support.structlog_capture import fresh_module_logger


class _LoggingTool(Protocol):
    """What the assertions read from either tool base class."""

    tool_name: str
    operation: str

    @property
    def logger(self) -> structlog.stdlib.BoundLogger: ...


@pytest.fixture(autouse=True)
def _fresh_logger() -> Iterator[None]:
    yield from fresh_module_logger(base)


@pytest.mark.unit
@pytest.mark.parametrize(
    "tool",
    [_search_events_tool_instance, _get_current_weather_tool_impl],
    ids=["connector_tool", "api_key_connector_tool"],
)
def test_a_tool_built_at_import_logs_through_the_later_configuration(
    tool: _LoggingTool,
) -> None:
    with structlog.testing.capture_logs() as captured:
        tool.logger.info("probe_event")

    assert captured == [
        {
            "event": "probe_event",
            "log_level": "info",
            "tool": tool.tool_name,
            "operation": tool.operation,
        }
    ]
