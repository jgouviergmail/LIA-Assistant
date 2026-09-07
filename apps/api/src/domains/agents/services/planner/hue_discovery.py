"""Reading the names of the person's Hue lights and rooms, for the planner.

Extracted from :mod:`smart_planner_service` on 2026-09-07, when recording this
read pushed that module past its shrink-only size cap. The cap does not move,
so the answer is an extraction — and this is a unit: one question (what are the
person's devices called?), one discovery call, one rendering.

**It is a READ, and it is recorded.** The planner reaches the bridge through
its CLIENT, so the tool gate that fills the consultation register never sees
it: the same lookup is registered when the person asks « quelles lampes
ai-je ? » through a tool, and was silent when the planner asked it on their
behalf. The Hue WRITES were never at risk — ``control_hue_light_tool`` and its
siblings declare ``mutation_policy="reversible"`` and are gated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.domains.agents.context.runtime_context import runtime_user_id_str

if TYPE_CHECKING:  # pragma: no cover - typing only
    from langchain_core.runnables import RunnableConfig

logger = structlog.get_logger(__name__)


async def build_iot_device_context(
    domains: list[str] | None,
    config: RunnableConfig,
) -> str:
    """Discover IoT device names and inject them into planner context.

    When Hue domain is active, performs a lightweight discovery call to the
    Hue Bridge API to fetch available light and room names. This allows the
    planner to map user descriptions to exact device names, avoiding
    paraphrased names (e.g., "plafond du salon" vs "Plafond salon").

    Follows the same pattern as MCP reference discovery: fetch external
    resource metadata before planning so the LLM can make informed decisions.

    Args:
        domains: Detected domains for the current query.
        config: RunnableConfig with user/session info for credential lookup.

    Returns:
        IoT context string with available device names, or empty string.
    """
    from time import perf_counter

    from src.domains.agents.constants import INTENTION_HUE

    if not domains or INTENTION_HUE not in domains:
        return ""

    try:
        from uuid import UUID

        from src.domains.agents.effects.treatments import record_treatment
        from src.domains.connectors.clients.philips_hue_client import PhilipsHueClient
        from src.domains.connectors.service import ConnectorService
        from src.infrastructure.database.session import AsyncSessionLocal

        config.get("configurable", {})
        user_id = runtime_user_id_str(None)
        if not user_id:
            return ""

        user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id

        # Create a short-lived session for credential lookup
        async with AsyncSessionLocal() as db_session:
            connector_service = ConnectorService(db_session)
            credentials = await connector_service.get_hue_credentials(user_uuid)
            if not credentials:
                return ""

            client = PhilipsHueClient(user_uuid, credentials, connector_service)

            # Discovery calls — lightweight GET requests to the Hue Bridge.
            # Recorded: the planner reaches the bridge through its CLIENT,
            # so the tool gate that fills the consultation register never
            # sees it, and the same read is registered when the person
            # asks « quelles lampes ai-je ? » and silent when the planner
            # asks it for them. The WRITES stay gated by their tools.
            _started = perf_counter()
            _read_failed = False
            try:
                lights = await client.list_lights()
                rooms = await client.list_rooms()
            except Exception:
                _read_failed = True
                raise
            finally:
                record_treatment(
                    "planner:hue",
                    None,
                    succeeded=not _read_failed,
                    duration_ms=int((perf_counter() - _started) * 1000),
                )

        light_names = [
            lt.get("metadata", {}).get("name", "")
            for lt in lights
            if lt.get("metadata", {}).get("name")
        ]
        room_names = [
            rm.get("metadata", {}).get("name", "")
            for rm in rooms
            if rm.get("metadata", {}).get("name")
        ]

        if not light_names and not room_names:
            return ""

        parts: list[str] = []
        if light_names:
            parts.append(
                "AVAILABLE HUE LIGHTS (use EXACT name for light_name_or_id):\n"
                + ", ".join(f'"{n}"' for n in light_names)
            )
        if room_names:
            parts.append(
                "AVAILABLE HUE ROOMS (use EXACT name for room_name_or_id):\n"
                + ", ".join(f'"{n}"' for n in room_names)
            )

        logger.debug(
            "iot_device_context_injected",
            domain=INTENTION_HUE,
            light_count=len(light_names),
            room_count=len(room_names),
        )
        return "\n".join(parts)

    except Exception as e:
        logger.debug(
            "iot_device_context_failed",
            domain=INTENTION_HUE,
            error=str(e),
            error_type=type(e).__name__,
        )
        return ""
