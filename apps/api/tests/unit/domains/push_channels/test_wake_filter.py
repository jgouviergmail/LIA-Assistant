"""Deterministic wake pre-filter (ADR-261): published rules, bounded reasons."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.domains.push_channels.wake_filter import (
    CalendarWakeRules,
    MailWakeRules,
    any_calendar_passes,
    any_mail_passes,
    calendar_passes,
    calendar_rules_from_settings,
    mail_passes,
    mail_rules_from_settings,
)

pytestmark = pytest.mark.unit

RULES = MailWakeRules(
    require_labels=frozenset({"IMPORTANT"}),
    exclude_labels=frozenset({"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}),
    exclude_list_mail=True,
)
CAL = CalendarWakeRules(lookahead_hours=24, recent_update_minutes=10)
ME = "me@example.com"


def _mail(labels: list[str], headers: dict[str, str] | None = None) -> dict:
    return {
        "labelIds": labels,
        "payload": {"headers": [{"name": k, "value": v} for k, v in (headers or {}).items()]},
    }


@pytest.mark.parametrize(
    ("message", "passes", "reason"),
    [
        (_mail(["INBOX", "IMPORTANT"]), True, "important"),
        (_mail(["INBOX"]), False, "no_required_label"),
        (_mail(["INBOX", "IMPORTANT", "CATEGORY_PROMOTIONS"]), False, "excluded_label"),
        (_mail(["INBOX", "IMPORTANT"], {"List-Unsubscribe": "<mailto:x>"}), False, "list_mail"),
        (_mail(["INBOX", "IMPORTANT"], {"Precedence": "bulk"}), False, "list_mail"),
        ({}, False, "no_required_label"),
    ],
)
def test_mail_verdicts(message: dict, passes: bool, reason: str) -> None:
    verdict = mail_passes(message, RULES)
    assert (verdict.passes, verdict.reason) == (passes, reason)


def test_mail_batch_passes_when_any_message_does() -> None:
    assert any_mail_passes([_mail(["INBOX"]), _mail(["IMPORTANT"])], RULES).passes is True
    assert any_mail_passes([], RULES).reason == "no_message"
    assert any_mail_passes([_mail(["INBOX"])], RULES).reason == "no_required_label"


def test_list_mail_rule_can_be_switched_off_and_labels_are_settings() -> None:
    rules = mail_rules_from_settings(
        SimpleNamespace(
            push_wake_mail_require_labels=["STARRED"],
            push_wake_mail_exclude_labels=[],
            push_wake_mail_exclude_list_mail=False,
        )
    )
    assert mail_passes(_mail(["STARRED"], {"List-Unsubscribe": "x"}), rules).passes is True
    assert mail_passes(_mail(["IMPORTANT"]), rules).reason == "no_required_label"


def _event(**overrides: object) -> dict:
    now = datetime.now(UTC)
    base: dict = {
        "id": "e1",
        "status": "confirmed",
        "updated": (now - timedelta(minutes=2)).isoformat(),
        "start": {"dateTime": (now + timedelta(hours=3)).isoformat()},
        "organizer": {"email": "boss@example.com"},
        "attendees": [{"email": ME, "responseStatus": "accepted"}],
    }
    base.update(overrides)
    return base


def test_calendar_verdicts() -> None:
    now = datetime.now(UTC)
    assert calendar_passes(_event(), user_email=ME, now=now, rules=CAL).reason == "changed_by_other"
    assert (
        calendar_passes(
            _event(attendees=[{"email": ME, "responseStatus": "needsAction"}]),
            user_email=ME,
            now=now,
            rules=CAL,
        ).reason
        == "needs_action"
    )
    assert (
        calendar_passes(_event(organizer={"email": ME}), user_email=ME, now=now, rules=CAL).reason
        == "own_event"
    )
    assert (
        calendar_passes(
            _event(updated=(now - timedelta(hours=2)).isoformat()),
            user_email=ME,
            now=now,
            rules=CAL,
        ).reason
        == "not_recent"
    )
    assert (
        calendar_passes(
            _event(start={"dateTime": (now + timedelta(days=3)).isoformat()}),
            user_email=ME,
            now=now,
            rules=CAL,
        ).reason
        == "outside_lookahead"
    )
    assert (
        calendar_passes(_event(status="cancelled"), user_email=ME, now=now, rules=CAL).reason
        == "cancelled"
    )
    assert calendar_passes({}, user_email=ME, now=now, rules=CAL).reason == "not_recent"


def test_calendar_batch_and_settings() -> None:
    now = datetime.now(UTC)
    assert any_calendar_passes([], user_email=ME, now=now, rules=CAL).reason == "no_event"
    assert (
        any_calendar_passes(
            [_event(status="cancelled"), _event()], user_email=ME, now=now, rules=CAL
        ).passes
        is True
    )
    rules = calendar_rules_from_settings(
        SimpleNamespace(
            push_wake_calendar_lookahead_hours=2, push_wake_calendar_recent_update_minutes=5
        )
    )
    assert rules == CalendarWakeRules(lookahead_hours=2, recent_update_minutes=5)


def test_all_day_event_dates_are_accepted() -> None:
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(hours=20)).date().isoformat()
    verdict = calendar_passes(_event(start={"date": tomorrow}), user_email=ME, now=now, rules=CAL)
    assert verdict.reason in {"changed_by_other", "outside_lookahead"}
