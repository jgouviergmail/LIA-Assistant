"""References select complete captured evidence without reproducing its formatting."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.domains.journals import consolidation_output as output
from src.domains.journals import portrait_catalogue as catalogue
from src.domains.journals.portrait_diagnostics import PortraitValidationError

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
        "in_brief": True,
    }


def _parse(support):
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [_claim(support)]})
    )
    assert result.valid, result.error
    return result.portrait_claims


def test_catalogue_reference_resolves_exact_metadata_without_model_recopied_quote():
    line = "- [personal]  Il demande une prochaine action concrète en urgence. (2026-10-07)"
    identifier = catalogue.source_item_id("memories", line)
    claims = _parse({"source": "memories", "item_id": identifier})
    evidence = output.render_exact_evidence(claims, [], {"memories": line})
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
    before_suffix = "- Truncated body… (2026-10-07)"
    ending = "- Truncated debrief…"
    sections = {
        "memories": "## MEMORIES\n" + "\n".join([good, before_suffix, ending]),
        "habits": "",
    }
    rendered = catalogue.render_catalogue_sections(sections)
    assert rendered["memories"].startswith("## MEMORIES\n")
    assert catalogue.source_item_id("memories", good) in rendered["memories"]
    assert rendered["memories"].endswith(
        f"- [portrait_item_id={catalogue.source_item_id('memories', good)}] {good[2:]}"
    )
    assert before_suffix not in rendered["memories"] and ending not in rendered["memories"]
    assert rendered["habits"] == ""


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
    with pytest.raises(ValueError):
        output.render_exact_evidence(_parse(support), [], sections)


def test_identifiers_change_with_source_or_content():
    line = "- A complete fact."
    identifier = catalogue.source_item_id("memories", line)
    assert identifier == catalogue.source_item_id("memories", line)
    assert identifier != catalogue.source_item_id("interests", line)
    assert identifier != catalogue.source_item_id("memories", "- A changed fact.")


def test_truncated_quote_cannot_gain_admission_through_a_reference():
    line = "- A truncated fact… (2026-10-07)"
    with pytest.raises(ValueError):
        catalogue.source_item_id("memories", line)


@pytest.mark.parametrize("shape", ["both", "neither", "empty_id"])
def test_support_requires_exactly_one_selector(shape):
    support = {"source": "memories"}
    if shape == "both":
        support.update(quote="- A complete fact.", item_id="pi_" + "0" * 20)
    elif shape == "empty_id":
        support["item_id"] = ""
    assert not output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [_claim(support)]})
    ).valid


def test_journal_reference_is_bound_to_uuid_revision_and_complete_current_content():
    entry = _entry()
    identifier = catalogue.journal_item_id(entry)
    claims = _parse({"source": f"journal:{entry.id}", "item_id": identifier})
    proof = output.render_exact_evidence(claims, [entry], {})[0]["supports"][0]
    assert proof["quote"] == entry.content and proof["revision"] == 1
    entry.revision += 1
    assert identifier != catalogue.journal_item_id(entry)
    with pytest.raises(ValueError):
        output.render_exact_evidence(claims, [entry], {})


@pytest.mark.parametrize(
    "extra", [{"level": "L0"}, {"confidence": "low"}, {"contradiction_count": 1}]
)
def test_nonoperational_journal_entries_have_no_catalogue_reference(extra):
    assert catalogue.journal_item_id(_entry(**extra)) is None


def test_legacy_whole_quote_stays_exact_and_cannot_be_body_matched():
    line = "- [personal] A complete fact. (2026-10-07)"
    claims = _parse({"source": "memories", "quote": line})
    assert (
        output.render_exact_evidence(claims, [], {"memories": line})[0]["supports"][0]["quote"]
        == line
    )
    with pytest.raises(ValueError):
        output.render_exact_evidence(
            _parse({"source": "memories", "quote": "A complete fact."}), [], {"memories": line}
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
    proofs = output.render_exact_evidence(
        parsed.portrait_claims, [], {"memories": first + "\n" + second}
    )
    assert [proof["quote"] for proof in proofs[0]["supports"]] == [first, second]


def test_reference_and_legacy_quote_of_same_item_are_duplicate_evidence():
    line = "- A complete fact."
    claim = _claim({"source": "memories", "item_id": catalogue.source_item_id("memories", line)})
    claim["supports"].append({"source": "memories", "quote": line})
    parsed = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    with pytest.raises(ValueError, match="duplicate"):
        output.render_exact_evidence(parsed.portrait_claims, [], {"memories": line})


def test_multiline_item_has_no_usable_first_fragment_but_other_whole_items_survive():
    fragment = "- Architecture (other, Conception"
    good = "- Another complete fact."
    section = "## INTERESTS\n" + fragment + "\nRéhabilitation; weight +3)\n" + good
    assert [item.quote for item in catalogue.eligible_source_items("interests", section)] == [good]
    assert fragment not in catalogue.render_catalogue_sections({"interests": section})["interests"]
    with pytest.raises(ValueError):
        output.render_exact_evidence(
            _parse({"source": "interests", "quote": fragment}), [], {"interests": section}
        )


def test_completely_ineligible_source_has_no_misleading_header():
    assert catalogue.render_catalogue_sections(
        {"relation_debriefs": "## DEBRIEFS (2 items)\n- Cut…\n- Also cut…"}
    ) == {"relation_debriefs": ""}


def test_overlong_source_passage_cannot_be_offered_or_resolved():
    line = "- " + "x" * catalogue.PORTRAIT_SUPPORT_QUOTE_MAX_CHARS
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
    with pytest.raises(ValueError, match="metadata"):
        output.grounded_portraits(parsed.portrait_claims, [], {"memories": line})


def test_catalogue_header_reports_admissible_items_and_keeps_source_total():
    rendered = catalogue.render_catalogue_sections(
        {"memories": "## MEMORIES (2 of 2 relevant memories)\n- Complete fact.\n- Cut…"}
    )
    assert rendered["memories"].startswith("## MEMORIES (1 of 2 relevant memories)\n")


@pytest.mark.parametrize("marker", ["pi_" + "a" * 64, "portrait_item_id=reference"])
def test_catalogue_references_are_forbidden_in_visible_portrait_prose(marker):
    claim = _claim({"source": "memories", "quote": "- Complete fact."})
    claim["text"] = f"Il apprécie une prochaine action, source {marker}."
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    assert not result.valid


def test_invalid_claim_diagnostics_do_not_copy_private_input_values():
    secret = "PRIVATE_X sensitive correspondence subject PRIVATE_X"
    claim = _claim({"source": "memories", "quote": "- " + secret})
    claim["text"] = "DO " + secret
    result = output.parse_maintenance_output(
        json.dumps({"actions": [], "portrait_claims": [claim]})
    )
    assert not result.valid
    assert secret not in result.error
    assert "PRIVATE_X" not in result.error
    assert "natural prose" in result.error
    assert "portrait_claims" in result.error and "text" in result.error


def test_invalid_payload_diagnostics_are_bounded():
    claims = [_claim({"source": "memories", "quote": "- " + "x" * 5100}) for _ in range(32)]
    result = output.parse_maintenance_output(json.dumps({"actions": [], "portrait_claims": claims}))
    assert not result.valid
    assert len(result.error) <= 4096
    assert result.error.count("string_too_long") <= 8


@pytest.mark.parametrize("change", ["id", "content"])
def test_journal_reference_cannot_be_reused_after_rule_identity_or_content_changes(change):
    entry = _entry()
    claims = _parse({"source": f"journal:{entry.id}", "item_id": catalogue.journal_item_id(entry)})
    if change == "id":
        entry.id = uuid4()
    else:
        entry.content += " Additional restriction."
    with pytest.raises(ValueError):
        output.render_exact_evidence(claims, [entry], {})


def test_legacy_and_catalogue_selectors_produce_identical_canonical_review_evidence():
    line = "- [personal] Complete conditional preference. (2026-10-07)"
    reference = _parse(
        {"source": "memories", "item_id": catalogue.source_item_id("memories", line)}
    )
    legacy = _parse({"source": "memories", "quote": line})
    assert output.render_exact_evidence(
        reference, [], {"memories": line}
    ) == output.render_exact_evidence(legacy, [], {"memories": line})


def test_unknown_reference_has_indexed_content_free_rejection_diagnostics():
    line = "- PRIVATE_X complete confidential source item."
    claims = _parse({"source": "memories", "item_id": "pi_" + "0" * 64})
    with pytest.raises(PortraitValidationError) as caught:
        output.render_exact_evidence(claims, [], {"memories": line})
    assert caught.value.details == {
        "phase": "source_proof",
        "source": "memories",
        "selector_kind": "item_id",
        "unknown_reference": True,
        "claim_index": 0,
        "support_index": 0,
    }
    assert "PRIVATE_X" not in str(caught.value) + repr(caught.value.details)
