"""Transitions and reveals of a deck that is presented (ADR-274).

A deck someone PRESENTS moves: each slide fades in, and the points of a slide
appear one click at a time — the speaker's rhythm. A deck to READ stays still:
a reader scrolls, and a point waiting for a click is a point a reader never
sees. Whether a deck moves is the person's choice (``DocumentAnimations``) read
with the writer's declaration of how the deck will be used (``delivery``).

python-pptx writes neither a transition nor a timing tree. Both are written
here as PresentationML (ECMA-376 Part 1, §19.3 and §19.5), in the order the
schema fixes for a slide: ``cSld``, ``clrMapOvr``, ``transition``, ``timing``,
``extLst``. One effect only, PowerPoint's « Fade » entrance: the most sober
of them, and the one a reader of any version plays.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement

from src.core.document_preferences import DocumentAnimations

#: A slide's own transition: a fade, at PowerPoint's medium speed.
TRANSITION_SPEED = "med"
#: A revealed point fades in over this long, once the speaker clicks.
REVEAL_FADE_MS = 500
#: PowerPoint's preset number of the « Fade » entrance effect.
_FADE_PRESET = "10"
#: What may follow a transition in a slide, in schema order.
_AFTER_TRANSITION = ("p:timing", "p:extLst")
_AFTER_TIMING = ("p:extLst",)


def deck_moves(animations: DocumentAnimations, delivery: str) -> bool:
    """Whether a deck fades and reveals.

    Args:
        animations: The person's choice.
        delivery: The writer's canonical declaration (``presented``, ``read``
            or empty, which reads as « read »).

    Returns:
        True when the deck moves.
    """
    if animations is DocumentAnimations.NEVER:
        return False
    if animations is DocumentAnimations.ALWAYS:
        return True
    return delivery == "presented"


@dataclass(frozen=True, slots=True)
class Target:
    """A shape, or one paragraph of it, that appears.

    Attributes:
        shape_id: The shape's id on its slide.
        paragraph: The paragraph to reveal, or ``None`` for the whole shape.
        has_text: Whether the shape carries text — a text shape declares how it
            builds, a picture or a plain fill declares nothing.
    """

    shape_id: int
    paragraph: int | None = None
    has_text: bool = False


@dataclass(frozen=True, slots=True)
class Reveal:
    """What one click shows: its targets appear together, the first leading."""

    targets: tuple[Target, ...]


def _element(tag: str, parent: Any | None = None, **attributes: str) -> Any:
    element = OxmlElement(tag)
    for name, value in attributes.items():
        element.set(name, value)
    if parent is not None:
        parent.append(element)
    return element


def _insert_before_any(slide_element: Any, element: Any, successors: Sequence[str]) -> None:
    """Place ``element`` before the first of ``successors`` the slide holds, else last."""
    for tag in successors:
        follower = slide_element.find(qn(tag))
        if follower is not None:
            follower.addprevious(element)
            return
    slide_element.append(element)


def add_transition(slide: Any) -> None:
    """Fade the slide in (once: a slide has one transition)."""
    slide_element = slide._element
    if slide_element.find(qn("p:transition")) is not None:
        return
    transition = _element("p:transition", spd=TRANSITION_SPEED)
    _element("p:fade", transition)
    _insert_before_any(slide_element, transition, _AFTER_TRANSITION)


def _ids() -> Iterator[str]:
    """Time-node ids, unique and increasing within one slide's tree."""
    number = 0
    while True:
        number += 1
        yield str(number)


def _target(parent: Any, target: Target) -> None:
    holder = _element("p:tgtEl", parent)
    shape = _element("p:spTgt", holder, spid=str(target.shape_id))
    if target.paragraph is not None:
        text = _element("p:txEl", shape)
        index = str(target.paragraph)
        _element("p:pRg", text, st=index, end=index)


def _start_at(parent: Any, delay: str) -> None:
    conditions = _element("p:stCondLst", parent)
    _element("p:cond", conditions, delay=delay)


def _effect(parent: Any, target: Target, ids: Iterator[str], node_type: str) -> None:
    """One « Fade » entrance: made visible at once, then faded in."""
    group = _element("p:par", parent)
    node = _element(
        "p:cTn",
        group,
        id=next(ids),
        presetID=_FADE_PRESET,
        presetClass="entr",
        presetSubtype="0",
        fill="hold",
        grpId="0",
        nodeType=node_type,
    )
    _start_at(node, "0")
    children = _element("p:childTnLst", node)

    show = _element("p:set", children)
    behaviour = _element("p:cBhvr", show)
    instant = _element("p:cTn", behaviour, id=next(ids), dur="1", fill="hold")
    _start_at(instant, "0")
    _target(behaviour, target)
    names = _element("p:attrNameLst", behaviour)
    _element("p:attrName", names).text = "style.visibility"
    value = _element("p:to", show)
    _element("p:strVal", value, val="visible")

    fade = _element("p:animEffect", children, transition="in", filter="fade")
    fade_behaviour = _element("p:cBhvr", fade)
    _element("p:cTn", fade_behaviour, id=next(ids), dur=str(REVEAL_FADE_MS))
    _target(fade_behaviour, target)


def _click(parent: Any, reveal: Reveal, ids: Iterator[str]) -> None:
    """One click of the main sequence: the first target leads, the others follow with it."""
    group = _element("p:par", parent)
    node = _element("p:cTn", group, id=next(ids), fill="hold")
    _start_at(node, "indefinite")
    inner_group = _element("p:par", _element("p:childTnLst", node))
    inner = _element("p:cTn", inner_group, id=next(ids), fill="hold")
    _start_at(inner, "0")
    effects = _element("p:childTnLst", inner)
    for index, target in enumerate(reveal.targets):
        _effect(effects, target, ids, "clickEffect" if index == 0 else "withEffect")


def _slide_condition(parent: Any, tag: str, event: str) -> None:
    conditions = _element(tag, parent)
    condition = _element("p:cond", conditions, evt=event, delay="0")
    _element("p:sldTgt", _element("p:tgtEl", condition))


def _builds(timing: Any, reveals: Sequence[Reveal]) -> None:
    """How each text shape builds: by paragraph, or as one object with its fill."""
    declared: dict[int, bool] = {}
    for reveal in reveals:
        for target in reveal.targets:
            if target.has_text:
                by_paragraph = target.paragraph is not None
                declared[target.shape_id] = declared.get(target.shape_id, False) or by_paragraph
    if not declared:
        return
    builds = _element("p:bldLst", timing)
    for shape_id, by_paragraph in declared.items():
        if by_paragraph:
            _element("p:bldP", builds, spid=str(shape_id), grpId="0", build="p")
        else:
            _element("p:bldP", builds, spid=str(shape_id), grpId="0", animBg="1")


def add_reveals(slide: Any, reveals: Sequence[Reveal]) -> None:
    """Make each reveal wait for its click.

    Args:
        slide: A python-pptx slide whose shapes the targets name.
        reveals: The clicks, in order; empty writes nothing.

    Raises:
        ValueError: When the slide already has a timing tree — PresentationML
            allows one, and a second would make PowerPoint repair the file.
    """
    if not reveals:
        return
    if slide._element.find(qn("p:timing")) is not None:
        raise ValueError("a slide has one timing tree")
    ids = _ids()
    timing = _element("p:timing")
    root_group = _element("p:par", _element("p:tnLst", timing))
    root = _element(
        "p:cTn", root_group, id=next(ids), dur="indefinite", restart="never", nodeType="tmRoot"
    )
    sequence = _element("p:seq", _element("p:childTnLst", root), concurrent="1", nextAc="seek")
    main = _element("p:cTn", sequence, id=next(ids), dur="indefinite", nodeType="mainSeq")
    clicks = _element("p:childTnLst", main)
    for reveal in reveals:
        _click(clicks, reveal, ids)
    _slide_condition(sequence, "p:prevCondLst", "onPrev")
    _slide_condition(sequence, "p:nextCondLst", "onNext")
    _builds(timing, reveals)
    _insert_before_any(slide._element, timing, _AFTER_TIMING)


__all__ = [
    "REVEAL_FADE_MS",
    "TRANSITION_SPEED",
    "Reveal",
    "Target",
    "add_reveals",
    "add_transition",
    "deck_moves",
]
