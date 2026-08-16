"""Atomic reference-seed bundle contract (ADR-215, B09).

What must hold:
- the wrapper runs ONE psql process with ON_ERROR_STOP=1 and
  --single-transaction over the five seed files plus the verifier (last);
  no loop launches psql per file;
- the wrapper recomputes the six-record digest from the LOGICAL
  repository-relative names and refuses a mismatch before any database
  call; a non-zero psql exit propagates and never prints success;
- the verification SQL raises blocking exceptions for every domain and
  writes the marker in the same transaction, using the persisted enum
  member-name token SELF_HOST_SEED_BUNDLE;
- the ORM round-trips that raw token (Enum(native_enum=False) stores
  member names);
- the entrypoint refuses a non-empty marker and requires
  SEED_BUNDLE_SHA256.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()
WRAPPER = ROOT / "apps/api/scripts/data/apply_reference_seeds.sh"
VERIFY_SQL = ROOT / "infrastructure/database/seeds/verify_reference_seeds.sql"
ENTRYPOINT = ROOT / "apps/api/docker-entrypoint.sh"

SEED_ORDER = [
    "google_api_pricing_seed.sql",
    "image_generation_pricing_seed.sql",
    "llm_config_seed.sql",
    "llm_pricing_seed.sql",
    "personalities_seed.sql",
    "verify_reference_seeds.sql",
]


def _wrapper_body() -> str:
    return WRAPPER.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Static wrapper contract
# ---------------------------------------------------------------------------


def test_single_psql_invocation_with_transaction() -> None:
    body = _wrapper_body()
    assert "ON_ERROR_STOP=1" in body
    assert "--single-transaction" in body
    assert body.count('"$PSQL_BIN"') == 1, "exactly one psql invocation"
    assert "for seed_file" not in body
    # The six -f arguments appear in the exact order, verifier LAST.
    positions = [body.find(f'-f "$SEEDS_DIR/{name}"') for name in SEED_ORDER]
    assert all(p != -1 for p in positions), positions
    assert positions == sorted(positions)
    assert "seed_bundle_version=$expected" in body


def test_verify_sql_blocks_and_marks_in_one_transaction() -> None:
    body = VERIFY_SQL.read_text(encoding="utf-8")
    assert body.count("RAISE EXCEPTION") >= 6
    for table, bound in [
        ("personalities", "14"),
        ("personality_translations", "84"),
        ("google_api_pricing", "9"),
        ("image_generation_pricing", "27"),
        # Floors re-audited 2026-08-15 (seed regenerated from production:
        # 139 pricing rows incl. audio-hour units, 42 overrides).
        ("llm_model_pricing", "139"),
        ("llm_config_overrides", "42"),
    ]:
        assert table in body and bound in body
    marker_pos = body.find("INSERT INTO system_settings")
    assert marker_pos > body.rfind(
        "RAISE EXCEPTION"
    ), "the marker insert must FOLLOW every check in the same transaction"
    assert "'SELF_HOST_SEED_BUNDLE'" in body
    assert ":'seed_bundle_version'" in body


def test_entrypoint_gates_on_marker_and_digest() -> None:
    body = ENTRYPOINT.read_text(encoding="utf-8")
    assert "SELF_HOST_SEED_BUNDLE" in body
    assert "SEED_BUNDLE_SHA256" in body
    assert "apply_reference_seeds.sh" in body


# ---------------------------------------------------------------------------
# ORM round-trip of the raw member-name token
# ---------------------------------------------------------------------------


def test_marker_key_roundtrips_through_the_orm() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from src.domains.system_settings.models import SystemSetting, SystemSettingKey

    engine = create_engine("sqlite://")
    SystemSetting.__table__.create(engine)
    with Session(engine) as session:
        session.add(SystemSetting(key=SystemSettingKey.SELF_HOST_SEED_BUNDLE, value="a" * 64))
        session.commit()
        raw = session.execute(text("SELECT key FROM system_settings")).scalar_one()
        assert raw == "SELF_HOST_SEED_BUNDLE", (
            "Enum(native_enum=False) persists MEMBER NAMES — raw SQL must " "write this exact token"
        )
        loaded = session.query(SystemSetting).one()
        assert loaded.key is SystemSettingKey.SELF_HOST_SEED_BUNDLE
        assert loaded.value == "a" * 64


# ---------------------------------------------------------------------------
# Executable behavior (POSIX shell required — skipped where unavailable)
# ---------------------------------------------------------------------------


def _sh() -> str | None:
    return shutil.which("sh")


def _make_seed_tree(tmp_path: Path) -> Path:
    """Build (or rebuild) the seed tree; callers may hash it then run it."""
    seeds = tmp_path / "seeds"
    # Idempotent: a test that hashes the tree and then executes the wrapper
    # builds it twice on the same tmp_path.
    seeds.mkdir(exist_ok=True)
    for name in SEED_ORDER:
        (seeds / name).write_text(f"-- {name}\n", encoding="utf-8")
    return seeds


def _expected_digest(seeds: Path) -> str:
    digest = hashlib.sha256()
    for name in SEED_ORDER:
        file_hash = hashlib.sha256((seeds / name).read_bytes()).hexdigest()
        digest.update(
            f"infrastructure/database/seeds/{name}".encode() + b"\0" + file_hash.encode() + b"\n"
        )
    return digest.hexdigest()


def _fake_psql(tmp_path: Path, exit_code: int) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "psql"
    fake.write_text(
        '#!/bin/sh\nprintf \'%s \' "$@" > "$FAKE_PSQL_ARGV"\n' f"exit {exit_code}\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return fake


@pytest.mark.skipif(_sh() is None, reason="POSIX sh unavailable")
class TestWrapperExecution:
    def _run(
        self, tmp_path: Path, digest: str, psql_exit: int = 0
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        seeds = _make_seed_tree(tmp_path)
        _fake_psql(tmp_path, psql_exit)
        argv_file = tmp_path / "argv.txt"
        env = {
            **os.environ,
            "SEEDS_DIR": seeds.as_posix(),
            "PSQL_BIN": (tmp_path / "bin" / "psql").as_posix(),
            "FAKE_PSQL_ARGV": argv_file.as_posix(),
            "POSTGRES_USER": "u",
            "POSTGRES_DB": "d",
        }
        proc = subprocess.run(
            [_sh(), WRAPPER.as_posix(), digest],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        return proc, argv_file

    def test_valid_digest_invokes_psql_once(self, tmp_path: Path) -> None:
        seeds_digest = _expected_digest(_make_seed_tree(tmp_path))
        proc, argv_file = self._run(tmp_path, seeds_digest)
        assert proc.returncode == 0, proc.stderr
        argv = argv_file.read_text(encoding="utf-8")
        assert "--single-transaction" in argv
        assert "ON_ERROR_STOP=1" in argv
        assert argv.count("-f ") == 6

    def test_digest_mismatch_refuses_before_psql(self, tmp_path: Path) -> None:
        proc, argv_file = self._run(tmp_path, "0" * 64)
        assert proc.returncode == 3
        assert "mismatch" in proc.stderr
        assert not argv_file.exists(), "psql must never run on a digest mismatch"

    def test_psql_failure_propagates(self, tmp_path: Path) -> None:
        seeds_digest = _expected_digest(_make_seed_tree(tmp_path))
        proc, _ = self._run(tmp_path, seeds_digest, psql_exit=7)
        assert proc.returncode == 7
        assert "success" not in proc.stdout.lower()
