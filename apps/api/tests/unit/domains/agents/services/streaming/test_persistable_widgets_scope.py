"""Only THIS turn's widgets get attached to the message being archived.

``_emit_post_stream_registry`` deliberately falls back to the cross-turn
``registry`` for DISPLAY when the turn produced nothing. That fallback carries
up to ``REGISTRY_MAX_ITEMS`` entries — 70 observed in production (run
``e8f42f65``). Capturing from it would attach widgets from earlier turns to a
message that never displayed them: metadata bloat, and a stale payload kept
alive far past its turn.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.services.streaming.service import StreamingService


def _widget(registry_id: str, skill_name: str = "interactive-map") -> dict[str, Any]:
    return {
        "id": registry_id,
        "type": "SKILL_APP",
        "payload": {
            "_registry_id": registry_id,
            "skill_name": skill_name,
            "frame_url": "https://www.google.com/maps/embed?pb=x",
            "is_system_skill": True,
        },
        "meta": {"source": "skill", "timestamp": "2026-07-21T09:13:00Z"},
    }


async def _drain(service: StreamingService, state: dict[str, Any]) -> None:
    """Run the emission generator to completion, discarding the SSE chunks."""
    async for _ in service._emit_post_stream_registry(state, set(), "test-run"):
        pass


class TestPersistableWidgetScope:
    @pytest.fixture
    def service(self) -> StreamingService:
        return StreamingService.__new__(StreamingService)  # no I/O deps needed

    @pytest.fixture(autouse=True)
    def _init_attributes(self, service: StreamingService) -> None:
        service.persistable_widgets = {}
        service.voice_context_registry = None

    async def test_captures_the_widget_this_turn_produced(self, service: StreamingService) -> None:
        state = {
            "current_turn_registry": {"skill_app_now": _widget("skill_app_now")},
            "registry": {"skill_app_now": _widget("skill_app_now")},
        }

        await _drain(service, state)

        assert set(service.persistable_widgets) == {"skill_app_now"}

    async def test_ignores_the_cross_turn_fallback_registry(
        self, service: StreamingService
    ) -> None:
        """The production shape: this turn produced no widget, but the fallback
        registry still carries one from an earlier turn."""
        state: dict[str, Any] = {
            "current_turn_registry": {},
            "registry": {
                "skill_app_previous_turn": _widget("skill_app_previous_turn"),
                "weather_1": {
                    "id": "weather_1",
                    "type": "WEATHER",
                    "payload": {},
                    "meta": {"source": "tool", "timestamp": "2026-07-21T09:13:00Z"},
                },
            },
        }

        await _drain(service, state)

        assert service.persistable_widgets == {}

    async def test_keeps_only_the_current_turn_slice_of_a_mixed_registry(
        self, service: StreamingService
    ) -> None:
        state = {
            "current_turn_registry": {"skill_app_now": _widget("skill_app_now")},
            "registry": {
                "skill_app_now": _widget("skill_app_now"),
                "skill_app_old": _widget("skill_app_old", skill_name="tic-tac-toe"),
            },
        }

        await _drain(service, state)

        assert set(service.persistable_widgets) == {"skill_app_now"}

    async def test_empty_state_captures_nothing(self, service: StreamingService) -> None:
        await _drain(service, {})
        assert service.persistable_widgets == {}
