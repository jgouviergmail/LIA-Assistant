"""Operational scheduler failures keep their type, diagnostic text stays at DEBUG."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED

from src.infrastructure.scheduler import leader_elector as module


@pytest.mark.parametrize("stage", ["acquire", "shutdown", "start", "callback", "renew", "election"])
async def test_failure_text_never_reaches_operational_scheduler_events(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    private = "PRIVATE_CALLBACK_PAYLOAD"
    failure = RuntimeError(private)
    log = MagicMock()
    monkeypatch.setattr(module, "logger", log)
    redis = AsyncMock()
    redis.eval.return_value = 1
    scheduler = MagicMock(state=STATE_STOPPED, running=False)
    elector = module.SchedulerLeaderElector(redis, scheduler)
    try:
        if stage == "acquire":
            redis.set.side_effect = failure
            assert await elector._try_acquire() is False
        elif stage == "shutdown":
            scheduler.running = True
            scheduler.shutdown.side_effect = failure
            await elector.shutdown()
        elif stage == "start":
            scheduler.add_job.side_effect = failure
            await elector._become_leader()
        elif stage == "callback":
            elector._on_elected = AsyncMock(side_effect=failure)
            await elector._become_leader()
        elif stage == "renew":
            elector._is_leader = True
            scheduler.state = STATE_RUNNING
            redis.eval.side_effect = failure
            await elector._renew_lock()
            assert not elector.is_leader
        else:
            elector._re_election_interval = 0
            monkeypatch.setattr(elector, "_try_acquire", AsyncMock(side_effect=failure))
            await elector._re_election_loop()

        events = [
            call for method in [log.info, log.warning, log.error] for call in method.call_args_list
        ]
        assert events
        assert any(call.kwargs.get("error_type") == "RuntimeError" for call in events)
        assert all(private not in repr(call) for call in events)
        assert any(call.kwargs.get("exc_info") is failure for call in log.debug.call_args_list)
    finally:
        await elector.shutdown()
