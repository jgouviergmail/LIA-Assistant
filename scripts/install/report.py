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


def render_report(
    public: PublicAnswers,
    *,
    release_summary: str,
    backup_dir: Path,
    optional_unkeyed: Mapping[str, str],
) -> str:
    """Render the final non-secret installation report."""
    lines = [
        "LIA installation complete.",
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
    if optional_unkeyed:
        lines.append("")
        lines.append("Optional capabilities without a configured key (degraded):")
        lines.extend(
            f"  - {llm_type} ({provider}) — add the key later in the Admin UI"
            for llm_type, provider in sorted(optional_unkeyed.items())
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
