"""Database dumps must not live inside the directory a deployment replaces.

The production deploy rebuilds the remote directory on every run. It used to do
so with ``sudo rm -rf ~/lia/*``, and ``POSTGRES_BACKUP_HOST_DIR`` defaulted to
``./backups/postgres`` — *inside* that directory. Every deployment therefore
erased every PostgreSQL dump the backup sidecar had produced since the previous
one.

Measured on the production host, 2026-08-05, minutes after a deployment::

    ls -la --time-style=+%Y-%m-%d_%H:%M ~/<deploy-dir>/backups/postgres
    drwx------ 2 <user> <user> 4096 2026-08-05_10:36 .   <- empty, stamped at deploy time

The sidecar (ADR-109) had been writing dumps that no restore could ever use: the
capability existed, the retention was zero, and nothing said so. The runbook
``DATABASE_BACKUP_RESTORE.md`` describes restoring from files that a deployment
had already removed.

Staging the bundle and swapping with ``mv`` (A2) is not enough on its own — the
dumps would merely move into ``lia.prev.*`` and disappear with the retention
sweep. The fix is positional: backups belong OUTSIDE the deployment directory,
so no deployment can reach them, whatever it does to its own tree.
"""

from __future__ import annotations

import re
from pathlib import Path
from posixpath import normpath

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"
ENV_TEMPLATES = (".env.prod.example", ".env.min.prod")

# The compose file lives at the root of the deployed directory, so a host path
# is safe only when it climbs out of it.
_BACKUP_MOUNT = re.compile(r"\$\{POSTGRES_BACKUP_HOST_DIR:-(?P<default>[^}]+)\}")


def _escapes_deploy_dir(host_path: str) -> bool:
    """Whether a compose host path resolves outside the deployed directory."""
    cleaned = host_path.strip()
    if cleaned.startswith(("/", "~")):
        return True  # absolute, or anchored in the operator's home
    # Relative paths resolve against the compose file's directory. Normalising
    # tells us whether the result climbs above it.
    return normpath(cleaned).startswith("..")


def _declared_default() -> str:
    compose = yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))
    volumes = (compose.get("services") or {}).get("postgres-backup", {}).get("volumes") or []
    for entry in volumes:
        match = _BACKUP_MOUNT.search(str(entry))
        if match:
            return match.group("default")
    pytest.fail("docker-compose.prod.yml must mount POSTGRES_BACKUP_HOST_DIR for postgres-backup")


class TestBackupsSurviveADeployment:
    """A dump inside the deployed tree is a dump the next deploy destroys."""

    def test_compose_default_is_outside_the_deployed_directory(self) -> None:
        default = _declared_default()

        assert _escapes_deploy_dir(default), (
            f"POSTGRES_BACKUP_HOST_DIR defaults to {default!r}, which resolves INSIDE the "
            f"deployed directory — the one every deployment replaces. Point it at a sibling "
            f"path (e.g. '../lia-data/postgres-backups') so the dumps outlive the deploy."
        )

    @pytest.mark.parametrize("template", ENV_TEMPLATES)
    def test_shipped_templates_do_not_reintroduce_the_defect(self, template: str) -> None:
        """The templates are what operators copy — they must carry the safe value."""
        path = REPO_ROOT / template
        if not path.is_file():
            pytest.skip(f"{template} absent from this checkout")

        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("POSTGRES_BACKUP_HOST_DIR="):
                continue
            value = line.split("=", 1)[1].split("#")[0].strip()
            assert _escapes_deploy_dir(value), (
                f"{template} sets POSTGRES_BACKUP_HOST_DIR={value!r}, inside the deployed "
                f"directory: an operator copying this template gets backups that the next "
                f"deployment erases."
            )
