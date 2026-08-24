"""Load the vendored registry snapshot.

The snapshot ships with the source tree and is the ONLY registry source at
runtime: nothing here touches the network. Refreshing it is a developer task
(``task llm:catalogue:fetch``) whose output is reviewed like any other diff.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("snapshot.json")

Snapshot = dict[str, dict[str, dict[str, Any]]]


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def load_snapshot() -> Snapshot:
    """Return the vendored snapshot, keyed by source then by entry key.

    Returns:
        ``{"litellm": {key: fields}, "modelsdev": {"provider/model": fields}}``.
    """
    raw = _raw()
    return {"litellm": raw["litellm"], "modelsdev": raw["modelsdev"]}


def snapshot_generated_at() -> datetime:
    """Return when the snapshot was fetched (timezone-aware UTC)."""
    return datetime.fromisoformat(_raw()["generated_at"])
