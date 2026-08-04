"""What a finished call hands back to the reader, and what it must not decide.

The post-call synthesis already extracted the facts a human would act on — a
date and a place the callee PROPOSED, a surcharge they mentioned, an option
they left open. All of it was persisted (``structured_data``, D-8) and none of
it was ever exposed: the calls surface showed a prose recap and the T01 lists,
so a proposed price increase existed in the database and nowhere the person
paying it could see it.

Publishing it is what makes the debrief actionable — and the rule that comes
with it is that publishing is ALL the backend does. Nothing here is accepted,
booked or ordered; the interface turns each field into a draft the user sends
themselves.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.telephony.schemas import TelephonyCallSummary

pytestmark = pytest.mark.unit


def _call(structured: dict[str, object] | None) -> PhoneCall:
    call = PhoneCall(
        user_id=uuid.uuid4(),
        callee_display="Le Jardin",
        objective="Réserver une table mardi",
        status=PhoneCallStatus.COMPLETED.value,
        structured_data=structured or {},
    )
    call.id = uuid.uuid4()
    call.created_at = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
    call.summary = "La table est disponible."
    call.debrief = None
    call.completed_at = None
    call.call_seconds = 42.0
    call.outcome = None
    return call


class TestTheDecisionsReachTheReader:
    def test_a_proposed_date_and_place_are_published(self) -> None:
        """They are what a meeting draft is built from — subject, when, where."""
        summary = TelephonyCallSummary.model_validate(
            _call({"proposed_datetime": "2026-08-05T19:00:00", "location": "Le Jardin, terrasse"})
        )

        assert summary.structured_data is not None
        assert summary.structured_data.proposed_datetime == "2026-08-05T19:00:00"
        assert summary.structured_data.location == "Le Jardin, terrasse"

    def test_a_cost_mentioned_on_the_call_is_published(self) -> None:
        """A surcharge nobody can see is a surcharge nobody can refuse."""
        summary = TelephonyCallSummary.model_validate(
            _call({"additional_costs": "supplément terrasse +3 €"})
        )

        assert summary.structured_data is not None
        assert summary.structured_data.additional_costs == "supplément terrasse +3 €"

    def test_a_deferred_decision_is_published_as_such(self) -> None:
        """The assistant flagged it precisely BECAUSE it did not accept it."""
        summary = TelephonyCallSummary.model_validate(
            _call({"pending_user_decision": "menu enfant ou demi-portion ?"})
        )

        assert summary.structured_data is not None
        assert summary.structured_data.pending_user_decision == "menu enfant ou demi-portion ?"

    def test_an_empty_extraction_publishes_nothing_rather_than_blanks(self) -> None:
        """A call that yielded no structured fact says so by absence."""
        summary = TelephonyCallSummary.model_validate(_call(None))

        assert summary.structured_data is not None
        assert summary.structured_data.proposed_datetime is None
        assert summary.structured_data.additional_costs is None
        assert summary.structured_data.agreed is None

    def test_the_phone_number_never_travels_with_it(self) -> None:
        """The surface exposes the display name, never the encrypted number."""
        summary = TelephonyCallSummary.model_validate(_call({"agreed": True}))

        assert not hasattr(summary, "callee_phone")
        assert summary.callee_display == "Le Jardin"

    def test_unknown_extraction_keys_are_ignored_rather_than_leaked(self) -> None:
        """The vendor payload may grow; the published contract does not.

        `StructuredCallData` is `extra="ignore"`, so a richer transcript never
        breaks ingestion — and never smuggles an unreviewed field into the UI.
        """
        summary = TelephonyCallSummary.model_validate(
            _call({"agreed": True, "raw_transcript": "…tout ce qui a été dit…"})
        )

        assert summary.structured_data is not None
        assert not hasattr(summary.structured_data, "raw_transcript")
        assert summary.structured_data.agreed is True
