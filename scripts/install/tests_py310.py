"""Python 3.10 wizard self-check (ADR-215, B01) — NO pytest, NO venv.

Run by the dedicated CI job as ``python -B scripts/install/tests_py310.py``
under EXACTLY Python 3.10: importing every wizard module there proves no
3.11+ syntax or runtime API slipped in (StrEnum, tomllib, datetime.UTC...).
It also re-checks the stdlib-only import allowlist by AST and exercises the
enum + manifest surface.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

INSTALL_ROOT = Path(__file__).resolve().parent

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def check_stdlib_only() -> None:
    for module_path in sorted(INSTALL_ROOT.glob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if name.startswith("scripts.install"):
                    continue
                check(
                    top in sys.stdlib_module_names,
                    f"{module_path.name}: non-stdlib import {name}",
                )


def check_imports_and_enums() -> None:
    from scripts.install import (  # noqa: F401
        answers,
        compose,
        deploy,
        envgen,
        host_paths,
        i18n,
        log,
        manifest,
        model,
        preflight,
        questions,
        redaction,
        report,
        rollback,
        seed_bundle,
        state,
        verify,
    )

    check(model.InstallMode("local") is model.InstallMode.LOCAL, "InstallMode")
    check(model.Exposure("caddy") is model.Exposure.CADDY, "Exposure")
    check(state.Step("bootstrap") is state.Step.BOOTSTRAP, "Step")
    check(
        model.REQUIRED_PROVIDER_IDS == ("deepseek", "openai"),
        "provider tuple drifted",
    )
    check(len(questions.build_questions()) >= 13, "questionnaire too short")

    fake_digest = "ab" * 32
    platforms = tuple(
        manifest.PlatformArtifact(
            platform=platform,
            manifest_digest=f"sha256:{fake_digest}",
            config_digest=f"sha256:{fake_digest}",
        )
        for platform in ("linux/amd64", "linux/arm64")
    )
    parsed = manifest.SelfHostManifest(
        schema_version=1,
        release_version="v0",
        source_sha="0" * 40,
        built_at="2026-01-01T00:00:00Z",
        bundle_archive_sha256=fake_digest,
        bundle_tree_sha256=fake_digest,
        source_context_archive_sha256=fake_digest,
        source_context_tree_sha256=fake_digest,
        images=tuple(
            manifest.ImageArtifact(
                service=service,
                reference=f"ghcr.io/x/y/{service}@sha256:{fake_digest}",
                platforms=platforms,
            )
            for service in manifest._catalogue_services()
        ),
        sboms={"api": fake_digest, "web": fake_digest},
        qualification="passed",
    )
    errors = manifest.validate_manifest(parsed)
    check(errors == (), f"fixture manifest invalid: {errors}")


def main() -> int:
    if sys.version_info >= (3, 11):
        print(
            f"WARNING: running under {sys.version.split()[0]}; the CI job "
            "pins 3.10 — local runs only smoke-check.",
            file=sys.stderr,
        )
    check(sys.dont_write_bytecode, "must run with -B (PYTHONDONTWRITEBYTECODE)")
    check_stdlib_only()
    check_imports_and_enums()
    if FAILURES:
        for failure in FAILURES:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("py310 wizard self-check: all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
