"""The person's notes in a ReAct turn: recorded, shown in place, folded at the exit (ADR-385).

The door that opens, reads and closes them is proven on PostgreSQL
(``tests/integration/domains/agents/api/test_turn_notes_door.py``); these tests pin
what the loop does with what it read: where each call shows a note, in which order
beside a recovery pass, and how the turn's request reads once the loop is over.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.domains.agents.api.turn_notes import TakenNote
from src.domains.agents.nodes import react_recovery as rr
from src.domains.agents.nodes import react_turn_notes as notes
from src.domains.agents.nodes.react_shown import with_shown
from src.domains.agents.utils.react_budget import react_turn_reset
from src.infrastructure.llm.message_view import WRITTEN_AT_KEY

pytestmark = pytest.mark.unit

ZONE = "Europe/Paris"
WRITTEN = datetime(2026, 11, 13, 17, 42, tzinfo=UTC)
#: How a model reads 17:42 UTC in Paris (ADR-381's stamp).
STAMP = "[Fri 13 Nov 2026, 18:42]"


def _record(text: str = "only the ones open on Sunday", **overrides: Any) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "text": text,
        "written_at": WRITTEN.isoformat(),
        "anchor_id": "t1",
        "passes_before": 0,
        **overrides,
    }


def _loop() -> list[BaseMessage]:
    return [
        SystemMessage("system"),
        HumanMessage("Find restaurants near the station", id="h1"),
        AIMessage("", id="a1", tool_calls=[{"id": "c1", "name": "places", "args": {}}]),
        ToolMessage("r1", tool_call_id="c1", id="t1"),
        AIMessage("", id="a2", tool_calls=[{"id": "c2", "name": "places", "args": {}}]),
        ToolMessage("r2", tool_call_id="c2", id="t2"),
    ]


def _shown(messages: list[BaseMessage], records: list[dict[str, Any]]) -> list[BaseMessage]:
    return with_shown(messages, notes.notes_shown(records, ZONE))


class TestWhereACallShowsANote:
    def test_a_note_follows_the_message_the_loop_had_when_it_read_it(self) -> None:
        out = _shown(_loop(), [_record()])

        assert [m.id for m in out[:4]] == [None, "h1", "a1", "t1"]
        note = out[4]
        assert isinstance(note, HumanMessage)
        assert [m.id for m in out[5:]] == ["a2", "t2"]

    def test_the_note_reads_when_it_was_written_and_what_it_is(self) -> None:
        note = _shown(_loop(), [_record()])[4]

        text = str(note.content)
        assert text.startswith(f"{STAMP} ")
        assert text.endswith("only the ones open on Sunday")
        # The framing line says it is the person's, added while the loop worked.
        assert "while you were working" in text

    def test_every_call_shows_the_same_bytes(self) -> None:
        records = [_record()]
        assert _shown(_loop(), records)[4].content == _shown(_loop(), records)[4].content

    def test_a_note_with_braces_is_shown_as_written(self) -> None:
        note = _shown(_loop(), [_record("the {table} for {count}")])[4]
        assert str(note.content).endswith("the {table} for {count}")

    def test_two_notes_on_one_place_keep_the_order_they_were_read(self) -> None:
        out = _shown(_loop(), [_record("first"), _record("second")])
        texts = [str(m.content) for m in out if isinstance(m, HumanMessage)][1:]
        assert [text.rsplit(": ", 1)[-1] for text in texts] == ["first", "second"]

    def test_nothing_is_written_to_the_given_list(self) -> None:
        sent = _loop()
        _shown(sent, [_record()])
        assert len(sent) == 6

    def test_a_missing_place_still_shows_the_note(self) -> None:
        out = _shown(_loop(), [_record(anchor_id="gone")])
        assert isinstance(out[-1], HumanMessage)
        assert str(out[-1].content).endswith("only the ones open on Sunday")

    def test_no_note_leaves_the_messages_as_they_are(self) -> None:
        sent = _loop()
        assert _shown(sent, []) == sent


class TestANoteBesideARecoveryPass:
    PASS = {"anchor_id": "t1", "draft": "D1", "unresolved": ["A"]}

    def _out(self, passes_before: int) -> list[str]:
        shown = [
            *rr.recovery_shown([self.PASS]),
            *notes.notes_shown([_record(passes_before=passes_before)], ZONE),
        ]
        out = with_shown(_loop()[:4], shown)
        return [
            (
                "note"
                if isinstance(m, HumanMessage) and "while you were working" in str(m.content)
                else (
                    "directive"
                    if isinstance(m, HumanMessage) and m.id is None
                    else str(m.id or m.content)
                )
            )
            for m in out[3:]
        ]

    def test_a_note_read_before_the_pass_comes_before_its_draft(self) -> None:
        assert self._out(passes_before=0) == ["t1", "note", "D1", "directive"]

    def test_a_note_read_after_the_pass_comes_after_its_directive(self) -> None:
        assert self._out(passes_before=1) == ["t1", "D1", "directive", "note"]

    def test_the_recovery_composition_is_unchanged_without_notes(self) -> None:
        sent = _loop()[:4]
        assert rr.with_recovery_directives(sent, [self.PASS]) == with_shown(
            sent, rr.recovery_shown([self.PASS])
        )


class TestTheExitFoldsTheNotesIntoTheRequest:
    def test_each_note_follows_the_question_with_its_stamp(self) -> None:
        question = HumanMessage("Find restaurants near the station", id="h1")
        folded = notes.fold_notes(question, [_record("only Sunday"), _record("and cheap")], ZONE)

        assert folded is not question and folded.id == "h1"
        text = str(folded.content)
        assert text.startswith("Find restaurants near the station\n\n")
        assert text.count(STAMP) == 2
        assert text.endswith("and cheap")
        assert text.index("only Sunday") < text.index("and cheap")

    def test_the_folded_note_reads_as_the_note_the_loop_was_shown(self) -> None:
        record = _record()
        shown = str(_shown(_loop(), [record])[4].content)
        folded = str(notes.fold_notes(HumanMessage("q", id="h1"), [record], ZONE).content)
        assert folded.endswith(shown)

    def test_folding_twice_changes_nothing(self) -> None:
        question = HumanMessage("q", id="h1")
        once = notes.fold_notes(question, [_record()], ZONE)
        assert notes.fold_notes(once, [_record()], ZONE) is once

    def test_a_question_with_parts_gets_the_notes_as_one_more_part(self) -> None:
        question = HumanMessage(
            [{"type": "text", "text": "What is on this photo?"}, {"type": "image_url"}], id="h1"
        )
        folded = notes.fold_notes(question, [_record()], ZONE)
        assert isinstance(folded.content, list) and len(folded.content) == 3
        last = folded.content[-1]
        assert isinstance(last, dict) and str(last["text"]).endswith("only the ones open on Sunday")
        assert notes.fold_notes(folded, [_record()], ZONE) is folded

    def test_the_keyword_arguments_travel_with_the_question(self) -> None:
        question = HumanMessage(
            "q", id="h1", additional_kwargs={WRITTEN_AT_KEY: WRITTEN.isoformat()}
        )
        folded = notes.fold_notes(question, [_record()], ZONE)
        assert folded.additional_kwargs == question.additional_kwargs

    def test_no_note_no_fold(self) -> None:
        question = HumanMessage("q", id="h1")
        assert notes.fold_notes(question, [], ZONE) is question

    def test_the_response_reads_the_same_completed_request(self) -> None:
        state = {"react_turn_notes": [_record()], "user_timezone": ZONE}
        question = HumanMessage("Find restaurants", id="h1")
        folded = notes.fold_notes(question, state["react_turn_notes"], ZONE)

        assert notes.with_turn_notes("Find restaurants", state) == folded.content
        assert notes.with_turn_notes(str(folded.content), state) == folded.content
        assert notes.with_turn_notes("Find restaurants", {}) == "Find restaurants"


class TestWhatTheLoopRecords:
    async def test_a_note_read_is_recorded_after_the_last_message_with_the_passes_before_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        message_id = uuid4()

        async def read() -> list[TakenNote]:
            return [TakenNote(message_id, "only Sunday", WRITTEN)]

        monkeypatch.setattr(notes, "read_turn_notes", read)
        state = {
            "messages": _loop()[:4],
            "react_recovery_passes": [{"anchor_id": "h1", "draft": "D", "unresolved": []}],
            "react_turn_notes": [_record("earlier")],
        }

        records = await notes.take_turn_notes(state)

        assert [record["text"] for record in records] == ["earlier", "only Sunday"]
        assert records[-1] == {
            "id": str(message_id),
            "text": "only Sunday",
            "written_at": WRITTEN.isoformat(),
            "anchor_id": "t1",
            "passes_before": 1,
        }

    async def test_nothing_read_keeps_the_records(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def read() -> list[TakenNote]:
            return []

        monkeypatch.setattr(notes, "read_turn_notes", read)
        earlier = [_record("earlier")]
        assert await notes.take_turn_notes({"messages": _loop(), "react_turn_notes": earlier}) == (
            earlier
        )


class TestTheLoopsExit:
    async def test_the_exit_closes_the_notes_and_folds_them_into_the_question(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed: list[bool] = []

        async def close() -> None:
            closed.append(True)

        monkeypatch.setattr(notes, "close_turn_notes", close)
        state = {"messages": _loop(), "react_turn_notes": [_record()], "user_timezone": ZONE}

        update = await notes.settle_turn_notes(state)

        assert closed == [True]
        [folded] = update["messages"]
        assert folded.id == "h1"
        assert str(folded.content).endswith("only the ones open on Sunday")

    async def test_an_exit_without_notes_closes_them_and_writes_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed: list[bool] = []

        async def close() -> None:
            closed.append(True)

        monkeypatch.setattr(notes, "close_turn_notes", close)
        assert await notes.settle_turn_notes({"messages": _loop()}) == {}
        assert closed == [True]

    async def test_the_question_is_the_persons_never_a_synthetic_scaffold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.shared.extraction_targets import SYNTHETIC_MESSAGE_KEY

        async def close() -> None:
            return None

        monkeypatch.setattr(notes, "close_turn_notes", close)
        scaffold = HumanMessage(
            "[USER REFUSAL]", id="s1", additional_kwargs={SYNTHETIC_MESSAGE_KEY: True}
        )
        state = {
            "messages": [*_loop(), scaffold],
            "react_turn_notes": [_record()],
            "user_timezone": ZONE,
        }
        [folded] = (await notes.settle_turn_notes(state))["messages"]
        assert folded.id == "h1"


def test_a_turn_starts_with_no_note() -> None:
    assert react_turn_reset()["react_turn_notes"] == []


def test_the_record_keys_are_plain_values_a_checkpoint_keeps() -> None:
    """msgpack: a record is a dict of str and int, nothing to reconstruct."""
    record = notes.note_record(
        TakenNote(UUID(int=1), "words", WRITTEN), anchor_id="t1", passes_before=2
    )
    assert record == {
        "id": str(UUID(int=1)),
        "text": "words",
        "written_at": WRITTEN.isoformat(),
        "anchor_id": "t1",
        "passes_before": 2,
    }
    assert all(isinstance(value, str | int) for value in record.values())
