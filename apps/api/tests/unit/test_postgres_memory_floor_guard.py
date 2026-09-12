"""The unreclaimable floor of the Postgres container leaves room under its limit.

Measured on production over the night of 2026-09-11 (Prometheus, 10-minute
steps): the daily backup filled ``shared_buffers`` at 02:00 Paris and the
container then sat at 900-950 MiB of a 1 GiB limit for the rest of the night —
512 MB of shared memory plus ~350 MB of private backend memory, neither of
which the kernel can reclaim. Every morning activity pushed it to 990-1 009 MiB
(five ``ContainerMemoryNearLimit`` cycles at 95.6-99.65 %) and 272 MB of the
database went to zram swap by 08:00. Not a leak: two incompressible components
whose SUM equalled the limit.

The floor is ``shared_buffers`` plus one private backend per PERSISTENT
connection — every worker holds its pool minimums open whether or not anyone
is talking to it (7 MB each, measured over 52 idle backends). This guard reads
both halves where they are declared, the compose file and the shipped prod
profile, and requires the floor to stay under half the container's limit, so
the page cache and ``work_mem`` keep the other half. Raising a pool size or
lowering the limit fails here, with the arithmetic in the message.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from src.infrastructure.database.connection_budget import compute_connection_budget
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

#: Private memory of an idle client backend, measured 2026-09-12 (average over 52).
IDLE_BACKEND_BYTES = 7 * 1024 * 1024
#: The floor may take this share of the limit; the rest is cache and work_mem.
FLOOR_SHARE = 0.5

_UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3, "KB": 1024, "MB": 1024**2, "GB": 1024**3}

_ENV_KEYS = {
    "WEB_CONCURRENCY",
    "DATABASE_POOL_SIZE",
    "DATABASE_MAX_OVERFLOW",
    "LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE",
    "LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE",
    "LANGGRAPH_STORE_POOL_MIN_SIZE",
    "LANGGRAPH_STORE_POOL_MAX_SIZE",
    "DATABASE_MAX_CONNECTIONS",
    "DATABASE_RESERVED_CONNECTIONS",
}


def _bytes(value: str) -> int:
    match = re.fullmatch(r"(\d+)\s*([KMG]B?)?", value.strip(), re.IGNORECASE)
    assert match, f"unreadable size {value!r}"
    number, unit = match.groups()
    return int(number) * (_UNITS[unit.upper()] if unit else 1)


def _env_ints(path: Path, keys: set[str]) -> dict[str, int]:
    values: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        key, _, rest = raw.strip().partition("=")
        token = rest.split("#", 1)[0].strip()
        if key in keys and token.isdigit():
            values[key] = int(token)
    return values


def _code_defaults() -> dict[str, int]:
    """What a key ABSENT from a profile resolves to at boot: the code's default."""
    from src.core import constants

    return {
        "WEB_CONCURRENCY": constants.WEB_CONCURRENCY_DEFAULT,
        "DATABASE_POOL_SIZE": constants.DATABASE_POOL_SIZE_DEFAULT,
        "DATABASE_MAX_OVERFLOW": constants.DATABASE_MAX_OVERFLOW_DEFAULT,
        "LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE": constants.LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE_DEFAULT,
        "LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE": constants.LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE_DEFAULT,
        "LANGGRAPH_STORE_POOL_MIN_SIZE": constants.LANGGRAPH_STORE_POOL_MIN_SIZE_DEFAULT,
        "LANGGRAPH_STORE_POOL_MAX_SIZE": constants.LANGGRAPH_STORE_POOL_MAX_SIZE_DEFAULT,
        "DATABASE_MAX_CONNECTIONS": constants.DATABASE_MAX_CONNECTIONS_DEFAULT,
        "DATABASE_RESERVED_CONNECTIONS": constants.DATABASE_RESERVED_CONNECTIONS_DEFAULT,
    }


def postgres_floor(
    compose: Path, env_profile: Path, *, fill_from_code_defaults: bool = False
) -> tuple[int, int, str]:
    """``(floor_bytes, limit_bytes, explanation)`` for a compose file and an env profile.

    Args:
        compose: The compose file declaring the postgres service.
        env_profile: The env profile the API boots with.
        fill_from_code_defaults: Resolve a key the profile omits to the code's
            default, as the boot does — for the MINIMAL self-host profile, which
            only writes what differs from the defaults. The full production
            profile must declare every key.
    """
    service = yaml.safe_load(compose.read_text(encoding="utf-8"))["services"]["postgres"]
    command = service["command"]
    if not isinstance(command, str):
        command = " ".join(command)
    shared = re.search(r"shared_buffers=(\S+)", command)
    assert shared, "postgres command must declare shared_buffers explicitly"
    shared_bytes = _bytes(shared.group(1))
    limit_bytes = _bytes(service["deploy"]["resources"]["limits"]["memory"])

    values = _env_ints(env_profile, _ENV_KEYS)
    if fill_from_code_defaults:
        values = {**_code_defaults(), **values}
    missing = _ENV_KEYS - values.keys()
    assert not missing, f"{env_profile.name} lacks {sorted(missing)}"
    budget = compute_connection_budget(
        SimpleNamespace(
            web_concurrency=values["WEB_CONCURRENCY"],
            database_pool_size=values["DATABASE_POOL_SIZE"],
            database_max_overflow=values["DATABASE_MAX_OVERFLOW"],
            langgraph_checkpoint_pool_min_size=values["LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE"],
            langgraph_checkpoint_pool_max_size=values["LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE"],
            langgraph_store_pool_min_size=values["LANGGRAPH_STORE_POOL_MIN_SIZE"],
            langgraph_store_pool_max_size=values["LANGGRAPH_STORE_POOL_MAX_SIZE"],
            database_max_connections=values["DATABASE_MAX_CONNECTIONS"],
            database_reserved_connections=values["DATABASE_RESERVED_CONNECTIONS"],
        )
    )
    floor = shared_bytes + budget.persistent_total * IDLE_BACKEND_BYTES
    explanation = (
        f"shared_buffers {shared_bytes >> 20} MiB + {budget.persistent_total} persistent "
        f"backends ({values['WEB_CONCURRENCY']} workers x ({values['DATABASE_POOL_SIZE']} + "
        f"{values['LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE']} + "
        f"{values['LANGGRAPH_STORE_POOL_MIN_SIZE']})) x {IDLE_BACKEND_BYTES >> 20} MiB "
        f"= {floor >> 20} MiB against a {limit_bytes >> 20} MiB limit"
    )
    return floor, limit_bytes, explanation


def test_the_shipped_production_profile_leaves_half_the_limit_to_the_cache() -> None:
    root = repo_root_or_skip()
    compose = root / "docker-compose.prod.yml"
    if not compose.is_file():
        pytest.skip("guard needs the full repository checkout (docker-compose.prod.yml).")

    floor, limit, explanation = postgres_floor(compose, root / ".env.prod.example")

    assert floor <= limit * FLOOR_SHARE, (
        f"Postgres' unreclaimable floor takes {100 * floor / limit:.0f}% of its limit: "
        f"{explanation}. Lower the persistent pools or raise the limit. Measured 2026-09-11: "
        f"a floor at the limit oscillates at 95-99% and swaps the database to zram every morning."
    )


def test_the_minimal_self_host_profile_leaves_half_the_limit_to_the_cache() -> None:
    """The profile the installer renders (`.env.min.prod.example`) obeys the same rule.

    It carried the pre-ADR-283 sizing (20 persistent per worker) until v1.44.5,
    which under the shipped 2G limit put the floor at 55 % — the rule the full
    profile satisfies was not read for the profile a self-hoster actually gets.
    Keys the minimal profile omits resolve to the code's defaults, as at boot.
    """
    root = repo_root_or_skip()
    compose = root / "docker-compose.prod.yml"
    profile = root / ".env.min.prod.example"
    if not compose.is_file() or not profile.is_file():
        pytest.skip("guard needs the full repository checkout.")

    floor, limit, explanation = postgres_floor(compose, profile, fill_from_code_defaults=True)

    assert floor <= limit * FLOOR_SHARE, (
        f"the self-host profile's Postgres floor takes {100 * floor / limit:.0f}% of the "
        f"limit: {explanation}."
    )


class TestTheArithmeticReadsWhatItClaims:
    def test_the_incident_profile_is_refused(self, tmp_path: Path) -> None:
        """1 GiB, shared_buffers 512 MB, 20 persistent per worker x 4: the 2026-09-11 night."""
        compose = tmp_path / "compose.yml"
        compose.write_text(
            "services:\n  postgres:\n    command: postgres -c shared_buffers=512MB\n"
            "    deploy:\n      resources:\n        limits:\n          memory: 1G\n",
            encoding="utf-8",
        )
        env = tmp_path / "prod.env"
        env.write_text(
            "WEB_CONCURRENCY=4\nDATABASE_POOL_SIZE=20\nDATABASE_MAX_OVERFLOW=10\n"
            "LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE=1\nLANGGRAPH_CHECKPOINT_POOL_MAX_SIZE=8\n"
            "LANGGRAPH_STORE_POOL_MIN_SIZE=1\nLANGGRAPH_STORE_POOL_MAX_SIZE=4\n"
            "DATABASE_MAX_CONNECTIONS=200\nDATABASE_RESERVED_CONNECTIONS=5\n",
            encoding="utf-8",
        )
        floor, limit, _ = postgres_floor(compose, env)
        assert floor == 512 * 1024**2 + 4 * 22 * IDLE_BACKEND_BYTES
        assert floor > limit * FLOOR_SHARE

    def test_sizes_are_read_in_compose_and_postgres_spellings(self) -> None:
        assert _bytes("1G") == 1024**3
        assert _bytes("512MB") == 512 * 1024**2
        assert _bytes("2048M") == 2 * 1024**3
        assert _bytes("64kB") == 64 * 1024
