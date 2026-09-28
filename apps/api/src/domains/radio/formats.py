"""What the station can air — every format declared once, with its whole contract.

A format is not a label: it says what it may be made of (the person's records OR
public news, never both — the isolation that keeps an injected article away
from a person's mail), who may speak in it, how long it lasts, how often it may
return and how long a prepared copy stays fresh. The grid, the fact packs, the
writer's brief, the verifier and the settings panel all read THIS table; none
keeps a private copy. The music under a programme follows from it too
(:func:`music_mood`): the player plays it, the segment is voice alone.

Checked at import, both ways (ADR-085): a member with no spec would never air,
a spec with no member would plan something nothing can write.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Final

from src.domains.radio.constants import (
    FLASH_NOTES_MAX,
    JOURNAL_EVENING_FROM_HOUR,
    JOURNAL_NOON_FROM_HOUR,
    MUSIC_MORNING_FROM_HOUR,
    MUSIC_MORNING_UNTIL_HOUR,
    SPEECH_CHARS_PER_MINUTE,
)


class RadioFormat(StrEnum):
    """A kind of programme the station can put on air."""

    #: The station comes on: who is speaking, the time, what is coming.
    OPENING = "opening"
    #: The listener's journal — their own records, in the edition of the moment: the
    #: morning's day ahead and things to note, the noon's done and left, the evening's
    #: look back and week ahead (:func:`journal_edition`, ADR-324 decision 41).
    JOURNAL = "journal"
    #: A handful of headlines, read briskly.
    HEADLINES = "headlines"
    #: The news bulletin: several stories, read by the anchor.
    BULLETIN = "bulletin"
    #: One short story.
    BRIEF = "brief"
    #: One story taken apart by an expert: context, background, stakes, outlook.
    ANALYSIS = "analysis"
    #: One story in depth, with an expert: history, context, facts, analysis, outlook,
    #: an open question.
    DOSSIER = "dossier"
    #: The station's editorial: a view on ONE story, chosen with the listener's taste in
    #: mind (its id is the column's, which it was, so stored settings keep their meaning).
    COLUMN = "column"
    #: A moderator and two or three of the station's commentators with opposed views on
    #: ONE story; the moderator concludes.
    DEBATE = "debate"
    #: Two or three of the station's commentators, keen on the subject, talk ONE story
    #: through.
    DISCUSSION = "discussion"
    #: One figure, and what it means.
    NUMBER = "number"
    #: The station signs off when the automatic stop arrives.
    SIGN_OFF = "sign_off"
    #: The station says the listener heard every story left — once a session (decision 38).
    NOTHING_NEW = "nothing_new"
    #: LIA breaks in to say what she just wrote to the listener in the chat — the
    #: station's own, never the grid's (``flash``).
    FLASH = "flash"


class JournalEdition(StrEnum):
    """Which journal the listener hears, decided by their clock (ADR-324 decision 41)."""

    #: What is planned and to do: the day ahead, and the things to note.
    MORNING = "morning"
    #: What was done this morning, and what is left this afternoon.
    NOON = "noon"
    #: A look back at the day, then tomorrow and the rest of the week.
    EVENING = "evening"


def journal_edition(local: datetime) -> JournalEdition:
    """The journal's edition at ``local`` on the listener's clock.

    Args:
        local: An instant on the listener's clock (the rule reads its hour alone).

    Returns:
        The morning's until ``JOURNAL_NOON_FROM_HOUR``, the noon's until
        ``JOURNAL_EVENING_FROM_HOUR``, the evening's after.
    """
    if local.hour >= JOURNAL_EVENING_FROM_HOUR:
        return JournalEdition.EVENING
    if local.hour >= JOURNAL_NOON_FROM_HOUR:
        return JournalEdition.NOON
    return JournalEdition.MORNING


#: The programmes the journal replaced (ADR-324 decision 41), still READ where they were
#: stored — a live session's slots and failures — never written or offered again.
LEGACY_FORMATS: Final[Mapping[str, RadioFormat]] = {
    "my_day": RadioFormat.JOURNAL,
    "for_you": RadioFormat.JOURNAL,
    "recap": RadioFormat.JOURNAL,
}


def read_format(value: object) -> RadioFormat | None:
    """A stored format, read forgivingly.

    Args:
        value: Whatever was stored.

    Returns:
        The current member it names, the journal for a programme the journal replaced,
        ``None`` for anything else.
    """
    if not isinstance(value, str):
        return None
    try:
        return RadioFormat(value)
    except ValueError:
        return LEGACY_FORMATS.get(value)


class RadioRole(StrEnum):
    """A voice on air. The host is LIA herself — the station's own voice."""

    HOST = "host"
    ANCHOR = "anchor"
    EXPERT = "expert"
    #: The editorialist (the column's voice, which it was).
    COLUMNIST = "columnist"
    #: The station's commentators of a debate or a discussion — voices the station casts
    #: itself, never presented as real people.
    SPEAKER_A = "speaker_a"
    SPEAKER_B = "speaker_b"
    SPEAKER_C = "speaker_c"


#: The roles a listener gives a voice in the settings.
CONFIGURABLE_ROLES: Final[tuple[RadioRole, ...]] = (
    RadioRole.HOST,
    RadioRole.ANCHOR,
    RadioRole.EXPERT,
    RadioRole.COLUMNIST,
)
#: The station's commentators, cast by the station with the engine's other voices.
SPEAKER_ROLES: Final[tuple[RadioRole, ...]] = (
    RadioRole.SPEAKER_A,
    RadioRole.SPEAKER_B,
    RadioRole.SPEAKER_C,
)
#: Who may voice an OPINION line: the editorialist and the commentators, each view theirs.
OPINION_ROLES: Final[frozenset[RadioRole]] = frozenset({RadioRole.COLUMNIST, *SPEAKER_ROLES})


class Material(StrEnum):
    """What a format may be made of. Never two of them in one segment."""

    #: The person's own records — spoken by the host alone.
    PERSONAL = "personal"
    #: Public news — never mixed with a record of the person.
    NEWS = "news"
    #: Nothing beyond the clock and the programme itself.
    NONE = "none"


class Frequency(StrEnum):
    """How often a person wants a format to come back."""

    OFF = "off"
    RARE = "rare"
    NORMAL = "normal"
    OFTEN = "often"


#: Rotation weight of each frequency. ``OFF`` weighs nothing and is filtered
#: before the draw, so a format switched off can never be drawn by accident.
FREQUENCY_WEIGHTS: Final[dict[Frequency, int]] = {
    Frequency.OFF: 0,
    Frequency.RARE: 1,
    Frequency.NORMAL: 3,
    Frequency.OFTEN: 6,
}


class MusicMood(StrEnum):
    """The station music under a programme — the keys of the web player's library."""

    MORNING = "morning"
    NEWS = "news"
    EVENING = "evening"
    CALM = "calm"


@dataclass(frozen=True, slots=True)
class FormatSpec:
    """Everything one format needs to exist.

    Attributes:
        format: The member this spec describes.
        material: What the segment may be made of (``PERSONAL`` formats are
            spoken by the host alone — checked at import).
        roles: Who may speak in the body. The host is always available for the
            transitions in and out, whatever the format.
        target_seconds: How long the segment should last — the writer's brief.
        max_seconds: Beyond this (with ``SCRIPT_LENGTH_TOLERANCE``) the script
            is refused rather than cut.
        min_gap_seconds: The shortest spacing between two airings in a session.
        max_per_session: How many times it may air in one session (``None`` =
            no bound beyond the spacing).
        validity_seconds: How long a prepared, unplayed copy stays fresh.
        default_frequency: What a person who never chose gets.
        user_selectable: Whether the settings panel offers a frequency for it
            (the opening and the sign-off belong to the station, not the menu).
        needs_analysis: Whether the expert analysis runs before the writer.
        min_distinct_voices: Distinct voices the segment cannot do without. One
            voice can read anything, the host included; only a DIALOGUE (the
            anchor questioning the expert) makes no sense in a single voice.
        label_key: The i18n key the settings panel resolves for it.
        spoken_as: How a radio names it, in plain English: the writer says it
            in the listener's language when it hands over (an id such as
            ``brief`` is a word no listener knows, and a model keeps it).
        stories_max: The most stories one segment tells — news stories, or
            the listener's own subjects — enforced by the editor and published
            to the writer from here (``None``: no bound; every news format has
            one).
        renews_subjects: Whether it always brings stories the listener never
            heard (the headlines, the bulletin, a brief, the figure). An ANGLE
            (``False``) may come back to a story heard, from its own angle —
            never the story of the programme just before, never one the same
            programme already took (decision 39).
    """

    format: RadioFormat
    material: Material
    roles: tuple[RadioRole, ...]
    target_seconds: int
    max_seconds: int
    min_gap_seconds: int
    max_per_session: int | None
    validity_seconds: int
    default_frequency: Frequency
    user_selectable: bool
    needs_analysis: bool
    min_distinct_voices: int
    label_key: str
    spoken_as: str
    stories_max: int | None
    renews_subjects: bool

    def target_chars(self, language: str) -> int:
        """The script length that fills ``target_seconds`` in ``language``.

        Args:
            language: Backend-canonical language code (``fr``, ``zh-CN``…).

        Returns:
            Characters of speech; an unknown language gets the French rate.
        """
        rate = SPEECH_CHARS_PER_MINUTE.get(language, SPEECH_CHARS_PER_MINUTE["fr"])
        return round(self.target_seconds * rate / 60)

    def max_chars(self, language: str) -> int:
        """The script length that fills ``max_seconds`` in ``language``."""
        rate = SPEECH_CHARS_PER_MINUTE.get(language, SPEECH_CHARS_PER_MINUTE["fr"])
        return round(self.max_seconds * rate / 60)


def _spec(
    fmt: RadioFormat,
    material: Material,
    roles: tuple[RadioRole, ...],
    *,
    spoken_as: str,
    stories: int | None = None,
    target: int,
    maximum: int,
    gap: int,
    per_session: int | None,
    validity: int,
    frequency: Frequency = Frequency.NORMAL,
    selectable: bool = True,
    analysis: bool = False,
    distinct_voices: int = 1,
    renews: bool = True,
) -> FormatSpec:
    return FormatSpec(
        format=fmt,
        material=material,
        roles=roles,
        target_seconds=target,
        max_seconds=maximum,
        min_gap_seconds=gap,
        max_per_session=per_session,
        validity_seconds=validity,
        default_frequency=frequency,
        user_selectable=selectable,
        needs_analysis=analysis,
        min_distinct_voices=distinct_voices,
        label_key=f"radio.formats.{fmt.value}",
        spoken_as=spoken_as,
        stories_max=stories,
        renews_subjects=renews,
    )


_HOST = (RadioRole.HOST,)
_ANCHOR = (RadioRole.ANCHOR,)

FORMAT_SPECS: Final[dict[RadioFormat, FormatSpec]] = {
    RadioFormat.OPENING: _spec(
        RadioFormat.OPENING,
        Material.NONE,
        _HOST,
        spoken_as="the welcome",
        target=25,
        maximum=50,
        gap=0,
        per_session=1,
        validity=300,
        selectable=False,
    ),
    RadioFormat.JOURNAL: _spec(
        RadioFormat.JOURNAL,
        Material.PERSONAL,
        _HOST,
        spoken_as="the listener's journal",
        target=120,
        maximum=240,
        # Two editions never back to back: a session started minutes before an edition
        # changes waits this long before the next one's journal (decision 41).
        gap=600,
        # Once per EDITION is the grid's rule; a session bound would refuse the second.
        per_session=None,
        validity=1800,
    ),
    RadioFormat.HEADLINES: _spec(
        RadioFormat.HEADLINES,
        Material.NEWS,
        _ANCHOR,
        spoken_as="the headlines",
        stories=5,
        target=50,
        maximum=90,
        gap=900,
        per_session=None,
        validity=1800,
    ),
    RadioFormat.BULLETIN: _spec(
        RadioFormat.BULLETIN,
        Material.NEWS,
        _ANCHOR,
        spoken_as="the news bulletin",
        stories=6,
        target=130,
        maximum=240,
        gap=1800,
        per_session=None,
        validity=3600,
    ),
    RadioFormat.BRIEF: _spec(
        RadioFormat.BRIEF,
        Material.NEWS,
        _ANCHOR,
        spoken_as="a short news item",
        stories=1,
        target=30,
        maximum=60,
        gap=120,
        per_session=None,
        validity=7200,
        frequency=Frequency.OFTEN,
    ),
    RadioFormat.ANALYSIS: _spec(
        RadioFormat.ANALYSIS,
        Material.NEWS,
        (RadioRole.ANCHOR, RadioRole.EXPERT),
        spoken_as="an analysis with an expert",
        stories=1,
        target=270,
        maximum=420,
        gap=1200,
        per_session=None,
        validity=7200,
        analysis=True,
        distinct_voices=2,
        renews=False,
    ),
    RadioFormat.DOSSIER: _spec(
        RadioFormat.DOSSIER,
        Material.NEWS,
        (RadioRole.ANCHOR, RadioRole.EXPERT),
        spoken_as="an in-depth report",
        stories=1,
        # Five minutes: measured on the half-hour simulation, a longer one could not be
        # produced behind three short programmes without the listener waiting.
        target=300,
        maximum=450,
        gap=2400,
        per_session=None,
        validity=7200,
        frequency=Frequency.RARE,
        analysis=True,
        distinct_voices=2,
        renews=False,
    ),
    RadioFormat.COLUMN: _spec(
        RadioFormat.COLUMN,
        Material.NEWS,
        (RadioRole.COLUMNIST,),
        spoken_as="the editorial",
        stories=1,
        target=180,
        maximum=300,
        gap=1200,
        per_session=None,
        validity=7200,
        renews=False,
    ),
    RadioFormat.DEBATE: _spec(
        RadioFormat.DEBATE,
        Material.NEWS,
        (RadioRole.ANCHOR, *SPEAKER_ROLES),
        spoken_as="a debate",
        stories=1,
        target=300,
        maximum=450,
        gap=2400,
        per_session=None,
        validity=7200,
        frequency=Frequency.RARE,
        analysis=True,
        distinct_voices=3,
        renews=False,
    ),
    RadioFormat.DISCUSSION: _spec(
        RadioFormat.DISCUSSION,
        Material.NEWS,
        SPEAKER_ROLES,
        spoken_as="a discussion between enthusiasts",
        stories=1,
        target=240,
        maximum=360,
        gap=2400,
        per_session=None,
        validity=7200,
        frequency=Frequency.RARE,
        distinct_voices=2,
        renews=False,
    ),
    RadioFormat.NUMBER: _spec(
        RadioFormat.NUMBER,
        Material.NEWS,
        _ANCHOR,
        spoken_as="the figure of the day",
        stories=1,
        target=40,
        maximum=70,
        gap=1200,
        per_session=None,
        validity=7200,
        frequency=Frequency.RARE,
    ),
    RadioFormat.SIGN_OFF: _spec(
        RadioFormat.SIGN_OFF,
        Material.NONE,
        _HOST,
        spoken_as="the goodbye",
        target=12,
        maximum=30,
        gap=0,
        per_session=1,
        validity=600,
        selectable=False,
    ),
    # Planned by the grid alone, once, when the desk is exhausted (ADR-324 decision 38).
    RadioFormat.NOTHING_NEW: _spec(
        RadioFormat.NOTHING_NEW,
        Material.NONE,
        _HOST,
        spoken_as="a word that nothing new came in",
        target=15,
        maximum=35,
        gap=0,
        per_session=1,
        validity=600,
        selectable=False,
    ),
    # Planned by nobody: the loop starts one when a notification reaches the chat
    # while the listener hears the antenna (ADR-324 decision 32).
    RadioFormat.FLASH: _spec(
        RadioFormat.FLASH,
        Material.PERSONAL,
        _HOST,
        spoken_as="a news flash",
        stories=FLASH_NOTES_MAX,
        target=25,
        maximum=60,
        gap=0,
        per_session=None,
        validity=600,
        frequency=Frequency.OFF,
        selectable=False,
    ),
}


def selectable_formats() -> tuple[RadioFormat, ...]:
    """The formats a person may tune, in declaration order."""
    return tuple(fmt for fmt, spec in FORMAT_SPECS.items() if spec.user_selectable)


def read_frequencies(raw: object) -> dict[RadioFormat, Frequency]:
    """Stored frequencies, read ENTRY by entry.

    A frequency for a programme with no menu entry now — one the journal replaced, one
    nobody knows, the station's own — or a frequency nobody reads is dropped alone,
    never the listener's other choices with it (ADR-324 decision 41).

    Args:
        raw: Whatever was stored under ``frequencies``.

    Returns:
        The readable entries, keyed by the tunable format each names.
    """
    if not isinstance(raw, Mapping):
        return {}
    kept: dict[RadioFormat, Frequency] = {}
    for name, value in raw.items():
        try:
            fmt, frequency = RadioFormat(str(name)), Frequency(str(value))
        except ValueError:
            continue
        if FORMAT_SPECS[fmt].user_selectable:
            kept[fmt] = frequency
    return kept


def daypart_mood(local: datetime) -> MusicMood:
    """The station's music at ``local`` on the listener's clock, news aside."""
    if MUSIC_MORNING_FROM_HOUR <= local.hour < MUSIC_MORNING_UNTIL_HOUR:
        return MusicMood.MORNING
    if local.hour >= JOURNAL_EVENING_FROM_HOUR:
        return MusicMood.EVENING
    return MusicMood.CALM


def music_mood(fmt: RadioFormat, local: datetime) -> MusicMood:
    """The music the player plays under ``fmt`` airing at ``local``.

    News is read over the news music whatever the hour; everything else follows
    the listener's day.

    Args:
        fmt: The programme.
        local: When it airs, on the listener's clock.

    Returns:
        The mood whose music carries it.
    """
    if FORMAT_SPECS[fmt].material is Material.NEWS:
        return MusicMood.NEWS
    return daypart_mood(local)


def assert_format_registry_complete(specs: Mapping[Any, FormatSpec] | None = None) -> None:
    """Refuse to boot on a format with no spec, a spec with no format, or a lie.

    Args:
        specs: The table to check. Defaults to the shipped one; a caller passes
            its own only to prove the guard fires.

    Raises:
        RuntimeError: Naming what is missing or inconsistent.
    """
    table = FORMAT_SPECS if specs is None else specs
    missing = sorted(fmt.value for fmt in set(RadioFormat) - set(table))
    unknown = sorted(str(getattr(k, "value", k)) for k in set(table) - set(RadioFormat))
    if missing or unknown:
        raise RuntimeError(
            f"Radio format registry incomplete: formats with no spec={missing}, "
            f"specs with no format={unknown}"
        )
    for fmt, spec in table.items():
        _assert_spec_coherent(fmt, spec)


def _stories_incoherent(spec: FormatSpec) -> bool:
    """A news format must bound its stories; a bound is at least one, and material to tell."""
    bound = spec.stories_max
    if bound is None:
        return spec.material is Material.NEWS
    return bound < 1 or spec.material is Material.NONE


#: Every coherence rule of a format spec, and the defect it names — a decision
#: table read in order, so a new rule is one line and one message.
_SPEC_RULES: Final[tuple[tuple[Callable[[FormatSpec], bool], str], ...]] = (
    (lambda spec: not spec.roles, "has nobody to speak"),
    (
        lambda spec: not 0 < spec.target_seconds <= spec.max_seconds,
        "targets more than its own maximum",
    ),
    (lambda spec: spec.validity_seconds <= 0, "is stale the moment it is written"),
    # Only LIA speaks about the person: a fictional guest reading someone's
    # appointments aloud would put a stranger's voice on their life.
    (
        lambda spec: spec.material is Material.PERSONAL and spec.roles != (RadioRole.HOST,),
        "gives the person's records to another voice",
    ),
    (
        lambda spec: not 1 <= spec.min_distinct_voices <= len({RadioRole.HOST, *spec.roles}),
        "demands voices its own roles cannot hold",
    ),
    (
        lambda spec: spec.needs_analysis and spec.material is not Material.NEWS,
        "would analyse something that is not news",
    ),
    (
        lambda spec: not spec.label_key.startswith("radio.formats."),
        "has a label the settings panel cannot resolve",
    ),
    (_stories_incoherent, "bounds its stories incoherently"),
    (
        lambda spec: not spec.renews_subjects and spec.material is not Material.NEWS,
        "comes back to subjects it has none of",
    ),
    (
        lambda spec: spec.renews_subjects and bool(set(spec.roles) & set(SPEAKER_ROLES)),
        "puts a commentator in a programme that only renews its stories",
    ),
)


def _assert_spec_coherent(fmt: Any, spec: FormatSpec) -> None:
    if spec.format is not fmt:
        raise RuntimeError(f"Radio format spec filed under {fmt} declares {spec.format}")
    for broken, defect in _SPEC_RULES:
        if broken(spec):
            raise RuntimeError(f"Radio format {fmt} {defect}")


# The boot carries this: every process that imports the registry checks it.
assert_format_registry_complete()
