"""Pure verdict vocabulary for the habits domain (C-04, audit 2026-08-19).

Extracted from ``models.py`` so ``rhythm.py`` keeps its "pure and I/O-free"
promise for real: importing the detector used to pull the ORM chain
(BaseModel -> SQLAlchemy -> settings), which made the calibration harness
impossible to run outside the application env. ``models.py`` re-exports the
enum, so every historical import keeps working.
"""

from __future__ import annotations

from enum import Enum


class ProfileVerdict(str, Enum):
    """Verdict of the rhythm detector for one day class (or the profile).

    - WINDOWS: stable active windows were claimed.
    - DIFFUSE: activity everywhere — no time habit (an information, not a
      failure).
    - NONE: no window met the thresholds.
    - INSUFFICIENT: not enough observed days yet ("still learning").
    - SPARSE: too few active days — window claims would be factually false
      for an occasional user; recurrences remain detectable.
    """

    WINDOWS = "windows"
    DIFFUSE = "diffuse"
    NONE = "none"
    INSUFFICIENT = "insufficient"
    SPARSE = "sparse"
