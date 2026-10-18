"""Recording fakes of the deploy primitives' tests (B08/B12/B14).

A runner that records every argv byte and answers from a script, and the
public answers and Compose selection of a plain LAN installation.
"""

from __future__ import annotations

from pathlib import Path

from scripts.install.compose import build_invocation
from scripts.install.deploy import CommandResult
from scripts.install.model import Exposure, InstallMode, PublicAnswers

DIGEST = "e" * 64


class _Runner:
    def __init__(self, results: list[CommandResult] | None = None) -> None:
        self.calls: list[dict] = []
        self._results = list(results or [])

    def __call__(self, argv, *, stdin=None, env=None):
        self.calls.append({"argv": list(argv), "stdin": stdin, "env": env})
        if self._results:
            return self._results.pop(0)
        return CommandResult(returncode=0, stdout="", stderr="")


def _public(mode: InstallMode = InstallMode.LOCAL) -> PublicAnswers:
    return PublicAnswers(
        language="en",
        mode=mode,
        exposure=Exposure.LAN,
        admin_email="admin@ops.tld",
        admin_name="Ops",
        default_language="fr",
        observability=False,
        skill_sandbox=False,
        server_host="192.168.1.50",
        web_domain=None,
        api_domain=None,
        caddy_email=None,
        manifest_path=None,
    )


def _invocation(mode: InstallMode = InstallMode.LOCAL):
    return build_invocation(_public(mode), root=Path("."))
