"""The operator's switch over the public demonstrator link.

"Take the demo offline" is the most urgent action an operator can need, so it
must be one click away and take effect immediately — not at the next deploy.

What must hold:
- flipping it goes through the AUDITED generic store, like every other
  operator decision, with the admin and the reason recorded;
- the admin surface reports the DEPLOYMENT fact too (whether a URL is even
  configured): switching on an instance that serves no demonstrator must read
  as "nothing to show", not as a working link;
- the endpoints are superuser-only — the anonymous read is the other route,
  and it discloses the URL only when the switch is on.
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _settings(url: str) -> MagicMock:
    fake = MagicMock()
    fake.demo_instance_public_url = url
    return fake


async def test_the_admin_view_reports_the_switch_and_the_deployment_fact() -> None:
    from src.domains.product.public_demo_link_admin import read_admin_view

    with (
        patch(
            "src.domains.product.public_demo_link.settings",
            _settings("https://demo.example.org"),
        ),
        patch(
            "src.domains.product.public_demo_link.read_setting",
            AsyncMock(return_value=True),
        ),
    ):
        view = await read_admin_view()

    assert view.enabled is True
    assert view.url == "https://demo.example.org"
    # An operator must be able to tell "switched off" from "nothing deployed".
    assert view.url_configured is True


async def test_switching_on_without_a_deployed_url_reads_as_nothing_to_show() -> None:
    from src.domains.product.public_demo_link_admin import read_admin_view

    with (
        patch("src.domains.product.public_demo_link.settings", _settings("")),
        patch(
            "src.domains.product.public_demo_link.read_setting",
            AsyncMock(return_value=True),
        ),
    ):
        view = await read_admin_view()

    assert view.url_configured is False
    # The switch is honestly reported as ON, but nothing is served: the admin
    # card can then say WHY instead of showing a link that does not exist.
    assert view.enabled is False
    assert view.url is None


async def test_flipping_the_switch_is_audited() -> None:
    from src.domains.product.public_demo_link_admin import set_public_demo_link
    from src.domains.system_settings.models import SystemSettingKey

    db = AsyncMock()
    admin_id = uuid4()
    request = MagicMock()
    write = AsyncMock()

    with (
        patch("src.domains.product.public_demo_link_admin.write_setting", write),
        patch(
            "src.domains.product.public_demo_link.settings",
            _settings("https://demo.example.org"),
        ),
        patch(
            "src.domains.product.public_demo_link.read_setting",
            AsyncMock(return_value=False),
        ),
    ):
        await set_public_demo_link(
            db, enabled=False, admin_user_id=admin_id, request=request, change_reason="incident"
        )

    write.assert_awaited_once_with(
        db,
        SystemSettingKey.PUBLIC_DEMO_LINK_ENABLED,
        False,
        action=ANY,
        admin_user_id=admin_id,
        request=request,
        change_reason="incident",
    )


def test_the_admin_router_is_superuser_only() -> None:
    from src.domains.product.public_demo_link_admin import router

    names = [
        getattr(dependency.dependency, "__name__", "")
        for dependency in getattr(router, "dependencies", [])
    ]
    # The anonymous route is the OTHER one; this one flips the switch.
    assert any("superuser" in name for name in names), names
