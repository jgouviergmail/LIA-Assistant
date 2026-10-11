"""Plugins API router contract (ADR-225).

Thin-composition endpoints over the already-tested orchestrator:
upload import, hardened URL import (reusing the skills SSRF fetch), listing
with component counts, and group uninstall. Plus the arbitrage-F lock on the
skills DELETE endpoint (a plugin's skill leaves through its plugin).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException, ValidationError
from src.domains.plugins.router import (
    PluginUrlImportRequest,
    delete_plugin,
    import_plugin_from_url,
    list_plugins,
)
from src.domains.plugins.schemas import PluginImportReport

pytestmark = pytest.mark.unit

_MANIFEST = (
    b'{"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "p"}'
)


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    return user


def _zip(members: dict[str, bytes]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for arc, data in members.items():
            zf.writestr(arc, data)
    return buf.getvalue()


class TestImportFromUrl:
    async def test_plugin_zip_reaches_the_orchestrator(self) -> None:
        content = _zip({"plugin.json": _MANIFEST})
        report = PluginImportReport(plugin_id=str(uuid4()), name="p")
        svc = MagicMock()
        svc.import_upload = AsyncMock(return_value=report)
        user = _user()

        with (
            patch(
                "src.domains.skills.url_import.fetch_skill_from_url",
                AsyncMock(return_value=(content, "plugin.zip")),
            ),
            patch(
                "src.domains.plugins.import_service.PluginImportService",
                return_value=svc,
            ),
        ):
            result = await import_plugin_from_url(
                body=PluginUrlImportRequest(url="https://example.com/plugin.zip"),
                user=user,
                db=MagicMock(),
            )

        svc.import_upload.assert_awaited_once_with(content, owner_id=user.id)
        assert result.name == "p"

    async def test_non_plugin_content_is_rejected(self) -> None:
        not_a_plugin = _zip({"alpha/SKILL.md": b"---\nname: alpha\n---\n"})

        with patch(
            "src.domains.skills.url_import.fetch_skill_from_url",
            AsyncMock(return_value=(not_a_plugin, "skill.zip")),
        ):
            with pytest.raises(BaseAPIException):
                await import_plugin_from_url(
                    body=PluginUrlImportRequest(url="https://example.com/skill.zip"),
                    user=_user(),
                    db=MagicMock(),
                )


class TestListPlugins:
    async def test_listing_uses_shared_owned_ui_projection(self) -> None:
        from src.domains.plugins.schemas import PluginListResponse

        user = _user()
        db = MagicMock()
        report = PluginListResponse()
        with patch(
            "src.domains.plugins.projection.list_plugin_projection", AsyncMock(return_value=report)
        ) as project:
            result = await list_plugins(user=user, db=db)
        assert result is report
        project.assert_awaited_once_with(db, user.id)


class TestDeletePlugin:
    async def test_delete_delegates_to_uninstall(self) -> None:
        svc = MagicMock()
        svc.uninstall = AsyncMock()
        user = _user()
        plugin_id = uuid4()

        with patch(
            "src.domains.plugins.import_service.PluginImportService",
            return_value=svc,
        ):
            await delete_plugin(plugin_id=plugin_id, user=user, db=MagicMock())

        svc.uninstall.assert_awaited_once_with(plugin_id, owner_id=user.id)


class TestSkillDeleteLock:
    """Arbitrage F on the skills endpoint: plugin skills leave via the plugin."""

    async def test_plugin_owned_skill_deletion_is_blocked(self) -> None:
        from src.domains.skills.router import delete_skill

        user = _user()
        cache = MagicMock()
        cache.get_by_name_for_user.return_value = {
            "name": "alpha",
            "scope": "user",
            "owner_id": str(user.id),
            "source_path": "/tmp/x/SKILL.md",
        }
        row = SimpleNamespace(plugin_id=uuid4())
        repo = MagicMock()
        repo.get_owned = AsyncMock(return_value=row)

        with (
            patch("src.domains.skills.cache.SkillsCache", cache),
            patch("src.domains.skills.repository.SkillRepository", return_value=repo),
        ):
            with pytest.raises(ValidationError):
                await delete_skill(skill_name="alpha", user=user, db=MagicMock())
