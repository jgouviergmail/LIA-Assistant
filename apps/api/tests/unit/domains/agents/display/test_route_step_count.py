"""Route disclosure counts describe the steps a person can actually read."""

import pytest
from bs4 import BeautifulSoup

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.route_card import RouteCard

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "steps, expected_instructions",
    [
        (["Walk ahead", {"instruction": "Turn left"}], ["Walk ahead", "Turn left"]),
        (
            [None, {"instruction": "Turn left"}, False, 42, [], "Continue ahead"],
            ["Turn left", "Continue ahead"],
        ),
        ([None, False, 42, []], []),
        ([], []),
    ],
)
def test_route_step_count_matches_readable_steps(
    steps: list[object], expected_instructions: list[str]
) -> None:
    """Malformed siblings neither inflate the label nor renumber valid steps."""
    markup = BeautifulSoup(
        RouteCard().render(
            {"origin": "Start", "destination": "End", "steps": steps},
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert [
        item.get_text(strip=True) for item in markup.select(".lia-route__step-instruction")
    ] == expected_instructions
    assert [item.get_text(strip=True) for item in markup.select(".lia-route__step-number")] == [
        str(index) for index in range(1, len(expected_instructions) + 1)
    ]
    disclosure = markup.select_one(".lia-collapsible__trigger")
    if expected_instructions:
        assert disclosure is not None
        label = disclosure.select_one(":scope > span:not(.lia-collapsible__icon)")
        assert label is not None
        assert label.get_text(strip=True) == f"Steps ({len(expected_instructions)})"
    else:
        assert disclosure is None
