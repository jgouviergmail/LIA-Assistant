"""Where the toolbox reads and writes (ADR-329).

Two mounts, both set by the Taskfile:

- ``/data`` — the named volume ``lia-wake-data``: downloaded corpora, voices,
  synthesised clips and computed features. Gigabytes, never in the repository.
- ``/out`` — the repository's ``apps/web/public/models/wake``: the shipped
  models and their manifests, a few megabytes, committed.
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("WAKE_DATA_DIR", "/data"))
OUT_DIR = Path(os.environ.get("WAKE_OUT_DIR", "/out"))

DOWNLOADS = DATA_DIR / "downloads"
VOICES = DATA_DIR / "voices"
CORPORA = DATA_DIR / "corpora"
WORK = DATA_DIR / "work"


def language_dir(language: str) -> Path:
    """The working directory of one language (clips, features, checkpoints)."""
    path = WORK / language
    path.mkdir(parents=True, exist_ok=True)
    return path
