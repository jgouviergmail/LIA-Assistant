"""
Unit tests for Excalidraw position corrector.

Tests overlap detection, resolution, background detection,
background resizing, and camera fixing.

Phase: evolution F2 — Admin MCP Excalidraw
Created: 2026-03-07
"""

import json

from src.infrastructure.mcp.excalidraw.position_corrector import (
    MIN_SHAPE_GAP_H,
    MIN_SHAPE_GAP_V,
    _classify_backgrounds,
    _fix_camera,
    _get_bbox,
    _overlaps,
    _resize_backgrounds,
    _resolve_overlaps,
    correct_positions,
)


class TestCorrectPositions:
    """Test the main correct_positions() function."""

    def test_no_overlaps_unchanged(self):
        elements = [
            {"type": "cameraUpdate", "width": 800, "height": 600, "x": 0, "y": 0},
            {"type": "rectangle", "id": "a", "x": 0, "y": 0, "width": 200, "height": 80},
            {"type": "rectangle", "id": "b", "x": 400, "y": 0, "width": 200, "height": 80},
        ]
        result = json.loads(correct_positions(json.dumps(elements)))
        shapes = [e for e in result if e["type"] == "rectangle"]
        assert shapes[0]["x"] == 0
        assert shapes[1]["x"] == 400

    def test_overlapping_shapes_separated(self):
        elements = [
            {"type": "rectangle", "id": "a", "x": 0, "y": 0, "width": 200, "height": 80},
            {"type": "rectangle", "id": "b", "x": 150, "y": 10, "width": 200, "height": 80},
        ]
        result = json.loads(correct_positions(json.dumps(elements)))
        shapes = {e["id"]: e for e in result if e["type"] == "rectangle"}
        a = _get_bbox(shapes["a"])
        b = _get_bbox(shapes["b"])
        assert not _overlaps(a, b)

    def test_invalid_json_passthrough(self):
        assert correct_positions("not valid json") == "not valid json"

    def test_empty_list_passthrough(self):
        assert correct_positions("[]") == "[]"

    def test_preserves_element_types(self):
        elements = [
            {"type": "cameraUpdate", "width": 800, "height": 600, "x": 0, "y": 0},
            {"type": "text", "id": "t1", "x": 10, "y": 10, "text": "Title"},
            {"type": "rectangle", "id": "r1", "x": 0, "y": 50, "width": 100, "height": 60},
            {"type": "ellipse", "id": "e1", "x": 300, "y": 50, "width": 80, "height": 80},
            {"type": "arrow", "id": "a1", "x": 100, "y": 80, "endX": 300, "endY": 80},
        ]
        result = json.loads(correct_positions(json.dumps(elements)))
        types = {e["type"] for e in result}
        assert types == {"cameraUpdate", "text", "rectangle", "ellipse", "arrow"}

    def test_background_excluded_and_resized(self):
        """Background should be excluded from overlap and resized to fit content."""
        elements = [
            {"type": "rectangle", "id": "bg", "x": 0, "y": 0, "width": 800, "height": 600},
            {"type": "rectangle", "id": "a", "x": 50, "y": 50, "width": 200, "height": 80},
            {"type": "rectangle", "id": "b", "x": 350, "y": 50, "width": 200, "height": 80},
            {"type": "rectangle", "id": "c", "x": 50, "y": 300, "width": 200, "height": 80},
        ]
        result = json.loads(correct_positions(json.dumps(elements)))
        bg = next(e for e in result if e.get("id") == "bg")
        content = [e for e in result if e["type"] == "rectangle" and e.get("id") != "bg"]
        # Content shapes unchanged (no overlaps)
        assert content[0]["x"] == 50
        assert content[1]["x"] == 350
        # Background encompasses all content
        for s in content:
            assert bg["x"] <= s["x"]
            assert bg["y"] <= s["y"]
            assert bg["x"] + bg["width"] >= s["x"] + s.get("width", 0)
            assert bg["y"] + bg["height"] >= s["y"] + s.get("height", 0)

    def test_preserves_row_alignment(self):
        """Shapes in same row should stay at similar y after correction."""
        elements = [
            {"type": "rectangle", "id": "a", "x": 0, "y": 50, "width": 200, "height": 80},
            {"type": "rectangle", "id": "b", "x": 180, "y": 40, "width": 200, "height": 80},
            {"type": "rectangle", "id": "c", "x": 370, "y": 45, "width": 200, "height": 80},
        ]
        result = json.loads(correct_positions(json.dumps(elements)))
        shapes = {e["id"]: e for e in result if e["type"] == "rectangle"}
        # All shapes should be pushed horizontally (same row), not vertically
        # y values should stay close to original
        assert abs(shapes["a"]["y"] - 50) < 1
        assert abs(shapes["b"]["y"] - 40) < 1 or abs(shapes["b"]["y"] - shapes["a"]["y"]) < 20
        assert abs(shapes["c"]["y"] - 45) < 1 or abs(shapes["c"]["y"] - shapes["a"]["y"]) < 20

    def test_inline_text_preserved(self):
        """Shapes with inline text should keep their text property."""
        elements = [
            {
                "type": "rectangle",
                "id": "a",
                "x": 0,
                "y": 0,
                "width": 200,
                "height": 80,
                "text": "Label A",
                "textAlign": "center",
                "verticalAlign": "middle",
            },
        ]
        result = json.loads(correct_positions(json.dumps(elements)))
        shape = next(e for e in result if e.get("id") == "a")
        assert shape["text"] == "Label A"
        assert shape["textAlign"] == "center"


class TestOverlaps:
    """Test overlap detection."""

    def test_clear_overlap(self):
        a = (0, 0, 200, 80)
        b = (150, 10, 350, 90)
        assert _overlaps(a, b, padding_h=0, padding_v=0)

    def test_no_overlap(self):
        a = (0, 0, 200, 80)
        b = (400, 0, 600, 80)
        assert not _overlaps(a, b, padding_h=0, padding_v=0)

    def test_overlap_with_padding(self):
        a = (0, 0, 200, 80)
        b = (220, 0, 420, 80)  # 20px apart
        assert _overlaps(a, b, padding_h=60, padding_v=0)  # 60px padding -> overlap
        assert not _overlaps(a, b, padding_h=10, padding_v=0)  # 10px padding -> no overlap


class TestClassifyBackgrounds:
    """Test background shape detection."""

    def test_large_container_detected(self):
        shapes = [
            {"id": "bg", "x": 0, "y": 0, "width": 500, "height": 400},
            {"id": "a", "x": 50, "y": 50, "width": 100, "height": 60},
            {"id": "b", "x": 250, "y": 50, "width": 100, "height": 60},
            {"id": "c", "x": 50, "y": 200, "width": 100, "height": 60},
        ]
        bg, content = _classify_backgrounds(shapes)
        assert len(bg) == 1
        assert bg[0]["id"] == "bg"
        assert len(content) == 3

    def test_no_background_when_all_separate(self):
        shapes = [
            {"id": "a", "x": 0, "y": 0, "width": 100, "height": 60},
            {"id": "b", "x": 300, "y": 0, "width": 100, "height": 60},
            {"id": "c", "x": 600, "y": 0, "width": 100, "height": 60},
        ]
        bg, content = _classify_backgrounds(shapes)
        assert len(bg) == 0
        assert len(content) == 3


class TestResolveOverlaps:
    """Test overlap resolution."""

    def test_two_overlapping_shapes(self):
        shapes = [
            {"id": "a", "x": 0, "y": 0, "width": 200, "height": 80},
            {"id": "b", "x": 150, "y": 10, "width": 200, "height": 80},
        ]
        corrections = _resolve_overlaps(shapes)
        assert len(corrections) > 0
        a = _get_bbox(shapes[0])
        b = _get_bbox(shapes[1])
        assert not _overlaps(a, b)

    def test_no_overlap_no_corrections(self):
        shapes = [
            {"id": "a", "x": 0, "y": 0, "width": 200, "height": 80},
            {"id": "b", "x": 500, "y": 500, "width": 200, "height": 80},
        ]
        corrections = _resolve_overlaps(shapes)
        assert len(corrections) == 0

    def test_chain_overlap_resolved(self):
        """Three overlapping shapes should all be separated."""
        shapes = [
            {"id": "a", "x": 0, "y": 0, "width": 200, "height": 80},
            {"id": "b", "x": 150, "y": 0, "width": 200, "height": 80},
            {"id": "c", "x": 300, "y": 0, "width": 200, "height": 80},
        ]
        _resolve_overlaps(shapes)
        for i in range(len(shapes)):
            for j in range(i + 1, len(shapes)):
                assert not _overlaps(_get_bbox(shapes[i]), _get_bbox(shapes[j]))


class TestResizeBackgrounds:
    """Test background resizing."""

    def test_background_fits_content(self):
        bg = [{"id": "bg", "x": 0, "y": 0, "width": 100, "height": 100}]
        content = [
            {"id": "a", "x": 50, "y": 50, "width": 200, "height": 80},
            {"id": "b", "x": 400, "y": 300, "width": 200, "height": 80},
        ]
        _resize_backgrounds(bg, content)
        assert bg[0]["x"] < 50  # Padding before first shape
        assert bg[0]["y"] < 50
        assert bg[0]["x"] + bg[0]["width"] > 600  # After last shape
        assert bg[0]["y"] + bg[0]["height"] > 380


class TestFixCamera:
    """Test camera auto-sizing."""

    def test_camera_covers_content(self):
        elements = [
            {"type": "cameraUpdate", "width": 100, "height": 100, "x": 0, "y": 0},
            {"type": "rectangle", "id": "a", "x": 0, "y": 0, "width": 300, "height": 200},
        ]
        _fix_camera(elements)
        assert elements[0]["width"] >= 300
        assert elements[0]["height"] >= 200

    def test_camera_inserted_if_missing(self):
        elements = [
            {"type": "rectangle", "id": "a", "x": 0, "y": 0, "width": 100, "height": 60},
        ]
        _fix_camera(elements)
        assert elements[0]["type"] == "cameraUpdate"


class TestRealisticSimplifiedFormat:
    """Test with elements using the simplified format (inline text, endX/endY arrows).

    This is the format the LLM should generate per our updated guidelines.
    """

    def _build_diagram(self) -> list[dict]:
        """Build a realistic diagram using simplified format with overlaps."""
        return [
            {"type": "cameraUpdate", "x": -50, "y": -50, "width": 800, "height": 600},
            # Background
            {
                "type": "rectangle",
                "id": "bg",
                "x": -20,
                "y": -20,
                "width": 900,
                "height": 500,
                "backgroundColor": "#dbeafe",
            },
            # Row 1 (overlapping)
            {
                "type": "rectangle",
                "id": "client",
                "x": 0,
                "y": 0,
                "width": 200,
                "height": 80,
                "text": "Client",
                "textAlign": "center",
                "verticalAlign": "middle",
                "backgroundColor": "#dbeafe",
            },
            {
                "type": "rectangle",
                "id": "server",
                "x": 180,
                "y": 10,
                "width": 200,
                "height": 80,
                "text": "Server",
                "textAlign": "center",
                "verticalAlign": "middle",
                "backgroundColor": "#fecaca",
            },
            {
                "type": "rectangle",
                "id": "db",
                "x": 350,
                "y": 5,
                "width": 200,
                "height": 80,
                "text": "Database",
                "textAlign": "center",
                "verticalAlign": "middle",
                "backgroundColor": "#d1fae5",
            },
            # Row 2
            {
                "type": "rectangle",
                "id": "cache",
                "x": 50,
                "y": 200,
                "width": 200,
                "height": 80,
                "text": "Cache",
                "textAlign": "center",
                "verticalAlign": "middle",
                "backgroundColor": "#fef3c7",
            },
            {
                "type": "rectangle",
                "id": "queue",
                "x": 320,
                "y": 200,
                "width": 200,
                "height": 80,
                "text": "Queue",
                "textAlign": "center",
                "verticalAlign": "middle",
                "backgroundColor": "#e9d5ff",
            },
            # Arrows (simplified format)
            {
                "type": "arrow",
                "id": "a1",
                "x": 200,
                "y": 40,
                "endX": 300,
                "endY": 40,
                "endArrowhead": "arrow",
            },
            {
                "type": "arrow",
                "id": "a2",
                "x": 500,
                "y": 50,
                "endX": 600,
                "endY": 50,
                "endArrowhead": "arrow",
            },
            # Free text label
            {
                "type": "text",
                "id": "title",
                "x": 200,
                "y": -50,
                "text": "Architecture",
                "fontSize": 28,
            },
        ]

    def test_no_overlaps(self):
        elements = self._build_diagram()
        result = json.loads(correct_positions(json.dumps(elements)))
        shapes = [e for e in result if e["type"] in ("rectangle", "ellipse", "diamond")]
        bg, content = _classify_backgrounds(shapes)
        for i in range(len(content)):
            for j in range(i + 1, len(content)):
                a = _get_bbox(content[i])
                b = _get_bbox(content[j])
                assert not _overlaps(
                    a, b, padding_h=0, padding_v=0
                ), f"{content[i]['id']} overlaps {content[j]['id']}"

    def test_inline_text_preserved(self):
        """Inline text on shapes must survive correction."""
        elements = self._build_diagram()
        result = json.loads(correct_positions(json.dumps(elements)))
        shapes = {
            e.get("id"): e for e in result if e["type"] == "rectangle" and e.get("id") != "bg"
        }
        assert shapes["client"]["text"] == "Client"
        assert shapes["server"]["text"] == "Server"
        assert shapes["db"]["text"] == "Database"

    def test_background_resized(self):
        elements = self._build_diagram()
        result = json.loads(correct_positions(json.dumps(elements)))
        bg = next(e for e in result if e.get("id") == "bg")
        content = [e for e in result if e["type"] == "rectangle" and e.get("id") != "bg"]
        for s in content:
            assert bg["x"] <= s["x"]
            assert bg["y"] <= s["y"]

    def test_minimum_gaps(self):
        elements = self._build_diagram()
        result = json.loads(correct_positions(json.dumps(elements)))
        shapes = [e for e in result if e["type"] in ("rectangle",) and e.get("id") != "bg"]
        bg, content = _classify_backgrounds(shapes)
        if not content:
            content = shapes
        for i in range(len(content)):
            for j in range(i + 1, len(content)):
                a = _get_bbox(content[i])
                b = _get_bbox(content[j])
                h_gap = max(b[0] - a[2], a[0] - b[2])
                v_gap = max(b[1] - a[3], a[1] - b[3])
                assert h_gap >= MIN_SHAPE_GAP_H or v_gap >= MIN_SHAPE_GAP_V, (
                    f"{content[i].get('id')} <-> {content[j].get('id')}: "
                    f"h_gap={h_gap:.0f}, v_gap={v_gap:.0f}"
                )
