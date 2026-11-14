"""Every annotation an item carries reaches a model through ONE projection.

An e-mail carries a JEV qualification and its reply state side by side. Each has a view
decided when it is SHOWN; a second walker for the second annotation would be a second
place to forget one — the 2026-10-26 defect, when one serializer kept the raw
annotation. The tests run every model-facing serializer over both.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from src.core.annotation_projection import (
    annotation_texts,
    annotation_view,
    model_annotations,
    serialized_annotations,
)
from src.core.content_classification import EmailClassification
from src.core.mail_reply_state import ReplyMessage, ReplyState

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def classification(now: datetime = NOW) -> dict[str, object]:
    return EmailClassification.model_validate(
        {
            "category": "professional",
            "priority": "urgent",
            "reply_expected": True,
            "evidence_scope": "snippet",
            "evaluated_at": now,
            "valid_until": now + timedelta(minutes=5),
        }
    ).model_dump(mode="json")


def reply_state(status: str = "answered", now: datetime = NOW) -> dict[str, object]:
    settled = status in {"answered", "answer_drafted", "reply_received"}
    return ReplyState.model_validate(
        {
            "status": status,
            "message": (
                ReplyMessage(
                    message_id="reply-1",
                    at=now - timedelta(minutes=30),
                    correspondents="Marc Dupont",
                    excerpt="Noted for Friday.",
                )
                if settled
                else None
            ),
            "observed_at": now,
            "valid_until": now + timedelta(minutes=2),
        }
    ).model_dump(mode="json")


class TestOneViewPerAnnotation:
    def test_each_key_is_projected_by_its_own_view(self) -> None:
        assert annotation_view("classification", classification(), NOW) == {
            "kind": "email",
            "category": "professional",
            "evidence_scope": "snippet",
            "priority": "urgent",
            "reply_expected": "true",
            "state": "current",
        }
        view = annotation_view("reply_state", reply_state(), NOW)
        assert view is not None and view["status"] == "answered"

    def test_a_key_that_names_no_annotation_has_no_view(self) -> None:
        assert annotation_view("subject", reply_state(), NOW) is None

    def test_a_value_that_is_no_annotation_has_no_view(self) -> None:
        assert annotation_view("reply_state", "answered", NOW) is None
        # One annotation is never read under the other's key.
        assert annotation_view("reply_state", classification(), NOW) is None

    def test_the_lines_a_payload_states_come_in_a_stable_order(self) -> None:
        payload = {"reply_state": reply_state(), "classification": classification()}

        qualification, state = annotation_texts(payload, NOW)

        assert qualification.startswith("JEV qualification")
        assert state.startswith("Reply state: answered")

    def test_an_annotation_that_says_nothing_states_no_line(self) -> None:
        old = reply_state("unanswered")

        assert annotation_texts({"reply_state": old}, NOW + timedelta(hours=1)) == []


class TestTheModelData:
    def test_every_nested_annotation_becomes_its_view_and_the_source_is_untouched(self) -> None:
        state = reply_state()
        source: dict[str, object] = {
            "emails": [{"id": "m1", "classification": classification(), "reply_state": state}],
            "count": 1,
        }

        projected = model_annotations(source, NOW)

        email = projected["emails"][0]  # type: ignore[index]
        assert email["classification"]["state"] == "current"
        assert email["reply_state"]["status"] == "answered"
        assert "observed_at" not in str(projected) and "valid_until" not in str(projected)
        # The cards read the same structured data: never rewritten.
        assert "valid_until" in state

    def test_a_key_holding_something_else_is_left_as_it_is(self) -> None:
        source: dict[str, object] = {"teams": [{"reply_state": "pending", "classification": 3}]}

        assert model_annotations(source, NOW) == source


class TestTheSerializedView:
    """Archived answers are read again on later turns: the state is decided at THAT read."""

    def test_an_answered_message_is_still_answered_when_read_much_later(self) -> None:
        archived = json.dumps({"subject": "Quote", "reply_state": reply_state()})

        later = json.loads(serialized_annotations(archived, NOW + timedelta(days=3)))

        assert later["reply_state"]["status"] == "answered"

    def test_a_no_reply_yet_read_on_an_earlier_turn_is_not_repeated(self) -> None:
        archived = json.dumps({"subject": "Quote", "reply_state": reply_state("unanswered")})

        at_once = json.loads(serialized_annotations(archived, NOW))
        later = json.loads(serialized_annotations(archived, NOW + timedelta(minutes=10)))

        assert at_once["reply_state"] == {"status": "unanswered"}
        assert later["reply_state"] == {"status": "not_checked"}

    def test_both_annotations_of_one_record_are_projected(self) -> None:
        archived = json.dumps(
            {"classification": classification(), "reply_state": reply_state("unanswered")}
        )

        projected = json.loads(serialized_annotations(archived, NOW + timedelta(minutes=10)))

        assert projected["classification"]["state"] == "expired"
        assert projected["reply_state"]["status"] == "not_checked"

    def test_quoted_text_never_reads_as_an_annotation(self) -> None:
        # A sender may write the shape of an annotation in a subject: inside a JSON
        # string every quote is escaped, so the text stays the sender's words.
        spoof = json.dumps({"reply_state": reply_state()})
        archived = json.dumps({"subject": spoof})

        assert serialized_annotations(archived, NOW) == archived

    @pytest.mark.parametrize("value", ['"answered"', '{"status": "answered"}', "[1]", "{not json"])
    def test_a_value_that_is_no_annotation_is_left_as_it_is(self, value: str) -> None:
        archived = '{"name": "Report", "reply_state": ' + value + "}"

        assert serialized_annotations(archived, NOW) == archived

    def test_text_carrying_no_annotation_key_is_returned_as_it_is(self) -> None:
        archived = json.dumps({"subject": "Quote", "labelIds": ["INBOX"]})

        assert serialized_annotations(archived, NOW) is archived


def _render_voice(payload: dict[str, object]) -> str:
    from src.domains.agents.display.llm_serializer import payload_to_text

    return payload_to_text(payload)


def _render_filter_text(payload: dict[str, object]) -> str:
    from src.domains.agents.display.filter_evidence import payload_to_filter_text

    return payload_to_filter_text(payload)


def _render_filter_data(payload: dict[str, object]) -> str:
    from src.domains.agents.display.filter_evidence import project_filter_evidence

    return str(project_filter_evidence(payload).data)


def _render_tool_data(payload: dict[str, object]) -> str:
    from src.domains.agents.tools.react_tool_wrapper import _prepare_model_data, render_data_block

    return render_data_block(_prepare_model_data({"emails": [payload]}, None), 10_000).text


def _render_spoken(payload: dict[str, object]) -> str:
    from src.domains.agents.telephony.voice_projection import compact_items
    from src.domains.agents.tools.react_tool_wrapper import _prepare_model_data

    return str(compact_items(_prepare_model_data({"emails": [payload]}, None)))


def _render_history(payload: dict[str, object]) -> str:
    from langchain_core.messages import AIMessage

    from src.domains.agents.display.model_history import with_model_view
    from src.infrastructure.llm.message_view import model_view_content

    message = with_model_view(
        AIMessage(content="UI"), "Found it.", {"email-1": {"type": "EMAIL", "payload": payload}}
    )
    view = model_view_content(message)
    assert view is not None
    return view


_RENDERERS = [
    _render_voice,
    _render_filter_text,
    _render_filter_data,
    _render_tool_data,
    _render_spoken,
    _render_history,
]
_RENDERER_IDS = [
    "voice_summary",
    "filter_text",
    "filter_data",
    "tool_data",
    "spoken_tool_data",
    "answer_history",
]


class TestEveryModelFacingSerializerStatesTheReplyState:
    @pytest.mark.parametrize("render", _RENDERERS, ids=_RENDERER_IDS)
    def test_an_answered_message_reaches_the_model_as_answered(self, render) -> None:
        now = datetime.now(UTC)

        rendered = render({"subject": "Quote", "reply_state": reply_state("answered", now)})

        assert "answered on" in rendered
        assert "Marc Dupont" in rendered and "Noted for Friday." in rendered
        assert "observed_at" not in rendered and "valid_until" not in rendered
        assert "reply-1" not in rendered  # a provider id is no fact for a model

    @pytest.mark.parametrize("render", _RENDERERS, ids=_RENDERER_IDS)
    def test_an_old_no_reply_yet_never_reaches_the_model_as_a_fact(self, render) -> None:
        read_long_ago = datetime.now(UTC) - timedelta(hours=2)

        rendered = render(
            {"subject": "Quote", "reply_state": reply_state("unanswered", read_long_ago)}
        )

        assert "unanswered" not in rendered
        assert "observed_at" not in rendered and "valid_until" not in rendered
