"""Marketing-claim guard (ADR-215, G6).

Until a qualified mono-provider-profile evidence file exists, public copy
must not promise `turnkey`, `one key`, `one endpoint`, or `zero friction`
installation. The evidence path is the ONLY way to relax this guard —
editing the claim into the docs turns CI red instead.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

FORBIDDEN_CLAIMS = (
    r"\bturn-?key\b",
    r"\bone\s+key\b",
    r"\bone\s+endpoint\b",
    r"\bzero\s+friction\b",
)

SURFACES = (
    "README.md",
    "docs/GETTING_STARTED.md",
    "docs/guides/GUIDE_SELF_HOSTING.md",
    "docs/guides/GUIDE_SHOWROOM.md",
    "docs/technical/DEMO_INSTANCE.md",
    ".github/workflows/release.yml",
    "scripts/install/report.py",
)

EVIDENCE_FILE = "docs/audit/mono-provider-profile-evidence.json"


def test_no_installation_claim_beyond_the_qualified_evidence() -> None:
    root = repo_root_or_skip()
    if (root / EVIDENCE_FILE).is_file():
        pytest.skip("qualified mono-provider evidence exists — claims allowed")
    for surface in SURFACES:
        body = (root / surface).read_text(encoding="utf-8")
        for pattern in FORBIDDEN_CLAIMS:
            match = re.search(pattern, body, re.IGNORECASE)
            assert match is None, (
                f"{surface} claims {match.group(0)!r} without qualified "
                f"evidence ({EVIDENCE_FILE} missing)"
            )
