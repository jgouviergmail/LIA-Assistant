"""
Unit tests for Web Fetch Tool.

Tests cover:
- Helper functions: _extract_language, _html_to_markdown, _sanitize_markdown, _truncate_content
- Readability article → full fallback
- Sanitization of dangerous URI protocols (javascript, data, vbscript, file, about)
- Content-Type case-insensitive handling
- Full tool invocation with mocked httpx (success, timeout, 404, non-HTML, too large)
- Post-redirect SSRF check
- UnifiedToolOutput and RegistryItem format validation
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.domains.agents.tools.web_fetch_tools import (
    _clean_html,
    _estimate_text_word_count,
    _extract_language,
    _html_to_markdown,
    _sanitize_markdown,
    _truncate_content,
)

# ============================================================================
# FIXTURES
# ============================================================================

SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="fr-FR">
<head><title>Test Article</title></head>
<body>
<header><nav>Menu items</nav></header>
<article>
<h1>Test Article Title</h1>
<p>This is the main article content with enough text to pass the minimum length threshold.
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt
ut labore et dolore magna aliqua.</p>
<p>Second paragraph with more content to ensure readability extracts a meaningful article.</p>
</article>
<footer>Footer content</footer>
</body>
</html>
"""

# Simulates a homepage with many article cards but readability only extracts
# the featured one (short extraction, low ratio vs full page content)
HOMEPAGE_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head><title>TechBlog - Actualités Tech</title></head>
<body>
<header><nav>Menu principal</nav></header>
<main>
<section class="featured">
<article><h2>Article vedette</h2><p>Un court résumé de l'article vedette.</p></article>
</section>
<section class="articles">
<article><h2>Comment sécuriser votre réseau domestique</h2>
<p>Dans cet article nous explorons les meilleures pratiques pour protéger votre réseau
WiFi domestique contre les intrusions et les attaques malveillantes. Découvrez les
étapes essentielles pour configurer votre routeur correctement.</p></article>
<article><h2>Les 10 meilleurs outils open source de 2026</h2>
<p>Notre sélection annuelle des outils open source incontournables pour les développeurs
et administrateurs système. De la conteneurisation à l'observabilité.</p></article>
<article><h2>Intelligence artificielle et vie privée</h2>
<p>L'IA générative soulève des questions fondamentales sur la protection des données
personnelles. Analyse des enjeux et des solutions émergentes.</p></article>
<article><h2>Tutoriel Docker avancé pour les microservices</h2>
<p>Apprenez à orchestrer vos microservices avec Docker Compose et Kubernetes.
Guide pratique avec exemples de configuration production-ready.</p></article>
<article><h2>Cybersécurité : les menaces émergentes en 2026</h2>
<p>Tour d'horizon des nouvelles menaces cybernétiques qui ciblent les entreprises
et les particuliers cette année. Ransomware, phishing avancé et deepfakes.</p></article>
<article><h2>Linux 7.0 : toutes les nouveautés du noyau</h2>
<p>Le nouveau noyau Linux apporte des améliorations significatives en performance
et en sécurité. Découvrez les changements majeurs et leur impact.</p></article>
<article><h2>Programmation Rust pour les développeurs Python</h2>
<p>Guide de transition pour les développeurs Python qui souhaitent adopter Rust
pour leurs projets nécessitant haute performance et sécurité mémoire.</p></article>
<article><h2>Cloud souverain : état des lieux en Europe</h2>
<p>Où en est le cloud souverain européen ? Analyse des offres disponibles et
des enjeux de souveraineté numérique pour les entreprises.</p></article>
</section>
</main>
<aside><h3>Archives</h3><p>2025, 2024, 2023...</p></aside>
<footer>Copyright 2026 TechBlog</footer>
</body>
</html>
"""


# ============================================================================
# _clean_html() TESTS
# ============================================================================


class TestCleanHtml:
    """Tests for HTML pre-cleaning (script/style removal)."""

    def test_removes_script_blocks_with_content(self):
        html = '<body><script>var x = localStorage.getItem("theme");</script><p>Hello</p></body>'
        cleaned = _clean_html(html)
        assert "localStorage" not in cleaned
        assert "Hello" in cleaned

    def test_removes_style_blocks_with_content(self):
        html = "<body><style>.hidden{display:none} body{margin:0}</style><p>Visible</p></body>"
        cleaned = _clean_html(html)
        assert "display:none" not in cleaned
        assert "Visible" in cleaned

    def test_removes_noscript_blocks(self):
        html = "<body><noscript><p>Enable JS</p></noscript><p>Main content</p></body>"
        cleaned = _clean_html(html)
        assert "Enable JS" not in cleaned
        assert "Main content" in cleaned

    def test_removes_multiline_script_blocks(self):
        """Real-world scripts span multiple lines (korben.info pattern)."""
        html = """<body>
        <script>
        try {
            var t = localStorage.getItem("theme");
            if (t) document.documentElement.classList.add(t);
        } catch(e) {}
        </script>
        <h2>Article Title</h2>
        <p>Article content here.</p>
        </body>"""
        cleaned = _clean_html(html)
        assert "localStorage" not in cleaned
        assert "classList" not in cleaned
        assert "Article Title" in cleaned
        assert "Article content" in cleaned

    def test_removes_multiple_script_blocks(self):
        html = (
            "<body>"
            "<script>var a=1;</script>"
            "<p>Content</p>"
            "<script>var b=2;</script>"
            "</body>"
        )
        cleaned = _clean_html(html)
        assert "var a" not in cleaned
        assert "var b" not in cleaned
        assert "Content" in cleaned

    def test_extracts_body_content(self):
        html = (
            "<html><head><title>Test</title><link rel='stylesheet' href='style.css'></head>"
            "<body><p>Body content</p></body></html>"
        )
        cleaned = _clean_html(html)
        assert "Body content" in cleaned
        assert "<head>" not in cleaned
        assert "stylesheet" not in cleaned

    def test_handles_html_without_body(self):
        html = "<p>No body tags here</p>"
        cleaned = _clean_html(html)
        assert "No body tags here" in cleaned

    def test_removes_svg_blocks(self):
        html = (
            '<body><svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg><p>Text</p></body>'
        )
        cleaned = _clean_html(html)
        assert "<svg" not in cleaned
        assert "Text" in cleaned

    def test_removes_iframe_blocks(self):
        html = '<body><iframe src="https://ads.example.com"></iframe><p>Text</p></body>'
        cleaned = _clean_html(html)
        assert "ads.example.com" not in cleaned
        assert "Text" in cleaned

    def test_case_insensitive_tag_removal(self):
        html = "<body><SCRIPT>alert(1)</SCRIPT><p>Safe</p></body>"
        cleaned = _clean_html(html)
        assert "alert" not in cleaned
        assert "Safe" in cleaned


# ============================================================================
# _estimate_text_word_count() TESTS
# ============================================================================


class TestEstimateTextWordCount:
    """Tests for HTML text word count estimation."""

    def test_counts_words_from_plain_html(self):
        html = "<p>Hello world this is a test</p>"
        assert _estimate_text_word_count(html) == 6

    def test_strips_tags_before_counting(self):
        html = "<h1>Title</h1><p>One <strong>two</strong> three</p>"
        assert _estimate_text_word_count(html) == 4

    def test_returns_zero_for_empty_html(self):
        assert _estimate_text_word_count("") == 0
        assert _estimate_text_word_count("<div></div>") == 0

    def test_handles_nested_tags(self):
        html = "<div><ul><li>Item one</li><li>Item two</li></ul></div>"
        assert _estimate_text_word_count(html) >= 4


# ============================================================================
# _extract_language() TESTS
# ============================================================================


class TestExtractLanguage:
    """Tests for HTML lang attribute extraction."""

    def test_extracts_fr(self):
        html = '<html lang="fr"><head></head><body></body></html>'
        assert _extract_language(html) == "fr"

    def test_extracts_language_with_region(self):
        html = '<html lang="fr-FR"><head></head><body></body></html>'
        assert _extract_language(html) == "fr"

    def test_extracts_english(self):
        html = "<html lang='en-US'><head></head><body></body></html>"
        assert _extract_language(html) == "en"

    def test_returns_none_when_no_lang(self):
        html = "<html><head></head><body></body></html>"
        assert _extract_language(html) is None

    def test_case_insensitive(self):
        html = '<HTML LANG="DE"><head></head><body></body></html>'
        assert _extract_language(html) == "de"

    def test_empty_string(self):
        assert _extract_language("") is None


# ============================================================================
# _html_to_markdown() TESTS
# ============================================================================


class TestHtmlToMarkdown:
    """Tests for HTML → Markdown conversion."""

    def test_article_mode_extracts_title(self):
        title, content = _html_to_markdown(SAMPLE_HTML, "article")
        assert title  # Non-empty title
        assert len(content) > 0

    def test_full_mode_extracts_title(self):
        title, content = _html_to_markdown(SAMPLE_HTML, "full")
        assert title == "Test Article"
        assert len(content) > 0

    def test_full_mode_without_title_tag(self):
        html = "<html><body><p>Content without title</p></body></html>"
        title, content = _html_to_markdown(html, "full")
        assert title == ""
        assert "Content without title" in content

    def test_article_fallback_to_full_when_extraction_too_short(self):
        """When readability returns < 100 chars HTML, fallback to full mode."""
        html = "<html><head><title>Short</title></head><body><p>x</p></body></html>"
        # readability will extract very little from this minimal HTML
        title, content = _html_to_markdown(html, "article")
        # Should still return something (either from article or fallback to full)
        assert isinstance(title, str)
        assert isinstance(content, str)

    def test_article_fallback_on_homepage_low_ratio(self):
        """On a homepage, readability extracts only the featured article.

        The smart fallback detects that the extraction ratio is low
        (< 30% of full page content) and switches to full mode,
        capturing all article titles and summaries.
        """
        title, content = _html_to_markdown(HOMEPAGE_HTML, "article")
        # In full mode, all article titles should be present
        assert "Comment sécuriser votre réseau domestique" in content
        assert "Les 10 meilleurs outils open source" in content
        assert "Intelligence artificielle et vie privée" in content
        assert "Tutoriel Docker avancé" in content
        assert "Cybersécurité" in content
        assert "Linux 7.0" in content
        assert "Programmation Rust" in content
        assert "Cloud souverain" in content

    def test_strips_script_and_style_tags_and_content(self):
        html = """
        <html><head><title>Clean</title></head>
        <body>
        <script>alert('xss')</script>
        <style>.hidden{display:none}</style>
        <p>Visible content</p>
        </body></html>
        """
        title, content = _html_to_markdown(html, "full")
        # Visible content must be present
        assert "Visible content" in content
        # Script/style tags AND their content must be stripped
        assert "<script>" not in content
        assert "<style>" not in content
        assert "alert" not in content
        assert "display:none" not in content

    def test_cleans_excessive_whitespace(self):
        html = """
        <html><head><title>Spaces</title></head>
        <body><p>Line 1</p><br><br><br><br><p>Line 2</p></body></html>
        """
        _, content = _html_to_markdown(html, "full")
        # No more than 2 consecutive newlines
        assert "\n\n\n" not in content


# ============================================================================
# _sanitize_markdown() TESTS
# ============================================================================


class TestSanitizeMarkdown:
    """Tests for dangerous URI stripping from markdown."""

    def test_strips_javascript_links(self):
        md = "Click [here](javascript:alert(1)) for info"
        sanitized = _sanitize_markdown(md)
        assert "javascript:" not in sanitized
        assert "here" in sanitized  # Keeps link text

    def test_strips_data_uri_links(self):
        md = "See [image](data:text/html,<h1>pwned</h1>) here"
        sanitized = _sanitize_markdown(md)
        assert "data:" not in sanitized
        assert "image" in sanitized  # Keeps link text

    def test_strips_vbscript_links(self):
        md = "Click [evil](vbscript:MsgBox(1)) here"
        sanitized = _sanitize_markdown(md)
        assert "vbscript:" not in sanitized
        assert "evil" in sanitized

    def test_strips_file_uri_links(self):
        md = "Read [secret](file:///etc/passwd) here"
        sanitized = _sanitize_markdown(md)
        assert "file:" not in sanitized
        assert "secret" in sanitized

    def test_strips_about_uri_links(self):
        md = "Go to [blank](about:blank) page"
        sanitized = _sanitize_markdown(md)
        assert "about:" not in sanitized
        assert "blank" in sanitized

    def test_case_insensitive(self):
        md = "Click [evil](JavaScript:void(0)) link"
        sanitized = _sanitize_markdown(md)
        assert "JavaScript:" not in sanitized

    def test_preserves_safe_links(self):
        md = "Visit [example](https://example.com) for info"
        sanitized = _sanitize_markdown(md)
        assert sanitized == md

    def test_handles_multiple_dangerous_links(self):
        md = "[a](javascript:alert(1)) and [b](data:text/html,x) and [c](https://safe.com)"
        sanitized = _sanitize_markdown(md)
        assert "javascript:" not in sanitized
        assert "data:" not in sanitized
        assert "https://safe.com" in sanitized


# ============================================================================
# _truncate_content() TESTS
# ============================================================================


class TestTruncateContent:
    """Tests for content truncation."""

    def test_no_truncation_when_under_limit(self):
        content = "Short content"
        result, was_truncated = _truncate_content(content, 1000)
        assert result == content
        assert was_truncated is False

    def test_truncation_when_over_limit(self):
        content = "A" * 500
        result, was_truncated = _truncate_content(content, 100)
        assert was_truncated is True
        assert len(result) > 100  # Includes truncation marker
        assert "[... Content truncated ...]" in result

    def test_exact_limit_no_truncation(self):
        content = "A" * 100
        result, was_truncated = _truncate_content(content, 100)
        assert result == content
        assert was_truncated is False

    def test_truncation_preserves_start(self):
        content = "START" + "x" * 1000
        result, _ = _truncate_content(content, 50)
        assert result.startswith("START")


# ============================================================================
# FULL TOOL TESTS (with mocked dependencies)
# ============================================================================


class _MockConfig:
    """Minimal config object returned by patched validate_runtime_config."""

    user_id = "test-user-123"


def _make_mock_response(
    *,
    status_code: int = 200,
    content_type: str = "text/html; charset=utf-8",
    html: str = SAMPLE_HTML,
    url: str = "https://example.com/article",
    content_length: str | None = None,
) -> MagicMock:
    """Create a mock httpx streaming response."""
    response = AsyncMock()
    response.status_code = status_code
    response.url = httpx.URL(url)

    headers = {"content-type": content_type}
    if content_length is not None:
        headers["content-length"] = content_length
    response.headers = headers

    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )

    response.aread = AsyncMock()
    response.content = html.encode("utf-8")
    response.text = html

    return response


def _make_httpx_mocks(mock_response: MagicMock) -> MagicMock:
    """Create nested httpx.AsyncClient context manager mocks."""
    mock_client = AsyncMock()
    mock_stream_cm = AsyncMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_stream_cm)

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_client_cm


@pytest.mark.slow
class TestFetchWebPageTool:
    """Integration-style tests for the full fetch_web_page_tool.

    Strategy: Patch validate_runtime_config to bypass ToolRuntime Pydantic
    validation. InjectedToolArg cannot accept MagicMock, so we intercept
    the validation at the application level.
    """

    @pytest.fixture(autouse=True)
    def mock_runtime(self):
        """Patch validate_runtime_config for all tool tests."""
        with patch(
            "src.domains.agents.tools.web_fetch_tools.validate_runtime_config",
            return_value=_MockConfig(),
        ) as mock:
            yield mock

    @pytest.fixture()
    def mock_validate_url(self):
        """Mock URL validation to return valid result."""
        from src.domains.agents.web_fetch.url_validator import UrlValidationResult

        with patch(
            "src.domains.agents.tools.web_fetch_tools.validate_url",
            new_callable=AsyncMock,
            return_value=UrlValidationResult(valid=True, url="https://example.com/article"),
        ) as mock:
            yield mock

    @pytest.fixture()
    def mock_validate_url_rejected(self):
        """Mock URL validation to return invalid result."""
        from src.domains.agents.web_fetch.url_validator import UrlValidationResult

        with patch(
            "src.domains.agents.tools.web_fetch_tools.validate_url",
            new_callable=AsyncMock,
            return_value=UrlValidationResult(
                valid=False, url="http://evil.com", error="Blocked hostname: evil.com"
            ),
        ) as mock:
            yield mock

    @pytest.fixture()
    def mock_validate_resolved_url(self):
        """Mock post-redirect URL validation."""
        with patch(
            "src.domains.agents.tools.web_fetch_tools.validate_resolved_url",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock:
            yield mock

    async def test_successful_fetch(self, mock_validate_url, mock_validate_resolved_url):
        """Test complete successful web fetch flow."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response()
        mock_client_cm = _make_httpx_mocks(mock_response)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke(
                {
                    "url": "https://example.com/article",
                    "extract_mode": "article",
                    "max_length": 30000,
                }
            )

        assert result.success is True
        assert result.structured_data is not None
        assert "web_fetchs" in result.structured_data
        assert isinstance(result.structured_data["web_fetchs"], list)
        assert len(result.structured_data["web_fetchs"]) == 1
        fetch_item = result.structured_data["web_fetchs"][0]
        assert "title" in fetch_item
        assert "url" in fetch_item
        assert "word_count" in fetch_item
        assert "language" in fetch_item

    async def test_successful_fetch_verifies_registry_updates(
        self, mock_validate_url, mock_validate_resolved_url
    ):
        """Test that successful fetch produces valid registry updates."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response()
        mock_client_cm = _make_httpx_mocks(mock_response)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://example.com/article"})

        assert result.success is True
        assert result.registry_updates is not None
        assert len(result.registry_updates) == 1
        registry_item = next(iter(result.registry_updates.values()))
        assert registry_item.type.value == "WEB_PAGE"
        assert registry_item.payload["url"] == "https://example.com/article"

    async def test_url_validation_failure(self, mock_validate_url_rejected):
        """Test that invalid URLs return failure with correct error code."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        result = await fetch_web_page_tool.ainvoke({"url": "http://evil.com"})

        assert result.success is False
        assert result.error_code == "INVALID_INPUT"
        assert "rejected" in result.message.lower()

    async def test_invalid_extract_mode_defaults(
        self, mock_validate_url, mock_validate_resolved_url
    ):
        """Test that invalid extract_mode falls back to default."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response()
        mock_client_cm = _make_httpx_mocks(mock_response)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke(
                {"url": "https://example.com", "extract_mode": "invalid_mode"}
            )

        # Should succeed (falls back to default "article" mode)
        assert result.success is True

    async def test_non_html_content_type_rejected(
        self, mock_validate_url, mock_validate_resolved_url
    ):
        """Test that non-HTML content types are rejected."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response(content_type="application/pdf")
        mock_client_cm = _make_httpx_mocks(mock_response)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://example.com/file.pdf"})

        assert result.success is False
        assert result.error_code == "INVALID_RESPONSE_FORMAT"
        assert "not an html" in result.message.lower()

    async def test_content_type_case_insensitive(
        self, mock_validate_url, mock_validate_resolved_url
    ):
        """Test that Content-Type matching is case-insensitive (HTTP spec)."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response(content_type="Text/HTML; Charset=UTF-8")
        mock_client_cm = _make_httpx_mocks(mock_response)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://example.com"})

        # Should succeed regardless of Content-Type casing
        assert result.success is True

    async def test_content_too_large_via_header(
        self, mock_validate_url, mock_validate_resolved_url
    ):
        """Test that oversized content is rejected via Content-Length header."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response(content_length="999999999")
        mock_client_cm = _make_httpx_mocks(mock_response)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://example.com/huge"})

        assert result.success is False
        assert result.error_code == "CONSTRAINT_VIOLATION"
        assert "too large" in result.message.lower()

    async def test_timeout_returns_failure(self, mock_validate_url):
        """Test that httpx timeout returns proper error."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_client = AsyncMock()
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://slow.example.com"})

        assert result.success is False
        assert result.error_code == "TIMEOUT"
        assert "timed out" in result.message.lower()

    async def test_http_404_returns_not_found(self, mock_validate_url):
        """Test that 404 errors return NOT_FOUND error code."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response(status_code=404)
        mock_client_cm = _make_httpx_mocks(mock_response)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://example.com/missing"})

        assert result.success is False
        assert result.error_code == "NOT_FOUND"
        assert "404" in result.message

    async def test_redirect_to_private_ip_blocked(self, mock_validate_url):
        """Test that redirect to a private IP is blocked (post-redirect SSRF)."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        # Response redirected to a different (private) URL
        mock_response = _make_mock_response(url="http://192.168.1.1/internal")
        mock_client_cm = _make_httpx_mocks(mock_response)

        with (
            patch(
                "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
                return_value=mock_client_cm,
            ),
            patch(
                "src.domains.agents.tools.web_fetch_tools.validate_resolved_url",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://example.com/redirect"})

        assert result.success is False
        assert result.error_code == "INVALID_INPUT"
        assert "redirect" in result.message.lower()
        assert "blocked" in result.message.lower()

    async def test_max_length_clamped(self, mock_validate_url, mock_validate_resolved_url):
        """Test that max_length is clamped to [1000, WEB_FETCH_MAX_OUTPUT_LENGTH]."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response()
        mock_client_cm = _make_httpx_mocks(mock_response)

        # Pass max_length=50 (below minimum of 1000)
        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke(
                {"url": "https://example.com", "max_length": 50}
            )

        # Should succeed (clamped to 1000, not fail)
        assert result.success is True

    async def test_network_error_returns_failure(
        self, mock_validate_url, mock_validate_resolved_url
    ):
        """Test that generic network errors (ConnectError, etc.) return EXTERNAL_API_ERROR."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)
        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://down.example.com"})

        assert result.success is False
        assert result.error_code == "EXTERNAL_API_ERROR"

    async def test_extraction_error_returns_failure(
        self, mock_validate_url, mock_validate_resolved_url
    ):
        """Test that HTML extraction errors return INVALID_RESPONSE_FORMAT."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response()
        mock_client_cm = _make_httpx_mocks(mock_response)

        with (
            patch(
                "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
                return_value=mock_client_cm,
            ),
            patch(
                "src.domains.agents.tools.web_fetch_tools._html_to_markdown",
                side_effect=RuntimeError("parse error"),
            ),
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://example.com/page"})

        assert result.success is False
        assert result.error_code == "INVALID_RESPONSE_FORMAT"

    async def test_http_500_returns_external_api_error(
        self, mock_validate_url, mock_validate_resolved_url
    ):
        """Test that HTTP 500 errors return EXTERNAL_API_ERROR (not NOT_FOUND)."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        mock_response = _make_mock_response(status_code=500)
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )
        mock_client_cm = _make_httpx_mocks(mock_response)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://example.com/error"})

        assert result.success is False
        assert result.error_code == "EXTERNAL_API_ERROR"

    async def test_content_too_large_via_body_size(
        self, mock_validate_url, mock_validate_resolved_url
    ):
        """Test rejection when actual body exceeds max size (no Content-Length header)."""
        from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

        large_body = b"<html><body>" + b"x" * 2_100_000 + b"</body></html>"
        mock_response = _make_mock_response(content_length=None)
        mock_response.aread = AsyncMock(return_value=large_body)
        mock_response.content = large_body
        mock_client_cm = _make_httpx_mocks(mock_response)

        with patch(
            "src.domains.agents.tools.web_fetch_tools.httpx.AsyncClient",
            return_value=mock_client_cm,
        ):
            result = await fetch_web_page_tool.ainvoke({"url": "https://example.com/huge"})

        assert result.success is False
        assert "too large" in result.message.lower() or "size" in result.message.lower()
