"""The README's « N+ building blocks » stays true against the living map.

The home page computes its « 60+ » from the living map's brick count, floored
to ten (``apps/web/src/components/landing/comparison/brick-floor.ts``). The
README quotes the same claim as prose (owner, 2026-11-15), and a number no CI
reads drifts in silence. A floor cannot go stale as bricks are added: it turns
false the day the map holds fewer bricks than it promises, and this guard is
what notices.
"""

from __future__ import annotations

import json
import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

README = "README.md"
FUNCTIONAL_MAP = "apps/web/src/data/maps/functional.json"
BRICK_CLAIM = re.compile(r"\b(?P<count>\d+)\+ building blocks\b")


def brick_claims(text: str) -> list[int]:
    """Every « N+ building blocks » a document states.

    Args:
        text: The document's contents.

    Returns:
        The quoted floors, in reading order.
    """
    return [int(match.group("count")) for match in BRICK_CLAIM.finditer(text)]


def unkept_claims(text: str, bricks: int) -> list[int]:
    """The quoted floors the living map no longer holds.

    Args:
        text: The document's contents.
        bricks: The number of bricks the functional map declares.

    Returns:
        Each floor above ``bricks``, in reading order.
    """
    return [claim for claim in brick_claims(text) if claim > bricks]


def test_a_floor_above_the_map_is_refused_and_a_kept_one_passes() -> None:
    text = "A complete environment of 70+ building blocks, then 60+ building blocks."
    assert brick_claims(text) == [70, 60]
    assert unkept_claims(text, bricks=60) == [70]
    assert unkept_claims(text, bricks=75) == []


def test_the_readme_promises_no_more_bricks_than_the_map_holds() -> None:
    root = repo_root_or_skip()
    readme = (root / README).read_text(encoding="utf-8")
    bricks = len(json.loads((root / FUNCTIONAL_MAP).read_text(encoding="utf-8"))["bricks"])
    # A guard that reads no claim guards nothing: drop it with the sentence.
    assert brick_claims(readme), f"{README} no longer quotes « N+ building blocks »"
    assert unkept_claims(readme, bricks) == [], (
        f"{README} promises more building blocks than {FUNCTIONAL_MAP} holds ({bricks}): "
        "quote a floor the map keeps"
    )
