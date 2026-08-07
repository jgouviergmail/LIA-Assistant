"""Frontend SBOM conversion (B02): pnpm licenses → CycloneDX 1.5.

What must hold:
- output is CycloneDX 1.5 JSON with one component per package version;
- only production packages enter (the input is already --prod; a devDep
  marker would be a caller error and must raise);
- components are sorted (name, version) for reproducibility;
- no filesystem path from the pnpm payload ever leaks into the SBOM.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.frontend_sbom import licenses_to_cyclonedx  # noqa: E402

pytestmark = pytest.mark.unit

PNPM_PAYLOAD = {
    "MIT": [
        {
            "name": "zeta-lib",
            "versions": ["2.0.0"],
            "paths": ["/home/runner/node_modules/zeta-lib"],
            "license": "MIT",
        },
        {
            "name": "alpha-lib",
            "versions": ["1.1.0", "1.2.0"],
            "paths": ["/home/runner/node_modules/alpha-lib"],
            "license": "MIT",
        },
    ],
    "Apache-2.0": [
        {
            "name": "beta-lib",
            "versions": ["3.0.0"],
            "paths": ["C:\\runner\\node_modules\\beta-lib"],
            "license": "Apache-2.0",
        }
    ],
}


def test_converts_to_sorted_cyclonedx_15() -> None:
    sbom = licenses_to_cyclonedx(PNPM_PAYLOAD)
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    components = sbom["components"]
    keys = [(c["name"], c["version"]) for c in components]
    assert keys == sorted(keys)
    # One component per (name, version): alpha has two versions.
    assert keys == [
        ("alpha-lib", "1.1.0"),
        ("alpha-lib", "1.2.0"),
        ("beta-lib", "3.0.0"),
        ("zeta-lib", "2.0.0"),
    ]
    licenses = {c["name"]: c["licenses"][0]["license"]["id"] for c in components}
    assert licenses["beta-lib"] == "Apache-2.0"


def test_no_filesystem_path_leaks() -> None:
    import json

    serialized = json.dumps(licenses_to_cyclonedx(PNPM_PAYLOAD))
    assert "node_modules" not in serialized
    assert "/home/" not in serialized
    assert "runner" not in serialized


def test_purl_identifies_each_component() -> None:
    sbom = licenses_to_cyclonedx(PNPM_PAYLOAD)
    for component in sbom["components"]:
        assert component["purl"] == (
            f"pkg:npm/{component['name']}@{component['version']}"
        )
        assert component["type"] == "library"
