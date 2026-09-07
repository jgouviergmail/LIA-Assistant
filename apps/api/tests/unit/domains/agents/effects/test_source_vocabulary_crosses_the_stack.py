"""The register's vocabulary means the same thing on both sides of the wire.

`proactive` was added to :class:`EffectSource`, rows started arriving with it,
and the frontend's union still listed three values. TypeScript could not
complain — the value comes from an API response — so the badge rendered the raw
translation key to the user, and every test stayed green because none of them
rendered a proactive row.

The frontend has its own guard for the LABELS. This one guards the thing that
guard cannot see: that the two lists are the same list. A value the backend can
emit and the frontend does not know is a badge nobody wrote; a value the
frontend knows and the backend cannot emit is dead vocabulary that reads as
supported.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domains.agents.effects.models import EffectSource
from src.domains.agents.effects.origin import RegisterOrigin

pytestmark = pytest.mark.unit

_WEB_TYPES = Path(__file__).resolve().parents[6] / "web" / "src" / "types"

#: Where the frontend declares each vocabulary, as a RUNTIME list so both this
#: guard and the frontend's own can iterate it.
_TYPES_FILE = _WEB_TYPES / "effects.ts"
_ORIGIN_FILE = _WEB_TYPES / "register-origin.ts"


def _declared(path: Path, constant: str) -> set[str]:
    """The values one frontend runtime list declares.

    Args:
        path: The ``.ts`` file holding the declaration.
        constant: The exported constant's name.

    Returns:
        The declared string values.
    """
    match = re.search(
        rf"export const {constant} = \[(?P<values>[^\]]*)\] as const;",
        path.read_text(encoding="utf-8"),
    )
    assert match is not None, (
        f"{constant} not found in {path.name} — if the declaration moved, move "
        "this guard with it rather than deleting it"
    )
    return {value.strip().strip("'\"") for value in match["values"].split(",") if value.strip()}


def _frontend_sources() -> set[str]:
    """The authorships the frontend declares."""
    return _declared(_TYPES_FILE, "EFFECT_SOURCES")


def _frontend_origins() -> set[str]:
    """The readings the frontend declares."""
    return _declared(_ORIGIN_FILE, "REGISTER_ORIGINS")


class TestTheTwoSidesShareOneVocabulary:
    def test_the_frontend_file_is_where_this_guard_expects_it(self) -> None:
        assert _TYPES_FILE.is_file(), f"{_TYPES_FILE} not found"

    def test_no_authorship_reaches_a_frontend_that_cannot_name_it(self) -> None:
        backend = {member.value for member in EffectSource}
        missing = backend - _frontend_sources()
        assert not missing, (
            f"the API can emit {sorted(missing)} and the frontend declares no badge "
            "for it — the register would show the raw translation key"
        )

    def test_the_frontend_declares_nothing_the_backend_cannot_emit(self) -> None:
        backend = {member.value for member in EffectSource}
        extra = _frontend_sources() - backend
        assert not extra, f"declared in the frontend but never emitted: {sorted(extra)}"


class TestTheTwoSidesShareOneReadingVocabulary:
    """The same trap, one level up.

    ``RegisterOrigin`` selects WHICH rows a tab holds. A reading the backend
    accepts and the frontend cannot name is a tab nobody can open; one the
    frontend sends and the backend rejects is a tab that 422s. Neither is
    visible to a type union, which exists only at compile time — the very
    reason ``EFFECT_SOURCES`` is a runtime list.
    """

    def test_the_frontend_file_is_where_this_guard_expects_it(self) -> None:
        assert _ORIGIN_FILE.is_file(), f"{_ORIGIN_FILE} not found"

    def test_no_reading_is_offered_that_the_frontend_cannot_name(self) -> None:
        backend = {member.value for member in RegisterOrigin}
        missing = backend - _frontend_origins()
        assert not missing, (
            f"the API accepts {sorted(missing)} and the frontend declares no " "reading for it"
        )

    def test_the_frontend_asks_for_nothing_the_backend_refuses(self) -> None:
        backend = {member.value for member in RegisterOrigin}
        extra = _frontend_origins() - backend
        assert not extra, (
            f"declared in the frontend but not a RegisterOrigin: {sorted(extra)} "
            "— the request would be rejected"
        )
