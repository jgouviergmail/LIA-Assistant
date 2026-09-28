"""Who speaks: one voice per role, from the voice engine the radio is configured on.

The person may choose a voice per role; the choice is STORED as a voice id and
read FORGIVINGLY here, because the engine behind the radio's voice slot is an
administrator's setting that can change after the choice was made: an id the
current catalogue does not hold is dropped and the role falls back to a default,
never to an error (writes are strict, reads are forgiving).

The defaults give every role its own voice when the catalogue allows it and
alternate genders along the roles, so a two-voice format (the analysis: anchor
and expert) is heard as a dialogue. The station's COMMENTATORS (a debate's, a
discussion's) are never the listener's choice: they take the voices nobody else
speaks with first, then the expert's and the editorialist's (who never speak in
their programmes), then the moderator's (heard in a discussion, where the moderator
does not speak), and a commentator left with LIA's voice or another speaker's of the
same programme stays silent (:meth:`Cast.voiced_roles`) — LIA never argues a view,
and two opposed views are never heard in one voice. How many DISTINCT
voices a programme's roles are left with is what the grid reads to allow or
refuse it — a cast never schedules a conversation it cannot perform.

An engine whose voices each speak one language (the family says so) is cast
among the voices of the listener's language; when it has none, among all of
them, because a voice with an accent beats no programme. A stored choice
outside the voices usable for the listener's language falls back too: the
settings only ever offer usable ones, so such a choice means the language
changed since it was made.

Pure: the catalogue is an input (a live list for an account-scoped engine).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.core.i18n_types import canonical_language
from src.domains.radio.formats import CONFIGURABLE_ROLES, SPEAKER_ROLES, RadioRole
from src.domains.voice.voices_catalog import VoiceOption

#: The order roles are cast in: the host first (the station's voice), then the
#: news roles in the order a dialogue needs them, then the station's commentators.
CAST_ORDER: tuple[RadioRole, ...] = (*CONFIGURABLE_ROLES, *SPEAKER_ROLES)
#: The roles whose voices a commentator may borrow: they never speak in a debate or
#: a discussion.
_LENDERS: tuple[RadioRole, ...] = (RadioRole.EXPERT, RadioRole.COLUMNIST)


@dataclass(frozen=True, slots=True)
class Cast:
    """The voice of every role.

    Attributes:
        voices: The voice id each role speaks with.
    """

    voices: Mapping[RadioRole, str]

    def voiced_roles(self, roles: Sequence[RadioRole]) -> tuple[RadioRole, ...]:
        """The roles of a programme that speak — a commentator only with a voice of its own.

        A commentator whose voice LIA speaks with (the host frames every programme) or
        another role of the programme already has is left out; so is a role the cast
        holds no voice for (a cast stored before the commentators). Every other role
        speaks: its dialogue is the grid's to judge (:meth:`distinct_voices_of`).
        """
        host = self.voices.get(RadioRole.HOST)
        taken: set[str] = {host} if host is not None else set()
        voiced: list[RadioRole] = []
        for role in roles:
            voice = self.voices.get(role)
            if voice is None or (role in SPEAKER_ROLES and voice in taken):
                continue
            voiced.append(role)
            taken.add(voice)
        return tuple(voiced)

    def distinct_voices_of(self, roles: Sequence[RadioRole]) -> int:
        """How many different voices a programme's speaking roles are heard with."""
        return len({self.voices[role] for role in self.voiced_roles(roles)})


def usable_voices(
    catalogue: Sequence[VoiceOption], language: str, multilingual: bool
) -> list[VoiceOption]:
    """The voices a listener may be cast from — what the settings offer, and accept.

    Args:
        catalogue: The engine's voices.
        language: The listener's language.
        multilingual: Whether every voice of the engine speaks every language.

    Returns:
        Every voice for a multilingual engine; else those of the listener's
        language, or all of them when it has none (an accent beats no programme).
    """
    if multilingual:
        return list(catalogue)
    # Both sides through the one locale door: the catalogue says « zh », the
    # listener « zh-CN », and only the canonical forms compare. A code the
    # product does not support names nothing (None) rather than the default
    # language, so a voice of another language never passes for the listener's.
    wanted = canonical_language(language)
    matching = [
        voice
        for voice in catalogue
        if wanted is not None and canonical_language(voice.language) == wanted
    ]
    return matching or list(catalogue)


def _default_voice(
    usable: Sequence[VoiceOption], taken: set[str], previous_gender: str | None
) -> VoiceOption:
    fresh = [voice for voice in usable if voice.voice_id not in taken] or list(usable)
    contrasting = [
        voice for voice in fresh if previous_gender is None or voice.gender != previous_gender
    ]
    return (contrasting or fresh)[0]


def _speaker_voice(
    usable: Sequence[VoiceOption],
    voices: Mapping[RadioRole, str],
    speakers: set[str],
    previous_gender: str | None,
) -> VoiceOption:
    """A commentator's voice: one nobody speaks with, else one lent by a role that never
    speaks in its programmes, else one no other commentator has — the moderator's before
    LIA's, which never speaks a view (:meth:`Cast.voiced_roles`) where the moderator's is
    heard in a discussion —, else any."""
    tiers = _speaker_tiers(usable, voices, speakers)
    tier = next(tier for tier in tiers if tier)
    contrasting = [
        voice for voice in tier if previous_gender is None or voice.gender != previous_gender
    ]
    return (contrasting or tier)[0]


def _speaker_tiers(
    usable: Sequence[VoiceOption], voices: Mapping[RadioRole, str], speakers: set[str]
) -> tuple[list[VoiceOption], ...]:
    """Rank unused, lent and reused voices before the gender preference applies."""
    host = voices.get(RadioRole.HOST)
    kept = {voices[role] for role in (RadioRole.HOST, RadioRole.ANCHOR) if role in voices}
    lent = {voices[role] for role in _LENDERS if role in voices} - kept - speakers
    return (
        [voice for voice in usable if voice.voice_id not in set(voices.values())],
        [voice for voice in usable if voice.voice_id in lent],
        [voice for voice in usable if voice.voice_id not in speakers | {host}],
        [voice for voice in usable if voice.voice_id not in speakers],
        list(usable),
    )


def cast_voices(
    catalogue: Sequence[VoiceOption],
    chosen: Mapping[RadioRole, str],
    *,
    language: str,
    multilingual: bool,
) -> Cast | None:
    """Give every role a voice.

    Args:
        catalogue: The voices of the engine the radio speaks with, in the
            catalogue's order (the defaults follow it, so they are stable).
        chosen: The person's stored choice per role (read forgivingly; the
            commentators are never theirs to choose).
        language: The listener's language (backend-canonical code).
        multilingual: Whether the engine's voices speak every language.

    Returns:
        The cast, or ``None`` when the catalogue holds no voice at all.
    """
    usable = usable_voices(catalogue, language, multilingual)
    if not usable:
        return None
    by_id = {voice.voice_id: voice for voice in usable}
    voices: dict[RadioRole, str] = {}
    taken: set[str] = set()
    previous_gender: str | None = None
    for role in CONFIGURABLE_ROLES:
        voice = by_id.get(chosen.get(role, "")) or _default_voice(usable, taken, previous_gender)
        voices[role] = voice.voice_id
        taken.add(voice.voice_id)
        previous_gender = voice.gender
    speakers: set[str] = set()
    for role in SPEAKER_ROLES:
        voice = _speaker_voice(usable, voices, speakers, previous_gender)
        voices[role] = voice.voice_id
        speakers.add(voice.voice_id)
        previous_gender = voice.gender
    return Cast(voices=voices)


def engine_key(provider: str, model: str) -> str:
    """The voice engine a listener's voices are kept for: the radio voice slot's provider and model.

    A provider switched for another, or a model for another, is another engine; switched
    back, it finds the voices chosen on it.
    """
    return f"{provider}/{model}"


__all__ = ["CAST_ORDER", "Cast", "cast_voices", "engine_key", "usable_voices"]
