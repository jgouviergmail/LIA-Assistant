"""Read-only installation verifier beyond readiness (ADR-215, B12).

Invoked as ``python -m scripts.data.verify_installation --admin-email X
--seed-bundle-sha256 <64-hex>`` from the API container workdir, AFTER
``/ready`` reports healthy. ``/ready`` proves the process serves; this
verifier proves the INSTALL is functional:

- exactly one Alembic head in the code's script directory AND exactly one
  ``alembic_version`` row equal to it;
- the ``SELF_HOST_SEED_BUNDLE`` marker equals the EXACT expected bundle
  digest computed by the installer (never merely non-empty);
- the reference-data postconditions of ``verify_reference_seeds.sql`` still
  hold (same thresholds — that file is the contract's single source);
- the requested admin is active, verified, and superuser;
- every derived required provider key row exists and decrypts;
- every core LLM slot resolves inside the derived provider set on the
  POST-SEED effective configuration read from the real database rows.

All checks run even after one fails so the operator gets ONE complete
report. Output is stable non-secret JSON; no decrypted value is ever
included. Exit 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

#: (label, threshold, exact) — the SAME order and thresholds as
#: ``verify_reference_seeds.sql``, which is the authority. The two are pinned
#: together by ``test_reference_counts_mirror_the_seed_sql``: this copy had
#: silently drifted on four of six rows, and the one that had become STRICTER
#: than the SQL (``llm_config_overrides``, left at 41 when ADR-244 lowered the
#: floor to 39) declared a correct fresh install broken.
_REFERENCE_COUNTS: tuple[tuple[str, int, bool], ...] = (
    ("personalities", 14, True),
    ("personality_translations", 84, True),
    ("google_api_pricing", 18, False),
    ("image_generation_pricing", 27, False),
    ("llm_model_pricing", 139, False),
    ("llm_config_overrides", 39, False),
    ("llm_models", 124, False),
)

_REFERENCE_COUNTS_SQL = text(
    "SELECT"
    " (SELECT COUNT(*) FROM personalities) AS personalities,"
    " (SELECT COUNT(*) FROM personality_translations) AS personality_translations,"
    " (SELECT COUNT(*) FROM google_api_pricing) AS google_api_pricing,"
    " (SELECT COUNT(*) FROM image_generation_pricing) AS image_generation_pricing,"
    " (SELECT COUNT(*) FROM llm_model_pricing) AS llm_model_pricing,"
    " (SELECT COUNT(*) FROM llm_config_overrides) AS llm_config_overrides,"
    " (SELECT COUNT(*) FROM llm_models) AS llm_models"
)


class CheckName(str, Enum):
    """Independent installation checks, reported in this order."""

    MIGRATIONS = "migrations"
    SEED_MARKER = "seed_marker"
    REFERENCE_DATA = "reference_data"
    ADMIN = "admin"
    PROVIDER_KEYS = "provider_keys"
    PROVIDER_COVERAGE = "provider_coverage"


@dataclass(frozen=True)
class CheckResult:
    """One check outcome (stable code, value-free detail)."""

    name: CheckName
    passed: bool
    code: str
    detail: str


def load_single_alembic_head(config_path: Path) -> str:
    """Return the single head revision of the code's migration graph.

    Args:
        config_path: Path to ``alembic.ini``.

    Returns:
        The unique head revision id.

    Raises:
        RuntimeError: When the script directory has zero or multiple heads
            (a broken revision chain must fail before touching the DB).
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(config_path)))
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"expected exactly one Alembic head, found {len(heads)}")
    return heads[0]


async def _check_migrations(db: AsyncSession, expected_head: str) -> CheckResult:
    rows = (await db.execute(text("SELECT version_num FROM alembic_version"))).fetchall()
    if not rows:
        return CheckResult(CheckName.MIGRATIONS, False, "no_db_revision", "")
    if len(rows) > 1:
        return CheckResult(
            CheckName.MIGRATIONS, False, "multiple_db_revisions", f"rows={len(rows)}"
        )
    db_head = str(rows[0][0])
    if db_head != expected_head:
        return CheckResult(
            CheckName.MIGRATIONS,
            False,
            "db_head_mismatch",
            f"db={db_head} code={expected_head}",
        )
    return CheckResult(CheckName.MIGRATIONS, True, "ok", db_head)


async def _check_seed_marker(db: AsyncSession, expected_sha256: str) -> CheckResult:
    rows = (
        await db.execute(
            text("SELECT value FROM system_settings WHERE key = 'SELF_HOST_SEED_BUNDLE'")
        )
    ).fetchall()
    if not rows:
        return CheckResult(CheckName.SEED_MARKER, False, "marker_missing", "")
    marker = str(rows[0][0])
    if marker != expected_sha256:
        # Bundle digests are hashes of public seed files — short prefixes
        # are safe and let the operator match against the installer log.
        return CheckResult(
            CheckName.SEED_MARKER,
            False,
            "marker_mismatch",
            f"db={marker[:12]} expected={expected_sha256[:12]}",
        )
    return CheckResult(CheckName.SEED_MARKER, True, "ok", marker[:12])


async def _check_reference_data(db: AsyncSession) -> CheckResult:
    row = (await db.execute(_REFERENCE_COUNTS_SQL)).fetchone()
    counts = tuple(int(v) for v in row) if row else (0,) * len(_REFERENCE_COUNTS)
    deficient = [
        f"{label}={count}(expected{'=' if exact else '>='}{threshold})"
        for (label, threshold, exact), count in zip(_REFERENCE_COUNTS, counts, strict=True)
        if ((count != threshold) if exact else (count < threshold))
    ]
    if deficient:
        return CheckResult(CheckName.REFERENCE_DATA, False, "reference_counts", " ".join(deficient))
    return CheckResult(CheckName.REFERENCE_DATA, True, "ok", "")


async def _check_admin(db: AsyncSession, admin_email: str) -> CheckResult:
    rows = (
        await db.execute(
            text("SELECT is_active, is_verified, is_superuser" " FROM users WHERE email = :email"),
            {"email": admin_email},
        )
    ).fetchall()
    if not rows:
        return CheckResult(CheckName.ADMIN, False, "admin_missing", "")
    is_active, is_verified, is_superuser = rows[0]
    missing = [
        flag
        for flag, value in (
            ("is_active", is_active),
            ("is_verified", is_verified),
            ("is_superuser", is_superuser),
        )
        if not value
    ]
    if missing:
        return CheckResult(CheckName.ADMIN, False, "admin_flags", " ".join(missing))
    return CheckResult(CheckName.ADMIN, True, "ok", "")


async def _check_provider_keys(db: AsyncSession, required_providers: Sequence[str]) -> CheckResult:
    from src.core.security.utils import decrypt_data

    rows = (
        await db.execute(text("SELECT provider, encrypted_key FROM provider_api_keys"))
    ).fetchall()
    encrypted_by_provider = {str(p): str(k) for p, k in rows}
    missing = [p for p in required_providers if p not in encrypted_by_provider]
    if missing:
        return CheckResult(
            CheckName.PROVIDER_KEYS, False, "provider_keys_missing", " ".join(missing)
        )
    undecryptable = []
    for provider in required_providers:
        try:
            if not decrypt_data(encrypted_by_provider[provider]):
                undecryptable.append(provider)
        except Exception:  # value-free by design: provider name only
            undecryptable.append(provider)
    if undecryptable:
        return CheckResult(
            CheckName.PROVIDER_KEYS,
            False,
            "provider_keys_undecryptable",
            " ".join(undecryptable),
        )
    return CheckResult(CheckName.PROVIDER_KEYS, True, "ok", "")


async def _check_provider_coverage(db: AsyncSession) -> CheckResult:
    from src.domains.llm_config.constants import LLM_DEFAULTS
    from src.domains.llm_config.install_contract import (
        CURRENT_CORE_LLM_TYPES,
        CURRENT_CORE_PROVIDER_IDS,
    )

    rows = (
        await db.execute(text("SELECT llm_type, provider FROM llm_config_overrides"))
    ).fetchall()
    db_overrides = {str(t): (str(p) if p is not None else None) for t, p in rows}
    out_of_set = []
    for llm_type in CURRENT_CORE_LLM_TYPES:
        provider = db_overrides.get(llm_type) or LLM_DEFAULTS[llm_type].provider
        if provider not in CURRENT_CORE_PROVIDER_IDS:
            out_of_set.append(f"{llm_type}={provider}")
    if out_of_set:
        return CheckResult(
            CheckName.PROVIDER_COVERAGE, False, "provider_coverage", " ".join(out_of_set)
        )
    return CheckResult(CheckName.PROVIDER_COVERAGE, True, "ok", "")


async def verify_installation(
    db: AsyncSession,
    *,
    admin_email: str,
    expected_alembic_head: str,
    expected_seed_bundle_sha256: str,
) -> tuple[CheckResult, ...]:
    """Run every check (never short-circuits) and return one full report.

    A check that raises (e.g. missing tables on an unmigrated database) is
    reported as ``check_error`` with the exception TYPE only, and the
    session is rolled back so the aborted transaction cannot poison the
    remaining checks.
    """
    from src.domains.llm_config.install_contract import (
        required_current_core_provider_ids,
    )

    plan: tuple[tuple[CheckName, Callable[[], Awaitable[CheckResult]]], ...] = (
        (CheckName.MIGRATIONS, lambda: _check_migrations(db, expected_alembic_head)),
        (CheckName.SEED_MARKER, lambda: _check_seed_marker(db, expected_seed_bundle_sha256)),
        (CheckName.REFERENCE_DATA, lambda: _check_reference_data(db)),
        (CheckName.ADMIN, lambda: _check_admin(db, admin_email)),
        (
            CheckName.PROVIDER_KEYS,
            lambda: _check_provider_keys(db, required_current_core_provider_ids()),
        ),
        (CheckName.PROVIDER_COVERAGE, lambda: _check_provider_coverage(db)),
    )
    results: list[CheckResult] = []
    for name, factory in plan:
        try:
            results.append(await factory())
        except Exception as exc:
            # Best-effort recovery: rollback failures would only re-raise the
            # same broken-connection condition the check already reported.
            with suppress(Exception):
                await db.rollback()
            results.append(CheckResult(name, False, "check_error", type(exc).__name__))
    return tuple(results)


def render_json(results: Sequence[CheckResult]) -> str:
    """Render the non-secret operator report."""
    return json.dumps(
        {
            "passed": all(r.passed for r in results),
            "checks": [
                {
                    "name": r.name.value,
                    "passed": r.passed,
                    "code": r.code,
                    "detail": r.detail,
                }
                for r in results
            ],
        }
    )


def _find_alembic_ini() -> Path:
    """Locate alembic.ini in both layouts (host apps/api and container /app)."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "alembic.ini"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("alembic.ini not found in any parent tree")


async def _run(admin_email: str, expected_seed_bundle_sha256: str) -> int:
    expected_head = load_single_alembic_head(_find_alembic_ini())

    from src.infrastructure.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        results = await verify_installation(
            session,
            admin_email=admin_email,
            expected_alembic_head=expected_head,
            expected_seed_bundle_sha256=expected_seed_bundle_sha256,
        )
    print(render_json(results))
    return 0 if all(r.passed for r in results) else 4


def main() -> int:
    """Entry point: validate inputs BEFORE opening any database session."""
    parser = argparse.ArgumentParser(
        description="Verify functional installation postconditions (read-only)."
    )
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--seed-bundle-sha256", required=True)
    args = parser.parse_args()
    if not _SHA256_HEX.fullmatch(args.seed_bundle_sha256):
        print(json.dumps({"status": "input_error", "code": "invalid_seed_bundle_sha256"}))
        return 2
    return asyncio.run(_run(args.admin_email, args.seed_bundle_sha256))


if __name__ == "__main__":
    sys.exit(main())
