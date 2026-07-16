"""Guard for the bounded F028 asyncpg ``Connection._cancel`` warning ignore.

The suite-wide RuntimeWarning ``coroutine 'Connection._cancel' was never
awaited`` is a driver teardown artifact (asyncpg finalizes a GC'd connection
with a pending cancel). It is silenced by a *scoped, message-specific*
``filterwarnings`` entry — but that ignore is only defensible for the pinned
asyncpg version. This guard binds the two together:

* the ignore documents ``driver: asyncpg==<version>`` in its comment;
* the installed asyncpg must equal that documented version.

So the moment asyncpg is bumped, this test fails and forces a human to re-check
whether the driver still leaks and the ignore is still needed (audit F028: "un
test qui échoue dès que l'allowlist n'est plus nécessaire"). It also proves the
ignore stays narrowly scoped and never degrades into a blanket RuntimeWarning
silence.
"""

from __future__ import annotations

import re
import tomllib
from importlib.metadata import version

import pytest

from tests._repo_paths import find_apps_api_root

_INSTALLED_ASYNCPG = version("asyncpg")

_PYPROJECT = find_apps_api_root() / "pyproject.toml"
_TEXT = _PYPROJECT.read_text(encoding="utf-8")
_CONFIG = tomllib.loads(_TEXT)
_FILTERS: list[str] = _CONFIG["tool"]["pytest"]["ini_options"]["filterwarnings"]

_CANCEL_FILTER = "ignore:coroutine 'Connection\\._cancel' was never awaited:RuntimeWarning"


def _documented_asyncpg_version() -> str:
    match = re.search(r"driver:\s*asyncpg==(\d+\.\d+\.\d+)", _TEXT)
    assert match is not None, "F028 allowlist comment must document `driver: asyncpg==X.Y.Z`"
    return match.group(1)


def test_scoped_cancel_ignore_is_present() -> None:
    assert _CANCEL_FILTER in _FILTERS, (
        "the scoped F028 Connection._cancel ignore was removed; if asyncpg no longer "
        "leaks, also delete this guard and the allowlist comment"
    )


def test_installed_asyncpg_matches_the_bounded_version() -> None:
    documented = _documented_asyncpg_version()
    assert _INSTALLED_ASYNCPG == documented, (
        f"asyncpg is now {_INSTALLED_ASYNCPG} but the F028 Connection._cancel ignore is "
        f"bounded to {documented}. Re-run the agents suite under warnings-as-errors: if the "
        "driver no longer leaks, remove the filterwarnings entry (and this guard); otherwise "
        "update the documented `driver: asyncpg==` version and the review_by date."
    )


def test_ignore_never_degrades_to_a_blanket_runtimewarning() -> None:
    blanket = {"ignore::RuntimeWarning", "ignore:::RuntimeWarning", "ignore::Warning"}
    assert not (blanket & set(_FILTERS)), (
        "a blanket RuntimeWarning ignore would mask real un-awaited-coroutine bugs; keep "
        "the F028 ignore message-scoped"
    )


@pytest.mark.parametrize("field", ["owner:", "review_by:", "driver:"])
def test_allowlist_comment_carries_governance_metadata(field: str) -> None:
    assert field in _TEXT, f"F028 bounded-allowlist comment must document `{field}`"
