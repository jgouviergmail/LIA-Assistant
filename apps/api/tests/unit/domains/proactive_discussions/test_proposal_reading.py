"""One malformed proposal is set aside alone; the context call's answer survives it."""

import pytest
from pydantic import ValidationError

from src.core.constants import DISCUSSION_CONTEXT_PROPOSALS_MAX
from src.domains.proactive_discussions.contextualization.proposal_reading import read_proposals
from src.domains.proactive_discussions.llm_contracts import ContextInterpretation

pytestmark = pytest.mark.unit

EPISODE = {
    "kind": "episode",
    "summary": "A fictional move across town",
    "qualification": "possible",
    "anchor": "calendar:a",
    "references": ["calendar:a", "emails:b"],
}
RESOLUTION = {"status": "insufficient", "reason": "not enough"}


def proposal(**changes: object) -> dict[str, object]:
    return {**EPISODE, **changes}


def test_a_reference_listed_twice_or_empty_is_repaired_never_refused():
    kept, refused = read_proposals(
        [proposal(references=["emails:b", " emails:b ", "", "calendar:a"])]
    )
    assert not refused
    assert kept[0].references == ("emails:b", "calendar:a")


def test_an_episode_whose_anchor_is_missing_from_its_references_rests_on_it():
    kept, refused = read_proposals([proposal(references=["emails:b"])])
    assert not refused
    assert kept[0].references == ("calendar:a", "emails:b")


def test_an_observation_resting_on_several_facts_is_the_episode_the_store_defines():
    # Measured 2026-10-21 on one configured model: the only proposal of a rebuild was
    # an observation citing two facts, and refusing it left the rebuild with nothing.
    kept, refused = read_proposals(
        [
            proposal(kind="observation", references=["calendar:a", "calendar:a"]),
            proposal(kind="observation", references=["calendar:a", "emails:b"]),
            proposal(kind="observation", references=["emails:b"]),
        ]
    )
    assert not refused
    assert [item.kind for item in kept] == ["observation", "episode", "episode"]
    assert kept[0].references == ("calendar:a",)
    assert kept[2].references == ("calendar:a", "emails:b")


def test_any_other_shape_the_contract_refuses_is_unreadable_and_counted():
    kept, refused = read_proposals(
        [proposal(summary=""), proposal(qualification="certain"), "not an object", proposal()]
    )
    assert len(kept) == 1
    assert refused == {"unreadable": 3}


def test_proposals_beyond_the_published_cap_are_set_aside_in_order():
    raw = [
        proposal(anchor=f"calendar:{index}")
        for index in range(DISCUSSION_CONTEXT_PROPOSALS_MAX + 2)
    ]
    kept, refused = read_proposals(raw)
    assert [item.anchor for item in kept] == [
        f"calendar:{index}" for index in range(DISCUSSION_CONTEXT_PROPOSALS_MAX)
    ]
    assert refused == {"beyond_cap": 2}


def test_the_answer_survives_its_malformed_proposals_and_says_how_many():
    # Measured 2026-10-21: one configured model returned one to four such proposals
    # among valid ones, and each refused the whole interpretation, then the run.
    output = ContextInterpretation.model_validate(
        {
            "classifications": [{"reference": "calendar:a", "sensitive_topics": []}],
            "proposals": [
                proposal(references=["emails:b", "emails:b"]),
                proposal(kind="observation"),
                proposal(summary=""),
                proposal(qualification="certain"),
            ],
            "resolution": RESOLUTION,
        }
    )
    assert [item.kind for item in output.proposals] == ["episode", "episode"]
    assert output.refused_proposals == {"unreadable": 2}
    assert output.resolution.status == "insufficient"


def test_the_answer_read_from_json_counts_the_same():
    data = ContextInterpretation.model_validate(
        {"proposals": [proposal(summary="")], "resolution": RESOLUTION}
    )
    again = ContextInterpretation.model_validate_json(
        '{"proposals": [{"kind": "observation", "summary": "", "qualification": "possible",'
        ' "anchor": "a", "references": ["a"]}], "resolution": '
        '{"status": "insufficient", "reason": "r"}}'
    )
    assert data.refused_proposals == again.refused_proposals == {"unreadable": 1}


def test_a_topic_label_or_the_resolution_stays_strict():
    # Dropping a malformed classification would read a sensitive fact as ordinary.
    with pytest.raises(ValidationError):
        ContextInterpretation.model_validate(
            {
                "classifications": [{"reference": "calendar:a", "sensitive_topics": ["gossip"]}],
                "resolution": RESOLUTION,
            }
        )
    with pytest.raises(ValidationError):
        ContextInterpretation.model_validate({"proposals": [], "resolution": {"status": "ready"}})


def test_the_refused_count_is_not_part_of_what_the_model_reads():
    schema = ContextInterpretation.model_json_schema()
    assert set(schema["properties"]) == {"classifications", "proposals", "resolution"}
    assert schema["properties"]["proposals"]["maxItems"] == DISCUSSION_CONTEXT_PROPOSALS_MAX
