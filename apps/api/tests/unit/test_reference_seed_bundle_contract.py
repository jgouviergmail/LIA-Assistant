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
    try:
        SystemSetting.__table__.create(engine)
        with Session(engine) as session:
            session.add(SystemSetting(key=SystemSettingKey.SELF_HOST_SEED_BUNDLE, value="a" * 64))
            session.commit()
            raw = session.execute(text("SELECT key FROM system_settings")).scalar_one()
            assert raw == "SELF_HOST_SEED_BUNDLE", (
                "Enum(native_enum=False) persists MEMBER NAMES — raw SQL must "
                "write this exact token"
            )
            loaded = session.query(SystemSetting).one()
            assert loaded.key is SystemSettingKey.SELF_HOST_SEED_BUNDLE
            assert loaded.value == "a" * 64
    finally:
        # Every async client/pool/connection has an owner that closes it — the
        # in-memory engine held its sqlite3 connection open past the test and
        # surfaced as a ResourceWarning at the leak guard's gc.collect().
        engine.dispose()


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


# ===========================================================================
# The demo preflight — third holder of the bundle's file list (2026-08-19)
# ===========================================================================

_PREFLIGHT = ROOT / "scripts" / "deploy" / "preflight-demo-prod.sh"
_DEMO_DRIVER = ROOT / "scripts" / "deploy" / "demo-prod.ps1"


def _seed_files_of(path: Path) -> list[str]:
    """The `SEED_FILES="..."` list a shell script hashes, in its own order."""
    block = path.read_text(encoding="utf-8").split('SEED_FILES="', 1)[1].split('"', 1)[0]
    return [line.strip() for line in block.splitlines() if line.strip()]


def _preflight_seed_files() -> list[str]:
    return _seed_files_of(_PREFLIGHT)


def _wrapper_seed_files() -> list[str]:
    return _seed_files_of(WRAPPER)


def test_the_preflight_hashes_exactly_the_bundle_in_the_same_order() -> None:
    """A third copy of the list is a third chance to drift.

    The preflight refuses a demo start whose seeds differ from the operator's
    tree. If its list ever fell out of step with the applier's, it would
    compute a DIFFERENT digest from correct files and refuse a perfectly good
    host — a guard that cries wolf gets disabled, which is worse than none.
    """
    assert _preflight_seed_files() == _wrapper_seed_files()


def test_the_demo_driver_hands_the_digest_to_the_preflight() -> None:
    """Otherwise the check sits there, silent, and proves nothing.

    The preflight compares against ``SEED_BUNDLE_SHA256``; unset, it skips.
    Every path that runs the preflight must therefore pass the digest the
    driver just computed from the local tree.
    """
    driver = _DEMO_DRIVER.read_text(encoding="utf-8")
    calls = driver.count("preflight-demo-prod.sh")
    armed = driver.count("SEED_BUNDLE_SHA256=$seedDigest sh scripts/deploy/preflight-demo-prod.sh")
    assert calls > 0, "the demo driver no longer runs the preflight at all"
    assert armed == calls, (
        f"{calls - armed} preflight call(s) run without SEED_BUNDLE_SHA256: the "
        "seed-drift check silently skips, and `demo:prod:up` goes back to "
        "failing inside the container after the migrations."
    )


def test_the_preflight_names_the_command_that_fixes_a_seed_drift() -> None:
    """A refusal that does not say what to do costs a round-trip.

    The remedy is an ORDER — ship the files, then start — and it is the part
    nobody could infer from two 64-hex strings.
    """
    text = _PREFLIGHT.read_text(encoding="utf-8")
    drift_section = text.split("3ter.", 1)[1].split("--- 4.", 1)[0]
    assert "task deploy:prod" in drift_section


def test_the_preflight_hashes_a_literal_backslash_zero_not_a_nul_byte() -> None:
    """The separator is TWO characters, and writing it as one silently rots.

    Authoring this check embedded a real NUL byte in the script instead of the
    ``\0`` escape (2026-08-19). Every syntax check still passed, the refusal
    path still fired, and the digest it computed was simply WRONG — so a host
    carrying the right seeds would have been refused, and the guard would have
    been switched off as unreliable. A binary byte in a POSIX script is never
    intentional here.
    """
    raw = _PREFLIGHT.read_bytes()
    assert b"\x00" not in raw, (
        "preflight-demo-prod.sh contains a NUL byte: the bundle-digest printf "
        "must carry the two-character escape \0, not the byte it denotes."
    )
    assert rb"printf '%s\0%s\n'" in raw, (
        "the preflight must hash the same <path NUL sha256 LF> records as "
        "apply_reference_seeds.sh, or its digest cannot be compared to theirs."
    )
