"""Seeding a production database requires intent AND an empty target.

``apps/api/docker-entrypoint.sh`` can apply the reference content of a fresh
install (personalities, LLM pricing). That branch is destructive — the seed files
DELETE before they insert::

    infrastructure/database/seeds/personalities_seed.sql
        DELETE FROM personality_translations;
        DELETE FROM personalities;

and the schema propagates it: ``personality_translations.personality_id`` is
``ON DELETE CASCADE`` and ``users.personality_id`` is ``ON DELETE SET NULL``, so
a spurious run would reset the personality every user has chosen.

The original gate seeded whenever ``SELECT COUNT(*) FROM personalities`` returned
``0``, and read the count as::

    PERSONALITIES_COUNT=$(... psql ... 2>/dev/null | tr -d ' ' || echo "0")

fail-OPEN on the destructive side: any psql failure — wrong password, connection
reset, lock timeout — became "0", i.e. "the database is empty", i.e. "wipe and
re-seed".

Two independent conditions now guard it, and neither can be satisfied by
accident:

1. **intent** — ``APPLY_SEEDS=true``, defaulting to false;
2. **target** — the ``personalities`` table is verifiably empty.

The row count survives only as a VETO. That reversal is what makes it safe: the
same unreadable answer that used to trigger the wipe now refuses it. The second
condition is not redundant with the first, because Compose interpolates
``${APPLY_SEEDS:-false}`` from the shell AND from the project ``.env``
(measured), so a value left behind in an env file would otherwise re-arm the
deletion on every later deploy.

This guard is static on purpose. The gate runs in the container entrypoint, long
before any Python process exists, so the only oracle available to the unit suite
is the script itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
ENTRYPOINT = REPO_ROOT / "apps" / "api" / "docker-entrypoint.sh"
SEEDS_DIR = REPO_ROOT / "infrastructure" / "database" / "seeds"
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"


def _entrypoint_body() -> str:
    return ENTRYPOINT.read_text(encoding="utf-8")


def _executable_body() -> str:
    """The entrypoint without its comment lines.

    The fix documents the defect it removes by quoting the old ``|| echo "0"``
    in a comment. A guard that scanned raw text would match that prose and fail
    on the very explanation that makes the code reviewable.
    """
    return "\n".join(
        line for line in _entrypoint_body().splitlines() if not line.lstrip().startswith("#")
    )


class TestSeedsAreDestructive:
    """The premise of this guard, asserted rather than assumed."""

    def test_seed_files_delete_before_inserting(self) -> None:
        """If the seeds stopped being destructive, this guard could be relaxed."""
        destructive = [
            path.name
            for path in sorted(SEEDS_DIR.glob("*.sql"))
            if re.search(r"^\s*(DELETE|TRUNCATE)\b", path.read_text(encoding="utf-8"), re.M | re.I)
        ]

        assert destructive, (
            "no seed file deletes anymore — re-read the entrypoint gate: the "
            "fail-closed requirement below exists because applying seeds destroys data."
        )


class TestSeedsRequireExplicitIntent:
    """Destructive seeding is an operator decision, never an inference."""

    def test_row_count_vetoes_but_never_triggers(self) -> None:
        """The count may only REFUSE. Reversing its role is the whole fix.

        It used to be the trigger — "count == 0 means fresh install" — which also
        fired whenever the count could not be READ, because the failure branch
        yielded "0". As a veto the same unreadable answer refuses instead, so
        every failure mode lands on the safe side.
        """
        body = _executable_body()

        trigger = body.find('if [ "${APPLY_SEEDS:-false}" = "true" ]')
        count = body.find("EXISTING_PERSONALITIES=")
        assert trigger != -1 and count != -1, "both the intent test and the veto must exist"
        assert count > trigger, (
            "the row count must be read INSIDE the APPLY_SEEDS branch: consulted before "
            "it, it becomes a trigger again — the exact defect this gate removed."
        )

    def test_unreadable_count_refuses(self) -> None:
        """No answer must never be read as 'the database is empty'."""
        body = _executable_body()

        assert re.search(r'if\s+\[\s+-z\s+"\$EXISTING_PERSONALITIES"\s+\]', body), (
            "an unreadable count must have its own branch that refuses: a psql failure "
            '(bad password, reset connection, lock timeout) previously produced "0" '
            "and wiped live data."
        )

    def test_populated_database_refuses(self) -> None:
        """Intent alone is not enough — `APPLY_SEEDS` can arrive from .env.

        Compose interpolates ``${APPLY_SEEDS:-false}`` from the shell AND from
        the project ``.env`` (measured), so a value left behind in an env file
        would re-arm the deletion on every later deploy. The emptiness check is
        what makes that stale value harmless.
        """
        body = _executable_body()

        assert re.search(r'\[\s+"\$EXISTING_PERSONALITIES"\s+!=\s+"0"\s+\]', body), (
            "a non-empty personalities table must refuse the seeds: they delete before "
            "inserting, and users.personality_id is ON DELETE SET NULL."
        )

    def test_apply_seeds_is_the_only_trigger(self) -> None:
        """The seed loop must sit under an explicit APPLY_SEEDS test."""
        body = _executable_body()

        gate = re.search(
            r'if\s+\[\s+"\$\{APPLY_SEEDS:-false\}"\s+=\s+"true"\s+\]\s*;\s*then',
            body,
        )
        assert gate, (
            'the seed loop must be guarded by `if [ "${APPLY_SEEDS:-false}" = "true" ]`, '
            "defaulting to false so a normal boot never seeds."
        )

        seed_loop = body.find("for seed_file")
        assert (
            seed_loop > gate.start()
        ), "the seed loop must sit INSIDE the APPLY_SEEDS branch, not before it."

    def test_seeds_reach_the_container(self) -> None:
        """A gate whose files never arrive is a recovery path that does not exist.

        ``SEEDS_DIR`` lives under ``/app``, but the API image is built from the
        ``apps/api`` context, which holds no ``infrastructure/`` directory: the
        path can only exist through a mount. It never did — measured on
        production and on dev, 2026-08-05 — so the block had been dead code in
        every environment, and a rebuilt installation would have started with no
        personalities and no LLM pricing (breaking cost computation).

        The expected mount target is read FROM the entrypoint, so moving
        ``SEEDS_DIR`` fails here instead of silently re-orphaning the seeds.
        """
        seeds_dir = re.search(r'^SEEDS_DIR="([^"]+)"', _executable_body(), re.M)
        assert seeds_dir, "SEEDS_DIR must be declared in the entrypoint"
        target = seeds_dir.group(1)

        compose = yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))
        mounts = (compose.get("services") or {}).get("api", {}).get("volumes") or []
        mounted = [m for m in mounts if isinstance(m, str) and f":{target}" in m]

        assert mounted, (
            f"docker-compose.prod.yml must mount the seed files at {target}: the API "
            f"image is built from apps/api, which contains no infrastructure/ directory, "
            f"so without a mount the seed gate can never run and a fresh install has no "
            f"reference content."
        )
        assert all(
            m.endswith(":ro") for m in mounted
        ), f"the seed mount must be read-only: {mounted}"

    def test_operator_is_warned_that_seeding_destroys(self) -> None:
        """Whoever flips the switch must read what it costs."""
        body = _executable_body()

        assert re.search(r"echo\s+\"[^\"]*DESTRUCTIVE", body), (
            "the apply branch must announce that seeding is destructive: the operator "
            "who sets APPLY_SEEDS=true on a populated database needs that warning in "
            "the deployment log, not in a source comment they will never open."
        )
