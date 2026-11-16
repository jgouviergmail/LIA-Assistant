"""What a call a sweep closed owes its owner (2026-11-14): never a silent close."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.core.i18n import SUPPORTED_LANGUAGES
from src.core.i18n_telephony import get_return_phrases
from src.domains.telephony.closing_notices import ClosingReason, closing_notice
from src.domains.telephony.models import CallKind
from src.domains.telephony.repository import ClosedCall

pytestmark = pytest.mark.unit


def _closed(kind: CallKind, *, mode: str = "direct", callee: str = "Garage Martin") -> ClosedCall:
    return ClosedCall(
        id=uuid4(), user_id=uuid4(), callee_display=callee, call_kind=kind, call_mode=mode
    )


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_a_third_party_call_with_no_report_names_its_callee_and_says_the_end_is_unknown(
    language: str,
) -> None:
    notice = closing_notice(
        _closed(CallKind.THIRD_PARTY), ClosingReason.NO_REPORT, language=language
    )
    phrases = get_return_phrases(language)
    assert notice == (
        phrases["no_report"].format(callee="Garage Martin"),
        phrases["title"],
    )
    assert "Garage Martin" in notice[0]


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_an_owner_call_with_no_report_is_told_in_the_second_person(language: str) -> None:
    notice = closing_notice(_closed(CallKind.SELF), ClosingReason.NO_REPORT, language=language)
    phrases = get_return_phrases(language)
    assert notice == (phrases["relay_no_report"], phrases["self_call_title"])


def test_a_synthesis_that_gave_up_says_no_summary_could_be_made() -> None:
    third = closing_notice(
        _closed(CallKind.THIRD_PARTY), ClosingReason.SYNTHESIS_GAVE_UP, language="fr"
    )
    owner = closing_notice(_closed(CallKind.SELF), ClosingReason.SYNTHESIS_GAVE_UP, language="fr")
    phrases = get_return_phrases("fr")
    assert third == (phrases["fallback"], phrases["title"])
    assert owner == (phrases["relay_failed"], phrases["self_call_title"])


@pytest.mark.parametrize("reason", list(ClosingReason))
def test_a_verification_call_owes_no_return(reason: ClosingReason) -> None:
    assert closing_notice(_closed(CallKind.VERIFICATION), reason, language="en") is None


@pytest.mark.parametrize("reason", list(ClosingReason))
def test_a_live_owner_call_owes_no_return(reason: ClosingReason) -> None:
    """Every request of a Live call already reached the chat during the call."""
    live = _closed(CallKind.SELF, mode="delegated")
    assert closing_notice(live, reason, language="en") is None


def test_a_callee_name_with_braces_is_written_as_is() -> None:
    """The name is a value: it never reaches ``str.format`` as a template."""
    notice = closing_notice(
        _closed(CallKind.THIRD_PARTY, callee="Atelier {velo}"),
        ClosingReason.NO_REPORT,
        language="en",
    )
    assert notice is not None
    assert "Atelier {velo}" in notice[0]
