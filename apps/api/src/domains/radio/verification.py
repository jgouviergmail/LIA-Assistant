"""The deterministic editor: every line is checked against the facts it cites.

Nothing a script says reaches a voice unchecked. Each line is repaired where the
fix is mechanical (whitespace, a title too long, too many refs, parts out of
order, the date or time said without citing the clock fact that states it, a
station format — the opening, the sign-off — written all over its music, the
stories past the format's bound) and
DROPPED where it is not — an unknown source, a number found in none of the cited
facts, a quote longer than the fair-use bound, a guest voicing the person's
records, an opinion in any voice but a commentator's. The whole segment is
REFUSED rather than cut when too little survives or when it runs far past its
format's length (ADR-275: a shortened answer announced as whole is the defect). Each decision names its rule, so the
pipeline can count them and a reader can learn why a sentence never aired.

What this cannot see, and says so: a number written out in words, and a claim
that paraphrases a cited fact wrongly without a digit. The optional model
verifier covers the second (:func:`drop_unsupported` applies its verdict under
the SAME refusal rules); the writer is told to write figures as digits, which
the voices read aloud anyway.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.domains.radio.constants import (
    INTRO_OUTRO_MAX_LINES,
    LINE_MAX_CHARS,
    MAX_DROPPED_LINE_RATIO,
    REFS_MAX_PER_LINE,
    SCRIPT_LENGTH_TOLERANCE,
    SCRIPT_TITLE_MAX_CHARS,
    TRANSITION_FREE_INTEGER_MAX,
)
from src.domains.radio.facts import (
    CLOCK_FACT_ID,
    FRAMING_KINDS,
    FactKind,
    FactPack,
    RadioFact,
    Sensitivity,
)
from src.domains.radio.formats import FORMAT_SPECS, OPINION_ROLES, Material, RadioRole
from src.domains.radio.numbers import readings_of, stated_numbers
from src.domains.radio.script import (
    LineKind,
    RadioDelivery,
    ScriptDraft,
    ScriptLine,
    ScriptPart,
)
from src.domains.shared.commercial_content import is_commercial_content


class Violation(StrEnum):
    """Why a line was dropped (a bounded vocabulary: a metric label)."""

    EMPTY_TEXT = "empty_text"
    LINE_TOO_LONG = "line_too_long"
    UNKNOWN_REF = "unknown_ref"
    MISSING_REF = "missing_ref"
    ROLE_NOT_ALLOWED = "role_not_allowed"
    PERSON_OUTSIDE_HOST = "person_outside_host"
    UNSUPPORTED_NUMBER = "unsupported_number"
    QUOTE_TOO_LONG = "quote_too_long"
    #: An opinion in a voice that is not a commentator's (the editorialist, a
    #: debate's or a discussion's commentators).
    OPINION_OUTSIDE_COMMENTATORS = "opinion_outside_commentators"
    TOO_MANY_TRANSITIONS = "too_many_transitions"
    #: A story past the format's bound (a repair: it never counts against the
    #: segment — a bulletin cut back to its stories is a bulletin, not a gutted one).
    STORY_BEYOND_FORMAT = "story_beyond_format"
    #: The model verifier found the claim unsupported by the facts it cites.
    NOT_SUPPORTED = "not_supported"
    COMMERCIAL_CONTENT = "commercial_content"


class Refusal(StrEnum):
    """Why a whole segment was refused."""

    NO_BODY = "no_body"
    TOO_LONG = "too_long"
    TOO_MANY_DROPPED = "too_many_dropped"
    SUBJECT_NOT_ANNOUNCED = "subject_not_announced"


@dataclass(frozen=True, slots=True)
class VerifiedLine:
    """A line that passed every check, ready for a voice."""

    role: RadioRole
    part: ScriptPart
    kind: LineKind
    text: str
    delivery: RadioDelivery
    refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """What survived, what was dropped and why, and whether the segment stands.

    Attributes:
        title: The segment's title, repaired.
        lines: The lines that may air, in air order.
        origins: Each kept line's place in the draft (the refusal counts on it).
        dropped: The draft places dropped, with their rule.
        refusal: Why the segment cannot stand, if it cannot.
    """

    title: str
    lines: tuple[VerifiedLine, ...]
    origins: tuple[int, ...]
    dropped: tuple[tuple[int, Violation], ...]
    refusal: Refusal | None

    @property
    def accepted(self) -> bool:
        """True when the segment may be voiced."""
        return self.refusal is None


#: A quoted span, whichever the language's quotation marks.
_QUOTE_RE: Final[re.Pattern[str]] = re.compile(
    r"«\s*(.+?)\s*»|“(.+?)”|„(.+?)“|\"(.+?)\"|「(.+?)」|『(.+?)』"
)
_WS_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_PART_ORDER: Final[dict[ScriptPart, int]] = {
    ScriptPart.INTRO: 0,
    ScriptPart.BODY: 1,
    ScriptPart.OUTRO: 2,
}
#: The kinds that state something from the news or the person's records.
_NEEDS_FACT: Final[frozenset[LineKind]] = frozenset({LineKind.FACT, LineKind.OPINION})
#: Drops that repair the script's shape rather than reject what a line said.
_REPAIRS: Final[frozenset[Violation]] = frozenset({Violation.STORY_BEYOND_FORMAT})


def announce_subject(draft: ScriptDraft, pack: FactPack) -> ScriptDraft:
    """Make a one-story programme's displayed subject its first spoken words.

    The writer can supply a good title yet begin with a generic format teaser.
    Put that same title in the first intro line, citing the story the script
    actually uses, before the usual deterministic and optional model checks.
    """
    spec = FORMAT_SPECS[pack.format]
    if spec.material is not Material.NEWS or spec.stories_max != 1:
        return draft
    title = _WS_RE.sub(" ", draft.title).strip()[:SCRIPT_TITLE_MAX_CHARS].strip()
    if not title:
        return draft
    facts = pack.by_id()
    told = next(
        (
            (line, ref)
            for line in draft.lines
            for ref in line.refs
            if ref in facts and facts[ref].kind is FactKind.NEWS
        ),
        None,
    )
    if told is None:
        return draft
    first_story_line, news_ref = told
    lines = list(draft.lines)
    intro_index = next(
        (index for index, line in enumerate(lines) if line.part is ScriptPart.INTRO), None
    )
    if intro_index is None:
        sentence = title if title.endswith((".", "!", "?", "…", "。", "！", "？")) else f"{title}."
        lines.insert(
            0,
            ScriptLine(
                role=first_story_line.role,
                part=ScriptPart.INTRO,
                kind=LineKind.FACT,
                text=sentence,
                delivery=first_story_line.delivery,
                refs=[news_ref],
            ),
        )
    else:
        intro = lines[intro_index]
        text = _WS_RE.sub(" ", intro.text).strip()
        if title.casefold() not in text.casefold():
            sentence = (
                title if title.endswith((".", "!", "?", "…", "。", "！", "？")) else f"{title}."
            )
            text = (
                f"{sentence} {text}"
                if len(sentence) + len(text) + 1 <= LINE_MAX_CHARS
                else sentence
            )
        lines[intro_index] = intro.model_copy(
            update={
                "text": text,
                "kind": LineKind.FACT if intro.kind is LineKind.TRANSITION else intro.kind,
                "refs": list(dict.fromkeys([news_ref, *intro.refs])),
            }
        )
    return draft.model_copy(update={"lines": lines})


def _quotes(text: str) -> Iterable[str]:
    for match in _QUOTE_RE.finditer(text):
        yield next(group for group in match.groups() if group is not None)


def _supporting_text(fact: RadioFact) -> str:
    """What a line citing ``fact`` may take its numbers from.

    The fact, and the name of its source: « according to France 24 » attributes
    the cited fact, it does not state a 24 (measured 2026-09-26 on a real
    bulletin: two of three dropped lines were this, not an invented figure).
    """
    return f"{fact.text} {fact.source.label}" if fact.source is not None else fact.text


def _without_station(text: str, station_name: str) -> str:
    """The line with every mention of the station's own name blanked.

    « Welcome to Radio 42 » names the station the listener called so: it states
    no 42. Blanking the MENTION — rather than supporting the name's numbers
    everywhere — keeps « 42 deaths » a claim like any other. A name that is a
    number alone makes that number a mention wherever it appears: the
    listener's choice. No name blanks nothing (an empty pattern matches
    between every character).
    """
    name = station_name.strip()
    if not name:
        return text
    return re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)


def _number_violation(
    line: ScriptLine, text: str, cited: list[RadioFact], station_name: str
) -> bool:
    supported = frozenset().union(*(readings_of(_supporting_text(fact)) for fact in cited))
    for number in stated_numbers(_without_station(text, station_name)):
        if number.readings & supported:
            continue
        free = (
            line.kind is LineKind.TRANSITION
            and not number.grouped
            and int(number.digits) <= TRANSITION_FREE_INTEGER_MAX
        )
        if not free:
            return True
    return False


def _structural_violation(
    line: ScriptLine,
    text: str,
    refs: tuple[str, ...],
    facts: dict[str, RadioFact],
    allowed_roles: frozenset[RadioRole],
) -> Violation | None:
    """What is wrong with the line's form: empty, too long, phantom source, wrong voice."""
    if not text:
        return Violation.EMPTY_TEXT
    if len(text) > LINE_MAX_CHARS:
        return Violation.LINE_TOO_LONG
    if any(ref not in facts for ref in refs):
        return Violation.UNKNOWN_REF
    if line.role not in allowed_roles:
        return Violation.ROLE_NOT_ALLOWED
    return None


def _lacks_its_sources(line: ScriptLine, cited: list[RadioFact]) -> bool:
    """Whether the line cites less than its kind needs.

    An analysis line needs an analysis fact; a fact or an opinion needs a fact
    that is not an analysis point (the story itself, the person's records).
    """
    if line.kind is LineKind.ANALYSIS:
        return not any(f.kind is FactKind.ANALYSIS for f in cited)
    return line.kind in _NEEDS_FACT and not any(f.kind is not FactKind.ANALYSIS for f in cited)


def _content_violation(
    line: ScriptLine,
    text: str,
    cited: list[RadioFact],
    *,
    quote_max_chars: int,
    station_name: str,
) -> Violation | None:
    """What is wrong with what the line asserts, measured against what it cites."""
    if is_commercial_content(text):
        return Violation.COMMERCIAL_CONTENT
    if _lacks_its_sources(line, cited):
        return Violation.MISSING_REF
    if line.kind is LineKind.OPINION and line.role not in OPINION_ROLES:
        return Violation.OPINION_OUTSIDE_COMMENTATORS
    if line.role is not RadioRole.HOST and any(
        f.sensitivity is not Sensitivity.PUBLIC for f in cited
    ):
        return Violation.PERSON_OUTSIDE_HOST
    if _number_violation(line, text, cited, station_name):
        return Violation.UNSUPPORTED_NUMBER
    if any(len(quote) > quote_max_chars for quote in _quotes(text)):
        return Violation.QUOTE_TOO_LONG
    return None


def _refs_of(line: ScriptLine) -> tuple[str, ...]:
    """The line's refs, deduplicated in order and capped (a mechanical repair)."""
    seen: dict[str, None] = {}
    for ref in line.refs:
        cleaned = ref.strip()
        if cleaned:
            seen.setdefault(cleaned, None)
    return tuple(seen)[:REFS_MAX_PER_LINE]


def _with_clock(
    line: ScriptLine,
    text: str,
    refs: tuple[str, ...],
    facts: dict[str, RadioFact],
    station_name: str,
) -> tuple[str, ...]:
    """The refs, with the clock fact when it alone sources the line's other numbers (a repair).

    The date and the time are every segment's context: a line that says them
    and forgot to cite the clock is repaired, never dropped (measured
    2026-09-26: « il est 10 h 21 » in an uncited greeting was the opening's
    only drop on one model family).
    """
    clock = facts.get(CLOCK_FACT_ID)
    if clock is None or CLOCK_FACT_ID in refs or len(refs) >= REFS_MAX_PER_LINE:
        return refs
    cited = [facts[ref] for ref in refs]
    if _number_violation(line, text, cited, station_name) and not _number_violation(
        line, text, [*cited, clock], station_name
    ):
        return (*refs, CLOCK_FACT_ID)
    return refs


def _with_story(
    line: ScriptLine, refs: tuple[str, ...], facts: dict[str, RadioFact]
) -> tuple[str, ...]:
    """The refs, with its story's fact when points of ONE story alone source the line (a repair).

    An analysis point is the expert's reading of one story: an anchor who tells
    it in a `fact` line rests on that story all the same, and the model verifier
    then reads the line against both. Measured 2026-09-27: the anchors cite the
    points that hold the article's details — half their fact lines cited points
    alone (21 of 43 over three rounds), even when the writer was told not to —
    so four analyses in four lost their setting-out line, two the whole segment;
    repaired, fifteen in fifteen aired. A line whose points span stories, whose
    story has no fact in the pack, or which cites all it may is left to the rule.
    """
    if line.kind not in _NEEDS_FACT or len(refs) >= REFS_MAX_PER_LINE:
        return refs
    cited = [facts[ref] for ref in refs]
    if any(fact.kind is not FactKind.ANALYSIS for fact in cited):
        return refs
    stories = {fact.source.story_key if fact.source else None for fact in cited}
    if len(stories) != 1 or None in stories:
        return refs
    own = next(
        (
            fact.id
            for fact in facts.values()
            if fact.kind is not FactKind.ANALYSIS
            and fact.source is not None
            and fact.source.story_key in stories
        ),
        None,
    )
    return refs if own is None else (*refs, own)


def _speaks_as_body(draft: ScriptDraft, pack: FactPack) -> bool:
    """Whether every line is the body: a station format written all over its music.

    The opening and the sign-off ARE their few words (they carry no material),
    so a writer that put them all in the intro or the outro wrote a whole
    segment, not an empty one (measured 2026-09-26: both model families did, and
    both openings were refused). A format that informs keeps its rule: no body,
    nothing said.
    """
    return FORMAT_SPECS[pack.format].material is Material.NONE and not any(
        line.part is ScriptPart.BODY for line in draft.lines
    )


def verify_script(
    draft: ScriptDraft,
    pack: FactPack,
    *,
    language: str,
    quote_max_chars: int,
    station_name: str,
    roles: Collection[RadioRole] = (),
) -> VerificationResult:
    """Check a script against its facts; repair, drop or refuse.

    Args:
        draft: What the writer returned.
        pack: The facts it was given.
        language: Backend-canonical language (sizes the length ceiling).
        quote_max_chars: The longest quotation that may air.
        station_name: The station's name, which any line may say (a mention of
            it states none of its numbers).
        roles: The roles that speak (a commentator without a voice of its own
            is not among them); empty for the format's own. The host always may.

    Returns:
        The verified script, its dropped lines with their rule, and the refusal
        when the segment cannot stand.
    """
    spec = FORMAT_SPECS[pack.format]
    facts = pack.by_id()
    allowed_roles = frozenset({RadioRole.HOST, *(roles or spec.roles)})
    as_body = _speaks_as_body(draft, pack)
    kept: list[tuple[int, VerifiedLine]] = []
    dropped: list[tuple[int, Violation]] = []
    for index, line in enumerate(draft.lines):
        text = _WS_RE.sub(" ", line.text).strip()
        refs = _refs_of(line)
        violation = _structural_violation(line, text, refs, facts, allowed_roles)
        if violation is None:
            refs = _with_story(line, _with_clock(line, text, refs, facts, station_name), facts)
            cited = [facts[ref] for ref in refs]
            violation = _content_violation(
                line, text, cited, quote_max_chars=quote_max_chars, station_name=station_name
            )
        if violation is not None:
            dropped.append((index, violation))
            continue
        part = ScriptPart.BODY if as_body else line.part
        kept.append((index, VerifiedLine(line.role, part, line.kind, text, line.delivery, refs)))

    ordered, over_music = _order_and_cap_transitions(kept)
    dropped.extend(over_music)
    ordered, beyond = _within_story_bound(ordered, facts, FORMAT_SPECS[pack.format].stories_max)
    dropped.extend(beyond)
    title = _WS_RE.sub(" ", draft.title).strip()[:SCRIPT_TITLE_MAX_CHARS].strip()
    lines = [line for _, line in ordered]
    refusal = _refusal(draft, lines, dropped, pack, language)
    return VerificationResult(
        title=title,
        lines=tuple(lines),
        origins=tuple(index for index, _ in ordered),
        dropped=tuple(sorted(dropped)),
        refusal=refusal,
    )


def drop_unsupported(
    draft: ScriptDraft,
    pack: FactPack,
    result: VerificationResult,
    unsupported: frozenset[int],
    *,
    language: str,
) -> VerificationResult:
    """The verified script once the model verifier has read it.

    The lines it could not support are dropped, and the segment is judged
    again by the SAME rules — a body, a length, at most a quarter of its
    sourced lines lost — so a script the verifier gutted is refused, never
    aired shortened (ADR-275).

    Args:
        draft: What the writer returned.
        pack: The facts it was given.
        result: The deterministic verdict.
        unsupported: Places in ``result.lines`` the verifier did not support.
        language: Backend-canonical language (sizes the length ceiling).

    Returns:
        The verdict with those lines dropped under ``NOT_SUPPORTED``.
    """
    flagged = {pos for pos in unsupported if 0 <= pos < len(result.lines)}
    if not flagged:
        return result
    kept = [
        (origin, line)
        for pos, (origin, line) in enumerate(zip(result.origins, result.lines, strict=True))
        if pos not in flagged
    ]
    dropped = [
        *result.dropped,
        *((result.origins[pos], Violation.NOT_SUPPORTED) for pos in sorted(flagged)),
    ]
    lines = [line for _, line in kept]
    return VerificationResult(
        title=result.title,
        lines=tuple(lines),
        origins=tuple(origin for origin, _ in kept),
        dropped=tuple(sorted(dropped)),
        refusal=_refusal(draft, lines, dropped, pack, language),
    )


def _order_and_cap_transitions(
    kept: list[tuple[int, VerifiedLine]],
) -> tuple[list[tuple[int, VerifiedLine]], list[tuple[int, Violation]]]:
    """Intro first, body, outro last (a repair); at most a few lines over the music.

    Returns:
        The ordered lines with their draft places, and the extra music lines
        that were dropped.
    """
    by_part: dict[ScriptPart, list[tuple[int, VerifiedLine]]] = {part: [] for part in ScriptPart}
    for index, line in kept:
        by_part[line.part].append((index, line))
    extra: list[tuple[int, Violation]] = []
    for part in (ScriptPart.INTRO, ScriptPart.OUTRO):
        extra.extend(
            (index, Violation.TOO_MANY_TRANSITIONS)
            for index, _ in by_part[part][INTRO_OUTRO_MAX_LINES:]
        )
        by_part[part] = by_part[part][:INTRO_OUTRO_MAX_LINES]
    ordered = [
        pair for part in sorted(by_part, key=_PART_ORDER.__getitem__) for pair in by_part[part]
    ]
    return ordered, extra


def _within_story_bound(
    ordered: list[tuple[int, VerifiedLine]],
    facts: dict[str, RadioFact],
    stories_max: int | None,
) -> tuple[list[tuple[int, VerifiedLine]], list[tuple[int, Violation]]]:
    """At most the format's stories, the first told kept (a repair).

    A story is the facts the lines tell TOGETHER — the news, or the listener's
    own subjects, never what frames them (the clock, the weather, an analysis
    point): two facts one line cites are one story, so three outlets' takes on
    one event count once. A line that would tell a story past the bound is
    dropped whole (measured 2026-09-26: a bulletin of ten stories, a brief of
    two and a « for you » of three things, against a writer told the bound).

    Returns:
        The lines within the bound, and the ones dropped beyond it.
    """
    if stories_max is None:
        return ordered, []
    parent: dict[str, str] = {}

    def story(ref: str) -> str:
        while parent.setdefault(ref, ref) != ref:
            ref = parent[ref]
        return ref

    news = [
        [ref for ref in line.refs if facts[ref].kind not in FRAMING_KINDS] for _, line in ordered
    ]
    for refs in news:
        for ref in refs[1:]:
            parent[story(ref)] = story(refs[0])
    told: set[str] = set()
    kept: list[tuple[int, VerifiedLine]] = []
    beyond: list[tuple[int, Violation]] = []
    for (index, line), refs in zip(ordered, news, strict=True):
        stories = told | {story(ref) for ref in refs}
        if len(stories) > stories_max:
            beyond.append((index, Violation.STORY_BEYOND_FORMAT))
            continue
        told = stories
        kept.append((index, line))
    return kept, beyond


def _refusal(
    draft: ScriptDraft,
    lines: list[VerifiedLine],
    dropped: list[tuple[int, Violation]],
    pack: FactPack,
    language: str,
) -> Refusal | None:
    if not any(line.part is ScriptPart.BODY for line in lines):
        return Refusal.NO_BODY
    ceiling = FORMAT_SPECS[pack.format].max_chars(language) * SCRIPT_LENGTH_TOLERANCE
    if sum(len(line.text) for line in lines) > ceiling:
        return Refusal.TOO_LONG
    repaired = {i for i, violation in dropped if violation in _REPAIRS}
    judged = {
        i
        for i, line in enumerate(draft.lines)
        if line.kind is not LineKind.TRANSITION and i not in repaired
    }
    if judged:
        lost = {i for i, _ in dropped} & judged
        if len(lost) / len(judged) > MAX_DROPPED_LINE_RATIO:
            return Refusal.TOO_MANY_DROPPED
    return None
