"""An optional import failure cannot publish exception text or traceback locals."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from structlog.testing import capture_logs

pytestmark = pytest.mark.unit


def test_optional_tool_import_diagnostics_keep_only_finite_public_facts():
    from src.domains.agents.tools import _log_conditional_import_failure

    with capture_logs() as events:
        _log_conditional_import_failure("devops", ImportError("private-bootstrap-secret"))
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "conditional_tool_import_failed"
    assert event["tool_family"] == "devops"
    assert event["error_type"] == "ImportError"
    assert not event.get("exc_info")
    assert "private-bootstrap-secret" not in json.dumps(event)


def test_registry_import_failure_keeps_diagnostics_private_and_still_fails_loudly(monkeypatch):
    import importlib

    from src.domains.agents.tools import tool_registry

    configuration = SimpleNamespace(
        is_production=False,
        **{flag: False for flag, _, _ in tool_registry._FLAG_GATED_TOOL_MODULES},
    )
    monkeypatch.setattr("src.core.config.get_settings", lambda: configuration)
    monkeypatch.setattr(
        importlib, "import_module", Mock(side_effect=ImportError("private-bootstrap-secret"))
    )
    with capture_logs() as events:
        with pytest.raises(RuntimeError) as failure:
            tool_registry._import_tool_modules()
    assert "private-bootstrap-secret" not in str(failure.value)
    assert failure.value.__cause__ is None
    assert len(events) == 1 and events[0]["event"] == "tool_module_import_failed"
    assert events[0]["error_type"] == "ImportError"
    assert not events[0].get("exc_info")
    assert "private-bootstrap-secret" not in json.dumps(events)
