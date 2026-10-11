"""Source UI query is bounded and cannot select another account or mutate consents."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.peer_read_schemas import PeerUIQuery

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": "other"},
        {"section": "all"},
        {"limit": 51},
        {"limit": True},
        {"offset": -1},
        {"section": "preferences", "email_visible": True},
    ],
)
def test_peer_query_refuses_unknown_authority_actions_and_unbounded_pages(payload):
    with pytest.raises(ValidationError):
        PeerUIQuery.model_validate(payload)
