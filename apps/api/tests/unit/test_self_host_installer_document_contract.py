"""Static contracts for the self-host installer governing documents.

The July 29 design/plan stay historical context; the 2026-08-05 audit
addendum and activation plan govern every conflict. ADR-215 is the unique
installer architecture identifier (ADR-179 is already occupied).
"""

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()


def test_baseline_documents_delegate_to_the_august_addendum() -> None:
    spec = (ROOT / "docs/superpowers/specs/2026-07-29-self-host-installer-design.md").read_text(
        encoding="utf-8"
    )
    plan = (ROOT / "docs/superpowers/plans/2026-07-29-self-host-installer.md").read_text(
        encoding="utf-8"
    )
    active = "2026-08-05-self-host-installer-audit-addendum.md"
    assert active in spec
    assert active in plan
    assert len(re.findall(r"^- \[ \]", plan, flags=re.MULTILINE)) == 70
    assert re.search(r"^- \[[xX]\]", plan, flags=re.MULTILINE) is None


def test_adr_215_is_unique_and_indexed() -> None:
    adr = ROOT / "docs/architecture/ADR-215-Self-Host-Installer.md"
    assert adr.is_file()
    assert "# ADR-215:" in adr.read_text(encoding="utf-8")
    index = (ROOT / "docs/architecture/ADR_INDEX.md").read_text(encoding="utf-8")
    assert adr.name in index
