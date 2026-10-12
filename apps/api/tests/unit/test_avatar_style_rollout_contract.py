"""An operator campaign cannot silently become a universal installation default."""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
REPO_ROOT = repo_root_or_skip()
VARIABLE = "AVATAR_STYLE_ROLLOUT_ID"


@pytest.mark.parametrize("filename", [".env.example", ".env.prod.example"])
def test_operator_campaign_examples_are_disabled(filename: str) -> None:
    body = (REPO_ROOT / filename).read_text(encoding="utf-8")
    assert re.search(rf"^{VARIABLE}=\s*$", body, re.M)


def test_campaign_is_runtime_web_only_and_empty_by_default() -> None:
    body = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    parts = re.split(r"\n  ([a-z][a-z0-9-]*):\n", body)
    services = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    assert f"- {VARIABLE}=${{{VARIABLE}:-}}" in services["web"]
    assert VARIABLE not in services["web"].split("environment:", 1)[0]
    assert VARIABLE not in services["api"]


def test_installer_and_backend_do_not_activate_a_browser_campaign() -> None:
    # The local display preference is not an account database column, backend
    # Settings value or wizard decision. An ordinary install must stay inert.
    for path in (REPO_ROOT / "scripts/install").glob("*.py"):
        assert VARIABLE not in path.read_text(encoding="utf-8"), path
    for path in (REPO_ROOT / "apps/api/src/core/config").glob("*.py"):
        assert VARIABLE not in path.read_text(encoding="utf-8"), path
