"""Source hyperlink block for interest notification content (ADR-131).

Citations are appended deterministically AFTER LLM presentation — never
LLM-generated — so URLs cannot be hallucinated or malformed. The chat UI
renders markdown links (MarkdownContent.tsx); push/Telegram surfaces get a
plain-text conversion in the dispatcher (markdown_links_to_plain).
"""

from urllib.parse import urlparse

from src.core.i18n_proactive import ProactiveMessages

_LINK_SEPARATOR = " · "


def build_sources_block(citations: list[str], language: str, max_links: int) -> str:
    """Build the markdown sources block appended to notification content.

    Args:
        citations: Raw citation URLs from the content source.
        language: User language (backend-canonical, e.g. "fr", "zh-CN").
        max_links: Cap on rendered links; 0 disables the block entirely.

    Returns:
        "\\n\\n<label> : [domain](url) · ..." or "" when disabled or empty.
    """
    if max_links <= 0 or not citations:
        return ""

    links: list[str] = []
    seen: set[str] = set()
    for url in citations:
        if url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        domain = parsed.netloc.removeprefix("www.")
        links.append(f"[{domain}]({url})")
        if len(links) >= max_links:
            break

    if not links:
        return ""
    label = ProactiveMessages.sources_label(language)
    return f"\n\n{label} : {_LINK_SEPARATOR.join(links)}"
