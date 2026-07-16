"""Tests for the PostgreSQL connection-budget invariant (audit F004).

The worst-case burst across all workers must fit under ``max_connections`` minus
a reserve; a single dev worker and the right-sized 4-worker prod profile fit,
while an un-tuned 4-worker profile (pool 30 + overflow 30) overcommits.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.infrastructure.database.connection_budget import (
    ConnectionBudgetError,
    compute_connection_budget,
    enforce_connection_budget,
    validate_connection_budget,
)


def _find_repo_file(name: str) -> Path:
    """Walk up from this test file until *name* is found at a directory root."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(name)


def _parse_env_ints(path: Path, keys: set[str]) -> dict[str, int]:
    """Extract ``KEY=INT`` pairs (ignoring inline ``# comments``) for *keys*."""
    values: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        if key not in keys:
            continue
        token = rest.split("#", 1)[0].strip()
        if token.isdigit():
            values[key] = int(token)
    return values


def _settings(
    workers: int,
    pool: int = 30,
    overflow: int = 30,
    ckpt_max: int = 8,
    store_max: int = 4,
    max_conn: int = 200,
    reserved: int = 5,
    is_production: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        web_concurrency=workers,
        database_pool_size=pool,
        database_max_overflow=overflow,
        langgraph_checkpoint_pool_max_size=ckpt_max,
        langgraph_store_pool_max_size=store_max,
        database_max_connections=max_conn,
        database_reserved_connections=reserved,
        is_production=is_production,
    )


def test_single_worker_dev_profile_fits():
    settings = _settings(workers=1)
    budget = compute_connection_budget(settings)
    # 1*(30+30) + 1*8 + 1*4 = 72 <= (200 - 5)
    assert budget.burst_total == 72
    assert budget.usable == 195
    assert budget.fits
    assert validate_connection_budget(settings) == []


def test_four_worker_default_profile_overcommits():
    settings = _settings(workers=4)
    budget = compute_connection_budget(settings)
    # 4*60 + 4*8 + 4*4 = 288 > 195 — the F004 overcommit.
    assert budget.burst_total == 288
    assert not budget.fits
    warnings = validate_connection_budget(settings)
    assert len(warnings) == 1
    assert "overcommit" in warnings[0]
    assert "288" in warnings[0] and "195" in warnings[0]


def test_right_sized_four_worker_profile_fits():
    settings = _settings(workers=4, pool=20, overflow=10)
    budget = compute_connection_budget(settings)
    # 4*30 + 32 + 16 = 168 <= 195
    assert budget.burst_total == 168
    assert budget.fits
    assert validate_connection_budget(settings) == []


def test_enforce_fails_fast_in_production_on_overcommit():
    """F004: production refuses to boot on an overcommit (fail-fast)."""
    settings = _settings(workers=4, is_production=True)  # 288 > 195
    with pytest.raises(ConnectionBudgetError) as exc:
        enforce_connection_budget(settings)
    assert "288" in str(exc.value) and "195" in str(exc.value)


def test_enforce_only_warns_in_development_on_overcommit():
    """F004: development is not blocked — the overcommit is returned as a warning."""
    settings = _settings(workers=4, is_production=False)  # 288 > 195
    warnings = enforce_connection_budget(settings)
    assert len(warnings) == 1 and "overcommit" in warnings[0]


def test_enforce_passes_in_production_when_profile_fits():
    """F004: a right-sized production profile boots with no warning."""
    settings = _settings(workers=4, pool=20, overflow=10, is_production=True)  # 168 <= 195
    assert enforce_connection_budget(settings) == []


@pytest.mark.parametrize("env_file", [".env.prod.example", ".env.example"])
def test_shipped_env_profile_fits_the_budget(env_file: str):
    """Ratchet (F004): the committed env templates must describe a profile that
    fits the connection budget. This prevents silently re-introducing the
    4-worker overcommit by editing the pool/overflow/worker knobs.
    """
    keys = {
        "WEB_CONCURRENCY",
        "DATABASE_POOL_SIZE",
        "DATABASE_MAX_OVERFLOW",
        "LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE",
        "LANGGRAPH_STORE_POOL_MAX_SIZE",
        "DATABASE_MAX_CONNECTIONS",
        "DATABASE_RESERVED_CONNECTIONS",
    }
    values = _parse_env_ints(_find_repo_file(env_file), keys)
    missing = keys - values.keys()
    assert not missing, f"{env_file} missing budget knobs: {sorted(missing)}"

    settings = _settings(
        workers=values["WEB_CONCURRENCY"],
        pool=values["DATABASE_POOL_SIZE"],
        overflow=values["DATABASE_MAX_OVERFLOW"],
        ckpt_max=values["LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE"],
        store_max=values["LANGGRAPH_STORE_POOL_MAX_SIZE"],
        max_conn=values["DATABASE_MAX_CONNECTIONS"],
        reserved=values["DATABASE_RESERVED_CONNECTIONS"],
    )
    budget = compute_connection_budget(settings)
    assert budget.fits, (
        f"{env_file} overcommits: burst {budget.burst_total} > usable {budget.usable} "
        f"({values['WEB_CONCURRENCY']} workers)"
    )
    assert validate_connection_budget(settings) == []
