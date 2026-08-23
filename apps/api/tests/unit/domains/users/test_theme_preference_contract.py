"""Cross-layer contract for the ``users.theme`` display preference.

The frontend encodes the OLED mode as the stored value ``"oled"`` — meaning
"dark, with absolute black" — because ``User.theme`` is a plain ``String(20)``
with no ``Literal``, no validator and no backend consumer. That is a deliberate
decision (it needs no migration), but it rests entirely on properties nothing
was asserting: the day someone tightens the field to
``Literal["light", "dark", "system"]``, or shortens the column, every OLED user
silently stops being able to save their preference and the failure surfaces as
a 422 in a PATCH nobody watches.

These tests make that contract opposable from the backend side, where the
change would actually be made.

The list is intentionally a MIRROR of ``apps/web/src/lib/theme-mode.ts``
(``PERSISTED``); adding a value on one side without the other is precisely the
drift being guarded.
"""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domains.shared.schemas import VALID_THEMES
from src.domains.users.models import User
from src.domains.users.schemas import UserUpdate

# Read from the server-side source of truth rather than restated, so this file
# cannot drift from the tuple it is guarding.
SUPPORTED_THEMES = VALID_THEMES


@pytest.mark.parametrize("theme", SUPPORTED_THEMES)
def test_user_update_accepts_every_shipped_theme(theme: str) -> None:
    """Every value the frontend can persist must survive schema validation."""
    assert UserUpdate(theme=theme).theme == theme


@pytest.mark.parametrize("theme", SUPPORTED_THEMES)
def test_every_shipped_theme_fits_the_column(theme: str) -> None:
    """The stored value must fit ``String(20)``.

    ``oled`` is the longest addition so far; a future ``dark-high-contrast``
    would not fit and must widen the column rather than be silently truncated.
    """
    column = User.__table__.columns["theme"]
    assert column.type.length is not None
    assert len(theme) <= column.type.length


def test_theme_field_rejects_a_mode_that_does_not_exist() -> None:
    """The field IS validated — which is exactly why the two sides must agree.

    Found by this test: `theme` is guarded by `validate_theme_field` in a shared
    mixin, several files away from its declaration. The frontend had shipped
    `"oled"` against a tuple that did not contain it, and the failure mode was
    invisible — the UI applies the change locally and only the PATCH answers
    422, so everything looks right until the next page load.
    """
    with pytest.raises(ValidationError, match="Invalid theme"):
        UserUpdate(theme="a-mode-that-does-not-exist-yet")


def test_backend_and_frontend_agree_on_the_shipped_modes() -> None:
    """The two halves of the contract, compared rather than trusted.

    `VALID_THEMES` here and `PERSISTED` in `theme-mode.ts` describe the same
    set. A comment asking both to be kept in sync is not a guard; reading the
    other side is.
    """
    # Anchored on apps/api rather than an index into the repo root, so moving
    # this file one directory deeper does not silently point it at nothing.
    api_root = Path(__file__).resolve().parents[4]
    theme_mode_ts = api_root.parent / "web" / "src" / "lib" / "theme-mode.ts"
    # Deliberately an assert and not a skip: a contract that quietly stops being
    # checked is worse than one that was never written.
    assert theme_mode_ts.is_file(), f"frontend contract not found at {theme_mode_ts}"

    source = theme_mode_ts.read_text(encoding="utf-8")
    match = re.search(r"const PERSISTED = new Set\(\[([^\]]*)\]\)", source)
    assert match, "PERSISTED set not found in theme-mode.ts"

    frontend = set(re.findall(r"'([^']+)'", match.group(1)))
    assert frontend == set(
        VALID_THEMES
    ), f"frontend persists {sorted(frontend)}, backend accepts {sorted(VALID_THEMES)}"


def test_theme_is_optional_so_a_partial_patch_leaves_it_alone() -> None:
    """A PATCH that touches only the colour theme must not reset the mode."""
    update = UserUpdate(color_theme="ocean")
    assert update.theme is None
    assert update.model_dump(exclude_unset=True) == {"color_theme": "ocean"}


def test_theme_column_defaults_to_system() -> None:
    """``system`` is where every account starts.

    The frontend's header toggle deliberately cycles only light -> dark -> OLED,
    so Settings must keep offering ``system`` — this default is the reason why.
    """
    column = User.__table__.columns["theme"]
    assert column.default.arg == "system"
    assert column.server_default.arg == "system"
    assert column.nullable is False


def test_theme_rejects_a_non_string() -> None:
    """Guard the obvious: the column is text, not an enum id or a flag."""
    with pytest.raises(ValidationError):
        UserUpdate(theme=["dark"])
