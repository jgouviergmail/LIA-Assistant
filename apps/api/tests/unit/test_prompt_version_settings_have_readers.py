"""Every ``*_prompt_version`` setting is read by the code (prompt audit 2026-09-12, lot D).

Four of them (``router``, ``v3_router``, ``v3_smart_planner``, ``contacts_agent``) had
no reader at all — the router prompt they versioned no longer exists — yet
``.env.example`` documented them and ``CLAUDE.md`` used ``ROUTER_PROMPT_VERSION`` as
its example. A knob nobody reads teaches an operator that turning it does something.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.config import Settings

API_ROOT = Path(__file__).resolve().parents[2]
SRC = API_ROOT / "src"


def _prompt_version_settings() -> list[str]:
    return sorted(name for name in Settings.model_fields if name.endswith("_prompt_version"))


def _source_outside_config() -> str:
    chunks: list[str] = []
    for path in SRC.rglob("*.py"):
        if "core" in path.parts and "config" in path.parts:
            continue
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_the_guard_sees_the_settings() -> None:
    assert len(_prompt_version_settings()) > 5


def test_every_prompt_version_setting_has_a_reader() -> None:
    source = _source_outside_config()
    unread = [
        name
        for name in _prompt_version_settings()
        if not re.search(rf"\.{re.escape(name)}\b", source)
    ]
    assert not unread, (
        f"settings with no reader: {unread} — delete them (and their .env lines), "
        "or wire the prompt they version"
    )
