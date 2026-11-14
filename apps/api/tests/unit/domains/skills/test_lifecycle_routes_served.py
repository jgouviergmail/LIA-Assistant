"""The two acts of a skill's life are served, switched with the skills, and never shadowed (lot 14)."""

from __future__ import annotations

import pytest
from starlette.routing import Match

from src.api.v1.routes import api_router
from tests._routes import capabilities_closing, served_routes

pytestmark = pytest.mark.unit

ACTS = {
    "/skills/dormant-decision": "settle_dormant_skills",
    "/skills/notes/restore-previous": "restore_previous_skill",
}


@pytest.mark.parametrize(("path", "endpoint"), sorted(ACTS.items()))
def test_each_act_is_served_by_its_own_route_under_the_skills_switch(
    path: str, endpoint: str
) -> None:
    scope = {"type": "http", "method": "POST", "path": path}
    # The FIRST full match is the one a request is served by.
    served = next(
        route
        for route in served_routes(api_router)
        if route.original_route.matches(scope)[0] is Match.FULL
    )

    assert served.endpoint.__name__ == endpoint
    assert "skills" in capabilities_closing(served)
