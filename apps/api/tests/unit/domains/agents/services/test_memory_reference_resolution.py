"""Resolving "ma femme" into a name — the step that decides who a query is about.

Every actionable turn passes through this service before the planner: it
rewrites "cherche l'adresse de ma femme" into "cherche l'adresse de Jane Smith"
so the planner searches for a person rather than for a relationship word. Two
properties matter more than the resolution itself:

- it is **fail-safe**. No memory facts, a timeout, a provider error — each must
  hand the ORIGINAL query back, never an empty or half-rewritten one. A silent
  failure here does not error: it makes LIA search for "ma femme" in a contact
  book, and the user sees "no result".
- its **fallback parser** must extract what it can from a malformed LLM answer,
  which is the only reason it exists (apostrophes in French names break the
  JSON the model emits).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.services.memory_reference_resolution_service import (
    MemoryReferenceResolutionService,
    ResolvedReferences,
    resolution_from_payload,
)

pytestmark = pytest.mark.unit

FACTS = "The user's wife is Jane Smith. The user's brother is Jean Dupond."


@pytest.fixture
def service() -> MemoryReferenceResolutionService:
    return MemoryReferenceResolutionService()


class TestResolvedReferences:
    """The value object the planner reads (the response prompt reads its mappings)."""

    def test_has_resolutions_reflects_the_mappings(self) -> None:
        assert not ResolvedReferences("q", "q", {}).has_resolutions()
        assert ResolvedReferences("q", "q", {"ma femme": "Jane"}).has_resolutions()


class TestFailSafeLadder:
    """Every failure mode must hand back the original query, intact."""

    async def test_no_memory_facts_short_circuits_without_calling_the_model(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        with patch.object(service, "_resolve_all_via_llm", AsyncMock()) as llm:
            result = await service.resolve_pre_planner("cherche ma femme", memory_facts=None)

        assert result.enriched_query == "cherche ma femme"
        assert result.mappings == {}
        llm.assert_not_awaited()

    @pytest.mark.parametrize("facts", ["", "   ", "\n\t "])
    async def test_blank_memory_facts_count_as_no_facts(
        self, service: MemoryReferenceResolutionService, facts: str
    ) -> None:
        with patch.object(service, "_resolve_all_via_llm", AsyncMock()) as llm:
            result = await service.resolve_pre_planner("cherche ma femme", memory_facts=facts)

        assert result.enriched_query == "cherche ma femme"
        llm.assert_not_awaited()

    async def test_a_timeout_returns_the_original_query(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        with patch.object(service, "_resolve_all_via_llm", AsyncMock(side_effect=TimeoutError)):
            result = await service.resolve_pre_planner("cherche ma femme", memory_facts=FACTS)

        assert result.original_query == "cherche ma femme"
        assert result.enriched_query == "cherche ma femme"
        assert result.mappings == {}

    async def test_a_provider_error_returns_the_original_query(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        with patch.object(
            service, "_resolve_all_via_llm", AsyncMock(side_effect=RuntimeError("provider down"))
        ):
            result = await service.resolve_pre_planner("cherche ma femme", memory_facts=FACTS)

        assert result.enriched_query == "cherche ma femme"
        assert result.mappings == {}

    async def test_a_successful_resolution_is_passed_through(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        resolved = ResolvedReferences(
            original_query="cherche ma femme",
            enriched_query="cherche Jane Smith",
            mappings={"ma femme": "Jane Smith"},
        )

        with patch.object(service, "_resolve_all_via_llm", AsyncMock(return_value=resolved)):
            result = await service.resolve_pre_planner("cherche ma femme", memory_facts=FACTS)

        assert result is resolved


class TestFallbackExtraction:
    """The parser that runs when the model's JSON is malformed."""

    def _extract(self, service: MemoryReferenceResolutionService, response: str) -> Any:
        return service._fallback_regex_extraction(response, "cherche ma femme")

    def test_an_empty_response_yields_the_original_query(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        result = self._extract(service, "")

        assert result.enriched_query == "cherche ma femme"
        assert result.mappings == {}

    def test_it_recovers_the_query_and_the_mappings(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        response = json.dumps(
            {"resolved_query": "cherche Jane Smith", "mappings": {"ma femme": "Jane Smith"}}
        )

        result = self._extract(service, response)

        assert result.enriched_query == "cherche Jane Smith"
        assert result.mappings == {"ma femme": "Jane Smith"}

    def test_it_recovers_from_prose_wrapped_around_the_json(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        """Models prepend explanations; the extractor must not care."""
        response = (
            'Voici le résultat :\n```json\n{"resolved_query": "cherche Jane Smith", '
            '"mappings": {"ma femme": "Jane Smith"}}\n```'
        )

        result = self._extract(service, response)

        assert result.enriched_query == "cherche Jane Smith"
        assert result.mappings == {"ma femme": "Jane Smith"}

    def test_a_missing_resolved_query_falls_back_to_the_original(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        """Half an answer must not produce half a query."""
        result = self._extract(service, '{"mappings": {"ma femme": "Jane Smith"}}')

        assert result.enriched_query == "cherche ma femme"
        assert result.mappings == {"ma femme": "Jane Smith"}

    def test_a_missing_mappings_section_yields_no_mapping(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        result = self._extract(service, '{"resolved_query": "cherche Jane Smith"}')

        assert result.enriched_query == "cherche Jane Smith"
        assert result.mappings == {}

    def test_several_references_are_all_recovered(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        response = (
            '{"resolved_query": "invite Jane Smith et Jean Dupond", '
            '"mappings": {"ma femme": "Jane Smith", "mon frère": "Jean Dupond"}}'
        )

        result = self._extract(service, response)

        assert result.mappings == {"ma femme": "Jane Smith", "mon frère": "Jean Dupond"}

    def test_the_original_query_is_always_preserved(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        """The response node needs the user's own words to phrase its answer."""
        result = self._extract(service, '{"resolved_query": "cherche Jane Smith"}')

        assert result.original_query == "cherche ma femme"

    def test_garbage_never_raises(self, service: MemoryReferenceResolutionService) -> None:
        for response in ["{{{", '"resolved_query"', "null", "[]", "resolved_query: x"]:
            result = self._extract(service, response)
            assert result.original_query == "cherche ma femme"
            assert isinstance(result.mappings, dict)


class TestPayloadIsReadForgivingly:
    """The model's JSON is read field by field; a bad field never sinks the rest."""

    def test_kinds_are_carried(self) -> None:
        result = resolution_from_payload(
            {
                "resolved_query": "itinéraire 12 rue des Lilas",
                "mappings": {"chez mon frère": "12 rue des Lilas, Lyon"},
                "kinds": {"chez mon frère": "postal_address"},
            },
            "itinéraire chez mon frère",
        )
        assert result.mappings == {"chez mon frère": "12 rue des Lilas, Lyon"}
        assert result.value_kinds == {"chez mon frère": "postal_address"}

    def test_absent_kinds_are_empty(self) -> None:
        result = resolution_from_payload({"mappings": {"ma femme": "Jane"}}, "q")
        assert result.value_kinds == {}
        assert result.enriched_query == "q"

    @pytest.mark.parametrize("payload", [[], "text", None, 3])
    def test_a_non_object_payload_resolves_nothing(self, payload: object) -> None:
        result = resolution_from_payload(payload, "cherche ma femme")
        assert (result.enriched_query, result.mappings, result.value_kinds) == (
            "cherche ma femme",
            {},
            {},
        )

    def test_non_string_values_and_containers_are_dropped(self) -> None:
        result = resolution_from_payload(
            {
                "resolved_query": 7,
                "mappings": {"a": "Jane", "b": None, "c": {"x": 1}},
                "kinds": ["x"],
            },
            "q",
        )
        assert (result.enriched_query, result.mappings, result.value_kinds) == (
            "q",
            {"a": "Jane"},
            {},
        )


class TestModelReplyWiring:
    async def test_the_kinds_of_a_reply_reach_the_result(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        reply = SimpleNamespace(
            text='```json\n{"resolved_query": "r", "mappings": {"chez ma sœur": "4 avenue Foch, Paris"}, '
            '"kinds": {"chez ma sœur": "postal_address"}}\n```'
        )
        llm = SimpleNamespace(ainvoke=AsyncMock(return_value=reply))
        with (
            patch(
                "src.domains.agents.services.memory_reference_resolution_service.get_llm",
                return_value=llm,
            ),
            patch(
                "src.core.llm_config_helper.get_llm_config_for_agent",
                return_value=SimpleNamespace(timeout_seconds=5),
            ),
        ):
            result = await service._resolve_all_via_llm(
                query="restaurants chez ma sœur", memory_facts=FACTS
            )
        assert result.mappings == {"chez ma sœur": "4 avenue Foch, Paris"}
        assert result.value_kinds == {"chez ma sœur": "postal_address"}

    def test_the_regex_fallback_declares_no_kind(
        self, service: MemoryReferenceResolutionService
    ) -> None:
        result = service._fallback_regex_extraction(
            '{"resolved_query": "cherche Jane", "mappings": {"ma femme": "Jane"}',
            "cherche ma femme",
        )
        assert result.value_kinds == {}
