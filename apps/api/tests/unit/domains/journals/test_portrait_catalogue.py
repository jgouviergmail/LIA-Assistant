"""References select complete captured evidence without reproducing its formatting."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.domains.journals import consolidation_output as output
from src.domains.journals import portrait_catalogue as catalogue
from tests.unit.domains.journals.evidence_view import evidence_view

pytestmark = pytest.mark.unit


def _entry(**extra):
    return SimpleNamespace(
        **{
            "id": uuid4(),
            "revision": 1,
            "content": "WHEN urgent -> DO give one step BECAUSE action was requested.",
            "level": "L1",
            "confidence": "medium",
            "contradiction_count": 0,
            "evidence_count": 0,
            "theme": "learnings",
            **extra,
        }
    )


def _claim(support):
    return {
        "facet": "interaction",
        "text": "Quand il demande une aide urgente, proposer une prochaine action concrète.",
        "supports": [support],
        "placement": "full",
    }


def _parse(support):
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [_claim(support)]})
    )
    assert result.valid, result.error
    return result.portrait_claims


def test_catalogue_reference_resolves_exact_metadata_without_model_recopied_quote():
    # An English item under a French reading: the reading is no paraphrase of it.
    line = "- [personal]  Asks for one concrete next step when something is urgent. (2026-10-07)"
    identifier = catalogue.source_item_id("memories", line)
    claims = _parse({"source": "memories", "item_id": identifier})
    evidence = evidence_view(claims, [], {"memories": line})
    assert evidence[0]["supports"] == [{"source": "memories", "quote": line}]
    published = []
    assert (
        output.grounded_portraits(claims, [], {"memories": line}, published=published)[0]
        == claims[0].text
    )
    assert published[0].supports[0].model_dump() == {"source": "memories", "quote": line}
    assert "pi_" not in output.grounded_portraits(claims, [], {"memories": line})[0]


def test_catalogue_display_keeps_header_and_omits_all_incomplete_items():
    good = "- A complete fact."
    continued = "- An item whose text\n  spills onto a continuation line"
    blank = "- "
    sections = {
        "memories": "## MEMORIES\n" + "\n".join([good, continued, blank]),
        "habits": "",
    }
    rendered = catalogue.render_catalogue_sections(sections)
    assert rendered["memories"].startswith("## MEMORIES\n")
    assert catalogue.source_item_id("memories", good) in rendered["memories"]
    assert rendered["memories"].endswith(
        f"- [portrait_item_id={catalogue.source_item_id('memories', good)}] {good[2:]}"
    )
    assert "spills" not in rendered["memories"]
    assert rendered["habits"] == ""


def test_a_natural_ellipsis_is_text_not_a_cut():
    # No reader clamps with an ellipsis any more: a line carrying one is a whole item.
    line = "- The person hesitates… then decides quickly."
    assert catalogue.eligible_source_items("memories", line)[0].quote == line
    assert catalogue.source_item_id("memories", line).startswith("pi_")


@pytest.mark.parametrize("failure", ["unknown", "wrong_source", "changed_body"])
def test_only_exact_current_source_and_item_identity_can_be_selected(failure):
    line = "- A complete conditional fact."
    identifier = catalogue.source_item_id("memories", line)
    support = {"source": "memories", "item_id": identifier}
    sections = {"memories": line}
    if failure == "unknown":
        support["item_id"] = "pi_" + "0" * 20
    elif failure == "wrong_source":
        support["source"] = "interests"
        sections["interests"] = line
    else:
        sections["memories"] = "- A changed complete conditional fact."
    # A reference that does not resolve in THIS snapshot proves nothing: dropped.
    assert evidence_view(_parse(support), [], sections) == []


def test_identifiers_change_with_source_or_content():
    line = "- A complete fact."
    identifier = catalogue.source_item_id("memories", line)
    assert identifier == catalogue.source_item_id("memories", line)
    assert identifier != catalogue.source_item_id("interests", line)
    assert identifier != catalogue.source_item_id("memories", "- A changed fact.")


def test_a_continued_or_blank_item_cannot_gain_admission_through_a_reference():
    with pytest.raises(ValueError):
        catalogue.source_item_id("memories", "- A fact\n  continued below")
    with pytest.raises(ValueError):
        catalogue.source_item_id("memories", "- ")


@pytest.mark.parametrize("shape", ["both", "neither", "empty_id"])
def test_support_requires_exactly_one_selector(shape):
    support = {"source": "memories"}
    if shape == "both":
        support.update(quote="- A complete fact.", item_id="pi_" + "0" * 20)
    elif shape == "empty_id":
        support["item_id"] = ""
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [_claim(support)]})
    )
    # The claim is unreadable: rejected and counted, the batch itself stays valid.
    assert result.valid and result.portrait_claims == []
    assert [item["claim_index"] for item in result.rejected_claims] == [0]


def test_journal_reference_is_bound_to_uuid_revision_and_complete_current_content():
    entry = _entry()
    identifier = catalogue.journal_item_id(entry)
    claims = _parse({"source": f"journal:{entry.id}", "item_id": identifier})
    proof = evidence_view(claims, [entry], {})[0]["supports"][0]
    assert proof["quote"] == entry.content and proof["revision"] == 1
    entry.revision += 1
    assert identifier != catalogue.journal_item_id(entry)
    assert evidence_view(claims, [entry], {}) == []


@pytest.mark.parametrize(
    "extra", [{"level": "L0"}, {"confidence": "low"}, {"contradiction_count": 1}]
)
def test_nonoperational_journal_entries_have_no_catalogue_reference(extra):
    assert catalogue.journal_item_id(_entry(**extra)) is None


def test_legacy_whole_quote_stays_exact_and_cannot_be_body_matched():
    line = "- [personal] A complete fact. (2026-10-07)"
    claims = _parse({"source": "memories", "quote": line})
    assert evidence_view(claims, [], {"memories": line})[0]["supports"][0]["quote"] == line
    assert (
        evidence_view(
            _parse({"source": "memories", "quote": "A complete fact."}), [], {"memories": line}
        )
        == []
    )


def test_distinct_same_source_references_do_not_alias_quote_none():
    first, second = "- First complete fact.", "- Second complete fact."
    claim = _claim({"source": "memories", "item_id": catalogue.source_item_id("memories", first)})
    claim["supports"].append(
        {"source": "memories", "item_id": catalogue.source_item_id("memories", second)}
    )
    parsed = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    proofs = evidence_view(parsed.portrait_claims, [], {"memories": first + "\n" + second})
    assert [proof["quote"] for proof in proofs[0]["supports"]] == [first, second]


def test_reference_and_legacy_quote_of_same_item_are_one_support():
    line = "- A complete fact."
    claim = _claim({"source": "memories", "item_id": catalogue.source_item_id("memories", line)})
    claim["supports"].append({"source": "memories", "quote": line})
    parsed = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    dropped: list[dict] = []
    # The same item cited twice is ONE support (a repair, ADR-184), never a drop.
    validated = output.validate_portrait_claims(
        parsed.portrait_claims, [], {"memories": line}, dropped=dropped
    )
    assert dropped == [] and len(validated) == 1
    assert [proof["quote"] for proof in validated[0].evidence] == [line]


def test_multiline_item_has_no_usable_first_fragment_but_other_whole_items_survive():
    fragment = "- Architecture (other, Conception"
    good = "- Another complete fact."
    section = "## INTERESTS\n" + fragment + "\nRéhabilitation; weight +3)\n" + good
    assert [item.quote for item in catalogue.eligible_source_items("interests", section)] == [good]
    assert fragment not in catalogue.render_catalogue_sections({"interests": section})["interests"]
    assert (
        evidence_view(
            _parse({"source": "interests", "quote": fragment}), [], {"interests": section}
        )
        == []
    )


def test_completely_ineligible_source_has_no_misleading_header():
    assert catalogue.render_catalogue_sections(
        {"relation_debriefs": "## DEBRIEFS (2 items)\n- Cut\n  across lines\n- "}
    ) == {"relation_debriefs": ""}


def test_overlong_source_passage_cannot_be_offered_or_resolved():
    # The assembler cuts at this bound before anything reaches the catalogue; here
    # the bound is the catalogue's own guard against a line nobody bounded.
    line = "- " + "x" * catalogue.PORTRAIT_ITEM_MAX_CHARS
    assert catalogue.eligible_source_items("memories", line) == []
    assert catalogue.render_catalogue_sections({"memories": "## MEMORIES\n" + line}) == {
        "memories": ""
    }


def test_reference_does_not_permit_raw_fact_copy_as_natural_portrait():
    line = "- A complete fact about the person."
    claim = _claim({"source": "memories", "item_id": catalogue.source_item_id("memories", line)})
    claim["text"] = line[2:]
    parsed = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    assert parsed.valid
    dropped: list[dict] = []
    assert (
        output.validate_portrait_claims(
            parsed.portrait_claims, [], {"memories": line}, dropped=dropped
        )
        == []
    )
    assert dropped[0]["reason"] == "exact proofs belong in metadata, not the portrait text"
    assert output.grounded_portraits(parsed.portrait_claims, [], {"memories": line}) == (
        None,
        None,
    )


def test_catalogue_header_reports_admissible_items_and_keeps_source_total():
    rendered = catalogue.render_catalogue_sections(
        {"memories": "## MEMORIES (2 of 2 relevant memories)\n- Complete fact.\n- Cut\n  over"}
    )
    assert rendered["memories"].startswith("## MEMORIES (1 of 2 relevant memories)\n")


@pytest.mark.parametrize("marker", ["pi_" + "a" * 64, "portrait_item_id=reference"])
def test_catalogue_references_are_forbidden_in_visible_portrait_prose(marker):
    claim = _claim({"source": "memories", "quote": "- Complete fact."})
    claim["text"] = f"Il apprécie une prochaine action, source {marker}."
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    assert result.valid and result.portrait_claims == []
    assert result.rejected_claims[0]["codes"] == ["value_error"]


def test_invalid_claim_diagnostics_do_not_copy_private_input_values():
    secret = "PRIVATE_X sensitive correspondence subject PRIVATE_X"
    claim = _claim({"source": "memories", "quote": "- " + secret})
    claim["text"] = "DO " + secret
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    # The rejection carries CODES, never the words (ADR-317).
    assert result.valid and result.portrait_claims == []
    diagnostics = json.dumps(result.rejected_claims)
    assert secret not in diagnostics and "PRIVATE_X" not in diagnostics
    assert result.rejected_claims[0]["codes"] == ["value_error"]


def test_rejected_claim_diagnostics_are_bounded():
    claims = [_claim({"source": "memories", "quote": "- " + "x" * 5100}) for _ in range(32)]
    result = output.parse_maintenance_output(json.dumps({"actions": [], "portrait_claims": claims}))
    assert result.valid and result.portrait_claims == []
    assert len(result.rejected_claims) == 32
    assert all(item["codes"] == ["string_too_long"] for item in result.rejected_claims)
    assert len(json.dumps(result.rejected_claims)) <= 4096


@pytest.mark.parametrize("change", ["id", "content"])
def test_journal_reference_cannot_be_reused_after_rule_identity_or_content_changes(change):
    entry = _entry()
    claims = _parse({"source": f"journal:{entry.id}", "item_id": catalogue.journal_item_id(entry)})
    if change == "id":
        entry.id = uuid4()
    else:
        entry.content += " Additional restriction."
    assert evidence_view(claims, [entry], {}) == []


def test_legacy_and_catalogue_selectors_produce_identical_canonical_evidence():
    line = "- [personal] Complete conditional preference. (2026-10-07)"
    reference = _parse(
        {"source": "memories", "item_id": catalogue.source_item_id("memories", line)}
    )
    legacy = _parse({"source": "memories", "quote": line})
    assert evidence_view(reference, [], {"memories": line}) == evidence_view(
        legacy, [], {"memories": line}
    )


def test_unknown_reference_has_indexed_content_free_rejection_diagnostics():
    line = "- PRIVATE_X complete confidential source item."
    claims = _parse({"source": "memories", "item_id": "pi_" + "0" * 64})
    dropped: list[dict] = []
    assert output.validate_portrait_claims(claims, [], {"memories": line}, dropped=dropped) == []
    assert dropped == [
        {
            "claim_index": 0,
            "reason": "portrait reference is not a complete authorized source item",
            "phase": "source_proof",
            "source": "memories",
            "selector_kind": "item_id",
            "unknown_reference": True,
            "support_index": 0,
        }
    ]
    assert "PRIVATE_X" not in repr(dropped)
