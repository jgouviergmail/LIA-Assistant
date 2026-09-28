"""Wire shapes of the radio (ADR-324).

Mirrored by ``apps/web/src/lib/radio/types.ts`` — a change on one side is a
change on both. What the player is told is only what it shows: a segment's
format, title, duration and transcript, each line with the PUBLIC sources it
rests on (an outlet's name, an article's link and date). A record of the
person's is named by its family alone — its id never leaves the server.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.domains.radio.constants import (
    PLAYHEAD_POSITION_MAX_SECONDS,
    SOURCE_ADDRESS_MAX_CHARS,
    SOURCE_LABEL_MAX_CHARS,
)
from src.domains.radio.formats import Frequency, MusicMood, RadioFormat, RadioRole
from src.domains.radio.names import speakable_name
from src.domains.radio.newsroom.sources import Discovery, DiscoveryOutcome
from src.domains.radio.personal import PersonalSource
from src.domains.radio.setup import VerificationMode

#: Where a session stands, as the player reads it.
RadioSessionStatus = Literal["starting", "on_air", "ending", "ended"]


class RadioStartRequest(BaseModel):
    """What the listener may choose for one session, on top of their settings."""

    model_config = ConfigDict(extra="forbid")

    timer_minutes: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Automatic stop in minutes for this session; 0 means none; absent means the "
            "listener's setting. Past the published maximum it is brought back to it."
        ),
    )
    public_mode: bool | None = Field(
        default=None,
        description="Nothing personal airs (listening in company); absent means the setting.",
    )


class RadioPlayheadRequest(BaseModel):
    """Where the player is — the only thing a report says."""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=1, description="The segment playing, or the next one expected.")
    position_s: float = Field(
        ge=0, le=PLAYHEAD_POSITION_MAX_SECONDS, description="Seconds into that segment."
    )
    playing: bool = Field(
        description="Whether a segment is being heard (False while paused or while the music waits)."
    )
    flash_heard: int = Field(
        default=0,
        ge=0,
        description="The highest news flash the player played to its end (0 for none).",
    )
    paused: bool = Field(
        default=False,
        description="Whether the listener paused — the automatic stop does not run meanwhile.",
    )


class RadioSourceResponse(BaseModel):
    """Where a sentence comes from."""

    label: str = Field(description="An outlet's name, or the family of the person's record.")
    url: str | None = Field(default=None, description="The article, for a public source.")
    published_at: datetime | None = Field(default=None, description="When it was published.")
    article_id: str | None = Field(
        default=None,
        description="The story whose article the page may open (a public source only).",
    )


class RadioTranscriptLineResponse(BaseModel):
    """One spoken line, when it starts, and what it rests on."""

    role: RadioRole = Field(description="Who speaks it.")
    text: str = Field(description="What is said.")
    offset_s: float = Field(description="Seconds into the segment where it starts.")
    sources: list[RadioSourceResponse] = Field(description="What it rests on.")


class RadioSegmentResponse(BaseModel):
    """A segment ready to air."""

    seq: int = Field(description="Its place in the session.")
    format: RadioFormat = Field(description="What kind of programme it is.")
    mood: MusicMood | None = Field(
        description="The station music the player plays under it; null when unknown."
    )
    title: str = Field(description="The programme title shown to the listener.")
    duration_s: float = Field(description="Its duration.")
    transcript: list[RadioTranscriptLineResponse] = Field(description="Its lines, in air order.")


class RadioSessionResponse(BaseModel):
    """The session, as every report is answered."""

    session_id: UUID = Field(description="The session.")
    status: RadioSessionStatus = Field(description="Where it stands.")
    segments: list[RadioSegmentResponse] = Field(
        description="Ready segments the player has not reported as finished, ascending."
    )
    cost_eur: float | None = Field(
        description="What the session has cost so far, every family, in euros; null if unknown."
    )
    stop_at: datetime | None = Field(description="The automatic stop, or null for none.")
    startup_estimate_s: float | None = Field(
        description="Seconds before the first voice, estimated when the session started."
    )
    end_reason: str | None = Field(description="Why it ended, once it has (bounded vocabulary).")
    mood: MusicMood | None = Field(
        description="The station music to play now: that of what airs next; null when unknown."
    )
    station_name: str | None = Field(
        default=None, description="The station's name, as its host says it; null when unknown."
    )
    cost_estimate_eur: float | None = Field(
        default=None,
        description=(
            "What the planned listening (cost_estimate_s) will cost, from what a second of "
            "radio has cost so far; null before enough was produced."
        ),
    )
    flash: RadioSegmentResponse | None = Field(
        default=None,
        description=(
            "A news flash to air NOW, cutting the programme on air and resuming it where it stopped; null when none."
        ),
    )
    cost_estimate_s: float | None = Field(
        default=None,
        description="The listening the estimate covers: the timer's, else an hour.",
    )
    segment_gap_s: float = Field(
        default=0.0,
        description=(
            "Seconds of the station's music between two programmes: the player waits as "
            "long before the next one (a news flash never waits)."
        ),
    )


class RadioFormatOptionResponse(BaseModel):
    """A format the listener may tune."""

    format: RadioFormat = Field(description="The format.")
    default_frequency: Frequency = Field(description="What a listener who never chose gets.")
    label_key: str = Field(description="The i18n key of its name.")
    stories_max: int | None = Field(
        default=None, description="The most stories one programme tells; null when not news."
    )


class RadioArticleResponse(BaseModel):
    """A story's article, as the radio page shows it under the transcript."""

    id: UUID = Field(description="The story.")
    outlet: str = Field(description="Its outlet's name.")
    url: str = Field(description="The article at its outlet.")
    published_at: datetime = Field(description="When it was published.")
    title: str = Field(description="The headline — in the listener's language when translated.")
    text: str = Field(description="The text, one blank line between paragraphs.")
    complete: bool = Field(
        description="Whether the text is the whole article (else the outlet's summary)."
    )
    cut: bool = Field(description="Whether the text stops before the article does.")
    translated: bool = Field(description="Whether the title and the text are a translation.")
    source_language: str | None = Field(description="The feed's language, when it declares one.")
    translation_failed: bool = Field(
        description="A translation was due and could not be made: the original is shown."
    )
    budget_reached: bool = Field(
        description=(
            "A translation was due and the listener's radio spent its rolling day's "
            "budget: the original is shown, and no model was asked."
        )
    )
    cost_eur: float | None = Field(
        description="What this reading cost the listener (0 from the cache; null when unknown)."
    )


class RadioBudgetResponse(BaseModel):
    """What the listener's radio spent over the rolling day (ADR-324 decision 37)."""

    limit_eur: float = Field(description="The bound over the window, in euros (0 = none).")
    spent_eur: float = Field(
        description=(
            "What the listener's radio — its sessions and article translations — spent "
            "over the window, in euros (a run counts whole while its last spend is in it)."
        )
    )
    window_hours: int = Field(description="The rolling window, in hours.")
    lifts_at: datetime | None = Field(
        description=(
            "While the bound is reached, when enough of the spend leaves the window to "
            "play again; null otherwise."
        )
    )


class RadioVoiceOptionResponse(BaseModel):
    """A voice of the engine the radio speaks with."""

    voice_id: str = Field(description="What a preference stores.")
    label: str = Field(description="Its name, as the engine gives it.")
    gender: str | None = Field(default=None, description="male, female, or null when unknown.")
    language: str | None = Field(default=None, description="The language it speaks, when one.")


class RadioOptionsResponse(BaseModel):
    """What the radio's settings may offer — published because it is enforced (ADR-184)."""

    formats: list[RadioFormatOptionResponse] = Field(description="The tunable formats, in order.")
    frequencies: list[Frequency] = Field(description="The frequencies a format may take.")
    sources: list[PersonalSource] = Field(description="The personal sources that may be silenced.")
    verification_modes: list[VerificationMode] = Field(description="The verification modes.")
    verification_default: VerificationMode = Field(
        description="The verification of a listener who never chose (the instance's default)."
    )
    verification_checked: dict[VerificationMode, list[RadioFormat]] = Field(
        description="The formats each mode has a model read (each read is billed)."
    )
    roles: list[RadioRole] = Field(description="The roles a voice may be chosen for.")
    voices: list[RadioVoiceOptionResponse] = Field(description="The engine's voices.")
    voice_id_max_chars: int = Field(description="The longest voice id a preference stores.")
    station_name_max_chars: int = Field(description="The longest name a station may be given.")
    timer_default_minutes: int = Field(
        description="The automatic stop of a listener who never chose."
    )
    timer_max_minutes: int = Field(
        description="The longest automatic stop a setting may hold (a setting of 0 means none)."
    )
    custom_sources_max: int = Field(description="How many sites a listener may add.")
    source_address_max_chars: int = Field(description="The longest site address accepted.")
    source_title_max_chars: int = Field(description="The longest name a site may be given.")
    noon_from_hour: int = Field(
        description="The local hour the journal's noon edition starts (ADR-324 decision 41)."
    )
    evening_from_hour: int = Field(
        description="The local hour the journal's evening edition starts."
    )


class RadioSourceRequest(BaseModel):
    """A site the listener names — to preview, then to add (the server looks again)."""

    model_config = ConfigDict(extra="forbid")

    address: str = Field(
        min_length=1,
        max_length=SOURCE_ADDRESS_MAX_CHARS,
        description="What the listener typed: a site, a page or a feed address.",
    )


class RadioSourcePreviewResponse(BaseModel):
    """What looking for a site's feed found, shown before the site is added."""

    outcome: DiscoveryOutcome = Field(description="How it ended (an error key when not found).")
    feed_url: str | None = Field(default=None, description="The feed found.")
    title: str | None = Field(default=None, description="The feed's own title.")
    language: str | None = Field(default=None, description="The language the feed declares.")
    entries: int | None = Field(default=None, description="How many entries it carries now.")

    @classmethod
    def of(cls, found: Discovery) -> RadioSourcePreviewResponse:
        """The wire shape of a discovery."""
        described = found.description
        return cls(
            outcome=found.outcome,
            feed_url=found.feed_url,
            title=described.title if described else None,
            language=described.language if described else None,
            entries=described.entries if described else None,
        )


class RadioCustomSourceResponse(BaseModel):
    """A site the listener added to their newsroom, and what it holds for them."""

    id: UUID = Field(description="The source.")
    feed_url: str = Field(description="Its feed.")
    title: str = Field(description="Its name (the listener may rename it).")
    language: str | None = Field(default=None, description="The language it declares.")
    paused: bool = Field(default=False, description="Paused: not read, not offered.")
    failing: bool = Field(default=False, description="Its last readings failed (backing off).")
    stories: int = Field(default=0, description="Stories it published within window_hours.")
    unheard: int = Field(default=0, description="Of those, the ones the listener never heard.")


class RadioBaseSourceResponse(BaseModel):
    """A base source (a feed of the shipped catalogue), and what it holds for the listener."""

    url: str = Field(description="Its address — what the settings untick it by.")
    name: str = Field(description="The outlet's name.")
    language: str = Field(description="The language it publishes in (backend code).")
    heard: bool = Field(description="Whether the listener's radio reads it (ticked).")
    failing: bool = Field(description="Its last readings failed (the newsroom backs off).")
    stories: int = Field(description="Stories it published within window_hours (exact).")
    unheard: int = Field(description="Of those, the ones the listener never heard.")


class RadioSourcesResponse(BaseModel):
    """Every source of the listener's newsroom, and what the station can air from them."""

    base: list[RadioBaseSourceResponse] = Field(description="The base sources, in order.")
    own: list[RadioCustomSourceResponse] = Field(description="The listener's own sites.")
    stories: int = Field(
        description="Stories the station can air: those of the ticked and running sources."
    )
    unheard: int = Field(description="Of those, the ones the listener never heard.")
    window_hours: int = Field(description="The window counted: the oldest story a programme airs.")


class RadioSourceUpdateRequest(BaseModel):
    """A change to one of the listener's sites: a new name, a pause, or both."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str | None = Field(default=None, description="Its new name (folded, speakable).")
    paused: bool | None = Field(default=None, description="Paused (true) or running (false).")

    @field_validator("title")
    @classmethod
    def _a_name_a_voice_can_say(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return speakable_name(value, max_chars=SOURCE_LABEL_MAX_CHARS, what="a site's name")

    @model_validator(mode="after")
    def _something_to_change(self) -> RadioSourceUpdateRequest:
        if self.title is None and self.paused is None:
            raise ValueError("a change names a new name, a pause, or both")
        return self


__all__ = [
    "RadioArticleResponse",
    "RadioBaseSourceResponse",
    "RadioBudgetResponse",
    "RadioCustomSourceResponse",
    "RadioFormatOptionResponse",
    "RadioOptionsResponse",
    "RadioPlayheadRequest",
    "RadioSegmentResponse",
    "RadioSessionResponse",
    "RadioSessionStatus",
    "RadioSourcePreviewResponse",
    "RadioSourceRequest",
    "RadioSourceResponse",
    "RadioSourceUpdateRequest",
    "RadioSourcesResponse",
    "RadioStartRequest",
    "RadioTranscriptLineResponse",
    "RadioVoiceOptionResponse",
]
