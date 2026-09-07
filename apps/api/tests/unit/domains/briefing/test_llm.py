"""Unit tests for briefing/llm.py — prompt rendering and LLM payload shape.

Focused on the pure helpers and on the contract between the cards bundle and
what gets injected into the LLM prompt; the actual LLM call is mocked.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.llm import _summarize_cards_for_llm, generate_synthesis
from src.domains.briefing.schemas import (
    CardsBundle,
    CardSection,
    CardStatus,
    ForecastAlert,
    ForecastAlertKind,
    MailsData,
    ReminderItem,
    RemindersData,
    WeatherData,
)

PARIS = ZoneInfo("Europe/Paris")


def _empty_section() -> CardSection:
    return CardSection(status=CardStatus.NOT_CONFIGURED, generated_at=datetime.now(UTC))


def _weather_section(*, alert: ForecastAlert | None = None) -> CardSection:
    return CardSection(
        status=CardStatus.OK,
        generated_at=datetime.now(UTC),
        data=WeatherData(
            temperature_c=18.0,
            condition_code="Clear",
            description="ensoleillé",
            icon_emoji="☀️",
            forecast_alert=alert,
            daily_forecast=[],
        ),
    )


def _bundle_with_weather(weather_section: CardSection) -> CardsBundle:
    return CardsBundle(
        weather=weather_section,
        agenda=_empty_section(),
        mails=_empty_section(),
        birthdays=_empty_section(),
        reminders=_empty_section(),
        health=_empty_section(),
        for_you=_empty_section(),
        tasks=_empty_section(),
        documents=_empty_section(),
    )


# =============================================================================
# _summarize_cards_for_llm — forecast_alert pivot encoding
# =============================================================================


@pytest.mark.unit
class TestSummarizeForecastAlertPivot:
    def test_emits_kind_at_time_pivot_when_alert_present(self) -> None:
        bundle = _bundle_with_weather(
            _weather_section(alert=ForecastAlert(kind=ForecastAlertKind.RAIN, time="23:00"))
        )
        out = json.loads(_summarize_cards_for_llm(bundle, verbose=True))
        assert out["weather"]["forecast_alert"] == "rain@23:00"

    def test_emits_none_when_no_alert(self) -> None:
        bundle = _bundle_with_weather(_weather_section(alert=None))
        out = json.loads(_summarize_cards_for_llm(bundle, verbose=True))
        assert out["weather"]["forecast_alert"] is None

    def test_supports_other_alert_kinds(self) -> None:
        for kind, expected in [
            (ForecastAlertKind.THUNDERSTORM, "thunderstorm@15:30"),
            (ForecastAlertKind.SNOW, "snow@06:00"),
            (ForecastAlertKind.DRIZZLE, "drizzle@08:15"),
        ]:
            bundle = _bundle_with_weather(
                _weather_section(alert=ForecastAlert(kind=kind, time=expected.split("@")[1]))
            )
            out = json.loads(_summarize_cards_for_llm(bundle, verbose=True))
            assert out["weather"]["forecast_alert"] == expected


# =============================================================================
# Prompt rendering — today_iso anchor injection
# =============================================================================


@pytest.mark.unit
class TestPromptTodayIsoInjection:
    @pytest.mark.asyncio
    async def test_synthesis_prompt_receives_today_iso(self) -> None:
        # Need at least BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA OK sections so
        # the early return is not triggered.
        empty_mails = CardSection(
            status=CardStatus.OK,
            generated_at=datetime.now(UTC),
            data=MailsData(items=[], total_unread_today=0),
        )
        bundle = CardsBundle(
            weather=_weather_section(),
            agenda=_empty_section(),
            mails=empty_mails,
            birthdays=_empty_section(),
            reminders=_empty_section(),
            health=_empty_section(),
            for_you=_empty_section(),
            tasks=_empty_section(),
            documents=_empty_section(),
        )
        captured: dict[str, str] = {}

        async def fake_invoke_and_track(*, rendered: str, **_: object) -> tuple[str, None]:
            captured["rendered"] = rendered
            return ("Belle journée.", None)

        user = type(
            "U",
            (),
            {
                "id": "00000000-0000-0000-0000-000000000000",
                "full_name": "Jean",
                "email": "jean@example.com",
            },
        )()

        with (
            patch("src.domains.briefing.llm._invoke_and_track", side_effect=fake_invoke_and_track),
            patch(
                "src.domains.briefing.llm._resolve_personality",
                new=AsyncMock(return_value=""),
            ),
        ):
            await generate_synthesis(user=user, user_tz=PARIS, cards=bundle, language="fr")

        rendered = captured.get("rendered", "")
        today_iso = datetime.now(PARIS).date().isoformat()
        assert today_iso in rendered, "Synthesis prompt must include today's ISO date as anchor"


# =============================================================================
# Reminders reach the SYNTHESIS, and never the greeting as a bare count
# =============================================================================


def _reminders_bundle() -> CardsBundle:
    """A dashboard whose reminders span two different days."""
    return CardsBundle(
        weather=_empty_section(),
        agenda=_empty_section(),
        mails=_empty_section(),
        birthdays=_empty_section(),
        reminders=CardSection(
            status=CardStatus.OK,
            generated_at=datetime.now(UTC),
            data=RemindersData(
                items=[
                    ReminderItem(content="Appeler Ana", trigger_at_local="aujourd'hui 18:00"),
                    ReminderItem(content="Payer la facture", trigger_at_local="demain 09:00"),
                ]
            ),
        ),
        health=_empty_section(),
        for_you=_empty_section(),
        tasks=_empty_section(),
        documents=_empty_section(),
    )


@pytest.mark.unit
class TestRemindersInThePrompt:
    """``briefing_synthesis_prompt.txt`` documents a ``reminders`` key and has
    done so all along; until the section became cacheable, no ordinary page
    load could deliver it. These pin what it now delivers — and what the
    greeting must still NOT be given."""

    def test_the_synthesis_receives_each_reminder_with_its_own_day(self) -> None:
        summary = json.loads(_summarize_cards_for_llm(_reminders_bundle(), verbose=True))
        assert summary["reminders"] == [
            {"content": "Appeler Ana", "trigger": "aujourd'hui 18:00"},
            {"content": "Payer la facture", "trigger": "demain 09:00"},
        ]

    def test_the_greeting_is_given_no_reminder_count(self) -> None:
        """A BARE count carries no day, and the agenda rule in this very file
        records what that produced: "deux rendez-vous cet après-midi" for
        events spread over two days. A reminder also fires on its own, so a
        fifteen-word greeting has better things to spend its single hint on."""
        summary = json.loads(_summarize_cards_for_llm(_reminders_bundle(), verbose=False))
        assert "reminders_count" not in summary
        assert "reminders" not in summary

    def test_an_empty_reminders_card_adds_nothing(self) -> None:
        bundle = _reminders_bundle()
        empty = bundle.model_copy(update={"reminders": _empty_section()})
        assert "reminders" not in json.loads(_summarize_cards_for_llm(empty, verbose=True))

    def test_the_synthesis_quotes_at_most_three(self) -> None:
        """Same cap as agenda, mails and documents — the prompt gets a hint,
        never a dump."""
        many = RemindersData(
            items=[
                ReminderItem(content=f"R{i}", trigger_at_local=f"demain 0{i}:00") for i in range(5)
            ]
        )
        bundle = _reminders_bundle()
        packed = bundle.model_copy(
            update={
                "reminders": CardSection(
                    status=CardStatus.OK, generated_at=datetime.now(UTC), data=many
                )
            }
        )
        summary = json.loads(_summarize_cards_for_llm(packed, verbose=True))
        assert len(summary["reminders"]) == 3
