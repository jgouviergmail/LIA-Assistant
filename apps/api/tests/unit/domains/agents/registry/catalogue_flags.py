"""The feature flags behind which catalogue manifests load, for full-catalogue guard runs.

A manifest gated OFF in the measuring environment escapes any guard run over
the default catalogue, and the same guard would then refuse the boot in
production. Measured 2026-09-03: ``place_phone_call_tool`` was invisible to the
first mutation-policy inventory because ``telephony_enabled`` was off.
"""

from __future__ import annotations

import pytest

CATALOGUE_FEATURE_FLAGS: tuple[str, ...] = (
    "health_metrics_enabled",
    "sub_agents_enabled",
    "image_generation_enabled",
    "document_generation_enabled",
    "devops_enabled",
    "diagnostics_enabled",
    "python_sandbox_tool_enabled",
    "telephony_enabled",
    # ``peers_enabled`` — NOT "peer_connections_enabled", which does not
    # exist: the phantom name silently disabled this branch and four peer
    # manifests escaped the guard entirely (measured 2026-09-04).
    "peers_enabled",
    "skills_enabled",
    "mcp_enabled",
)


def enable_every_catalogue_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch on every flag a catalogue manifest loads behind, for this test only.

    Args:
        monkeypatch: The test's monkeypatch, which restores every flag after.
    """
    from src.core.config import settings

    for flag in CATALOGUE_FEATURE_FLAGS:
        if hasattr(settings, flag):
            monkeypatch.setattr(settings, flag, True, raising=False)
