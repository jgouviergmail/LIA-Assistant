"""Discovery cannot become substring enumeration or another-account inspection."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.peer_discovery_schemas import PeerDiscoveryQuery

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": 1},
        {"query": "x" * 256},
        {"query": "Alice", "limit": 51},
        {"query": "Alice", "offset": -1},
        {"query": "Alice", "user_id": "other"},
        {"query": "Alice", "prefix": True},
    ],
)
def test_directory_query_cannot_expand_source_scope(payload):
    with pytest.raises(ValidationError):
        PeerDiscoveryQuery.model_validate(payload)
