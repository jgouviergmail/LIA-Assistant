"""
Excalidraw Position Corrector — Fixes spatial issues in LLM-generated elements.

The LLM generates standard Excalidraw JSON elements with separate text objects
using containerId. It often mispositions text labels and places shapes too close.

This module applies targeted corrections:
1. Re-centers all text elements with containerId inside their parent shapes
2. Pushes overlapping shapes apart while preserving row/column layout
3. Resizes background shapes to fit content
4. Adjusts camera to fit all content

The text re-centering is the KEY fix: the formula
  x = shape.x + (shape.width - text.width) / 2
  y = shape.y + (shape.height - text.height) / 2
ensures labels are always perfectly centered, regardless of what the LLM generated.

Phase: evolution F2 — Admin MCP Excalidraw
Created: 2026-03-07
"""

from __future__ import annotations

import json
import statistics
from typing import Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Minimum gaps between shapes after correction
MIN_SHAPE_GAP_H = 60
MIN_SHAPE_GAP_V = 50
MAX_CORRECTION_ITERATIONS = 80

# Background detection thresholds
_BG_MIN_CONTAINED = 2
_BG_AREA_RATIO_MIN = 3.0

# Camera sizes (4:3 aspect ratio)
_CAMERA_SIZES = [
    (400, 300),
    (600, 450),
    (800, 600),
    (1200, 900),
    (1600, 1200),
    (2400, 1800),
    (3200, 2400),
]

_SHAPE_TYPES = frozenset(("rectangle", "ellipse", "diamond"))


def correct_positions(elements_json: str) -> str:
    """Fix spatial issues in LLM-generated Excalidraw elements.

    Args:
        elements_json: JSON string of Excalidraw elements from the LLM.

    Returns:
        Corrected JSON string ready for the MCP server.
    """
    try:
        elements = json.loads(elements_json)
    except (json.JSONDecodeError, TypeError):
        logger.warning("excalidraw_corrector_invalid_json")
        return elements_json

    if not isinstance(elements, list) or not elements:
        return elements_json

    # Build lookup maps
    all_shapes: list[dict[str, Any]] = []
    bound_texts: list[dict[str, Any]] = []

    for elem in elements:
        etype = elem.get("type", "")
        if etype in _SHAPE_TYPES:
            all_shapes.append(elem)
        elif etype == "text" and elem.get("containerId"):
            bound_texts.append(elem)

    if not all_shapes:
        return elements_json

    # 1. Separate background shapes from content shapes
    bg_shapes, content_shapes = _classify_backgrounds(all_shapes)
    shape_map = {s.get("id", ""): s for s in all_shapes}

    # 2. Re-center ALL bound text elements inside their parent shapes
    text_fixes = _recenter_bound_texts(bound_texts, shape_map)

    # 3. Resolve overlapping content shapes
    corrections = _resolve_overlaps(content_shapes)

    # 4. If shapes moved, update their bound text again
    if corrections:
        _move_bound_texts_by_corrections(bound_texts, corrections)

    # 5. Resize backgrounds to fit content
    if bg_shapes and content_shapes:
        _resize_backgrounds(bg_shapes, content_shapes)

    # 6. Fix camera
    _fix_camera(elements)

    logger.info(
        "excalidraw_positions_corrected",
        shapes_count=len(content_shapes),
        bg_count=len(bg_shapes),
        text_fixes=text_fixes,
        overlap_corrections=len(corrections),
    )

    return json.dumps(elements)


def _get_bbox(elem: dict[str, Any]) -> tuple[float, float, float, float]:
    """Get bounding box (x1, y1, x2, y2) for an element."""
    x = elem.get("x", 0)
    y = elem.get("y", 0)
    w = elem.get("width", 100)
    h = elem.get("height", 60)
    return (x, y, x + w, y + h)


def _area(bbox: tuple[float, float, float, float]) -> float:
    """Get area of a bounding box."""
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def _center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    """Get center point of a bounding box."""
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _overlaps(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    padding_h: float = MIN_SHAPE_GAP_H,
    padding_v: float = MIN_SHAPE_GAP_V,
) -> bool:
    """Check if two bounding boxes overlap (with padding)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (
        ax2 + padding_h <= bx1
        or bx2 + padding_h <= ax1
        or ay2 + padding_v <= by1
        or by2 + padding_v <= ay1
    )


def _classify_backgrounds(
    shapes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate background shapes from content shapes."""
    if len(shapes) < _BG_MIN_CONTAINED + 1:
        return [], shapes

    bboxes = [_get_bbox(s) for s in shapes]
    centers = [_center(bb) for bb in bboxes]
    areas = [_area(bb) for bb in bboxes]

    bg_indices: set[int] = set()

    for i, bbox_i in enumerate(bboxes):
        contained_count = 0
        for j, (cx, cy) in enumerate(centers):
            if i == j:
                continue
            if bbox_i[0] <= cx <= bbox_i[2] and bbox_i[1] <= cy <= bbox_i[3]:
                contained_count += 1

        if contained_count < _BG_MIN_CONTAINED:
            continue

        other_areas = [a for j, a in enumerate(areas) if j != i and a > 0]
        if not other_areas:
            continue
        median_area = statistics.median(other_areas)
        if median_area > 0 and areas[i] / median_area >= _BG_AREA_RATIO_MIN:
            bg_indices.add(i)

    bg_shapes = [shapes[i] for i in bg_indices]
    content_shapes = [shapes[i] for i in range(len(shapes)) if i not in bg_indices]

    if bg_shapes:
        logger.debug(
            "excalidraw_backgrounds_detected",
            bg_ids=[s.get("id", "") for s in bg_shapes],
        )

    return bg_shapes, content_shapes


def _recenter_bound_texts(
    bound_texts: list[dict[str, Any]],
    shape_map: dict[str, dict[str, Any]],
) -> int:
    """Re-center all text elements with containerId inside their parent shape.

    Uses the standard Excalidraw centering formula:
      x = shape.x + (shape.width - text.width) / 2
      y = shape.y + (shape.height - text.height) / 2

    This fixes the most common LLM error: mispositioned text labels.

    Returns:
        Number of text elements re-centered.
    """
    fixes = 0
    for text in bound_texts:
        container_id = text.get("containerId", "")
        parent = shape_map.get(container_id)
        if not parent:
            continue

        px = parent.get("x", 0)
        py = parent.get("y", 0)
        pw = parent.get("width", 100)
        ph = parent.get("height", 60)

        tw = text.get("width", 80)
        th = text.get("height", 24)

        new_x = px + (pw - tw) / 2
        new_y = py + (ph - th) / 2

        old_x = text.get("x", 0)
        old_y = text.get("y", 0)

        if abs(new_x - old_x) > 2 or abs(new_y - old_y) > 2:
            text["x"] = new_x
            text["y"] = new_y
            fixes += 1

    return fixes


def _resolve_overlaps(
    shapes: list[dict[str, Any]],
) -> dict[str, tuple[float, float]]:
    """Push overlapping content shapes apart while preserving layout."""
    corrections: dict[str, tuple[float, float]] = {}

    for _iteration in range(MAX_CORRECTION_ITERATIONS):
        had_overlap = False

        for i in range(len(shapes)):
            for j in range(i + 1, len(shapes)):
                a_bbox = _get_bbox(shapes[i])
                b_bbox = _get_bbox(shapes[j])

                if not _overlaps(a_bbox, b_bbox):
                    continue

                had_overlap = True
                ax1, ay1, ax2, ay2 = a_bbox
                bx1, by1, bx2, by2 = b_bbox

                overlap_x = min(ax2 - bx1, bx2 - ax1) + MIN_SHAPE_GAP_H
                overlap_y = min(ay2 - by1, by2 - ay1) + MIN_SHAPE_GAP_V

                b_id = shapes[j].get("id", "")
                b_cx, a_cx = (bx1 + bx2) / 2, (ax1 + ax2) / 2
                b_cy, a_cy = (by1 + by2) / 2, (ay1 + ay2) / 2

                # Preserve row/column structure
                dx_centers = abs(b_cx - a_cx)
                dy_centers = abs(b_cy - a_cy)
                push_horizontal = dx_centers >= dy_centers

                if push_horizontal:
                    dx = overlap_x if b_cx >= a_cx else -overlap_x
                    shapes[j]["x"] = shapes[j].get("x", 0) + dx
                    prev = corrections.get(b_id, (0.0, 0.0))
                    corrections[b_id] = (prev[0] + dx, prev[1])
                else:
                    dy = overlap_y if b_cy >= a_cy else -overlap_y
                    shapes[j]["y"] = shapes[j].get("y", 0) + dy
                    prev = corrections.get(b_id, (0.0, 0.0))
                    corrections[b_id] = (prev[0], prev[1] + dy)

        if not had_overlap:
            break

    return corrections


def _move_bound_texts_by_corrections(
    bound_texts: list[dict[str, Any]],
    corrections: dict[str, tuple[float, float]],
) -> None:
    """Move bound text elements when their parent shape was pushed by overlap resolution."""
    for text in bound_texts:
        container_id = text.get("containerId", "")
        if container_id in corrections:
            dx, dy = corrections[container_id]
            text["x"] = text.get("x", 0) + dx
            text["y"] = text.get("y", 0) + dy


def _resize_backgrounds(
    bg_shapes: list[dict[str, Any]],
    content_shapes: list[dict[str, Any]],
) -> None:
    """Resize background shapes to fit content with padding."""
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for s in content_shapes:
        bbox = _get_bbox(s)
        min_x = min(min_x, bbox[0])
        min_y = min(min_y, bbox[1])
        max_x = max(max_x, bbox[2])
        max_y = max(max_y, bbox[3])

    if min_x == float("inf"):
        return

    padding = 60
    for bg in bg_shapes:
        bg["x"] = int(min_x - padding)
        bg["y"] = int(min_y - padding)
        bg["width"] = int(max_x - min_x + 2 * padding)
        bg["height"] = int(max_y - min_y + 2 * padding)


def _fix_camera(elements: list[dict[str, Any]]) -> None:
    """Update the cameraUpdate element to fit all content with padding."""
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for elem in elements:
        if elem.get("type") == "cameraUpdate":
            continue
        x = elem.get("x", 0)
        y = elem.get("y", 0)
        w = elem.get("width", 0)
        h = elem.get("height", 0)
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x + w)
        max_y = max(max_y, y + h)

    if min_x == float("inf"):
        return

    content_w = max_x - min_x + 100
    content_h = max_y - min_y + 100

    cam_w, cam_h = _CAMERA_SIZES[-1]
    for w, h in _CAMERA_SIZES:
        if w >= content_w and h >= content_h:
            cam_w, cam_h = w, h
            break

    cam_x = min_x - (cam_w - content_w) / 2 - 50
    cam_y = min_y - (cam_h - content_h) / 2 - 50

    for elem in elements:
        if elem.get("type") == "cameraUpdate":
            elem["width"] = cam_w
            elem["height"] = cam_h
            elem["x"] = int(cam_x)
            elem["y"] = int(cam_y)
            return

    elements.insert(
        0,
        {
            "type": "cameraUpdate",
            "width": cam_w,
            "height": cam_h,
            "x": int(cam_x),
            "y": int(cam_y),
        },
    )
