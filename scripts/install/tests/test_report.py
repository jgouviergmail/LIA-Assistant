"""Final report contract (B12/B13): informative, never secret."""

from __future__ import annotations

from pathlib import Path

from scripts.install.model import Exposure, InstallMode, PublicAnswers
from scripts.install.report import render_report

SECRETS = ("pw-CANARY-77", "sk-CANARY-99", "FERNET-CANARY==")


def _public(mode: InstallMode, exposure: Exposure) -> PublicAnswers:
    return PublicAnswers(
        language="en",
        mode=mode,
        exposure=exposure,
        admin_email="admin@ops.tld",
        admin_name="Ops",
        default_language="fr",
        observability=True,
        skill_sandbox=False,
        server_host="192.168.1.50" if exposure is Exposure.LAN else None,
        web_domain=None if exposure is Exposure.LAN else "lia.example.org",
        api_domain=None if exposure is Exposure.LAN else "api.example.org",
        caddy_email=None,
        manifest_path=(
            Path("lia-self-host-manifest.json")
            if mode is InstallMode.PREBUILT
            else None
        ),
    )


def test_lan_local_report_names_url_mode_and_backup_path() -> None:
    report = render_report(
        _public(InstallMode.LOCAL, Exposure.LAN),
        release_summary="local build",
        backup_dir=Path("/srv/lia-data/postgres-backups"),
        optional_unkeyed={"vision_analysis": "gemini"},
    )
    assert "http://192.168.1.50:3000" in report
    assert "local" in report
    assert "/srv/lia-data/postgres-backups" in report.replace("\\", "/")
    assert "vision_analysis" in report


def test_prebuilt_report_states_the_firebase_limitation() -> None:
    report = render_report(
        _public(InstallMode.PREBUILT, Exposure.CADDY),
        release_summary="v1.28.0 @sha256:abcd",
        backup_dir=Path("/srv/backups"),
        optional_unkeyed={},
    )
    assert "https://lia.example.org" in report
    assert "push" in report.lower() and "unavailable" in report.lower()
    assert "local build" in report.lower()


def test_report_never_carries_a_secret() -> None:
    report = render_report(
        _public(InstallMode.LOCAL, Exposure.LAN),
        release_summary="local build",
        backup_dir=Path("/srv/backups"),
        optional_unkeyed={},
    )
    for secret in SECRETS:
        assert secret not in report
    lowered = report.lower()
    for forbidden in ("fernet", "postgres_password", "secret_key"):
        assert forbidden not in lowered
