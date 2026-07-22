"""Tests for the post-call appointment suggestion (P14, interdomain Lot 1).

``StructuredCallData`` already extracts ``agreed`` / ``proposed_datetime`` /
``location`` — but they died as free text. The deterministic suggestion line
turns them into an actionable next step the user can confirm in chat (the
next turn flows through the normal pipeline with full context).
"""

from unittest.mock import patch

import pytest

from src.core.i18n_telephony import RETURN_PHRASES
from src.domains.telephony.models import PhoneCallStatus
from src.domains.telephony.return_synthesis import build_appointment_suggestion
from src.domains.telephony.schemas import StructuredCallData


def _structured(**kwargs) -> StructuredCallData:
    defaults = {
        "agreed": True,
        "proposed_datetime": "2026-07-25T20:00:00+02:00",
        "location": "Chez Marco",
    }
    defaults.update(kwargs)
    return StructuredCallData(**defaults)


@pytest.mark.unit
class TestBuildAppointmentSuggestion:
    """Deterministic gate: completed + agreed + parseable datetime."""

    def test_suggestion_contains_local_datetime_and_location(self):
        suggestion = build_appointment_suggestion(
            structured=_structured(),
            status=PhoneCallStatus.COMPLETED,
            language="fr",
            user_timezone="Europe/Paris",
        )
        assert suggestion is not None
        assert "2026-07-25 20:00" in suggestion
        assert "Chez Marco" in suggestion

    def test_naive_datetime_is_interpreted_in_user_timezone(self):
        suggestion = build_appointment_suggestion(
            structured=_structured(proposed_datetime="2026-07-25T20:00:00"),
            status=PhoneCallStatus.COMPLETED,
            language="en",
            user_timezone="Europe/Paris",
        )
        assert suggestion is not None
        # Naive → assumed already local: no shift
        assert "2026-07-25 20:00" in suggestion

    def test_aware_datetime_converted_to_user_timezone(self):
        suggestion = build_appointment_suggestion(
            structured=_structured(proposed_datetime="2026-07-25T18:00:00Z"),
            status=PhoneCallStatus.COMPLETED,
            language="en",
            user_timezone="Europe/Paris",
        )
        assert suggestion is not None
        # 18:00 UTC = 20:00 CEST
        assert "2026-07-25 20:00" in suggestion

    def test_none_when_not_agreed(self):
        assert (
            build_appointment_suggestion(
                structured=_structured(agreed=False),
                status=PhoneCallStatus.COMPLETED,
                language="fr",
                user_timezone="Europe/Paris",
            )
            is None
        )

    def test_none_when_no_datetime(self):
        assert (
            build_appointment_suggestion(
                structured=_structured(proposed_datetime=None),
                status=PhoneCallStatus.COMPLETED,
                language="fr",
                user_timezone="Europe/Paris",
            )
            is None
        )

    def test_none_when_datetime_unparseable(self):
        assert (
            build_appointment_suggestion(
                structured=_structured(proposed_datetime="next tuesday-ish"),
                status=PhoneCallStatus.COMPLETED,
                language="fr",
                user_timezone="Europe/Paris",
            )
            is None
        )

    def test_none_when_call_not_completed(self):
        assert (
            build_appointment_suggestion(
                structured=_structured(),
                status=PhoneCallStatus.NO_ANSWER,
                language="fr",
                user_timezone="Europe/Paris",
            )
            is None
        )

    def test_invalid_timezone_falls_back_without_crash(self):
        suggestion = build_appointment_suggestion(
            structured=_structured(proposed_datetime="2026-07-25T20:00:00"),
            status=PhoneCallStatus.COMPLETED,
            language="fr",
            user_timezone="Not/AZone",
        )
        assert suggestion is not None
        assert "2026-07-25 20:00" in suggestion

    def test_without_location_suggestion_still_renders(self):
        suggestion = build_appointment_suggestion(
            structured=_structured(location=None),
            status=PhoneCallStatus.COMPLETED,
            language="fr",
            user_timezone="Europe/Paris",
        )
        assert suggestion is not None
        assert "2026-07-25 20:00" in suggestion


@pytest.mark.unit
class TestAppointmentPhraseParity:
    """The suggestion phrases exist in all 6 supported languages."""

    def test_all_languages_have_appointment_keys(self):
        for lang, phrases in RETURN_PHRASES.items():
            assert "appointment_suggestion" in phrases, f"missing for '{lang}'"
            assert "{datetime_local}" in phrases["appointment_suggestion"], lang
            assert "appointment_location_part" in phrases, f"missing for '{lang}'"
            assert "{location}" in phrases["appointment_location_part"], lang

    def test_every_language_renders_via_helper(self):
        for lang in RETURN_PHRASES:
            suggestion = build_appointment_suggestion(
                structured=_structured(),
                status=PhoneCallStatus.COMPLETED,
                language=lang,
                user_timezone="Europe/Paris",
            )
            assert suggestion is not None
            assert "2026-07-25 20:00" in suggestion


@pytest.mark.unit
class TestSuggestionAppendedToDelivery:
    """The suggestion joins proposal_text before persist + dispatch."""

    def test_compose_delivery_text_appends_suggestion(self):
        from src.domains.telephony.return_synthesis import compose_delivery_text

        text = compose_delivery_text(
            proposal_text="J'ai réservé la table pour samedi soir.",
            structured=_structured(),
            status=PhoneCallStatus.COMPLETED,
            language="fr",
            user_timezone="Europe/Paris",
        )
        assert text.startswith("J'ai réservé la table pour samedi soir.")
        assert "2026-07-25 20:00" in text

    def test_compose_delivery_text_passthrough_when_gate_closed(self):
        from src.domains.telephony.return_synthesis import compose_delivery_text

        text = compose_delivery_text(
            proposal_text="Pas de réponse.",
            structured=_structured(agreed=None, proposed_datetime=None),
            status=PhoneCallStatus.NO_ANSWER,
            language="fr",
            user_timezone="Europe/Paris",
        )
        assert text == "Pas de réponse."

    def test_helper_failure_never_loses_the_proposal(self):
        from src.domains.telephony import return_synthesis

        with patch.object(
            return_synthesis,
            "build_appointment_suggestion",
            side_effect=RuntimeError("boom"),
        ):
            text = return_synthesis.compose_delivery_text(
                proposal_text="Résumé de l'appel.",
                structured=_structured(),
                status=PhoneCallStatus.COMPLETED,
                language="fr",
                user_timezone="Europe/Paris",
            )
        assert text == "Résumé de l'appel."
