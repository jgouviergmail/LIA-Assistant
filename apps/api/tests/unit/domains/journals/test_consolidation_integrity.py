"""Operational acceptance: malformed output and semantic drift fail closed."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.domains.journals.consolidation_output import (
    PortraitClaim,
    PortraitSupport,
    grounded_portraits,
    parse_maintenance_output,
    render_exact_evidence,
)
from src.domains.journals.maintenance_actions import validate_maintenance
from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "{}",
        '{"actions": "none"}',
        '{"actions":[{"action":"create"}]}',
        '{"actions":[{"action":"update"}]}',
    ],
)
def test_invalid_output_is_distinct_from_valid_no_op(raw):
    assert not parse_maintenance_output(raw).valid
    assert parse_maintenance_output('{"actions":[]}').valid


def test_same_uuid_different_spellings_cannot_be_updated_and_deleted():
    identifier = uuid4()
    output = parse_maintenance_output(
        json.dumps(
            {
                "actions": [
                    {"action": "update", "entry_id": identifier.hex.upper(), "content": "first"},
                    {"action": "delete", "entry_id": str(identifier)},
                ]
            }
        )
    )
    assert not output.valid


def test_opaque_portrait_prose_cannot_publish_the_measured_drift():
    output = parse_maintenance_output(
        json.dumps(
            {
                "actions": [],
                "portrait_full": "Recurring interest in cinema; the user is a decision maker.",
            }
        )
    )
    assert not output.valid


def _entry(content):
    return SimpleNamespace(
        id=uuid4(),
        content=content,
        level="L1",
        confidence="medium",
        contradiction_count=0,
        theme="learnings",
        revision=1,
        evidence_count=0,
    )


def test_conditional_method_keeps_its_trigger_and_does_not_become_identity():
    text = "WHEN checking a film release date -> DO verify the local release BECAUSE dates differ by country."
    entry = _entry(text)
    prose = "Pour une date de sortie au cinéma, vérifier la sortie locale avant de conclure : les calendriers varient selon le pays."
    claim = PortraitClaim(
        facet="interaction",
        text=prose,
        supports=[PortraitSupport(source=f"journal:{entry.id}", quote=text)],
        in_brief=True,
    )
    full, _ = grounded_portraits([claim], [entry], {})
    assert full == prose and "WHEN" not in full
    with pytest.raises(ValueError):
        grounded_portraits(
            [
                claim.model_copy(
                    update={
                        "supports": [
                            claim.supports[0].model_copy(
                                update={"quote": "The user has a recurring cinema interest."}
                            )
                        ]
                    }
                )
            ],
            [entry],
            {},
        )
    with pytest.raises(ValueError):
        grounded_portraits(
            [
                claim.model_copy(
                    update={
                        "supports": [
                            claim.supports[0].model_copy(
                                update={
                                    "quote": "DO verify the local release BECAUSE dates differ by country."
                                }
                            )
                        ]
                    }
                )
            ],
            [entry],
            {},
        )


def test_only_whole_authorized_source_items_can_support_the_portrait():
    line = "- Usual activity: weekdays 08:00-10:00; sparse observations"
    claim = PortraitClaim(
        facet="uncertainty",
        text="Les observations restent peu nombreuses, mais son activité semble se concentrer les matins de semaine entre huit et dix heures.",
        supports=[PortraitSupport(source="habits", quote=line)],
    )
    full, _ = grounded_portraits([claim], [], {"habits": line})
    assert "peu nombreuses" in full
    for quote in (line[:-10], line + "…"):
        with pytest.raises(ValueError):
            grounded_portraits(
                [
                    claim.model_copy(
                        update={"supports": [claim.supports[0].model_copy(update={"quote": quote})]}
                    )
                ],
                [],
                {"habits": line + "…"},
            )


def test_portrait_packs_complete_passages_under_both_budgets(monkeypatch):
    from src.core.config import settings

    entry = _entry(
        "WHEN urgent -> DO give one next step BECAUSE the user explicitly requested action."
    )
    prose = "Dans une situation urgente, concentrer l'aide sur une prochaine action concrète lorsqu'il l'a demandée."
    claim = PortraitClaim(
        facet="interaction",
        text=prose,
        supports=[PortraitSupport(source=f"journal:{entry.id}", quote=entry.content)],
        in_brief=True,
    )
    count = OpenAITokenCounter().count(prose, "gpt-4o")
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", count)
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 10)
    published = []
    full, brief = grounded_portraits([claim], [entry], {}, published=published)
    assert full is not None and brief is None
    assert published[0].in_brief is False
    assert OpenAITokenCounter().count(full, "gpt-4o") <= count
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 10)
    assert grounded_portraits([claim], [entry], {}) == (None, None)


@pytest.mark.parametrize("level", ["L2", "L3"])
def test_a_provisional_synthesis_retains_its_uncertainty_in_the_portrait(level):
    entry = _entry("The user may prefer deliberate choices for durable commitments.")
    entry.level = level
    entry.theme = "user_observations"
    prose = "Les échanges disponibles suggèrent qu'il pourrait privilégier des choix réfléchis pour les engagements durables."
    claim = PortraitClaim(
        facet="uncertainty",
        text=prose,
        supports=[PortraitSupport(source=f"journal:{entry.id}", quote=entry.content)],
    )
    full, _ = grounded_portraits([claim], [entry], {})
    assert full == prose
    assert render_exact_evidence([claim], [entry], {})[0]["provisional"] is True


def test_existing_l3_cannot_be_reclassified_as_a_method_lesson():
    entry = _entry("The user's durable preference.")
    entry.level = "L3"
    entry.theme = "user_observations"
    output = parse_maintenance_output(
        json.dumps(
            {
                "actions": [
                    {
                        "action": "update",
                        "entry_id": str(entry.id),
                        "theme": "learnings",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="identity facets"):
        validate_maintenance(output, [entry], 800)


def test_incompatible_merge_is_refused_before_provider_preparation():
    first = _entry("WHEN urgent -> DO give one option.")
    second = _entry("WHEN deciding for the long term -> DO compare options.")
    output = parse_maintenance_output(
        json.dumps(
            {
                "actions": [
                    {
                        "action": "merge",
                        "entry_id": str(first.id),
                        "merge_source_ids": [str(second.id)],
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="equivalent complete propositions"):
        validate_maintenance(output, [first, second], 800)


def _abstraction(supports):
    return {
        "action": "create",
        "theme": "user_observations",
        "title": "Durable synthesis",
        "content": "A supported broader preference.",
        "level": "L2",
        "support_ids": [str(entry.id) for entry in supports],
    }


def test_a_merged_away_rule_cannot_support_a_new_abstraction():
    first = _entry("WHEN preparing -> DO compare alternatives.")
    duplicate = _entry(first.content)
    second = _entry("WHEN finalizing -> DO verify the result.")
    first.confidence = duplicate.confidence = second.confidence = "high"
    output = parse_maintenance_output(
        json.dumps(
            {
                "actions": [
                    {
                        "action": "merge",
                        "entry_id": str(first.id),
                        "merge_source_ids": [str(duplicate.id)],
                    },
                    _abstraction([duplicate, second]),
                ]
            }
        )
    )
    assert output.valid
    with pytest.raises(ValueError, match="survive this batch unchanged"):
        validate_maintenance(output, [first, duplicate, second], 800)


def test_duplicate_propositions_do_not_count_as_independent_synthesis_supports():
    first = _entry("WHEN preparing -> DO compare alternatives.")
    duplicate = _entry(first.content)
    first.confidence = duplicate.confidence = "high"
    output = parse_maintenance_output(json.dumps({"actions": [_abstraction([first, duplicate])]}))
    assert output.valid
    with pytest.raises(ValueError, match="distinct complete propositions"):
        validate_maintenance(output, [first, duplicate], 800)
