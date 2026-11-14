"""Transitions and reveals: written where PresentationML puts them, only on a deck that moves."""

from __future__ import annotations

import io

import pptx
import pytest
from lxml.etree import _Element
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from pptx.slide import Slide as PptxSlide
from pptx.util import Inches

from src.core.document_preferences import DocumentAnimations
from src.domains.document_generation.renderers import pptx_geometry as geometry
from src.domains.document_generation.renderers.pptx_motion import (
    Reveal,
    Target,
    add_reveals,
    add_transition,
    deck_moves,
)

pytestmark = pytest.mark.unit


def _slide_with_body(paragraphs: int) -> tuple[PptxSlide, int]:
    presentation = geometry.base_presentation()
    slide: PptxSlide = presentation.slides.add_slide(
        presentation.slide_layouts[geometry.LAYOUT_CONTENT]
    )
    body = geometry.placeholder(slide, geometry.BODY_IDX)
    body.text_frame.text = "first"
    for index in range(1, paragraphs):
        body.text_frame.add_paragraph().text = f"point {index}"
    return slide, int(body.shape_id)


def _tile(slide: PptxSlide) -> int:
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(1), Inches(1))
    return int(shape.shape_id)


def _children(slide: PptxSlide) -> list[str]:
    return [str(child.tag) for child in slide._element]


def _all(slide: PptxSlide, tag: str) -> list[_Element]:
    return list(slide._element.iter(qn(tag)))


class TestWhetherADeckMoves:
    @pytest.mark.parametrize("delivery", ["presented", "read", ""])
    def test_never_keeps_every_deck_still(self, delivery: str) -> None:
        assert deck_moves(DocumentAnimations.NEVER, delivery) is False

    @pytest.mark.parametrize("delivery", ["presented", "read", ""])
    def test_always_moves_every_deck(self, delivery: str) -> None:
        assert deck_moves(DocumentAnimations.ALWAYS, delivery) is True

    @pytest.mark.parametrize(
        ("delivery", "moves"), [("presented", True), ("read", False), ("", False)]
    )
    def test_the_default_moves_a_presented_deck_only(self, delivery: str, moves: bool) -> None:
        assert deck_moves(DocumentAnimations.PRESENTED, delivery) is moves


class TestTheTransition:
    def test_it_follows_the_colour_map_and_fades(self) -> None:
        slide, _body = _slide_with_body(1)

        add_transition(slide)

        tags = _children(slide)
        assert tags.index(qn("p:transition")) == tags.index(qn("p:clrMapOvr")) + 1
        transition = _all(slide, "p:transition")[0]
        assert transition.get("spd") == "med"
        assert transition.find(qn("p:fade")) is not None

    def test_it_comes_before_a_timing_written_earlier(self) -> None:
        slide, body = _slide_with_body(2)
        add_reveals(slide, [Reveal((Target(body, 0, True),)), Reveal((Target(body, 1, True),))])

        add_transition(slide)

        tags = _children(slide)
        assert tags.index(qn("p:transition")) + 1 == tags.index(qn("p:timing"))

    def test_a_second_call_writes_no_second_transition(self) -> None:
        slide, _body = _slide_with_body(1)
        add_transition(slide)
        add_transition(slide)
        assert _children(slide).count(qn("p:transition")) == 1


class TestTheReveals:
    def test_each_point_waits_for_its_own_click(self) -> None:
        slide, body = _slide_with_body(3)

        add_reveals(slide, [Reveal((Target(body, index, True),)) for index in range(3)])

        clicks = [node for node in _all(slide, "p:cTn") if node.get("nodeType") == "clickEffect"]
        assert len(clicks) == 3
        ranges = {(rng.get("st"), rng.get("end")) for rng in _all(slide, "p:pRg")}
        # Each effect names its paragraph twice: once to show it, once to fade it in.
        assert sorted(ranges) == [("0", "0"), ("1", "1"), ("2", "2")]

    def test_shapes_shown_together_share_one_click(self) -> None:
        slide, body = _slide_with_body(1)
        tile = _tile(slide)

        add_reveals(slide, [Reveal((Target(tile), Target(body, None, True)))])

        nodes = [node.get("nodeType") for node in _all(slide, "p:cTn") if node.get("presetID")]
        assert nodes == ["clickEffect", "withEffect"]

    def test_every_time_node_has_its_own_id(self) -> None:
        slide, body = _slide_with_body(4)
        add_reveals(slide, [Reveal((Target(body, index, True),)) for index in range(4)])

        ids = [int(str(node.get("id"))) for node in _all(slide, "p:cTn")]
        assert ids == list(range(1, len(ids) + 1))

    def test_every_target_is_a_shape_of_the_slide(self) -> None:
        slide, body = _slide_with_body(2)
        add_reveals(slide, [Reveal((Target(body, 0, True),)), Reveal((Target(body, 1, True),))])

        shape_ids = {int(shape.shape_id) for shape in slide.shapes}
        targets = {int(str(target.get("spid"))) for target in _all(slide, "p:spTgt")}
        assert targets <= shape_ids

    def test_a_text_shape_declares_how_it_builds(self) -> None:
        slide, body = _slide_with_body(2)
        tile = _tile(slide)
        add_reveals(
            slide,
            [
                Reveal((Target(body, 0, True),)),
                Reveal((Target(body, 1, True),)),
                Reveal((Target(tile),)),
            ],
        )

        builds = [(build.get("spid"), build.get("build")) for build in _all(slide, "p:bldP")]
        # The body builds by paragraph, once; the text-less tile needs no entry.
        assert builds == [(str(body), "p")]

    def test_a_whole_text_shape_builds_as_one_object(self) -> None:
        slide, body = _slide_with_body(1)
        add_reveals(slide, [Reveal((Target(body, None, True),))])

        (build,) = _all(slide, "p:bldP")
        assert build.get("build") is None and build.get("animBg") == "1"

    def test_a_second_timing_tree_is_refused(self) -> None:
        slide, body = _slide_with_body(2)
        add_reveals(slide, [Reveal((Target(body, 0, True),)), Reveal((Target(body, 1, True),))])

        with pytest.raises(ValueError, match="one timing tree"):
            add_reveals(slide, [Reveal((Target(body, 0, True),))])
        assert _children(slide).count(qn("p:timing")) == 1

    def test_nothing_to_reveal_writes_no_timing(self) -> None:
        slide, _body = _slide_with_body(1)
        add_reveals(slide, [])
        assert qn("p:timing") not in _children(slide)

    def test_the_slide_still_reads_back(self) -> None:
        """python-pptx reopens what it wrote: the XML is well formed and in place."""
        presentation = geometry.base_presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[geometry.LAYOUT_CONTENT])
        body = geometry.placeholder(slide, geometry.BODY_IDX)
        body.text_frame.text = "a"
        body.text_frame.add_paragraph().text = "b"
        body_id = int(body.shape_id)
        add_reveals(
            slide, [Reveal((Target(body_id, 0, True),)), Reveal((Target(body_id, 1, True),))]
        )
        add_transition(slide)
        buffer = io.BytesIO()
        presentation.save(buffer)

        reread = pptx.Presentation(io.BytesIO(buffer.getvalue()))
        tags = [str(child.tag) for child in reread.slides[0]._element]
        assert tags[-2:] == [qn("p:transition"), qn("p:timing")]
