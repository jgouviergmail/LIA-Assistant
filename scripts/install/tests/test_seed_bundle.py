"""Python seed-bundle digest contract (B09).

``compute_seed_bundle_sha256`` must produce byte-for-byte the digest that
``apps/api/scripts/data/apply_reference_seeds.sh`` recomputes in-container:
six records ``<repo-relative POSIX path> NUL <sha256 of raw bytes> LF`` in
invocation order, hashed together. Any file change must change the digest.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from scripts.install.seed_bundle import (
    SEED_BUNDLE_FILES,
    SeedBundleError,
    compute_seed_bundle_sha256,
)
from scripts.install.tests.conftest import REPO_ROOT

EXPECTED_ORDER = (
    "google_api_pricing_seed.sql",
    "image_generation_pricing_seed.sql",
    "llm_config_seed.sql",
    "llm_pricing_seed.sql",
    "personalities_seed.sql",
    "verify_reference_seeds.sql",
)


def _independent_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for name in EXPECTED_ORDER:
        path = root / "infrastructure" / "database" / "seeds" / name
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(
            f"infrastructure/database/seeds/{name}".encode()
            + b"\0"
            + file_hash.encode()
            + b"\n"
        )
    return digest.hexdigest()


def test_order_matches_the_sh_wrapper_invocation_order() -> None:
    assert SEED_BUNDLE_FILES == EXPECTED_ORDER


def test_repo_digest_matches_the_independent_reimplementation() -> None:
    digest = compute_seed_bundle_sha256(REPO_ROOT)
    assert digest == _independent_digest(REPO_ROOT)
    assert len(digest) == 64 and digest == digest.lower()


def test_any_file_change_changes_the_digest(tmp_path: Path) -> None:
    seeds_src = REPO_ROOT / "infrastructure" / "database" / "seeds"
    seeds_dst = tmp_path / "infrastructure" / "database" / "seeds"
    seeds_dst.mkdir(parents=True)
    for name in EXPECTED_ORDER:
        shutil.copy(seeds_src / name, seeds_dst / name)
    baseline = compute_seed_bundle_sha256(tmp_path)
    assert baseline == compute_seed_bundle_sha256(REPO_ROOT)
    for name in EXPECTED_ORDER:
        target = seeds_dst / name
        original = target.read_bytes()
        target.write_bytes(original + b"\n-- mutated\n")
        assert compute_seed_bundle_sha256(tmp_path) != baseline, name
        target.write_bytes(original)


def test_a_missing_seed_file_is_a_stable_error(tmp_path: Path) -> None:
    with pytest.raises(SeedBundleError) as excinfo:
        compute_seed_bundle_sha256(tmp_path)
    assert "google_api_pricing_seed.sql" in str(excinfo.value)
