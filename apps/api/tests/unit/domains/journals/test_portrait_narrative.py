"""Natural portrait prose carries exact proofs privately, never as displayed text."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.domains.journals import consolidation_output as output

pytestmark = pytest.mark.unit


def _entry(content, *, level="L1", confidence="medium", theme="learnings"):
    return SimpleNamespace(
        id=uuid4(),
        content=content,
        level=level,
        confidence=confidence,
        theme=theme,
        revision=1,
        evidence_count=0,
        contradiction_count=0,
    )


def _claim(text, supports, *, facet="interaction", in_brief=True):
    return {"facet": facet, "text": text, "supports": supports, "in_brief": in_brief}


def _parse(claim):
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    assert result.valid, result.error
    return result.portrait_claims


def test_natural_privacy_constraint_keeps_its_exact_sensitive_proof_hidden(monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 1000)
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 1000)
    proof = "- Adresse personnelle : alex@example.invalid ; uniquement à sa demande explicite pour la tâche courante."
    prose = "Alex tient à garder la maîtrise de ses informations personnelles : son adresse ne doit être mobilisée qu'à sa demande explicite pour une tâche précise."
    claims = _parse(_claim(prose, [{"source": "memories", "quote": proof}]))
    published = []
    full, brief = output.grounded_portraits(claims, [], {"memories": proof}, published=published)
    assert full == brief == prose
    assert "alex@example.invalid" not in full and "[memories]" not in full
    assert published[0].supports[0].quote == proof
    evidence = output.render_exact_evidence(claims, [], {"memories": proof})
    assert evidence[0]["index"] == 0 and evidence[0]["text"] == prose
    assert evidence[0]["supports"][0]["quote"] == proof


def test_two_conditional_rules_support_coherent_prose_without_technical_labels():
    first = _entry(
        "WHEN urgent -> DO give one step BECAUSE immediate action was requested.",
        theme="self_reflection",
    )
    second = _entry(
        "WHEN choosing for the long term -> DO compare options and maintenance BECAUSE commitments endure."
    )
    prose = "Son besoin d'aide dépend du contexte : en urgence, privilégier une prochaine action ; pour un choix durable, comparer les options et leur entretien."
    claims = _parse(
        _claim(
            prose,
            [
                {"source": f"journal:{first.id}", "quote": first.content},
                {"source": f"journal:{second.id}", "quote": second.content},
            ],
        )
    )
    full, _ = output.grounded_portraits(claims, [first, second], {})
    assert full == prose and "WHEN" not in full
    proof = output.render_exact_evidence(claims, [first, second], {})
    assert proof[0]["supports"][0]["theme"] == "self_reflection"
    assert proof[0]["supports"][1]["revision"] == 1


@pytest.mark.parametrize(
    "text",
    [
        "WHEN urgent -> DO give one action BECAUSE it was requested.",
        "[learnings] Une préférence générale.",
        "Une préférence observée le 2026-10-07.",
        "Une préférence liée à 8d6f48d7-477b-4079-a774-deb89b68d604.",
        "- Une préférence présentée en liste.",
        "Sa préférence se résume à conf=high ev=2 co=0.",
    ],
)
def test_technical_or_raw_list_portraits_are_rejected(text):
    claim = _claim(text, [{"source": "memories", "quote": "- Source complète."}])
    assert not output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    ).valid


def test_legitimate_email_discourse_is_not_blocked_by_a_keyword_filter():
    prose = "Pour ses échanges par email, privilégier une formulation claire qui respecte le contrôle qu'il garde sur ses coordonnées."
    assert _parse(
        _claim(prose, [{"source": "memories", "quote": "- Il veut contrôler ses coordonnées."}])
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"facet": "family"},
        {"supports": []},
        {"source": "memories", "quote": "- Old extractive shape."},
        {"approved": True},
    ],
)
def test_unknown_facets_unproved_or_old_shapes_and_self_approval_are_rejected(bad):
    claim = {
        **_claim(
            "Un repère formulé naturellement.", [{"source": "memories", "quote": "- Source."}]
        ),
        **bad,
    }
    assert not output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    ).valid


@pytest.mark.parametrize(
    "failure", ["unknown_id", "wrong_quote", "partial_quote", "duplicate_support"]
)
def test_supports_are_exact_current_complete_and_unambiguous(failure):
    entry = _entry(
        "WHEN discussing a film date -> DO verify the local date BECAUSE one availability claim was wrong."
    )
    support = {"source": f"journal:{entry.id}", "quote": entry.content}
    if failure == "unknown_id":
        support["source"] = f"journal:{uuid4()}"
    elif failure == "wrong_quote":
        support["quote"] = "An unrelated statement."
    elif failure == "partial_quote":
        support["quote"] = entry.content.split(" BECAUSE")[0]
    supports = [support, support] if failure == "duplicate_support" else [support]
    claims = _parse(
        _claim("Pour une information sur un film, vérifier sa disponibilité locale.", supports)
    )
    with pytest.raises(ValueError):
        output.validate_portrait_claims(claims, [entry], {})


def test_provisional_synthesis_is_explicit_in_evidence_and_uses_uncertainty_facet():
    entry = _entry(
        "The user may prefer measured decisions for durable commitments.",
        level="L2",
        theme="user_observations",
    )
    support = {"source": f"journal:{entry.id}", "quote": entry.content}
    claims = _parse(
        _claim(
            "Les échanges disponibles suggèrent une préférence pour des choix réfléchis lorsqu'un engagement doit durer.",
            [support],
            facet="uncertainty",
        )
    )
    evidence = output.render_exact_evidence(claims, [entry], {})
    assert evidence[0]["provisional"] is True
    unsupported = _parse(
        _claim("Il préfère toujours les choix réfléchis.", [support], facet="posture")
    )
    with pytest.raises(ValueError):
        output.validate_portrait_claims(unsupported, [entry], {})
