"""The habits capability, read where the learning and its consumption ACT.

ADR-280 amendment (2026-09-11): ``habits`` moves from « the route is the
capability » to « the guard sits at the act ». Measured with the operator
switch OFF: the nightly job recomputed, the heartbeat was served the rhythm,
the tick was deferred toward the learned window, and only the settings panel
— the record the person reads and corrects — had closed. A switch removes
the CAPABILITY, never the RECORD (ADR-279's rule, generalised by ADR-280).

One predicate, async because the operator switch lives in the settings
store and must take effect without a restart; every act calls it AT CALL
TIME, never at boot. It never raises — a failing store resolves to the
deployment value (``is_capability_enabled``'s own contract).
"""

from __future__ import annotations

from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled


async def habits_capability_enabled() -> bool:
    """Whether habit learning and its consumption may act right now.

    Returns:
        True when both the deployment ceiling and the operator switch allow it.
    """
    return await is_capability_enabled(PlatformCapability.HABITS)
