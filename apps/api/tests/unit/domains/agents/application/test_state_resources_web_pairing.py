"""The open screens know every resource the API tells them to read again.

A confirmed application act names the resources it changed (``ApplicationResource``).
The web validates that event against its own list (``apps/web/src/types/application-state.ts``)
and refuses the WHOLE event when one name is unknown: a resource added on one side only
is a screen that never refreshes, silently (found adding ``writing_style``, 2026-11-16).
The API is the authority; this test holds the web copy to it, reading the TypeScript
source rather than a generated artefact.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from src.domains.agents.application.state_resources import ApplicationResource
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit


def test_the_web_knows_exactly_the_resources_the_api_publishes() -> None:
    path = Path(repo_root_or_skip()) / "apps" / "web" / "src" / "types" / "application-state.ts"
    source = path.read_text(encoding="utf-8")
    block = re.search(r"const applicationResource = z\.enum\(\[(.*?)\]\);", source, re.S)
    assert block is not None, "application-state.ts no longer declares applicationResource"

    known = set(re.findall(r"'([a-z_]+)'", block.group(1)))

    assert known == set(get_args(ApplicationResource))
