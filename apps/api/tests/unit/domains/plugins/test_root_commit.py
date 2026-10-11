"""A plugin root is recoverable across rename, commit rejection and missing acknowledgement."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.plugins.root_commit import PluginImportCompletionUnknown, commit_plugin_root

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "scenario", ["success", "rename_failure", "rejected", "lost_ack", "cleanup"]
)
async def test_plugin_root_commit_never_destroys_recoverable_bytes(tmp_path, scenario, existing):
    staged = tmp_path / "staging"
    staged.mkdir()
    (staged / "plugin.json").write_bytes(b"new approved version")
    live = tmp_path / "account" / "my-plugin"
    live.parent.mkdir(parents=True)
    if existing:
        live.mkdir()
        (live / "plugin.json").write_bytes(b"previous owned version")
    db = MagicMock(spec=AsyncSession)
    if scenario == "rejected":
        db.commit.side_effect = IntegrityError("commit", {}, ValueError("rejected"))
    elif scenario == "lost_ack":
        db.commit.side_effect = ConnectionError("ack lost")
    original_replace = __import__("os").replace
    failed = False

    def replace(source, target):
        nonlocal failed
        if scenario == "rename_failure" and Path(target) == live and not failed:
            failed = True
            raise OSError("new root could not be renamed")
        return original_replace(source, target)

    cleanup = (
        patch("src.domains.plugins.root_commit.cleanup_previous", side_effect=OSError("busy"))
        if scenario == "cleanup"
        else patch("src.domains.plugins.root_commit.logger")
    )
    with patch("src.domains.plugins.root_commit.os.replace", side_effect=replace), cleanup:
        if scenario in {"rename_failure", "rejected"}:
            with pytest.raises((OSError, IntegrityError)):
                await commit_plugin_root(db, staged, live)
            if existing:
                assert (live / "plugin.json").read_bytes() == b"previous owned version"
            else:
                assert not live.exists()
        elif scenario == "lost_ack":
            with pytest.raises(PluginImportCompletionUnknown):
                await commit_plugin_root(db, staged, live)
            assert (live / "plugin.json").read_bytes() == b"new approved version"
            assert (not existing) or any(
                path.read_bytes() == b"previous owned version"
                for path in tmp_path.rglob("plugin.json")
            )
        else:
            result = await commit_plugin_root(db, staged, live)
            assert result.committed and result.cleanup_pending == (scenario == "cleanup")
            assert (live / "plugin.json").read_bytes() == b"new approved version"
