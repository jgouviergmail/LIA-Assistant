"""What the initiative evaluator's prompt promises, held to what the code and tools do.

The prompt (ADR-062, restored to its enrichment role on 2026-11-08) asks the evaluator to
complete an answer with read-only checks in other domains: a route's weather, an
appointment's journey and the time to leave. Each promise here is one the code keeps.
"""

import re

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.routes.catalogue_manifests import get_route_catalogue_manifest

pytestmark = pytest.mark.unit

PROMPT = load_prompt("initiative_prompt", version="v1")
STATIC = PROMPT.split(DYNAMIC_CONTEXT_MARKER, 1)[0]


def test_follow_up_chips_are_considered_whether_or_not_it_acts() -> None:
    # The same call proposes the chips; a turn without an action still deserves them.
    assert "INDEPENDENT of should_act" in STATIC


def test_the_journey_check_asks_for_an_arrival_time_the_route_tool_takes() -> None:
    # « leave at 8:20 to be on time »: the route tool computes the departure from it.
    assert "as the arrival time" in STATIC
    assert "arrival_time" in {
        parameter.name for parameter in get_route_catalogue_manifest.parameters
    }


def test_it_names_no_parameter_the_tools_do_not_take() -> None:
    # The 2026-09-15 text required a ``target_timestamp`` no tool declares.
    assert "target_timestamp" not in PROMPT


def test_its_examples_are_english_only() -> None:
    # Prompts stay generic; illustrations are English (owner rule 2026-09-15).
    assert re.findall(r"[àâäéèêëîïôöùûüçœÀÂÄÉÈÊËÎÏÔÖÙÛÜÇŒ]", PROMPT) == []


def test_memory_and_interests_personalize_without_gating() -> None:
    # A route's weather needs no stored interest: context sets priorities, never a filter.
    assert "never required for one" in STATIC


def test_assistant_voice_addresses_the_person_informally() -> None:
    # Measured 2026-11-08: without the rule, the motivation shown verbatim switched between
    # the familiar and the formal form of address from one turn to the next.
    assert "address them informally" in STATIC
