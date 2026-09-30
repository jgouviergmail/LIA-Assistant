"""The radio's prompts, rendered from what a segment knows.

The writer, the analyst and the verifier each read ONE versioned prompt
(``prompts/v1``), laid out for the cache (ADR-309): what is the same for every
segment of a listener — the station, the language, the personality, the contract
and its bounds — above the dynamic-context marker; the segment's own format,
context and facts below it.
Every bound the verifier enforces is published to the writer here, from the same
constants (ADR-184: what a validator can reject, its producer must be able to
read).

What the context says is decided here, not left to the prompt: the listener's
first name is offered only to a format the host speaks — an anchor told the name
used it on air, measured 2026-09-26 — and what the listener cares about and has
said they like is offered to choose and pitch stories, never as facts to voice.
That taste is the same for the whole session, so it sits ABOVE the marker, in
the prefix the segments share; and only a format that CHOOSES news is shown it —
a host told the listener rides a bike said « the weather decides the bike » in
their own day (measured 2026-09-26), and a writer cannot hint at what it was
never told. The formats shown it are exactly those the default verification
reads (``checked_formats``), whose test refuses anything said about the listener
that no fact states. So a listener's segments share two prefixes, each reused.

Everything a stranger wrote — a feed's headline, an article, an e-mail's subject
in the listener's day — reaches the model inside the shared untrusted-content
wrapper (ADR-167), and every prompt says what it means: data, never
instructions. The verifier reads the script's lines inside it too: a writer
that copied an instruction from an article must not hand it on.

Pure: the template text is an input (the caller loads it).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from src.core.prompt_store import read_prompt_file
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.radio.checking import checked_positions
from src.domains.radio.constants import (
    INTRO_OUTRO_MAX_LINES,
    LINE_MAX_CHARS,
    SCRIPT_TITLE_MAX_CHARS,
    TRANSITION_FREE_INTEGER_MAX,
)
from src.domains.radio.facts import CLOCK_FACT_ID, FactPack, RadioFact, local_time_text
from src.domains.radio.formats import FORMAT_SPECS, Material, RadioFormat, RadioRole
from src.domains.radio.production import WritingRequest
from src.domains.radio.verification import VerifiedLine
from src.domains.shared.portrait_sources import clamp_item

#: The versioned prompt files (their stems, as the loader names them).
WRITER_PROMPT: Final[str] = "radio_writer_prompt"
ANALYST_PROMPT: Final[str] = "radio_analyst_prompt"
VERIFIER_PROMPT: Final[str] = "radio_verifier_prompt"

#: How many of the listener's stated tastes the writer is told at most (the newest first).
STATED_TASTES_SHOWN_MAX: Final[int] = 6
#: The longest stated taste the writer reads (a remembered taste is a sentence, not a page).
STATED_TASTE_MAX_CHARS: Final[int] = 160
#: The headlines of the stories heard a news writer is shown (the most recent).
ON_AIR_SHOWN_MAX: Final[int] = 30
#: A headline shown to the news writer — kept in the ledger at that length too.
HEADLINE_SHOWN_MAX_CHARS: Final[int] = 200


@dataclass(frozen=True, slots=True)
class RadioTemplates:
    """The three versioned prompts a session renders, read once.

    Attributes:
        writer: The ``radio_writer_prompt`` text.
        analyst: The ``radio_analyst_prompt`` text.
        verifier: The ``radio_verifier_prompt`` text.
    """

    writer: str
    analyst: str
    verifier: str


def load_templates() -> RadioTemplates:
    """The radio's prompts from the one store (read by path, cached per process).

    Raises:
        PromptFileError: When a file is missing — a deployment without its
            prompts cannot air, and says so at the first start.
    """
    return RadioTemplates(
        writer=read_prompt_file(WRITER_PROMPT),
        analyst=read_prompt_file(ANALYST_PROMPT),
        verifier=read_prompt_file(VERIFIER_PROMPT),
    )


@dataclass(frozen=True, slots=True)
class StationVoice:
    """What every segment of one listener's session shares.

    Attributes:
        station_name: The station's name in the listener's language.
        language_name: The listener's language, named for a model.
        personality: How the station speaks (the chosen personality's text).
    """

    station_name: str
    language_name: str
    personality: str


@dataclass(frozen=True, slots=True)
class ListenerTaste:
    """What the writer knows of the listener's taste — to choose and pitch, never to state.

    Attributes:
        interests: What they care about, strongest first — as many as the start read
            (``RADIO_INTEREST_TOPICS_MAX``), the ones the search looks up.
        stated: What they said they like or dislike (their remembered
            preferences), newest first.
    """

    interests: tuple[str, ...] = ()
    stated: tuple[str, ...] = ()


def render_fact(fact: RadioFact) -> str:
    """One fact as the writer reads it: id, kind, who may say it, whether the listener
    heard its story before (an angle comes back to it, decision 39), source, text."""
    source = f" — {fact.source.label}" if fact.source is not None else ""
    heard = ", heard before" if fact.returning else ""
    return f"[{fact.id}] ({fact.kind.value}, {fact.sensitivity.value}{heard}{source}) {fact.text}"


def _context(request: WritingRequest) -> str:
    spec = FORMAT_SPECS[request.format]
    lines = [f"- local date and time: {local_time_text(request.local_now)}"]
    if any(fact.id == CLOCK_FACT_ID for fact in request.pack.facts):
        lines[0] += f" (cite [{CLOCK_FACT_ID}] to say it)"
    lines.append(f"- before: {_spoken(request.previous, 'nothing')}")
    lines.append(
        f"- follows: {_spoken(request.following, 'not confirmed; announce no next programme')}"
    )
    lines.append(f"- names the station: {'yes' if request.station_id else 'no'}")
    mark = f"{request.clock_mark:%H:%M}" if request.clock_mark else "none"
    lines.append(f"- clock mark: {mark}")
    if request.edition is not None:
        lines.append(f"- journal edition: {request.edition.value}")
    if request.listener_name and RadioRole.HOST in spec.roles:
        lines.append(f"- listener's first name: {request.listener_name}")
    return "\n".join(lines)


def _spoken(fmt: RadioFormat | None, absent: str) -> str:
    return FORMAT_SPECS[fmt].spoken_as if fmt is not None else absent


def _on_air(request: WritingRequest) -> str:
    """The stories heard this session, fenced: headlines their outlets wrote."""
    if FORMAT_SPECS[request.format].material is not Material.NEWS:
        return "- not shown to this programme"
    titles = [title.strip() for title in request.on_air if title.strip()]
    if not titles:
        return "- nothing yet"
    return wrap_external_content(
        "\n".join(f"- {title}" for title in titles[-ON_AIR_SHOWN_MAX:]),
        source_url="radio:on_air",
        source_type="radio_on_air",
    )


def _listener(taste: ListenerTaste, fmt: RadioFormat) -> str:
    if FORMAT_SPECS[fmt].material is not Material.NEWS:
        return "- not shown to this programme"
    interests = [interest.strip() for interest in taste.interests if interest.strip()]
    stated = [clamp_item(text, STATED_TASTE_MAX_CHARS) for text in taste.stated if text.strip()]
    lines = []
    if interests:
        lines.append(f"- cares about: {', '.join(interests)}")
    if stated:
        lines.append(f"- has said: {'; '.join(stated[:STATED_TASTES_SHOWN_MAX])}")
    return "\n".join(lines) or "- nothing known"


def render_writer_prompt(
    template: str,
    request: WritingRequest,
    station: StationVoice,
    *,
    quote_max_chars: int,
    taste: ListenerTaste = ListenerTaste(),
) -> str:
    """The writer's prompt for one segment.

    Args:
        template: The ``radio_writer_prompt`` text.
        request: The segment to write.
        station: What the listener's session shares.
        quote_max_chars: The longest quotation the verifier lets through.
        taste: What the listener cares about and has said they like.

    Returns:
        The rendered prompt, static part above the marker.
    """
    spec = FORMAT_SPECS[request.format]
    return template.format(
        station_name=station.station_name,
        language_name=station.language_name,
        personality=station.personality,
        title_max_chars=SCRIPT_TITLE_MAX_CHARS,
        intro_outro_max_lines=INTRO_OUTRO_MAX_LINES,
        transition_free_integer_max=TRANSITION_FREE_INTEGER_MAX,
        quote_max_chars=quote_max_chars,
        line_max_chars=LINE_MAX_CHARS,
        listener=_listener(taste, request.format),
        format=request.format.value,
        format_spoken=spec.spoken_as,
        headlines_stories_max=FORMAT_SPECS[RadioFormat.HEADLINES].stories_max,
        bulletin_stories_max=FORMAT_SPECS[RadioFormat.BULLETIN].stories_max,
        roles=", ".join(role.value for role in request.roles or spec.roles),
        context=_context(request),
        on_air=_on_air(request),
        target_chars=spec.target_chars(request.language),
        max_chars=spec.max_chars(request.language),
        facts=wrap_external_content(
            "\n".join(render_fact(fact) for fact in request.pack.facts),
            source_url=f"radio:{request.format.value}",
            source_type="radio_facts",
        ),
    )


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """The story the analyst reads.

    Attributes:
        title: Its headline.
        outlet: Who published it.
        url: Where it was read.
        published_at: When (timezone-aware).
        article: Its full text.
    """

    title: str
    outlet: str
    url: str
    published_at: datetime
    article: str


def render_analyst_prompt(
    template: str,
    request: AnalysisRequest,
    station: StationVoice,
    *,
    min_points: int,
    max_points: int,
) -> str:
    """The analyst's prompt for one story.

    Args:
        template: The ``radio_analyst_prompt`` text.
        request: The story.
        station: What the listener's session shares.
        min_points: The fewest points asked for.
        max_points: The most points kept.

    Returns:
        The rendered prompt, static part above the marker.
    """
    # The headline and the outlet's name are a stranger's words too (a feed a
    # person added names itself): they travel INSIDE the fence with the text.
    article = (
        f"{request.title}\n{request.outlet} — {request.published_at.date().isoformat()}\n\n"
        f"{request.article}"
    )
    return template.format(
        station_name=station.station_name,
        language_name=station.language_name,
        min_points=min_points,
        max_points=max_points,
        article=wrap_external_content(article, source_url=request.url),
    )


def render_verifier_prompt(
    template: str, lines: Sequence[VerifiedLine], pack: FactPack, *, station_name: str
) -> str:
    """The verifier's prompt for one script: the lines that cite a fact, numbered.

    Each line shows its kind, because the kind decides the test: an opinion is
    checked for the specific claims it makes, never for the view it takes
    (measured 2026-09-26: told nothing, one model family rejected three
    opinions in four on every pass).

    Args:
        template: The ``radio_verifier_prompt`` text.
        lines: The verified lines, in air order.
        pack: The segment's facts.
        station_name: The station's name — naming it claims nothing, digits
            included; it is the listener's, so it stays below the marker.

    Returns:
        The rendered prompt: the station's name, the facts the lines cite and
        the numbered lines with their kind, the last two inside the
        untrusted-content wrapper.
    """
    checked = [lines[position] for position in checked_positions(lines)]
    cited = {ref for line in checked for ref in line.refs}
    facts = "\n".join(render_fact(fact) for fact in pack.facts if fact.id in cited)
    numbered = "\n".join(
        f"{number} ({line.kind.value}) [{', '.join(line.refs)}] {line.text}"
        for number, line in enumerate(checked, start=1)
    )
    origin = f"radio:{pack.format.value}"
    return template.format(
        station_name=station_name,
        facts=wrap_external_content(facts, source_url=origin, source_type="radio_facts"),
        lines=wrap_external_content(numbered, source_url=origin, source_type="radio_script"),
    )


__all__ = [
    "ANALYST_PROMPT",
    "HEADLINE_SHOWN_MAX_CHARS",
    "ON_AIR_SHOWN_MAX",
    "STATED_TASTES_SHOWN_MAX",
    "STATED_TASTE_MAX_CHARS",
    "VERIFIER_PROMPT",
    "WRITER_PROMPT",
    "AnalysisRequest",
    "ListenerTaste",
    "RadioTemplates",
    "StationVoice",
    "load_templates",
    "render_analyst_prompt",
    "render_fact",
    "render_verifier_prompt",
    "render_writer_prompt",
]
