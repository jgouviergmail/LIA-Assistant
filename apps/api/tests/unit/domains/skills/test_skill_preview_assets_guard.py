"""Every system skill ships the preview image its gallery modal serves.

``GET /skills/{name}/preview`` streams ``assets/preview.png`` and answers 404
when it is absent; the frontend then swaps in a faint fallback icon. That
fallback is indistinguishable from a working-but-empty thumbnail, which is how
all fourteen system skills shipped without a single preview image and nobody
noticed until a user reported "empty thumbnails" on 2026-07-27.

The images are generated, not hand-drawn: ``scripts/generate_skill_previews.py``
holds one drawing per skill. This guard pins both halves — the file exists on
disk, and it still matches what the generator produces — so a skill added
without a drawing, or a drawing edited without regenerating, fails the build
instead of silently degrading the gallery.
"""

from __future__ import annotations

import importlib.util
import io
import sys

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
SKILLS_DIR = REPO_ROOT / "data" / "skills" / "system"
GENERATOR = REPO_ROOT / "scripts" / "generate_skill_previews.py"

# Mirrors SKILL_PREVIEW_MAX_BYTES in core/constants.py: a larger file is served
# as a 404, so it would be as invisible as a missing one.
PREVIEW_MAX_BYTES = 2_097_152


def _system_skill_names() -> list[str]:
    """Directory names under ``data/skills/system``.

    Returns:
        Sorted skill names, empty when the directory is absent.
    """
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(p.name for p in SKILLS_DIR.iterdir() if p.is_dir())


def _load_generator():  # type: ignore[no-untyped-def]
    """Import the preview generator as a module.

    Returns:
        The imported module.
    """
    spec = importlib.util.spec_from_file_location("generate_skill_previews", GENERATOR)
    assert spec and spec.loader, f"cannot load {GENERATOR}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("skill_name", _system_skill_names())
def test_system_skill_ships_a_preview_image(skill_name: str) -> None:
    """The gallery modal must find an image to serve, within the served size.

    Args:
        skill_name: System skill under test.
    """
    preview = SKILLS_DIR / skill_name / "assets" / "preview.png"

    assert preview.is_file(), (
        f"{skill_name} has no assets/preview.png — its gallery card will fall "
        f"back to a blank icon. Run: python scripts/generate_skill_previews.py"
    )
    size = preview.stat().st_size
    assert 0 < size <= PREVIEW_MAX_BYTES, (
        f"{skill_name}: preview.png is {size} bytes; the endpoint serves a 404 "
        f"above {PREVIEW_MAX_BYTES}, which is as invisible as having none."
    )
    assert preview.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), (
        f"{skill_name}: preview.png is not a PNG — the endpoint declares "
        f"image/png and the browser will refuse it."
    )


def test_every_system_skill_has_a_registered_drawing() -> None:
    """A skill added without a drawing would ship without a preview forever."""
    module = _load_generator()
    missing = sorted(set(_system_skill_names()) - set(module.DRAWINGS))
    assert not missing, (
        f"no drawing registered in scripts/generate_skill_previews.py for: " f"{', '.join(missing)}"
    )


@pytest.mark.parametrize("skill_name", _system_skill_names())
def test_preview_matches_its_generator(skill_name: str) -> None:
    """The committed PNG shows what the generator draws today.

    Without this, editing a drawing silently leaves the old image shipped.

    Compared as **decoded pixels**, not as bytes. Byte equality looked stricter
    and was in fact unusable: zlib's output depends on the platform, so images
    generated on Windows never match a Linux CI run — the first push failed all
    fourteen with "differs from what the generator produces" while every drawing
    was in fact identical. Pixels are the invariant that carries the meaning
    ("the shipped image is the drawing"); the encoding is not.

    Args:
        skill_name: System skill under test.
    """
    module = _load_generator()
    if skill_name not in module.DRAWINGS:
        pytest.skip("covered by test_every_system_skill_has_a_registered_drawing")

    from PIL import Image

    shipped = Image.open(SKILLS_DIR / skill_name / "assets" / "preview.png")
    regenerated = Image.open(io.BytesIO(module.render(skill_name)))

    assert (shipped.size, shipped.mode) == (regenerated.size, regenerated.mode), (
        f"{skill_name}: preview.png is {shipped.size}/{shipped.mode}, the generator "
        f"produces {regenerated.size}/{regenerated.mode}. "
        f"Run: python scripts/generate_skill_previews.py"
    )
    assert shipped.tobytes() == regenerated.tobytes(), (
        f"{skill_name}: preview.png no longer shows what the generator draws. "
        f"Run: python scripts/generate_skill_previews.py"
    )
