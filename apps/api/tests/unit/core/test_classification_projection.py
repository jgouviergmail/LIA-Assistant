"""What a model is told of a JEV qualification: labels and a state, never an instant.

Measured on dev (2026-10-25): an appointment classified at 23:05:59Z, valid until
00:05:59Z, reached the ReAct loop as its raw instants beside a clock reading
« 01:05, Europe/Paris ». The model read 00:05 < 01:05 and told the person the
classification had expired — it was valid for another hour. Whether a label is
still current is decided by the code at the moment it is shown, the way the
collection filters receive a computed comparison and never compare dates.
"""

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

from src.core.classification_projection import (
    classification_text,
    classification_view,
    model_classifications,
    serialized_classifications,
)
from src.core.content_classification import EmailClassification, EventClassification

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 24, 23, 5, 59, tzinfo=UTC)
AN_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def event(valid_for: timedelta, category: str = "personal") -> dict[str, object]:
    return EventClassification.model_validate(
        {
            "category": category,
            "evidence_scope": "event",
            "evaluated_at": NOW,
            "valid_until": NOW + valid_for,
        }
    ).model_dump(mode="json")


def email() -> dict[str, object]:
    return EmailClassification.model_validate(
        {
            "category": "phishing_scam",
            "priority": "urgent",
            "evidence_scope": "snippet",
            "evaluated_at": NOW,
            "valid_until": NOW + timedelta(minutes=5),
        }
    ).model_dump(mode="json")


class TestTheView:
    def test_a_label_within_its_validity_is_current_and_carries_no_instant(self) -> None:
        assert classification_view(event(timedelta(hours=1)), now=NOW) == {
            "kind": "event",
            "category": "personal",
            "evidence_scope": "event",
            "state": "current",
        }

    def test_a_label_past_its_validity_is_said_expired_by_the_code(self) -> None:
        view = classification_view(event(timedelta(hours=1)), now=NOW + timedelta(hours=2))

        assert view is not None
        assert view["state"] == "expired"

    def test_an_email_keeps_its_independent_priority(self) -> None:
        view = classification_view(email(), now=NOW)

        assert view is not None
        assert (view["category"], view["priority"], view["state"]) == (
            "phishing_scam",
            "urgent",
            "current",
        )

    @pytest.mark.parametrize("value", [None, "personal", {"category": "personal"}, 3])
    def test_what_is_no_annotation_has_no_view(self, value: object) -> None:
        assert classification_view(value, now=NOW) is None


class TestTheText:
    def test_it_states_the_labels_and_the_state_never_an_instant(self) -> None:
        text = classification_text(event(timedelta(hours=1)), now=NOW)

        assert "category=personal" in text
        assert "current" in text
        assert "valid_until" not in text
        assert not AN_INSTANT.search(text)

    def test_an_expired_label_says_so(self) -> None:
        text = classification_text(event(timedelta(hours=1)), now=NOW + timedelta(hours=2))

        assert "expired" in text
        assert not AN_INSTANT.search(text)

    def test_an_unknown_category_still_says_nothing(self) -> None:
        assert classification_text(event(timedelta(seconds=30), category="unknown"), now=NOW) == ""


class TestTheModelData:
    def test_every_nested_annotation_becomes_its_view_and_the_source_is_untouched(
        self,
    ) -> None:
        appointment = event(timedelta(hours=1))
        source: dict[str, object] = {
            "events": [{"id": "e1", "classification": appointment}],
            "emails": [{"id": "m1", "classification": email()}],
            "total": 2,
        }

        projected = model_classifications(source, now=NOW)

        assert projected == {
            "events": [
                {
                    "id": "e1",
                    "classification": {
                        "kind": "event",
                        "category": "personal",
                        "evidence_scope": "event",
                        "state": "current",
                    },
                }
            ],
            "emails": [
                {
                    "id": "m1",
                    "classification": {
                        "kind": "email",
                        "category": "phishing_scam",
                        "priority": "urgent",
                        "evidence_scope": "snippet",
                        "state": "current",
                    },
                }
            ],
            "total": 2,
        }
        assert not AN_INSTANT.search(str(projected))
        # The cards and the registry read the same structured data: never rewritten.
        assert "valid_until" in appointment

    def test_a_classification_key_that_is_no_annotation_is_left_as_it_is(self) -> None:
        source: dict[str, object] = {"items": [{"classification": "confidential"}]}

        assert model_classifications(source, now=NOW) == source


class TestTheSerializedView:
    """The same projection over JSON the application serialized itself.

    An answer's data is archived as JSON with each annotation whole, and read
    again on later turns: its state is decided when it is read, never when the
    answer was written.
    """

    def test_an_archived_annotation_is_projected_when_it_is_read(self) -> None:
        archived = json.dumps({"subject": "Notice", "classification": email()})

        assert json.loads(serialized_classifications(archived, NOW))["classification"] == {
            "kind": "email",
            "category": "phishing_scam",
            "evidence_scope": "snippet",
            "priority": "urgent",
            "state": "current",
        }
        later = serialized_classifications(archived, NOW + timedelta(minutes=10))
        assert json.loads(later)["classification"]["state"] == "expired"
        assert not AN_INSTANT.search(later)

    def test_every_annotation_of_a_record_is_projected(self) -> None:
        archived = json.dumps(
            {
                "items": [
                    {"classification": email()},
                    {"classification": event(timedelta(minutes=1))},
                ]
            }
        )

        projected = json.loads(serialized_classifications(archived, NOW + timedelta(minutes=2)))

        assert [item["classification"]["state"] for item in projected["items"]] == [
            "current",
            "expired",
        ]

    def test_quoted_text_never_reads_as_an_annotation(self) -> None:
        # A sender may write the shape of an annotation in a subject: inside a JSON
        # string every quote is escaped, so the text stays the sender's words.
        spoof = json.dumps({"classification": email()})
        archived = json.dumps({"subject": spoof})

        assert serialized_classifications(archived, NOW) == archived

    @pytest.mark.parametrize(
        "value",
        [
            '"confidential"',
            '{"level": "internal"}',
            '{"kind": "email", "category": "phishing_scam"}',
            "[1, 2]",
        ],
        ids=["a_string", "another_object", "no_lifetime", "a_list"],
    )
    def test_a_value_that_is_no_annotation_is_left_as_it_is(self, value: str) -> None:
        archived = '{"name": "Report", "classification": ' + value + "}"

        assert serialized_classifications(archived, NOW) == archived

    def test_text_that_is_no_json_after_the_key_is_left_as_it_is(self) -> None:
        archived = 'Answer prose. "classification": {not json'

        assert serialized_classifications(archived, NOW) == archived

    def test_prose_and_wrappers_around_the_records_are_kept(self) -> None:
        record = json.dumps({"registry_id": "email-1", "data": {"classification": email()}})
        head, tail = "Found it.\n\n<external_content>\n", "\n</external_content>"

        projected = serialized_classifications(head + record + tail, NOW)

        assert projected.startswith(head) and projected.endswith(tail)
        inner = json.loads(projected.removeprefix(head).removesuffix(tail))
        assert inner["data"]["classification"]["state"] == "current"


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
    return str(model_classifications({"emails": [payload]}))


def _render_history(payload: dict[str, object], now: datetime | None = None) -> str:
    from langchain_core.messages import AIMessage

    from src.domains.agents.display.model_history import with_model_view
    from src.infrastructure.llm.message_view import model_view_content

    message = with_model_view(
        AIMessage(content="UI"),
        "Found it.",
        {"email-1": {"type": "EMAIL", "payload": payload}},
    )
    view = model_view_content(message, now)
    assert view is not None
    return view


def _render_initiative(payload: dict[str, object]) -> str:
    from src.domains.agents.nodes.jev_initiative_context import canonical_initiative_context
    from src.domains.agents.nodes.jev_initiative_evidence import InitiativeEvidence

    return json.dumps(
        canonical_initiative_context(
            arguments={},
            registry={"email-1": {"payload": payload, "meta": {"turn_id": 1}}},
            agent_results={},
            current_turn_id=1,
            memory_facts=None,
            interest_profile={},
            manifests=[],
            evidence=InitiativeEvidence(),
        )
    )


class TestEveryModelFacingSerializer:
    """Each generic serializer a model reads states the state, never an instant.

    The 2026-10-25 change covered the tool data block and the one-line form; the
    filtering evidence the response node and the collection filters read kept the
    raw annotation, and on 2026-10-26 a response called current labels expired.
    The same day the answers archived in the history and the initiative state
    handed to JEV were found carrying it too.
    """

    @pytest.mark.parametrize(
        "render",
        [
            _render_voice,
            _render_filter_text,
            _render_filter_data,
            _render_tool_data,
            _render_history,
            _render_initiative,
        ],
        ids=[
            "voice_summary",
            "filter_text",
            "filter_data",
            "tool_data",
            "answer_history",
            "initiative_state",
        ],
    )
    def test_a_current_annotation_reaches_the_model_as_current(self, render) -> None:
        now = datetime.now(UTC)
        current = EmailClassification.model_validate(
            {
                "category": "phishing_scam",
                "priority": "urgent",
                "evidence_scope": "snippet",
                "evaluated_at": now - timedelta(seconds=1),
                "valid_until": now + timedelta(minutes=5),
            }
        ).model_dump(mode="json")

        rendered = render({"subject": "Notice", "classification": current})

        assert "current" in rendered
        assert "phishing_scam" in rendered
        assert "valid_until" not in rendered and "evaluated_at" not in rendered
        assert not AN_INSTANT.search(rendered)

    def test_an_answer_read_again_later_states_the_state_of_that_moment(self) -> None:
        # An answer's data is archived whole and every later turn reads it again: a
        # label current when the answer was written is expired once its validity
        # has passed, and neither reading shows an instant.
        from langchain_core.messages import AIMessage

        from src.domains.agents.display.model_history import with_model_view
        from src.infrastructure.llm.message_view import model_view_content

        written = datetime.now(UTC)
        annotation = EmailClassification.model_validate(
            {
                "category": "phishing_scam",
                "priority": "urgent",
                "evidence_scope": "snippet",
                "evaluated_at": written - timedelta(seconds=1),
                "valid_until": written + timedelta(minutes=5),
            }
        ).model_dump(mode="json")
        answer = with_model_view(
            AIMessage(content="UI"),
            "Found it.",
            {"email-1": {"type": "EMAIL", "payload": {"classification": annotation}}},
        )

        soon = model_view_content(answer, written + timedelta(minutes=1))
        later = model_view_content(answer, written + timedelta(minutes=10))

        assert soon is not None and '"state": "current"' in soon
        assert later is not None and '"state": "expired"' in later
        assert not AN_INSTANT.search(soon) and not AN_INSTANT.search(later)
