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
2. **target** — verifiably NOBODY has chosen a personality yet.

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

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
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
            "a user who already chose a personality must refuse the seeds: they delete "
            "before inserting, and users.personality_id is ON DELETE SET NULL."
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

        # ADR-215: the per-file loop became ONE atomic wrapper invocation.
        seed_invocation = body.find("apply_reference_seeds.sh")
        assert (
            seed_invocation > gate.start()
        ), "the seed wrapper must sit INSIDE the APPLY_SEEDS branch, not before it."
        assert "for seed_file" not in body, (
            "per-file psql seeding returned — seeds must go through the single "
            "atomic wrapper (ADR-215, B09)"
        )

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

        # EVERY compose file that asks for the seeds must also carry them.
        # Checking prod by name let the demonstrator ask for the bundle with no
        # mount at all: the gate opened and the wrapper died on `missing seed
        # file google_api_pricing_seed.sql`, rolling the bundle back and
        # leaving a partial catalogue (measured 2026-08-07).
        asking = []
        for compose_path in sorted(REPO_ROOT.glob("docker-compose*.yml")):
            raw = compose_path.read_text(encoding="utf-8")
            if "APPLY_SEEDS=true" not in raw:
                continue
            compose = yaml.safe_load(raw)
            for name, spec in (compose.get("services") or {}).items():
                declared = (spec or {}).get("environment") or []
                if not any("APPLY_SEEDS=true" in str(entry) for entry in declared):
                    continue
                mounts = [m for m in ((spec or {}).get("volumes") or []) if isinstance(m, str)]
                mounted = [m for m in mounts if f":{target}" in m]
                asking.append((compose_path.name, name, mounted))

        assert asking, "no compose file arms APPLY_SEEDS — the recovery path is unreachable"
        for file_name, service, mounted in asking:
            assert mounted, (
                f"{file_name}:{service} sets APPLY_SEEDS=true but mounts nothing at "
                f"{target}: the API image is built from apps/api, which contains no "
                f"infrastructure/ directory, so the seed files can only arrive through "
                f"a mount. Without it the bundle fails and rolls back."
            )
            assert all(
                m.endswith(":ro") for m in mounted
            ), f"{file_name}:{service} mounts the seeds writable: {mounted}"

    def test_operator_is_warned_that_seeding_destroys(self) -> None:
        """Whoever flips the switch must read what it costs."""
        body = _executable_body()

        assert re.search(r"echo\s+\"[^\"]*DESTRUCTIVE", body), (
            "the apply branch must announce that seeding is destructive: the operator "
            "who sets APPLY_SEEDS=true on a populated database needs that warning in "
            "the deployment log, not in a source comment they will never open."
        )


class TestTheVetoAsksAQuestionThatCanBeAnsweredYes:
    """A veto no fresh install can satisfy is not a gate, it is a wall.

    The gate asked "is the personalities table empty?". Migrations run FIRST
    (`alembic upgrade head`, immediately above the gate) and
    `2025_12_03_0000-add_personalities` inserts fourteen rows unconditionally,
    so the answer was never yes. Measured 2026-08-07 on a genuinely fresh
    database: `personalities already holds 14 row(s) - SQL seeds SKIPPED`.

    The reference bundle could therefore never be applied by ANY installation.
    The cost is not cosmetic: the migrations carry 91 LLM prices where the
    bundle carries 242, and a model priced only by the bundle is billed by the
    provider and recorded at zero — the same class of blindness that left the
    demonstrator's daily ceiling reading 0,000025 EUR for 59 344 real tokens.

    What the gate protects is a user's CHOSEN personality, so that is what it
    must count.
    """

    def test_the_veto_counts_choices_not_rows(self) -> None:
        body = _executable_body()

        assert "FROM users WHERE personality_id IS NOT NULL" in body, (
            "counting rows in `personalities` can never be zero after the "
            "migrations that create them, so the seed branch is unreachable"
        )
        assert (
            "SELECT COUNT(*) FROM personalities;" not in body
        ), "the row count is the unreachable question; it must not come back"

    def test_the_migrations_still_populate_the_table_the_old_veto_watched(self) -> None:
        """Pin the fact the fix rests on, so a future change re-opens the case."""
        migration = (
            REPO_ROOT / "apps/api/alembic/versions/2025_12_03_0000-add_personalities.py"
        ).read_text(encoding="utf-8")

        assert "INSERT INTO personalities" in migration, (
            "if the migrations stop seeding personalities, the old row-count veto "
            "would become satisfiable again and this fix deserves a re-read"
        )
