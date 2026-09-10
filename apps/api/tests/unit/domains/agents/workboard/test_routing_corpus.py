"""Can a sentence about the board reach the board? (ADR-276, lot 3)

The corpus has two halves, and this file is the one that runs in CI.

**Deterministic half** — everything that decides routing WITHOUT a model: does
the domain exist, does its description tell it from the three things it is
confused with, do the manifests carry the words a person actually says, and is
every family's expected tool a tool that exists? A failure here is a defect
nobody would otherwise see until a real sentence went to the wrong domain.

**Provider half** — whether a real model picks the right tool for each of the
72 utterances. That is a MEASUREMENT, not a test: it needs a key, it costs
money, and a test that skips on a missing key is green and therefore rots
(ADR-155). It lives in ``scripts/measure_workboard_routing.py``, run by
``task workboard:corpus:measure``, exactly like the recurrence corpus.

The NEGATIVE families are the point: a corpus proving only the happy cases
proves nothing about the confusion that actually happens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

CORPUS_PATH = Path(__file__).parent / "routing_corpus.json"
LANGUAGES = ("fr", "en", "de", "es", "it", "zh-CN")


@pytest.fixture(scope="module")
def corpus() -> dict[str, Any]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def families(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    return list(corpus["families"])


class TestTheCorpusIsComplete:
    def test_it_covers_at_least_eight_families(self, families: list[dict[str, Any]]) -> None:
        assert len(families) >= 8

    def test_every_family_speaks_all_six_languages(self, families: list[dict[str, Any]]) -> None:
        """A routing rule that works in French and not in Chinese is a rule
        five readers out of six do not have."""
        for family in families:
            assert sorted(family["utterances"]) == sorted(LANGUAGES), family["name"]
            for language, sentence in family["utterances"].items():
                assert sentence.strip(), f"{family['name']}/{language}"

    def test_it_carries_negative_families(self, families: list[dict[str, Any]]) -> None:
        """The three neighbours a ticket is confused with, each with a reason
        written down."""
        negatives = [f for f in families if f["expect_domain"] != "ticket"]
        assert {f["expect_domain"] for f in negatives} == {"task", "reminder", "automation"}
        for family in negatives:
            assert family.get("_why", "").strip(), family["name"]

    def test_every_expected_tool_exists(self, families: list[dict[str, Any]]) -> None:
        """A corpus naming a tool nobody wrote would pass forever and measure
        nothing."""
        from src.domains.agents.workboard.catalogue_manifests import TICKET_AGENT_MANIFEST

        expected = {f["expect_tool"] for f in families if f["expect_tool"]}
        assert expected <= set(TICKET_AGENT_MANIFEST.tools)

    def test_every_workboard_tool_is_exercised(self, families: list[dict[str, Any]]) -> None:
        """A capability no sentence reaches is a capability nobody can ask for."""
        from src.domains.agents.workboard.catalogue_manifests import TICKET_AGENT_MANIFEST

        exercised = {f["expect_tool"] for f in families if f["expect_tool"]}
        assert exercised == set(TICKET_AGENT_MANIFEST.tools)


class TestTheDomainCanBeReached:
    def test_the_domain_is_registered_and_routable(self) -> None:
        from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

        domain = DOMAIN_REGISTRY["ticket"]
        assert domain.is_routable is True
        assert domain.result_key == "tickets"

    def test_its_description_names_the_words_people_use(self) -> None:
        from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

        described = DOMAIN_REGISTRY["ticket"].description.lower()
        for word in ("workboard", "board", "ticket", "kanban", "column"):
            assert word in described, word

    def test_its_description_separates_it_from_its_three_neighbours(self) -> None:
        """The router has only this sentence to tell a ticket from a provider
        to-do, a reminder and a routine."""
        from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

        described = DOMAIN_REGISTRY["ticket"].description.lower()
        assert "not" in described
        for neighbour in ("task", "reminder", "automation"):
            assert neighbour in described, neighbour

    def test_a_peer_name_keeps_the_peer_directory_in_play(self) -> None:
        """« confie-le à Marie » must not lose the connection directory."""
        from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

        assert DOMAIN_REGISTRY["ticket"].related_domains == ["peer"]

    def test_the_address_book_is_deliberately_absent(self) -> None:
        """The peers program measured what listing `contact` costs: Google
        contact tools pulled into every plan, and a missing scope invalidating
        the whole thing."""
        from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

        assert "contact" not in DOMAIN_REGISTRY["ticket"].related_domains


class TestTheManifestsCarryTheWords:
    def test_every_tool_declares_semantic_keywords(self) -> None:
        from src.domains.agents.workboard.catalogue_manifests import (
            comment_ticket_catalogue_manifest,
            create_ticket_catalogue_manifest,
            delete_ticket_catalogue_manifest,
            get_ticket_catalogue_manifest,
            list_tickets_catalogue_manifest,
            update_ticket_catalogue_manifest,
        )

        for manifest in (
            create_ticket_catalogue_manifest,
            update_ticket_catalogue_manifest,
            comment_ticket_catalogue_manifest,
            list_tickets_catalogue_manifest,
            get_ticket_catalogue_manifest,
            delete_ticket_catalogue_manifest,
        ):
            assert len(manifest.semantic_keywords) >= 3, manifest.name

    def test_the_board_is_named_in_the_keywords(self) -> None:
        """The word a person actually says has to appear somewhere the
        selection can see it."""
        from src.domains.agents.workboard.catalogue_manifests import (
            create_ticket_catalogue_manifest,
            list_tickets_catalogue_manifest,
        )

        words = " ".join(
            create_ticket_catalogue_manifest.semantic_keywords
            + list_tickets_catalogue_manifest.semantic_keywords
        ).lower()
        assert "board" in words
        assert "ticket" in words
