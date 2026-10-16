"""Who speaks: one voice per role, from the voice engine the radio is configured on.

The person may choose a voice for every role — the station's team and its
commentators (2026-10-16: the commentators were the station's alone, so a debate or
a discussion was heard in voices nobody had chosen). The choice is STORED as a voice
id and read FORGIVINGLY here, because the engine behind the radio's voice slot is
an administrator's setting that can change after the choice was made: an id the
current catalogue does not hold is dropped and the role falls back to a default,
never to an error (writes are strict, reads are forgiving).

Every voice the person chose is placed first, so no default ever takes one of them.
The defaults give every role of the team its own voice when the catalogue allows it
and alternate genders along the roles, so a two-voice format (the analysis: anchor
and expert) is heard as a dialogue. A COMMENTATOR (a debate's, a discussion's) left
automatic takes the voices nobody else speaks with first, then the expert's and
the editorialist's (who never speak in their programmes), then the moderator's
(heard in a discussion, where the moderator does not speak), and a commentator left
with LIA's voice or another speaker's of the same programme stays silent
(:meth:`Cast.voiced_roles`) — LIA never argues a view, and two opposed views are
never heard in one voice. The voices a commentator may not share are DERIVED from
the programmes (:data:`VOICES_APART`), so what a write refuses (:func:`shared_voice`)
is exactly what the cast would silence. How many DISTINCT voices a programme's roles
are left with is what the grid reads to allow or refuse it — a cast never schedules
a conversation it cannot perform.

An engine whose voices each speak one language (the family says so) is cast
among the voices of the listener's language; when it has none, among all of
them, because a voice with an accent beats no programme. An engine whose
voices speak every language offers them all, those native to the listener's
language first: speaking a language is not speaking it without an accent. A stored choice
outside the voices usable for the listener's language falls back too: the
settings only ever offer usable ones, so such a choice means the language
changed since it was made.

Pure: the catalogue is an input (a live list for an account-scoped engine).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from src.domains.radio.formats import FORMAT_SPECS, SPEAKER_ROLES, STAFF_ROLES, RadioRole
from src.domains.voice.engine_voices import usable_voices
from src.domains.voice.voices_catalog import VoiceOption

#: The roles whose voices a commentator may borrow: they never speak in a debate or
#: a discussion.
_LENDERS: tuple[RadioRole, ...] = (RadioRole.EXPERT, RadioRole.COLUMNIST)


def _voices_apart() -> Mapping[RadioRole, frozenset[RadioRole]]:
    """For each role, the roles whose voice it may not share.

    A commentator is silenced when its voice is LIA's (the host frames every
    programme) or another role's of a programme it speaks in
    (:meth:`Cast.voiced_roles`): the relation is read from the programmes
    themselves, both ways.
    """
    apart: dict[RadioRole, set[RadioRole]] = {role: set() for role in RadioRole}
    for spec in FORMAT_SPECS.values():
        for speaker in set(spec.roles) & set(SPEAKER_ROLES):
            for other in {RadioRole.HOST, *spec.roles} - {speaker}:
                apart[speaker].add(other)
                apart[other].add(speaker)
    return MappingProxyType({role: frozenset(others) for role, others in apart.items()})


#: For each role, the roles whose voice it may not share — what the settings publish,
#: the write refuses (:func:`shared_voice`) and the cast would silence.
VOICES_APART: Final[Mapping[RadioRole, frozenset[RadioRole]]] = _voices_apart()


def shared_voice(voices: Mapping[RadioRole, str]) -> bool:
    """Whether two roles that may not share a voice were given the same one.

    Args:
        voices: The voice chosen for each role (a role left out is automatic).

    Returns:
        Whether one commentator would sound like LIA, the moderator or another
        commentator — the voice the cast would silence.
    """
    return any(
        voices.get(other) == voice for role, voice in voices.items() for other in VOICES_APART[role]
    )


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
        chosen: The person's stored choice per role, the commentators' included
            (read forgivingly: a voice the catalogue does not hold is automatic).
        language: The listener's language (backend-canonical code).
        multilingual: Whether the engine's voices speak every language.

    Returns:
        The cast, or ``None`` when the catalogue holds no voice at all.
    """
    usable = usable_voices(catalogue, language, multilingual)
    if not usable:
        return None
    by_id = {voice.voice_id: voice for voice in usable}
    # Every voice the person chose is placed first: no default takes one of them.
    fixed = {role: by_id[voice] for role, voice in chosen.items() if voice in by_id}
    voices: dict[RadioRole, str] = {}
    taken = {voice.voice_id for voice in fixed.values()}
    previous_gender: str | None = None
    for role in STAFF_ROLES:
        voice = fixed.get(role) or _default_voice(usable, taken, previous_gender)
        voices[role] = voice.voice_id
        taken.add(voice.voice_id)
        previous_gender = voice.gender
    voices.update({role: fixed[role].voice_id for role in SPEAKER_ROLES if role in fixed})
    speakers = {voices[role] for role in SPEAKER_ROLES if role in voices}
    for role in SPEAKER_ROLES:
        voice = fixed.get(role) or _speaker_voice(usable, voices, speakers, previous_gender)
        voices[role] = voice.voice_id
        speakers.add(voice.voice_id)
        previous_gender = voice.gender
    return Cast(voices=voices)


__all__ = ["VOICES_APART", "Cast", "cast_voices", "shared_voice"]
