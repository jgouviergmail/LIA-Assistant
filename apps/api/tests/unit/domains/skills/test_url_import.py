"""URL-sourced skill import hardening (UXR Lot 10, B12).

Pins the SSRF matrix, the redirect refusal, the streamed size cap and the
content sniffing of ``fetch_skill_from_url``. The SSRF core is the REUSED
``agents/web_fetch/url_validator`` (scheme, hostname blacklist, DNS resolve +
blocked ranges incl. IPv4-mapped IPv6) — these tests exercise it through the
import path, plus the import-specific https-only pre-check.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import HTTPException

from src.domains.agents.web_fetch import url_validator
from src.domains.skills.url_import import fetch_skill_from_url

pytestmark = pytest.mark.unit

ZIP_MAGIC = b"PK\x03\x04rest-of-zip"
SKILL_MD = b"---\nname: net-skill\ndescription: d\n---\nBody."


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _detail(exc_info: pytest.ExceptionInfo[HTTPException]) -> str:
    return str(exc_info.value.detail)


class TestSsrfMatrix:
    async def test_plain_http_refused_before_any_io(self) -> None:
        with pytest.raises(HTTPException) as exc:
            await fetch_skill_from_url("http://example.com/skill.zip")
        assert exc.value.status_code == 400
        assert _detail(exc).startswith("url_not_https")

    @pytest.mark.parametrize(
        "url",
        [
            "https://127.0.0.1/skill.zip",
            "https://[::1]/skill.zip",
            "https://10.0.0.8/skill.zip",
            "https://172.16.4.2/skill.zip",
            "https://192.168.1.10/skill.zip",
            "https://169.254.169.254/latest/meta-data",
            "https://localhost/skill.zip",
        ],
    )
    async def test_private_and_metadata_targets_blocked(self, url: str) -> None:
        with pytest.raises(HTTPException) as exc:
            await fetch_skill_from_url(url)
        assert exc.value.status_code == 400
        assert _detail(exc).startswith("url_blocked")

    async def test_dns_resolving_to_private_ip_blocked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(url_validator, "_resolve_dns_sync", lambda _h: ["192.168.77.77"])
        with pytest.raises(HTTPException) as exc:
            await fetch_skill_from_url("https://rebind.example.com/skill.zip")
        assert exc.value.status_code == 400
        assert _detail(exc).startswith("url_blocked")


class TestFetchBehavior:
    @pytest.fixture(autouse=True)
    def _public_dns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(url_validator, "_resolve_dns_sync", lambda _h: ["93.184.216.34"])

    async def test_redirects_are_refused_not_followed(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://evil.example/x.zip"})

        with pytest.raises(HTTPException) as exc:
            await fetch_skill_from_url("https://example.com/skill.zip", client=_client(handler))
        assert exc.value.status_code == 400
        assert _detail(exc).startswith("url_blocked")

    async def test_non_200_is_fetch_failed(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        with pytest.raises(HTTPException) as exc:
            await fetch_skill_from_url("https://example.com/skill.zip", client=_client(handler))
        assert exc.value.status_code == 502
        assert _detail(exc).startswith("url_fetch_failed")

    async def test_oversized_body_aborts_mid_stream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "skills_url_import_max_bytes", 64)

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"x" * 1024)

        with pytest.raises(HTTPException) as exc:
            await fetch_skill_from_url("https://example.com/skill.zip", client=_client(handler))
        assert exc.value.status_code == 413
        assert _detail(exc).startswith("url_too_large")

    async def test_zip_filename_from_url_basename(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=ZIP_MAGIC)

        content, filename = await fetch_skill_from_url(
            "https://example.com/dl/my-skill.zip?token=1", client=_client(handler)
        )
        assert content == ZIP_MAGIC
        assert filename == "my-skill.zip"

    async def test_zip_magic_fallback_without_extension(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=ZIP_MAGIC)

        _content, filename = await fetch_skill_from_url(
            "https://example.com/download", client=_client(handler)
        )
        assert filename == "skill.zip"

    async def test_markdown_fallback_without_extension(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=SKILL_MD)

        content, filename = await fetch_skill_from_url(
            "https://example.com/raw/skill", client=_client(handler)
        )
        assert content == SKILL_MD
        assert filename == "SKILL.md"

    async def test_non_skill_content_rejected(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html><body>Not a skill</body></html>")

        with pytest.raises(HTTPException) as exc:
            await fetch_skill_from_url("https://example.com/page", client=_client(handler))
        assert exc.value.status_code == 422
        assert _detail(exc).startswith("url_not_skill_content")

    async def test_network_error_is_fetch_failed(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        with pytest.raises(HTTPException) as exc:
            await fetch_skill_from_url("https://example.com/skill.zip", client=_client(handler))
        assert exc.value.status_code == 502
        assert _detail(exc).startswith("url_fetch_failed")

    async def test_total_deadline_bounds_a_dripping_server(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """httpx timeouts are per phase — the TOTAL asyncio deadline must trip."""
        from src.core.config import settings

        monkeypatch.setattr(settings, "skills_url_import_timeout_seconds", 1)

        async def slow_handler(_request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(5)
            return httpx.Response(200, content=ZIP_MAGIC)

        with pytest.raises(HTTPException) as exc:
            await fetch_skill_from_url(
                "https://example.com/skill.zip", client=_client(slow_handler)
            )
        assert exc.value.status_code == 502
        assert "TotalDeadlineExceeded" in _detail(exc)
