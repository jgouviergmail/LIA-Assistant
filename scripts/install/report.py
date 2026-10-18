"""Final operator report (B12/B13).

Everything an operator needs — URL, mode, release identity, backup
location, known limitations — and nothing a log should not hold: no
password, key, generated secret, or internal token ever enters this text.
"""

from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping

from scripts.install.model import Exposure, InstallMode, PublicAnswers


def _origin(public: PublicAnswers) -> str:
    if public.exposure is Exposure.LAN:
        return f"http://{public.server_host}:3000"
    return f"https://{public.web_domain}"


INSTALLED_HEADING = "LIA installation complete."
RECONFIGURED_HEADING = "LIA reconfiguration complete."


def render_report(
    public: PublicAnswers,
    *,
    release_summary: str,
    backup_dir: Path,
    optional_unkeyed: Mapping[str, str] | None,
    heading: str = INSTALLED_HEADING,
) -> str:
    """Render the final non-secret installation report.

    Args:
        public: The installation's public answers.
        release_summary: How the images were obtained.
        backup_dir: Where the database backups land.
        optional_unkeyed: What the bootstrap reported degraded (capability →
            provider); ``None`` when this run has no such report — a
            reconfiguration touches no key, an unreadable bootstrap output
            says nothing — and the report then points at the Admin UI rather
            than claiming a list.
        heading: The first line.

    Returns:
        The report text.
    """
    lines = [
        heading,
        "",
        f"  Web UI:        {_origin(public)}",
        f"  Admin account: {public.admin_email}",
        f"  Install mode:  {public.mode.value}",
        f"  Release:       {release_summary}",
        f"  Exposure:      {public.exposure.value}",
        f"  Database backups: {backup_dir}",
    ]
    if public.observability:
        lines.append("  Observability stack: enabled (profile 'observability')")
    if optional_unkeyed is None:
        lines += [
            "",
            "Optional capabilities: the Admin UI (LLM Configuration) shows",
            "which provider keys this instance holds.",
        ]
    elif optional_unkeyed:
        lines.append("")
        lines.append("Optional capabilities without a configured key (degraded):")
        lines.extend(
            f"  - {capability} ({provider}) — add the key later in the Admin UI"
            for capability, provider in sorted(optional_unkeyed.items())
        )
    if public.mode is InstallMode.PREBUILT:
        lines += [
            "",
            "Limitations of the generic prebuilt artifact:",
            "  - Firebase web push is unavailable (public Firebase fields are",
            "    baked empty); notifications fall back to in-app delivery.",
            "  - Custom public build-time values require a local build",
            "    (./install.sh --local-build).",
        ]
    lines += [
        "",
        "Provider keys live encrypted in the database (Admin UI > LLM",
        "Configuration). This report contains no secrets by design.",
    ]
    return "\n".join(lines) + "\n"
