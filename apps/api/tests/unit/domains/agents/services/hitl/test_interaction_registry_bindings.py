"""Every registered HITL interaction is the CLASS its module declares (ADR-289 guard).

A registration decorator binds whatever sits on the next line. A helper
inserted between the decorator and the class it decorated registered a plain
function as the draft-critique interaction — every unit test still passed,
since they build the class directly, and only the served container said so
(``hitl_interaction_registered class_name=_sequence_summary``, 2026-09-16).
The registry is what the streaming service resolves at run time, so it is
what this test reads.
"""

from __future__ import annotations

import inspect

import pytest

from src.domains.agents.services.hitl.interactions import draft_critique
from src.domains.agents.services.hitl.protocols import HitlInteractionType
from src.domains.agents.services.hitl.registry import HitlInteractionRegistry

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("interaction_type", list(HitlInteractionType))
def test_every_type_is_bound_to_a_class(interaction_type: HitlInteractionType) -> None:
    bound = HitlInteractionRegistry._interactions.get(interaction_type)
    if bound is None:
        pytest.skip(f"{interaction_type.value} has no registered interaction")
    assert inspect.isclass(bound), f"{interaction_type.value} is bound to {bound!r}, not a class"
    assert hasattr(bound, "generate_question_stream")


def test_the_draft_critique_is_its_interaction_class() -> None:
    assert (
        HitlInteractionRegistry._interactions[HitlInteractionType.DRAFT_CRITIQUE]
        is draft_critique.DraftCritiqueInteraction
    )
