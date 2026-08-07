"""Static Compose matrix proof (B04/B05) — renders EVERY scenario.

For each (exposure x mode x observability x skill-sandbox) combination this
script generates the full artifact set into a temporary directory — private
``.env`` (rendered from ``.env.min.prod``), ``docker-compose.install.yml``,
the Caddyfile when applicable, and a fixture digest lock for prebuilt — and
runs ``docker compose ... config --quiet``. It never pulls, builds, or
starts anything. Exit 0 means every scenario's merged model is valid.

Run: apps/api/.venv/Scripts/python scripts/install/tests/render_compose_matrix.py
"""

from __future__ import annotations

import itertools
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.install.compose import (  # noqa: E402
    build_invocation,
    locked_services,
    render_caddyfile,
    render_install_override,
)
from scripts.install.envgen import (  # noqa: E402
    derive_environment,
    generate_secrets,
    render_env,
)
from scripts.install.manifest import (  # noqa: E402
    ImageArtifact,
    PlatformArtifact,
    SelfHostManifest,
    render_image_lock,
)
from scripts.install.model import (  # noqa: E402
    Exposure,
    InstallMode,
    PublicAnswers,
)
from scripts.install.seed_bundle import compute_seed_bundle_sha256  # noqa: E402

_COPIED_FILES = ("docker-compose.prod.yml", "docker-compose.skill-sandbox.yml")
_FAKE_DIGEST = "ab" * 32


def _public(
    exposure: Exposure,
    mode: InstallMode,
    observability: bool,
    skill_sandbox: bool,
) -> PublicAnswers:
    return PublicAnswers(
        language="en",
        mode=mode,
        exposure=exposure,
        admin_email="admin@ops.tld",
        admin_name="Ops",
        default_language="fr",
        observability=observability,
        skill_sandbox=skill_sandbox,
        server_host="192.168.1.50" if exposure is Exposure.LAN else None,
        web_domain=None if exposure is Exposure.LAN else "lia.example.org",
        api_domain=None if exposure is Exposure.LAN else "api.example.org",
        caddy_email="acme@example.org" if exposure is Exposure.CADDY else None,
        manifest_path=None,
    )


def _fixture_manifest(services: tuple[str, ...]) -> SelfHostManifest:
    """A structurally valid manifest pinning every requested service."""
    platforms = tuple(
        PlatformArtifact(
            platform=platform,
            manifest_digest=f"sha256:{_FAKE_DIGEST}",
            config_digest=f"sha256:{_FAKE_DIGEST}",
        )
        for platform in ("linux/amd64", "linux/arm64")
    )
    images = tuple(
        ImageArtifact(
            service=service,
            reference=f"ghcr.io/example/lia/{service}@sha256:{_FAKE_DIGEST}",
            platforms=platforms,
        )
        for service in services
    )
    return SelfHostManifest(
        schema_version=1,
        release_version="v0.0.0-matrix",
        source_sha="0" * 40,
        built_at="1970-01-01T00:00:00Z",
        bundle_archive_sha256=_FAKE_DIGEST,
        bundle_tree_sha256=_FAKE_DIGEST,
        source_context_archive_sha256=_FAKE_DIGEST,
        source_context_tree_sha256=_FAKE_DIGEST,
        images=images,
        sboms={"api": _FAKE_DIGEST, "web": _FAKE_DIGEST},
        qualification="passed",
    )


def _render_scenario(root: Path, public: PublicAnswers) -> list[str]:
    for name in _COPIED_FILES:
        shutil.copy(REPO_ROOT / name, root / name)
    seeds_digest = compute_seed_bundle_sha256(REPO_ROOT)
    sandbox_image = None
    if public.skill_sandbox and public.mode is InstallMode.PREBUILT:
        sandbox_image = f"ghcr.io/example/lia/api@sha256:{_FAKE_DIGEST}"
    (root / "docker-compose.install.yml").write_text(
        render_install_override(
            public,
            seed_intent=True,
            seed_bundle_sha256=seeds_digest,
            sandbox_api_image=sandbox_image,
        ),
        encoding="utf-8",
    )
    environment = derive_environment(public, generate_secrets())
    base_env = (REPO_ROOT / ".env.min.prod").read_text(encoding="utf-8")
    (root / ".env").write_text(render_env(base_env, dict(environment)), encoding="utf-8")
    if public.exposure is Exposure.CADDY:
        caddy_dir = root / "infrastructure" / "caddy"
        caddy_dir.mkdir(parents=True)
        (caddy_dir / "Caddyfile").write_text(
            render_caddyfile(public, template_root=REPO_ROOT), encoding="utf-8"
        )
    if public.mode is InstallMode.PREBUILT:
        manifest = _fixture_manifest(locked_services(public))
        (root / "docker-compose.images.yml").write_text(
            render_image_lock(manifest, locked_services(public)), encoding="utf-8"
        )
    invocation = build_invocation(public, root=root)
    return invocation.prefix() + ["config", "--quiet"]


def main() -> int:
    failures: list[str] = []
    scenarios = list(
        itertools.product(Exposure, InstallMode, (False, True), (False, True))
    )
    for exposure, mode, observability, sandbox in scenarios:
        label = f"{exposure.value}/{mode.value}/obs={observability}/sandbox={sandbox}"
        with tempfile.TemporaryDirectory(prefix="lia-matrix-") as tmp:
            root = Path(tmp)
            argv = _render_scenario(
                root, _public(exposure, mode, observability, sandbox)
            )
            result = subprocess.run(
                argv, cwd=root, capture_output=True, text=True
            )
            if result.returncode != 0:
                failures.append(f"{label}\n{result.stderr.strip()}")
                print(f"FAIL {label}")
            else:
                print(f"ok   {label}")
    if failures:
        print(f"\n{len(failures)}/{len(scenarios)} scenarios failed:", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"\nall {len(scenarios)} scenarios validate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
