"""The PROD folder must carry every root path the production build context needs.

``scripts/deploy/prepare-prod.ps1`` rebuilds a PROD directory from a **hand-kept
whitelist**, and that directory is the build CONTEXT of the production images.
CI never exercises this path: its own ``docker build`` runs against the whole
repository, so a path missing from the whitelist stays invisible until the image
is built on the Pi — ten minutes into a deployment.

That is exactly how v1.25.24 broke. ADR-157 added ``patches/`` — referenced by
``pnpm.patchedDependencies``, hence load-bearing for ``--frozen-lockfile`` — the
whitelist predated it, and the copy loop printed a yellow "non trouve" and
carried on. ``task deploy:prod`` then failed on
``COPY patches ./patches: "/patches": not found``.

This guard derives the requirement rather than restating it: the build contexts
come from ``docker-compose.prod.yml`` (what the deployment actually uses), and
only the services built from the repository ROOT are checked — the API builds
from ``apps/api``, whose content the script copies in its own dedicated section.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
PREPARE_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "prepare-prod.ps1"
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"

# `COPY [--flags] <src>... <dest>` — only the sources matter here.
_COPY = re.compile(r"^\s*COPY\s+(?P<body>.+)$", re.IGNORECASE)

# Root paths a Dockerfile copies that the whitelist does NOT have to carry,
# each with the reason it is exempt.
EXEMPT: dict[str, str] = {
    "apps": "copied per-app by the script's own apps/api and apps/web sections",
}


def _root_context_dockerfiles() -> list[tuple[str, Path]]:
    """(service, Dockerfile) for every prod service built from the repo root."""
    compose = yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))
    found: list[tuple[str, Path]] = []
    for service, spec in (compose.get("services") or {}).items():
        build = spec.get("build")
        if not isinstance(build, dict):
            continue
        if (build.get("context") or "").strip() not in {".", "./"}:
            continue
        dockerfile = build.get("dockerfile")
        if dockerfile:
            found.append((service, REPO_ROOT / dockerfile))
    return found


def _copied_root_paths(dockerfile: Path) -> set[str]:
    """Root-level sources a Dockerfile COPYs from the BUILD CONTEXT.

    `COPY --from=<stage>` reads from a previous stage's filesystem, not from the
    context, so those lines are skipped entirely rather than having their flag
    stripped — the path after them is an absolute path inside that stage.
    """
    found: set[str] = set()
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = _COPY.match(line)
        if not match:
            continue
        body = match.group("body")
        if "--from=" in body:
            continue
        tokens = [t for t in body.split() if not t.startswith("--")]
        for source in tokens[:-1]:  # the last token is the destination
            # `removeprefix`, not `strip("./")`: the latter also eats the LEADING
            # dot of a dotfile and turns `.npmrc` into `npmrc`, which then reads
            # as a missing path that was never missing.
            root = source.removeprefix("./").split("/")[0]
            if root and root not in EXEMPT and not root.startswith("$"):
                found.add(root)
    return found


def _whitelisted_paths() -> set[str]:
    """Root paths the preparation script copies into the PROD folder."""
    source = PREPARE_SCRIPT.read_text(encoding="utf-8")
    block = source.split("$rootPaths = @(", 1)
    assert len(block) == 2, "le bloc $rootPaths a disparu — la garde ne mesure plus rien"
    return set(re.findall(r'Path\s*=\s*"([^"]+)"', block[1].split(")", 1)[0]))


@pytest.mark.unit
def test_the_scan_still_finds_both_sides() -> None:
    """Guard against the guard rotting into a vacuous pass."""
    assert PREPARE_SCRIPT.exists(), "prepare-prod.ps1 introuvable"
    assert len(_whitelisted_paths()) >= 5, "liste blanche suspicieusement courte"

    services = _root_context_dockerfiles()
    assert services, "aucun service de production ne construit depuis la racine"
    for service, dockerfile in services:
        assert dockerfile.exists(), f"{service}: {dockerfile} introuvable"
        assert _copied_root_paths(dockerfile), f"{service}: aucune COPY de contexte reconnue"


@pytest.mark.unit
def test_every_copied_root_path_is_carried_into_the_prod_folder() -> None:
    whitelisted = _whitelisted_paths()
    offenders: list[str] = []
    for service, dockerfile in _root_context_dockerfiles():
        for missing in sorted(_copied_root_paths(dockerfile) - whitelisted):
            offenders.append(f"{service} ({dockerfile.name}) → {missing}")

    assert offenders == [], (
        "ces chemins sont copies depuis le contexte racine mais absents du dossier "
        f"PROD, donc `docker build` echouera sur l'hote de production : {offenders}. "
        "Ajouter chaque chemin a $rootPaths dans prepare-prod.ps1 (Required = $true "
        "quand son absence casse le build), ou l'exempter ici avec sa raison."
    )


@pytest.mark.unit
def test_patches_is_required_and_recursive() -> None:
    """`patches/` must be REQUIRED and copied recursively.

    It is a directory, and `pnpm install --frozen-lockfile` fails outright when a
    patch declared in `pnpm.patchedDependencies` is absent — so a warning would
    only move the failure to the production host, which is what happened.
    """
    entry = next(
        (
            line
            for line in PREPARE_SCRIPT.read_text(encoding="utf-8").splitlines()
            if '"patches"' in line and "Path" in line
        ),
        None,
    )
    assert entry is not None, "patches/ absent de $rootPaths"
    assert "Required = $true" in entry, f"patches/ doit etre requis : {entry.strip()}"
    assert "Recurse = $true" in entry, f"patches/ est un repertoire : {entry.strip()}"


@pytest.mark.unit
def test_a_missing_required_path_aborts_the_preparation() -> None:
    """The script must fail, not warn, when a required path is absent."""
    source = PREPARE_SCRIPT.read_text(encoding="utf-8")
    assert "$missingRequired" in source, "le suivi des chemins requis a disparu"
    assert re.search(
        r"if\s*\(\s*\$missingRequired\.Count\s*-gt\s*0\s*\)\s*\{\s*\r?\n\s*throw", source
    ), (
        "un chemin requis manquant doit lever, pas seulement s'afficher en jaune : "
        "c'est cet avertissement silencieux qui a laisse partir un dossier PROD "
        "incomplet en v1.25.24"
    )
