"""Cancellation cannot remove private package staging while its worker still uses it."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.plugins import import_service
from tests.unit.domains.plugins.test_import_service import _manifest, _plugin_zip

pytestmark = pytest.mark.unit


async def test_repeated_import_cancellation_finishes_the_same_stage_before_cleanup(monkeypatch):
    started, release = threading.Event(), threading.Event()
    observed = []
    original = import_service.stage_plugin_zip

    def stage(content, root, settings):
        result = original(content, root, settings)
        observed.append(root)
        started.set()
        assert release.wait(timeout=5)
        assert result.exists(), "package staging was cleaned before its worker finished"
        return result

    monkeypatch.setattr(import_service, "stage_plugin_zip", stage)
    service = import_service.PluginImportService(MagicMock(spec=AsyncSession))
    service._install_from_root = AsyncMock()
    task = asyncio.create_task(
        service.import_upload(_plugin_zip(manifest=_manifest()), owner_id=uuid4())
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(observed) == 1 and not observed[0].exists()
    service._install_from_root.assert_not_awaited()
