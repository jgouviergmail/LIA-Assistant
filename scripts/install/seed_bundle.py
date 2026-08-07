"""Seed-bundle digest (B09) — Python twin of ``apply_reference_seeds.sh``.

Both sides hash the SAME six records — ``<repo-relative POSIX path> NUL
<lowercase sha256 of raw bytes> LF`` in invocation order — so the digest
the installer computes on the host is the digest the in-container wrapper
recomputes and refuses to diverge from.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Invocation order of apply_reference_seeds.sh (verifier LAST).
SEED_BUNDLE_FILES: tuple[str, ...] = (
    "google_api_pricing_seed.sql",
    "image_generation_pricing_seed.sql",
    "llm_config_seed.sql",
    "llm_pricing_seed.sql",
    "personalities_seed.sql",
    "verify_reference_seeds.sql",
)

_SEEDS_SUBDIR = ("infrastructure", "database", "seeds")


class SeedBundleError(ValueError):
    """A seed file is missing — the bundle identity cannot be computed."""


def compute_seed_bundle_sha256(root: Path) -> str:
    """Compute the six-record bundle digest under ``root``.

    Args:
        root: Repository/bundle root containing
            ``infrastructure/database/seeds/``.

    Returns:
        64-hex lowercase digest.

    Raises:
        SeedBundleError: Naming every missing seed file.
    """
    seeds_dir = root.joinpath(*_SEEDS_SUBDIR)
    missing = [
        name for name in SEED_BUNDLE_FILES if not (seeds_dir / name).is_file()
    ]
    if missing:
        raise SeedBundleError(f"missing seed files: {' '.join(missing)}")
    digest = hashlib.sha256()
    for name in SEED_BUNDLE_FILES:
        file_hash = hashlib.sha256((seeds_dir / name).read_bytes()).hexdigest()
        record_path = "/".join((*_SEEDS_SUBDIR, name))
        digest.update(record_path.encode() + b"\0" + file_hash.encode() + b"\n")
    return digest.hexdigest()
