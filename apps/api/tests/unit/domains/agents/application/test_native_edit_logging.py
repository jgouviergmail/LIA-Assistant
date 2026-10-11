"""Native drafts can contain private locations; parse diagnostics carry facts only."""

from unittest.mock import MagicMock

import pytest

from src.domains.agents.services.hitl.draft_modifier import DraftModificationService

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "response", ['{"private_address":"Private road 123"}', '{"Private road 123']
)
def test_private_edit_parse_failures_do_not_log_the_original_text(
    monkeypatch, response: str
) -> None:
    log = MagicMock()
    monkeypatch.setattr("src.domains.agents.services.hitl.draft_modifier.logger", log)
    service = object.__new__(DraftModificationService)
    assert service._parse_modification_response(response, ["intent"], {}, sensitive=True) == {}
    assert "Private road 123" not in str(log.mock_calls)
    assert log.mock_calls
