"""What a model is told of a JEV qualification: labels and a state, never an instant.

Measured on dev (2026-10-25): an appointment classified at 23:05:59Z, valid until
00:05:59Z, reached the ReAct loop as its raw instants beside a clock reading
« 01:05, Europe/Paris ». The model read 00:05 < 01:05 and told the person the
classification had expired — it was valid for another hour. Whether a label is
still current is decided by the code at the moment it is shown, the way the
collection filters receive a computed comparison and never compare dates.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest

from src.core.classification_projection import (
    classification_text,
    classification_view,
    model_classifications,
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
