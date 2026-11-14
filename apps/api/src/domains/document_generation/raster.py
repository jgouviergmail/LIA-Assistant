"""SVG to PNG through PyMuPDF — the one raster door the renderers share (ADR-274).

python-docx writes no chart part and python-pptx no SVG picture, so a figure
bound for Word and a pictogram bound for PowerPoint become PNGs here. The PDF
renderer draws the same SVG as vectors and only borrows the lazy import.
"""

from __future__ import annotations

import importlib
from types import ModuleType


def pymupdf() -> ModuleType:
    """PyMuPDF, imported on first use rather than at boot.

    The import costs 43 MB per process on the production arm64 (measured
    2026-09-12; 118 MB on x86_64) and every uvicorn worker pays it, whether or
    not it ever renders a document. Python caches the module after the first
    call, so the accessor is a dictionary lookup afterwards. Pinned by
    ``tests/unit/test_lazy_heavy_imports_guard.py``.
    """
    return importlib.import_module("pymupdf")


def svg_to_png(
    svg: bytes, *, dpi: int | None = None, width_px: int | None = None, transparent: bool = False
) -> bytes:
    """Rasterize one SVG drawing.

    Args:
        svg: The drawing, UTF-8 encoded.
        dpi: The resolution, for a drawing sized in points (a figure).
        width_px: The exact pixel width, for a drawing sized by its viewBox (an
            icon); takes precedence over ``dpi``.
        transparent: Keep an alpha channel — a pictogram lies on whatever ground
            its slide has; a figure is drawn on white paper.

    Returns:
        The PNG bytes.
    """
    module = pymupdf()
    with module.open("svg", svg) as drawing:
        page = drawing[0]
        if width_px is not None:
            scale = width_px / page.rect.width
            pixmap = page.get_pixmap(matrix=module.Matrix(scale, scale), alpha=transparent)
        else:
            pixmap = page.get_pixmap(dpi=dpi, alpha=transparent)
        png: bytes = pixmap.tobytes("png")
    return png


__all__ = ["pymupdf", "svg_to_png"]
