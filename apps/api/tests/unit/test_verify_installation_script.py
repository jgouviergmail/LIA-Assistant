"""Installation verifier contract (ADR-215, B12).

``/ready`` proves the process serves; it does not prove the INSTALL is
functional. The verifier must prove, read-only and value-free:

- exactly one Alembic head in code AND one matching row in alembic_version;
- the seed marker equals the EXACT expected 64-hex bundle digest;
- the six reference-data postconditions still hold (same thresholds as
  verify_reference_seeds.sql — floors can only grow);
- the admin is active, verified, and superuser;
- every derived required provider key row exists AND decrypts;
- every core LLM slot resolves inside the derived provider set on the
  POST-SEED effective configuration read from the REAL database rows.

Every check runs even after an earlier one fails (one complete operator
report), and no decrypted key ever appears in the JSON output.
"""

from __future__ import annotations

import json
import re
from unittest.mock import MagicMock, patch

import pytest

from scripts.data.verify_installation import (
    CheckName,
    CheckResult,
    load_single_alembic_head,
    render_json,
    verify_installation,
)

pytestmark = pytest.mark.unit

HEAD = "abc123def456"
DIGEST = "d" * 64
KEY_CANARY = "sk-DECRYPTED-CANARY-77aa"
#: One value per row of ``_REFERENCE_COUNTS``, at or above each threshold.
#: The thresholds mirror ``verify_reference_seeds.sql`` and are pinned to it
#: by ``test_reference_counts_mirror_guard`` — this fixture follows them.
GREEN_COUNTS = (14, 84, 18, 27, 139, 39, 124)
# What a really-seeded database contains for the core (B10-bis): every
# qwen CODE default is overridden to deepseek; router is seeded NULL.
GREEN_OVERRIDES = [
    ("planner", "deepseek"),
    ("query_analyzer", "deepseek"),
    ("query_agent", "deepseek"),
    ("semantic_validator", "deepseek"),
    ("response", "deepseek"),
    ("react_agent", "deepseek"),
    ("router", None),
]


class _ScriptedDb:
    """Routes each executed statement to a scripted result by SQL fragment."""

    def __init__(self, responses: dict[str, MagicMock | Exception]) -> None:
        self._responses = responses
        self.executed: list[str] = []
        self.rollbacks = 0

    async def execute(self, statement: object, params: object = None) -> MagicMock:
        sql = str(statement)
        self.executed.append(sql)
        for needle, response in self._responses.items():
            if needle in sql:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected SQL in verifier: {sql}")

    async def rollback(self) -> None:
        self.rollbacks += 1


def _rows(rows: list[tuple]) -> MagicMock:
    result = MagicMock()
    result.fetchall.return_value = rows
    result.fetchone.return_value = rows[0] if rows else None
    return result


def _db(
    *,
    alembic_rows: list[tuple] | None = None,
    marker_rows: list[tuple] | None = None,
    counts: tuple = GREEN_COUNTS,
    admin_rows: list[tuple] | None = None,
    key_rows: list[tuple] | None = None,
    override_rows: list[tuple] | None = None,
) -> _ScriptedDb:
    return _ScriptedDb(
        {
            "FROM alembic_version": _rows(alembic_rows if alembic_rows is not None else [(HEAD,)]),
            "FROM system_settings": _rows(marker_rows if marker_rows is not None else [(DIGEST,)]),
            "AS personalities": _rows([counts]),
            "FROM users": _rows(admin_rows if admin_rows is not None else [(True, True, True)]),
            "FROM provider_api_keys": _rows(
                key_rows if key_rows is not None else [("openai", "enc-a"), ("deepseek", "enc-b")]
            ),
            "SELECT llm_type, provider FROM llm_config_overrides": _rows(
                override_rows if override_rows is not None else GREEN_OVERRIDES
            ),
        }
    )


async def _run(db: _ScriptedDb, *, decrypt: object | None = None) -> tuple[CheckResult, ...]:
    with patch(
        "src.core.security.utils.decrypt_data",
        side_effect=decrypt or (lambda _v: KEY_CANARY),
    ):
        return await verify_installation(
            db,  # type: ignore[arg-type]
            admin_email="admin@ops.tld",
            expected_alembic_head=HEAD,
            expected_seed_bundle_sha256=DIGEST,
        )


def _by_name(results: tuple[CheckResult, ...], name: CheckName) -> CheckResult:
    return next(r for r in results if r.name is name)


# ---------------------------------------------------------------------------
# Nominal
# ---------------------------------------------------------------------------


async def test_green_installation_passes_all_six_checks() -> None:
    results = await _run(_db())
    assert [r.name for r in results] == list(CheckName)
    assert all(r.passed for r in results), [r.code for r in results]
    assert all(r.code == "ok" for r in results)


async def test_all_checks_run_even_after_an_early_failure() -> None:
    results = await _run(_db(alembic_rows=[]))
    assert len(results) == len(CheckName)
    assert not _by_name(results, CheckName.MIGRATIONS).passed
    assert _by_name(results, CheckName.PROVIDER_COVERAGE).passed


async def test_a_sql_error_in_one_check_is_isolated_and_rolled_back() -> None:
    # An unmigrated database has none of the reference tables: the failing
    # check must report check_error (value-free) and ROLL BACK so the
    # aborted transaction cannot poison the remaining checks.
    db = _db()
    db._responses["AS personalities"] = RuntimeError("relation does not exist")
    results = await _run(db)
    failed = _by_name(results, CheckName.REFERENCE_DATA)
    assert not failed.passed
    assert failed.code == "check_error"
    assert failed.detail == "RuntimeError"
    assert "relation does not exist" not in render_json(results)
    assert db.rollbacks >= 1
    assert _by_name(results, CheckName.PROVIDER_COVERAGE).passed


async def test_no_decrypted_key_ever_reaches_the_json_report() -> None:
    payload = render_json(await _run(_db()))
    assert KEY_CANARY not in payload
    parsed = json.loads(payload)
    assert parsed["passed"] is True
    assert [c["name"] for c in parsed["checks"]] == [n.value for n in CheckName]


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("alembic_rows", "code"),
    [
        ([], "no_db_revision"),
        ([(HEAD,), ("ffff00000000",)], "multiple_db_revisions"),
        ([("ffff00000000",)], "db_head_mismatch"),
    ],
)
async def test_migration_failures_have_stable_codes(alembic_rows: list[tuple], code: str) -> None:
    result = _by_name(await _run(_db(alembic_rows=alembic_rows)), CheckName.MIGRATIONS)
    assert not result.passed
    assert result.code == code


def test_repo_alembic_config_has_exactly_one_head() -> None:
    from tests._repo_paths import repo_root_or_skip

    head = load_single_alembic_head(repo_root_or_skip() / "apps/api/alembic.ini")
    assert re.fullmatch(r"[0-9a-f]{12}", head)


# ---------------------------------------------------------------------------
# Seed marker
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("marker_rows", "code"),
    [([], "marker_missing"), ([("e" * 64,)], "marker_mismatch")],
)
async def test_marker_must_equal_the_exact_expected_digest(
    marker_rows: list[tuple], code: str
) -> None:
    result = _by_name(await _run(_db(marker_rows=marker_rows)), CheckName.SEED_MARKER)
    assert not result.passed
    assert result.code == code


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


async def test_reference_data_failure_names_only_the_deficient_tables() -> None:
    # personalities short of its EXACT 14, overrides short of their floor of 39;
    # everything else at or above threshold and therefore unnamed.
    deficient = (13, 84, 18, 27, 139, 38, 124)
    result = _by_name(await _run(_db(counts=deficient)), CheckName.REFERENCE_DATA)
    assert not result.passed
    assert result.code == "reference_counts"
    assert "personalities" in result.detail
    assert "llm_config_overrides" in result.detail
    assert "personality_translations" not in result.detail
    assert "llm_models" not in result.detail


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


async def test_missing_admin_is_reported() -> None:
    result = _by_name(await _run(_db(admin_rows=[])), CheckName.ADMIN)
    assert not result.passed
    assert result.code == "admin_missing"


async def test_admin_flag_failure_names_the_missing_flags() -> None:
    result = _by_name(await _run(_db(admin_rows=[(True, False, False)])), CheckName.ADMIN)
    assert not result.passed
    assert result.code == "admin_flags"
    assert "is_verified" in result.detail
    assert "is_superuser" in result.detail
    assert "is_active" not in result.detail


# ---------------------------------------------------------------------------
# Provider keys
# ---------------------------------------------------------------------------


async def test_missing_provider_row_is_reported_without_values() -> None:
    result = _by_name(await _run(_db(key_rows=[("openai", "enc-a")])), CheckName.PROVIDER_KEYS)
    assert not result.passed
    assert result.code == "provider_keys_missing"
    assert "deepseek" in result.detail
    assert "enc-a" not in result.detail


async def test_undecryptable_key_is_reported_without_values() -> None:
    def _explode(value: str) -> str:
        if value == "enc-b":
            raise ValueError("bad token")
        return KEY_CANARY

    results = await _run(_db(), decrypt=_explode)
    result = _by_name(results, CheckName.PROVIDER_KEYS)
    assert not result.passed
    assert result.code == "provider_keys_undecryptable"
    assert "deepseek" in result.detail
    assert "enc-b" not in result.detail
    assert KEY_CANARY not in render_json(results)


async def test_empty_decrypted_key_counts_as_undecryptable() -> None:
    results = await _run(_db(), decrypt=lambda _v: "")
    result = _by_name(results, CheckName.PROVIDER_KEYS)
    assert not result.passed
    assert result.code == "provider_keys_undecryptable"


# ---------------------------------------------------------------------------
# Provider coverage (post-seed effective view from the REAL rows)
# ---------------------------------------------------------------------------


async def test_out_of_set_core_slot_fails_coverage() -> None:
    rows = [("planner", "anthropic"), *GREEN_OVERRIDES[1:]]
    result = _by_name(await _run(_db(override_rows=rows)), CheckName.PROVIDER_COVERAGE)
    assert not result.passed
    assert result.code == "provider_coverage"
    assert result.detail == "planner=anthropic"


async def test_qwen_code_default_without_its_seed_override_fails_coverage() -> None:
    # An unseeded database exposes the qwen CODE defaults — the check must
    # evaluate the REAL rows, never assume the seed file was applied.
    result = _by_name(await _run(_db(override_rows=[])), CheckName.PROVIDER_COVERAGE)
    assert not result.passed
    assert "=qwen" in result.detail


async def test_null_override_falls_back_to_the_code_default() -> None:
    # router seeded NULL → code default (openai) → inside the derived set.
    result = _by_name(await _run(_db()), CheckName.PROVIDER_COVERAGE)
    assert result.passed


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def test_main_rejects_a_malformed_digest_before_any_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import scripts.data.verify_installation as module

    monkeypatch.setattr(
        "sys.argv",
        ["verify_installation", "--admin-email", "a@b.c", "--seed-bundle-sha256", "nothex"],
    )
    assert module.main() == 2
    out = json.loads(capsys.readouterr().out)
    assert out == {"status": "input_error", "code": "invalid_seed_bundle_sha256"}
