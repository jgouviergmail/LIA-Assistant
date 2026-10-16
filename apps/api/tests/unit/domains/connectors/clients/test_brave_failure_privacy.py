"""The optional-results search door keeps its fallback without logging query prose."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.connectors.clients import brave_search_client as module


async def test_optional_search_failure_has_safe_operational_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("PRIVATE_VENDOR_QUERY_TEXT")
    client = object.__new__(module.BraveSearchClient)
    monkeypatch.setattr(client, "search_or_raise", AsyncMock(side_effect=failure))
    log = MagicMock()
    monkeypatch.setattr(module, "logger", log)

    assert await client.search("PRIVATE_SEARCH_TEXT") is None

    log.warning.assert_called_once()
    assert log.warning.call_args.kwargs["error_type"] == "RuntimeError"
    assert "PRIVATE" not in repr(log.warning.call_args)
    assert any(call.kwargs.get("exc_info") is failure for call in log.debug.call_args_list)
