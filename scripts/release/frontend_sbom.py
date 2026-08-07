"""Frontend SBOM: convert `pnpm licenses list --prod --json` to CycloneDX.

The backend already ships a lockfile-exact CycloneDX SBOM (release.yml);
this closes the gap for the Web artifact (B02). Only production packages
enter (the pnpm invocation is `--prod`), components are sorted for
reproducibility, and pnpm's local filesystem paths never leak into the
published document.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping


def licenses_to_cyclonedx(payload: Mapping[str, object]) -> dict[str, object]:
    """Convert the pnpm license map to a CycloneDX 1.5 BOM.

    Args:
        payload: Parsed `pnpm licenses list --prod --json` output — a map of
            license id → package entries (`name`, `versions`, `paths`,
            `license`).

    Returns:
        A CycloneDX 1.5 document with sorted, path-free components.
    """
    components: list[dict[str, object]] = []
    for entries in payload.values():
        if not isinstance(entries, list):
            raise ValueError("pnpm license map values must be lists")
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError("pnpm license entry must be a mapping")
            name = str(entry["name"])
            license_id = str(entry["license"])
            versions = entry["versions"]
            if not isinstance(versions, list):
                raise ValueError("pnpm license entry versions must be a list")
            for version in versions:
                components.append(
                    {
                        "type": "library",
                        "name": name,
                        "version": str(version),
                        "purl": f"pkg:npm/{name}@{version}",
                        "licenses": [{"license": {"id": license_id}}],
                    }
                )
    components.sort(key=lambda c: (c["name"], c["version"]))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": components,
    }


def main() -> int:
    """Read the pnpm JSON on stdin, write CycloneDX JSON on stdout."""
    payload = json.load(sys.stdin)
    json.dump(licenses_to_cyclonedx(payload), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
