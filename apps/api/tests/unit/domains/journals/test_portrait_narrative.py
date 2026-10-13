"""Natural portrait prose carries exact proofs privately, never as displayed text."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.domains.journals import consolidation_output as output
from tests.unit.domains.journals.evidence_view import evidence_view

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


def _claim(text, supports, *, facet="interaction", placement="full"):
    return {"facet": facet, "text": text, "supports": supports, "placement": placement}


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
    assert full == prose and brief is None
    assert "alex@example.invalid" not in full and "[memories]" not in full
    assert published[0].supports[0].quote == proof
    evidence = evidence_view(claims, [], {"memories": proof})
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
    proof = evidence_view(claims, [first, second], {})
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
        "Il travaille 8 heures par jour.",
        "Joignable sur prenom@example.test.",
        "Il lit https://example.test chaque matin.",
    ],
)
def test_technical_or_raw_list_portraits_are_rejected(text):
    claim = _claim(text, [{"source": "memories", "quote": "- Source complète."}])
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    # A figure, an address or technical metadata in the prose drops THAT claim.
    assert result.valid and result.portrait_claims == []
    assert result.rejected_claims[0]["codes"] == ["value_error"]


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
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    assert result.valid and result.portrait_claims == []
    assert [item["claim_index"] for item in result.rejected_claims] == [0]


@pytest.mark.parametrize("failure", ["unknown_id", "wrong_quote", "partial_quote"])
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
    claims = _parse(
        _claim("Pour une information sur un film, vérifier sa disponibilité locale.", [support])
    )
    dropped: list[dict] = []
    assert output.validate_portrait_claims(claims, [entry], {}, dropped=dropped) == []
    assert dropped[0]["claim_index"] == 0 and dropped[0]["reason"]


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
    evidence = evidence_view(claims, [entry], {})
    assert evidence[0]["provisional"] is True
    # A provisional synthesis filed under another facet is REPAIRED to `uncertainty`
    # (the facet is metadata, ADR-184); the prompt asks for cautious words there.
    repaired = output.validate_portrait_claims(
        _parse(_claim("Il préfère toujours les choix réfléchis.", [support], facet="posture")),
        [entry],
        {},
    )
    assert repaired[0].provisional is True
    assert repaired[0].claim.facet == "uncertainty"


def test_a_support_cited_twice_is_one_support():
    entry = _entry(
        "WHEN discussing a film date -> DO verify the local date BECAUSE one claim was wrong."
    )
    support = {"source": f"journal:{entry.id}", "quote": entry.content}
    claims = _parse(
        _claim(
            "Pour une information sur un film, vérifier sa disponibilité locale.",
            [support, support],
        )
    )
    validated = output.validate_portrait_claims(claims, [entry], {})
    assert len(validated) == 1 and len(validated[0].evidence) == 1


def test_a_paragraph_restating_one_cited_item_is_dropped():
    line = "- [personal] Il garde une heure sans interruption le matin pour les dossiers difficiles. (2026-10-01)"
    claims = _parse(
        _claim(
            "Il garde chaque matin une heure sans interruption pour ses dossiers difficiles.",
            [{"source": "memories", "quote": line}],
        )
    )
    dropped: list[dict] = []
    assert output.validate_portrait_claims(claims, [], {"memories": line}, dropped=dropped) == []
    assert dropped[0]["reason"] == "portrait paragraph restates one cited item"


def test_a_reading_across_items_is_not_a_restatement():
    first = "- [personal] Il garde une heure sans interruption le matin pour les dossiers difficiles. (2026-10-01)"
    second = "- [personal] Il refuse les réunions avant dix heures. (2026-10-02)"
    claims = _parse(
        _claim(
            "Son début de journée est défendu contre toute sollicitation, et une proposition qui tombe dans ces heures sera refusée.",
            [{"source": "memories", "quote": first}, {"source": "memories", "quote": second}],
        )
    )
    assert (
        len(output.validate_portrait_claims(claims, [], {"memories": first + "\n" + second})) == 1
    )


def test_the_person_of_a_debrief_is_a_name_but_a_capitalised_common_word_is_not():
    # A relationship debrief opens on the person's name — the one position where a
    # name is certain — while « Les » after « Open: » is a capitalised common word.
    line = (
        "- Marine (written 2026-10-01): a colleague on the on-call rota — stands at the same"
        " point. Open: Les astreintes de novembre"
    )
    with_name = _parse(
        _claim(
            "Il compte sur Marine pour tenir la rotation quand il s'absente.",
            [{"source": "relation_debriefs", "quote": line}],
        )
    )
    dropped: list[dict] = []
    assert (
        output.validate_portrait_claims(with_name, [], {"relation_debriefs": line}, dropped=dropped)
        == []
    )
    assert dropped[0]["reason"] == "portrait paragraph carries a name taken from the evidence"
    without = _parse(
        _claim(
            "Les astreintes de novembre sont le terrain où sa volonté de déléguer se mesure"
            " à ce qu'il garde en main.",
            [{"source": "relation_debriefs", "quote": line}],
        )
    )
    assert len(output.validate_portrait_claims(without, [], {"relation_debriefs": line})) == 1


def test_an_open_loop_counterparty_is_a_name_and_a_lowercase_one_is_not():
    named = "- Réponse au devis (the person is waiting on someone, Marine; due around 2026-10-20)"
    claims = _parse(
        _claim(
            "Il attend une réponse de Marine avant de s'engager plus loin.",
            [{"source": "open_loops", "quote": named}],
        )
    )
    assert output.validate_portrait_claims(claims, [], {"open_loops": named}) == []
    common = "- Renvoyer le devis du vernis (the person owes it, l'ébéniste; due around 2026-10-15)"
    claims = _parse(
        _claim(
            "Le devis du vernis attend son retour vers l'ébéniste, et ce retard pèse sur l'atelier.",
            [{"source": "open_loops", "quote": common}],
        )
    )
    assert len(output.validate_portrait_claims(claims, [], {"open_loops": common})) == 1


def test_capitalised_german_nouns_shared_with_a_debrief_are_not_names():
    # Every German noun is capitalised: a guard reading capitals as names would drop a
    # legitimate German reading on every turn.
    line = (
        "- Marine (written 2026-10-01): eine Kollegin in der Rufbereitschaft — steht am selben"
        " Punkt. Open: Verteilung der Dienste"
    )
    claims = _parse(
        _claim(
            "Die Verteilung der Dienste bleibt der Punkt, an dem er die Kontrolle nicht abgibt,"
            " auch wenn er sie teilen möchte.",
            [{"source": "relation_debriefs", "quote": line}],
        )
    )
    assert len(output.validate_portrait_claims(claims, [], {"relation_debriefs": line})) == 1


def test_function_words_shared_with_an_item_do_not_make_a_restatement():
    # « dans », « cette », « avec », « pour », « sans », « tout » are function words of
    # four letters or more: a sentence sharing six of them and ONE content word with
    # an item is no paraphrase of it.
    line = (
        "- [personal] Dans cette période, avec son équipe, pour chaque dossier, "
        "sans attendre, tout est tranché vite. (2026-10-01)"
    )
    claims = _parse(
        _claim(
            "Dans cette phase, avec les siens, pour tout sujet, sans attendre, il tranche.",
            [{"source": "memories", "quote": line}],
        )
    )
    assert len(output.validate_portrait_claims(claims, [], {"memories": line})) == 1
