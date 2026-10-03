"""HTML → readable plain text, for every surface that cannot render markup.

Extracted from ``base.py`` beside it (frozen at its audited size, ADR-326):
the e-mail card, the plain-text door of the display layer
(``plain_text.strip_html_if_markup``), the interest sources and the components
package all read these two functions through their former home, which
re-exports them.

Every pattern here is LINEAR on the text it reads, and that is a property the
build holds (``test_flatteners_are_linear.py``): this code runs synchronously
on the event loop over text a third party wrote — an e-mail body reaches the
card WHOLE, before the display truncation (measured 2026-09-30: a 32 KB
plain-text body froze the loop for 3.3 s through the link pattern's ``\\s+``
followed by ``[^<>]*``, two classes that both match a blank). A quantifier
that can hand characters back to its neighbour is what makes a pattern
quadratic; the patterns below never share a character class across a boundary.
"""

from __future__ import annotations

import html
import re

# Elements whose *content* is never prose: CSS, JS, document metadata. Dropped
# whole by :func:`html_to_text`, content included.
#
# The closing tag is OPTIONAL (``|\Z``), and that is the point. Rich assistant
# content reaches flattening surfaces truncated — a notification body cut to its
# preview budget, a web snippet from a search source — so a ``<style>`` severed
# mid-rule keeps no ``</style>``. Requiring the pair let tag-stripping remove the
# ``<style>`` marker and surface its raw CSS as text: a lock-screen notification
# read "body{color:red;font-size:12px}".
#
# ``(?<!/)`` rejects a self-closing ``<script src="x"/>``: without it the lazy
# body would find no closing tag and swallow the rest of the document.
# The ``\1`` backreference keeps a ``<style>`` from being closed by a
# ``</script>``; the lazy body plus a terminating ``\Z`` keeps it linear.
_BLOCK_ELEMENT_RE = re.compile(
    r"<(head|style|script)\b[^<>]*(?<!/)>.*?(?:</\1\s*>|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# ``<a ...>text</a>``: ONE blank opens the attributes, then ``[^<>]*`` takes the
# rest — blanks included. The former ``\s+`` before ``[^<>]*`` let a run of
# blanks be split between the two in every possible way, and an unclosed
# ``<a`` followed by n blanks was rescanned n times (quadratic, measured: 64 000
# blanks cost 12 s). The two forms accept exactly the same strings; group 1 now
# keeps its leading blank, which ``href=`` is searched through unchanged.
# The text never crosses another link's opening: paired lazily across the
# whole text, each unclosed « <a » rescanned it to the end.
_LINK_RE = re.compile(r"<a\s([^<>]*)>((?:(?!<a\b)[\s\S])*?)</a>", re.IGNORECASE)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def html_to_text(html_content: str | None, preserve_links: bool = False) -> str:
    """
    Convert HTML email content to clean, readable plain text.

    Handles common email HTML patterns including:
    - Block elements (div, p, br, hr) → newlines
    - Lists (ul, ol, li) → bullet points
    - Links → [text](url) or just text
    - Tables → basic text extraction
    - Whitespace normalization
    - HTML entities decoding, once the tags are gone

    Args:
        html_content: Raw HTML string from email body
        preserve_links: If True, format links as [text](url)

    Returns:
        Clean plain text suitable for display
    """
    if not html_content:
        return ""

    text = str(html_content)

    # 1. Entities are decoded AFTER the tags are stripped (step 9b): a text
    # quoting markup (``&lt;marie@example.com&gt;``, a card value escaped by
    # its renderer) is text, and decoded first it became a tag the strip
    # removed — the phone read « Marie Dupont » with no address (review 14).

    # 2. Remove <head>, <style>, <script> blocks entirely — content included
    text = _BLOCK_ELEMENT_RE.sub("", text)

    # 3. Handle links: extract text and optionally URL
    if preserve_links:
        # Format: [link text](url)
        def link_replacer(match: re.Match[str]) -> str:
            attrs = match.group(1)
            link_text = match.group(2)
            href_match = _HREF_RE.search(attrs)
            if href_match and link_text.strip():
                url = href_match.group(1)
                # Skip mailto: links, just show email
                if url.startswith("mailto:"):
                    return link_text.strip()
                return f"[{link_text.strip()}]({url})"
            return link_text.strip()

        text = _LINK_RE.sub(link_replacer, text)
    else:
        # Just extract link text: its tags go, its text stays.
        text = re.sub(r"</?a\b[^<>]*>", "", text, flags=re.IGNORECASE)

    # 4. Handle block elements with proper spacing
    # Headers → newline before and after, each tag on its own: paired lazily,
    # 20 000 unclosed « <h1> » cost 4.6 s on the event loop (review 14).
    text = re.sub(r"</?h[1-6]\b[^<>]*>", "\n\n", text, flags=re.IGNORECASE)

    # Paragraphs → double newline
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^<>]*>", "", text, flags=re.IGNORECASE)

    # Divs → single newline (common in email formatting)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<div[^<>]*>", "", text, flags=re.IGNORECASE)

    # Line breaks
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    # Horizontal rules → separator line
    text = re.sub(r"<hr\s*/?>", "\n---\n", text, flags=re.IGNORECASE)

    # 5. Handle lists
    text = re.sub(r"<li[^<>]*>", "\n• ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[ou]l[^<>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</[ou]l>", "\n", text, flags=re.IGNORECASE)

    # 6. Handle tables (basic: extract cell content with spacing)
    text = re.sub(r"<tr[^<>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<t[dh][^<>]*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</t[dh]>", " | ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?table[^<>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?tbody[^<>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?thead[^<>]*>", "", text, flags=re.IGNORECASE)

    # 7. Handle blockquotes (common in email replies)
    text = re.sub(r"<blockquote[^<>]*>", "\n> ", text, flags=re.IGNORECASE)
    text = re.sub(r"</blockquote>", "\n", text, flags=re.IGNORECASE)
    # 7b. The response vocabulary (ADR-177): a definition list reads « label :
    # value » per line, and two adjacent spans (a stat's value and label) keep
    # a space between them — the browser's ``htmlToPlainText`` already did the
    # first, and a voice on the phone read « IntituléSenterre » (measured
    # 2026-09-20, ADR-301). The voice corpus pins the two sides to each other.
    text = re.sub(r"</dt>", " : ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</(?:dd|dl|summary|details|figcaption|caption)>", "\n", text, flags=re.IGNORECASE
    )
    text = re.sub(r"</span>\s*(?=<span)", " ", text, flags=re.IGNORECASE)

    # 8. Bold/italic → keep text, remove tags
    text = re.sub(r"</?(?:b|strong)[^<>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:i|em)[^<>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:u|s|strike)[^<>]*>", "", text, flags=re.IGNORECASE)

    # 9. Remove all remaining HTML tags — a tag never holds a « < », so a run of
    # unclosed ones is read once
    text = re.sub(r"<[^<>]+>", "", text)

    # 9b. Decode the entities of what is left, which is text (step 1). Before
    # the whitespace rules, as when the decoding came first: a decoded
    # no-break space at a line's edge is trimmed with the line.
    text = html.unescape(text)

    # 10. Normalize whitespace
    # Multiple spaces → single space
    text = re.sub(r"[ \t]+", " ", text)

    # Multiple newlines → max 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Clean up leading/trailing whitespace on each line
    lines = [line.strip() for line in text.split("\n")]

    # Remove consecutive empty lines (keep max 1 empty line between paragraphs)
    cleaned_lines = []
    previous_was_empty = False
    for line in lines:
        if line:  # Non-empty line
            cleaned_lines.append(line)
            previous_was_empty = False
        elif not previous_was_empty:  # First empty line after content
            cleaned_lines.append(line)
            previous_was_empty = True
        # Skip consecutive empty lines

    text = "\n".join(cleaned_lines)

    # Remove empty lines at start/end
    text = text.strip()

    # 11. Handle common email signatures patterns (optional cleanup)
    # Remove excessive dashes often used as separators
    text = re.sub(r"[-_]{5,}", "---", text)

    return text


def format_email_body(
    body: str | None,
    max_length: int | None = 500,
    preserve_links: bool = False,
) -> tuple[str, bool]:
    """
    Format email body for display with truncation.

    Args:
        body: Raw email body (HTML or plain text)
        max_length: Maximum characters to display; None retains all supplied text
        preserve_links: If True, format links as [text](url)

    Returns:
        Tuple of (formatted_text, is_truncated)
    """
    if not body:
        return "", False

    # Convert HTML to text
    text = html_to_text(body, preserve_links=preserve_links)

    # Truncate if needed
    is_truncated = max_length is not None and len(text) > max_length
    if is_truncated and max_length is not None:
        # Try to truncate at word boundary
        truncated = text[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.8:  # Only if we don't lose too much
            truncated = truncated[:last_space]
        text = truncated

    return text, is_truncated


__all__ = ["format_email_body", "html_to_text"]
