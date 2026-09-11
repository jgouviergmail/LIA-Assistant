"""Recurrence store: the request DESCRIPTOR travels as data, never as key (Q4).

A missed-routine offer used to have no object: the signature is the domain
alone (« email »), so the heartbeat could only say « your usual email thing ».
Composing the intent into the key would fragment every ledger (fewer
occurrences per signature, locks further out of reach — the decision
``resolve_actionable_domain`` documents). The analyzer's ``immediate_intent``
is therefore recorded as a bounded histogram INSIDE the payload, and one
reader answers « what does the person usually ask for ».
"""

from __future__ import annotations

import pytest

from src.infrastructure.cache import recurrence_store

pytestmark = pytest.mark.unit


class TestRecordIntent:
    def test_counts_one_intent_per_occurrence(self) -> None:
        data: dict = {"days": {}, "suggested_at": None}
        recurrence_store.record_intent(data, "search")
        recurrence_store.record_intent(data, "search")
        recurrence_store.record_intent(data, "send")
        assert data["intents"] == {"search": 2, "send": 1}

    @pytest.mark.parametrize("raw", [None, "", "   ", 42, "!!!"])
    def test_nothing_usable_records_nothing(self, raw: object) -> None:
        data: dict = {"days": {}}
        recurrence_store.record_intent(data, raw)  # type: ignore[arg-type]
        assert "intents" not in data or data["intents"] == {}

    def test_normalises_case_spacing_and_length(self) -> None:
        # The analyzer's field is a free string a model fills: what reaches
        # the ledger is lower-cased, trimmed, and cut to the bounded length,
        # so « Search » and « search » are one request, not two.
        data: dict = {"days": {}}
        recurrence_store.record_intent(data, "  Search ")
        recurrence_store.record_intent(data, "search")
        recurrence_store.record_intent(data, "x" * 100)
        assert data["intents"]["search"] == 2
        long_keys = [k for k in data["intents"] if k.startswith("x")]
        assert long_keys == ["x" * recurrence_store.INTENT_MAX_LENGTH]

    def test_distinct_intents_are_capped_by_dropping_the_rarest(self) -> None:
        data: dict = {"days": {}}
        for i in range(recurrence_store.INTENT_MAX_DISTINCT):
            for _ in range(i + 2):
                recurrence_store.record_intent(data, f"intent{i}")
        # One more distinct value than the cap: the rarest goes, and the
        # newcomer is kept ONLY when it is not itself the rarest.
        recurrence_store.record_intent(data, "newcomer")
        assert len(data["intents"]) == recurrence_store.INTENT_MAX_DISTINCT
        assert "newcomer" not in data["intents"]
        assert "intent0" in data["intents"]


class TestDominantIntent:
    def test_none_when_nothing_was_recorded(self) -> None:
        assert recurrence_store.dominant_intent({"days": {}}) is None
        assert recurrence_store.dominant_intent({"days": {}, "intents": {}}) is None

    def test_the_most_frequent_wins(self) -> None:
        data = {"days": {}, "intents": {"search": 3, "send": 5, "create": 1}}
        assert recurrence_store.dominant_intent(data) == "send"

    def test_a_tie_is_settled_deterministically(self) -> None:
        data = {"days": {}, "intents": {"send": 2, "create": 2}}
        assert recurrence_store.dominant_intent(data) == "create"

    def test_bad_counts_are_ignored(self) -> None:
        data = {"days": {}, "intents": {"search": "many", "send": 1, 7: 9}}
        assert recurrence_store.dominant_intent(data) == "send"


class TestLoadKeepsTheShape:
    async def test_a_payload_without_intents_reads_as_empty(self) -> None:
        class _Redis:
            async def get(self, key: str) -> str:
                return '{"days": {"2026-09-01": [8.0]}, "suggested_at": null}'

        data = await recurrence_store.load(_Redis(), "recurrence:u:email")
        assert data["intents"] == {}

    async def test_a_legacy_payload_converts_with_empty_intents(self) -> None:
        class _Redis:
            async def get(self, key: str) -> str:
                return '{"ts": [1756713600]}'

        data = await recurrence_store.load(_Redis(), "recurrence:u:email")
        assert data["intents"] == {}
        assert data["days"]
