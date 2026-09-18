"""What the sandbox promises to import, it can import (ADR-298, lot 5).

The ``<Computation>`` block and the manifest name the libraries a script may
use. A name that does not import in the sandbox image sends the model on a
failing run it then « corrects » for nothing; a name that rides a TRANSITIVE
dependency dies on somebody else's upgrade. So the catalogue is one declared
table, every distribution is a DIRECT entry of the manifest (ADR-112), and
every import name is tried — here on the lockfile CI installs, and in the
built image by ``task sandbox:libraries:check``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domains.agents.python_sandbox.libraries import (
    LIBRARY_GROUPS,
    PYTHON_SANDBOX_LIBRARIES,
    SandboxLibrary,
    missing_libraries,
    render_libraries,
)

pytestmark = pytest.mark.unit

_MANIFEST = Path(__file__).resolve().parents[5] / "requirements.txt"
_DIRECT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*[=<>~!]", re.M)


def _direct_distributions() -> set[str]:
    text = _MANIFEST.read_text(encoding="utf-8")
    return {m.group(1).lower().replace("_", "-") for m in _DIRECT.finditer(text)}


class TestTheTableIsWellFormed:
    def test_every_entry_is_complete_and_unique(self) -> None:
        names = [lib.import_name for lib in PYTHON_SANDBOX_LIBRARIES]
        assert len(names) == len(set(names)), "an import name is declared twice"
        for lib in PYTHON_SANDBOX_LIBRARIES:
            assert isinstance(lib, SandboxLibrary)
            assert lib.import_name and lib.distribution and lib.use
            assert lib.group in LIBRARY_GROUPS, f"{lib.import_name}: unknown group {lib.group!r}"

    def test_every_group_has_at_least_one_library(self) -> None:
        used = {lib.group for lib in PYTHON_SANDBOX_LIBRARIES}
        assert used == set(LIBRARY_GROUPS), "an empty group is a heading over nothing"

    def test_every_distribution_is_a_direct_manifest_entry(self) -> None:
        """The promise never rides a transitive dependency (ADR-112)."""
        direct = _direct_distributions()
        missing = sorted(
            lib.distribution
            for lib in PYTHON_SANDBOX_LIBRARIES
            if lib.distribution.lower().replace("_", "-") not in direct
        )
        assert not missing, f"promised but not pinned directly in requirements.txt: {missing}"


class TestThePromiseHolds:
    def test_every_import_name_imports_on_the_installed_lockfile(self) -> None:
        """CI installs the same lockfile the image does; a name that fails here
        would fail in the sandbox."""
        assert missing_libraries() == ()

    def test_missing_libraries_names_what_does_not_import(self) -> None:
        def _importer(name: str) -> object:
            if name == "pandas":
                raise ImportError(name)
            return object()

        assert missing_libraries(importer=_importer) == ("pandas",)


class TestTheRendering:
    def test_one_line_per_group_in_declaration_order(self) -> None:
        lines = render_libraries().splitlines()
        assert [line.split(":")[0] for line in lines] == list(LIBRARY_GROUPS)
        for lib in PYTHON_SANDBOX_LIBRARIES:
            assert lib.import_name in render_libraries()

    def test_a_library_is_named_by_its_import_name_not_its_distribution(self) -> None:
        """The model writes ``import bs4``, never ``import beautifulsoup4``."""
        rendered = render_libraries()
        assert "bs4" in rendered and "beautifulsoup4" not in rendered
        assert "fitz" in rendered and "PyMuPDF" not in rendered
