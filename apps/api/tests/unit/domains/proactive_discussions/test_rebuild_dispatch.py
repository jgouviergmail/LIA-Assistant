"""An explicit request wakes a retained native task without awaiting its model work."""

import asyncio
from uuid import uuid4

from src.infrastructure.proactive import discussion_rebuild
from src.infrastructure.proactive.discussion_rebuild import kick_context_rebuild


async def test_dispatch_returns_before_worker_finishes_and_carries_only_owner_and_epoch(
    monkeypatch,
):
    owner = uuid4()
    finish = asyncio.Event()
    calls = []

    async def run(user, *, rebuild_epoch):
        calls.append((user, rebuild_epoch))
        await finish.wait()

    # Patched where the name is READ: the dispatch module binds it at import.
    monkeypatch.setattr(discussion_rebuild, "run_for_owner", run)
    kick_context_rebuild(owner, 7)
    assert calls == []
    tasks = [
        task for task in asyncio.all_tasks() if task.get_name() == "discussion_context_rebuild"
    ]
    assert len(tasks) == 1
    try:
        await asyncio.sleep(0)
        assert calls == [(owner, 7)]
        assert not tasks[0].done()
    finally:
        finish.set()
        await asyncio.gather(*tasks)
