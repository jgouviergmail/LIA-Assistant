"""What the answers SHOWED is the one record a designation is read on (ADR-367 amendment).

The registry holds everything a turn FETCHED — a lookup an answer only consumed,
the candidates it set aside — and the context list what the last lookup of a
domain returned. Neither is what the person saw. The response declares what its
answer presents (``<relevant_ids>``); that declaration, recorded per turn, is
what « the second one » and « Marc's email » designate.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.config import settings
from src.domains.agents.constants import STATE_KEY_SHOWN_ITEMS
from src.domains.agents.context.shown_items import (
    ordinal_list,
    recorded_shown,
    shown_items,
    shown_order,
)
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType

pytestmark = pytest.mark.unit


def _email(item_id: str, subject: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "EMAIL",
        "payload": {"id": item_id, "subject": subject},
        "meta": {"source": "gmail", "domain": "emails", "turn_id": 1},
    }


REGISTRY: dict[str, Any] = {key: _email(key, key.upper()) for key in ("a", "b", "c", "m")}
REGISTRY["v"] = {
    "id": "v",
    "type": "EVENT",
    "payload": {"id": "v", "summary": "Dentiste"},
    "meta": {"source": "google_calendar", "domain": "events", "turn_id": 1},
}


def _state(*entries: tuple[int, list[str]], turn: int) -> dict[str, Any]:
    return {
        "current_turn_id": turn,
        "registry": REGISTRY,
        STATE_KEY_SHOWN_ITEMS: [{"turn_id": t, "ids": ids} for t, ids in entries],
    }


class TestWhatAnAnswerShowed:
    def test_cards_are_recorded_in_the_order_they_are_drawn(self) -> None:
        displayed = {"c": REGISTRY["c"], "a": REGISTRY["a"]}
        declared = "<relevant_ids>a,c</relevant_ids>Two mails."
        assert shown_order(displayed, declared, cards=True) == ["c", "a"]

    def test_without_cards_the_answer_s_own_order_is_recorded(self) -> None:
        displayed = {"c": REGISTRY["c"], "a": REGISTRY["a"]}
        declared = "<relevant_ids>a,c</relevant_ids>A first, then C."
        assert shown_order(displayed, declared, cards=False) == ["a", "c"]

    def test_an_undeclared_record_the_answer_kept_follows_the_declared_ones(self) -> None:
        displayed = {"c": REGISTRY["c"], "a": REGISTRY["a"]}
        assert shown_order(displayed, "<relevant_ids>a</relevant_ids>", cards=False) == ["a", "c"]

    def test_nothing_displayed_records_nothing(self) -> None:
        assert shown_order(None, "", cards=True) == []
        assert shown_order({}, "<relevant_ids></relevant_ids>", cards=False) == []


class TestTheRecordKeptAcrossTurns:
    def test_this_turn_is_recorded_beside_the_turns_still_in_reach(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "entity_resolution_max_turn_age", 2)
        state = _state((2, ["a"]), (3, ["b"]), turn=4)
        # At turn 5, turn 2 is three turns back: out of reach, dropped.
        assert recorded_shown(state, ["c"]) == [
            {"turn_id": 3, "ids": ["b"]},
            {"turn_id": 4, "ids": ["c"]},
        ]

    def test_a_resumed_turn_replaces_its_own_entry(self) -> None:
        state = _state((3, ["a"]), (4, ["b"]), turn=4)
        assert recorded_shown(state, ["c"]) == [
            {"turn_id": 3, "ids": ["a"]},
            {"turn_id": 4, "ids": ["c"]},
        ]

    def test_a_turn_that_showed_nothing_changes_nothing(self) -> None:
        assert recorded_shown(_state((3, ["a"]), turn=4), []) is None

    def test_a_malformed_record_is_read_forgivingly(self) -> None:
        state = {
            "current_turn_id": 4,
            STATE_KEY_SHOWN_ITEMS: [{"turn_id": "x"}, "junk", {"turn_id": 3, "ids": [1, "a"]}],
        }
        assert recorded_shown(state, ["b"]) == [
            {"turn_id": 3, "ids": ["a"]},
            {"turn_id": 4, "ids": ["b"]},
        ]


class TestWhatADescriptionReads:
    def test_newest_answer_first_each_item_once(self) -> None:
        items = shown_items(_state((1, ["a", "b"]), (2, ["b", "v"]), turn=3))
        assert [(item.item_id, item.turn) for item in items] == [("b", 2), ("v", 2), ("a", 1)]

    def test_only_the_turns_within_reach_and_never_this_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "entity_resolution_max_turn_age", 2)
        items = shown_items(_state((1, ["a"]), (2, ["b"]), (4, ["c"]), turn=4))
        assert [item.item_id for item in items] == ["b"]

    def test_an_item_fetched_but_never_shown_is_not_there(self) -> None:
        # « m » sits in the registry — a lookup consumed it — but no answer showed it.
        items = shown_items(_state((1, ["a"]), turn=2))
        assert [item.item_id for item in items] == ["a"]

    def test_an_item_since_evicted_from_the_registry_is_skipped(self) -> None:
        items = shown_items(_state((1, ["a", "gone"]), turn=2))
        assert [item.item_id for item in items] == ["a"]

    def test_a_registry_item_object_reads_like_its_checkpointed_dict(self) -> None:
        item = RegistryItem(
            id="o",
            type=RegistryItemType.EMAIL,
            payload={"id": "o", "subject": "Objet"},
            meta=RegistryItemMeta(source="gmail", domain="emails"),
        )
        state = {
            "current_turn_id": 2,
            "registry": {"o": item},
            STATE_KEY_SHOWN_ITEMS: [{"turn_id": 1, "ids": ["o"]}],
        }
        (shown,) = shown_items(state)
        assert (shown.domain, shown.payload["subject"]) == ("emails", "Objet")


class TestTheListAnOrdinalCounts:
    def test_the_newest_list_of_the_domain(self) -> None:
        turn, items = ordinal_list(_state((1, ["a", "b", "c"]), (2, ["v"]), turn=3), "emails")
        assert turn == 1 and [item.item_id for item in items] == ["a", "b", "c"]

    def test_a_listed_item_opened_alone_leaves_the_list_in_place(self) -> None:
        # « my mails » then « open the first »: « the second » is still B.
        turn, items = ordinal_list(_state((1, ["a", "b", "c"]), (2, ["a"]), turn=3), "emails")
        assert turn == 1 and [item.item_id for item in items] == ["a", "b", "c"]

    def test_an_item_opened_alone_counts_in_the_list_that_held_it(self) -> None:
        # « my mails » [A B C], « Marc's mails » [M B], then « open A »: A came
        # from the first list, not from the newest one.
        state = _state((1, ["a", "b", "c"]), (2, ["m", "b"]), (3, ["a"]), turn=4)
        turn, items = ordinal_list(state, "emails")
        assert turn == 1 and [item.item_id for item in items] == ["a", "b", "c"]

    def test_a_new_single_result_is_the_list(self) -> None:
        turn, items = ordinal_list(_state((1, ["a", "b", "c"]), (2, ["m"]), turn=3), "emails")
        assert turn == 2 and [item.item_id for item in items] == ["m"]

    def test_a_narrower_list_shown_since_replaces_the_wider_one(self) -> None:
        turn, items = ordinal_list(_state((1, ["a", "b", "c"]), (2, ["b", "c"]), turn=3), "emails")
        assert turn == 2 and [item.item_id for item in items] == ["b", "c"]

    def test_nothing_of_the_domain_shown(self) -> None:
        assert ordinal_list(_state((1, ["v"]), turn=2), "emails") == (None, [])
