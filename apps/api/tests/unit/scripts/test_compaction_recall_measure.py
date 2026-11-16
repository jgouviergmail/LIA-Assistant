"""The compaction recall bench (lot 16): its corpus, where each fact lands, how it is read."""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from scripts.agents import measure_compaction_recall as bench
from scripts.agents.compaction_recall_corpus import (
    DISCUSSIONS,
    KINDS,
    Discussion,
    Fact,
    discussion_messages,
    exchange_messages,
)
from src.core.config import settings
from src.infrastructure.llm.message_view import content_for_model

pytestmark = pytest.mark.unit


def _text(messages: list[BaseMessage]) -> str:
    """Every word of the messages, tool calls included."""
    return "\n".join(
        content_for_model(message) + " " + str(getattr(message, "tool_calls", "") or "")
        for message in messages
    )


def _cases() -> list[tuple[Discussion, Fact]]:
    return [(discussion, fact) for discussion in DISCUSSIONS for fact in discussion.facts]


class TestTheCorpus:
    def test_every_kind_is_planted_in_both_languages(self) -> None:
        for language in ("fr", "en"):
            planted = {
                fact.kind
                for discussion in DISCUSSIONS
                if discussion.language == language
                for fact in discussion.facts
            }
            assert planted == set(KINDS), language

    @pytest.mark.parametrize(
        ("discussion", "fact"), _cases(), ids=[f"{d.key}-{f.key}" for d, f in _cases()]
    )
    def test_a_rule_reads_its_own_exchange_and_nothing_else(
        self, discussion: Discussion, fact: Fact
    ) -> None:
        """A match in a context is the fact itself, never an echo of another exchange."""
        for index, exchange in enumerate(discussion.exchanges):
            said = _text(exchange_messages(discussion.key, index, exchange))
            matched = re.search(fact.pattern, said) is not None
            assert matched is (exchange.key == fact.exchange), (fact.key, exchange.key)

    def test_every_fact_lies_where_the_compaction_summarises(self) -> None:
        for discussion in DISCUSSIONS:
            summarised = bench.summarised_exchanges(discussion)
            for fact in discussion.facts:
                assert fact.exchange in summarised, (discussion.key, fact.key)

    def test_a_recent_fact_was_in_view_before_the_compaction(self) -> None:
        recent = [(d, f) for d, f in _cases() if f.recent]

        assert recent, "the corpus measures what a compaction takes from the window"
        for discussion, fact in recent:
            assert bench.holds(fact, discussion_messages(discussion)), fact.key


class TestHowAFactIsRead:
    _FACT = Fact("ladder", "person", "x", "Who lends the ladder?", r"Bartholomew")

    def test_the_view_is_what_the_response_model_reads(self) -> None:
        """A tool result is never in the response model's view: only the summary keeps it."""
        call = AIMessage("", tool_calls=[{"name": "t", "args": {}, "id": "c1"}])
        held = [
            HumanMessage("Who?"),
            call,
            ToolMessage("Bartholomew", tool_call_id="c1"),
            AIMessage("Someone."),
        ]

        assert not bench.holds(self._FACT, held)
        assert bench.holds(self._FACT, [*held, HumanMessage("Bartholomew lends it")])

    @pytest.mark.parametrize(
        ("answer", "expected"),
        [
            ("Bartholomew, the neighbour.", True),
            ("UNKNOWN", False),
            ("UNKNOWN — maybe Bartholomew", False),
            ("A neighbour.", False),
        ],
    )
    def test_an_answer_counts_when_it_states_the_fact_and_no_doubt(
        self, answer: str, expected: bool
    ) -> None:
        assert bench.answered(self._FACT, answer) is expected

    def test_a_tail_beginning_with_an_answer_starts_mid_exchange(self) -> None:
        summary = SystemMessage("[Conversation history compacted — compaction #1.]")
        on_person = [HumanMessage("Joke?"), AIMessage("Here.")]

        assert not bench.starts_mid_exchange([*on_person, summary])
        assert bench.starts_mid_exchange([AIMessage("Here."), *on_person, summary])
        assert not bench.starts_mid_exchange([summary])

    def test_the_tally_counts_each_kind_exactly(self) -> None:
        rows = [
            bench.Row("d", "a", "person", visible_before=False, held_after=True, answered=True),
            bench.Row("d", "b", "person", visible_before=True, held_after=False, answered=False),
            bench.Row("d", "c", "tool", visible_before=False, held_after=False, answered=None),
        ]

        tally = bench.tally(rows)

        assert tally["person"] == {
            "facts": 2,
            "held_after": 1,
            "lost_from_view": 1,
            "answered": 1,
            "asked": 2,
        }
        assert tally["tool"]["asked"] == 0 and tally["tool"]["held_after"] == 0


class TestTheCompactionFamily:
    async def test_a_named_family_is_the_model_the_compaction_asks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Several families summarise the same discussions; the slot's settings stay."""
        named = FakeListChatModel(responses=["## Summary\n- The daughter is Inès."])
        monkeypatch.setattr(bench, "family_llm", lambda slot, family: ("named", named, None))
        discussion = DISCUSSIONS[0]

        with bench.compaction_family(("provider", "model", "provider_default")) as name:
            after = await bench.compacted(discussion, callbacks=[])

        assert name == "named"
        fille = next(fact for fact in discussion.facts if fact.key == "fille")
        assert bench.holds(fille, after)


class TestTheCompactionRuns:
    async def test_the_production_node_replaces_what_it_summarises(self) -> None:
        """The real entry node, forced as a replay forces it, through the real reducer."""
        discussion = DISCUSSIONS[0]
        summarizer = FakeListChatModel(responses=["## Summary\n- The daughter is Inès."])

        with patch(
            "src.domains.agents.services.compaction_service.get_llm", return_value=summarizer
        ):
            after = await bench.compacted(discussion, callbacks=[])

        by_key = {fact.key: fact for fact in discussion.facts}
        assert bench.holds(by_key["fille"], after), "what the summary wrote is read"
        assert not bench.holds(by_key["montant"], after), "a tool's fact it dropped is gone"
        assert bench.holds(by_key["budget"], after), "the person's words are quoted as written"
        kept = settings.compaction_preserve_recent_messages
        assert [m.id for m in after if not isinstance(m, SystemMessage)] == [
            m.id for m in discussion_messages(discussion)[-kept:]
        ], "the tail is kept whole, everything before it replaced"
