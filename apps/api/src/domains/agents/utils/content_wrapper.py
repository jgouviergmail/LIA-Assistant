"""
External content wrapping for prompt injection prevention.

Wraps untrusted external content (web pages, search results) in XML-like markers
that signal to the LLM that the content is data-only and should not be interpreted
as instructions.

Architecture:
    wrap_external_content(content, source_url, source_type) -> str
        Wraps content with <external_content> tags and an UNTRUSTED warning.
        Escapes any occurrences of the tag itself within the content.

    strip_external_markers(content) -> str
        Removes wrapping markers, returning the original content.
        Useful for display or storage where markers are not needed.

Security:
    - Prevents prompt injection via web-fetched content
    - Escapes tag occurrences in content to prevent marker breakout
    - Feature-flagged via external_content_wrapping_enabled setting
"""

import re
from contextlib import suppress

from src.core.constants import (
    EXTERNAL_CONTENT_CLOSE_TAG,
    EXTERNAL_CONTENT_OPEN_TAG,
    EXTERNAL_CONTENT_WARNING,
    REGISTRY_INJECTION_NOTICE_PREFIX,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _escape_tags(content: str) -> str:
    """Escape external_content tags within content to prevent marker breakout.

    Replaces literal occurrences of the open/close tags with escaped versions
    so that the content cannot prematurely close the wrapper.
    """
    # Escape opening tag: <external_content -> &lt;external_content
    content = content.replace("<external_content", "&lt;external_content")
    # Escape closing tag: </external_content> -> &lt;/external_content&gt;
    content = content.replace("</external_content>", "&lt;/external_content&gt;")
    return content


def wrap_external_content(
    content: str,
    source_url: str,
    source_type: str = "web_page",
) -> str:
    """Wrap untrusted external content with safety markers.

    Adds XML-like tags and an UNTRUSTED warning that instructs the LLM
    to treat the enclosed content as data only.

    Args:
        content: The raw external content to wrap.
        source_url: URL or identifier of the content source.
        source_type: Type of content (e.g., "web_page", "search_synthesis", "search_snippet").

    Returns:
        Wrapped content string with safety markers.
    """
    if not content:
        return content

    escaped_content = _escape_tags(content)

    # Sanitize source_url: escape quotes to prevent XML attribute injection
    safe_source_url = source_url.replace('"', "&quot;")

    return (
        f'{EXTERNAL_CONTENT_OPEN_TAG} source="{safe_source_url}" type="{source_type}">'
        f"\n{EXTERNAL_CONTENT_WARNING}\n"
        f"{escaped_content}\n"
        f"{EXTERNAL_CONTENT_CLOSE_TAG}"
    )


# Regex pattern to strip external content markers (greedy across multiple wrapped blocks)
_STRIP_PATTERN = re.compile(
    r"<external_content[^>]*>\s*"
    + re.escape(EXTERNAL_CONTENT_WARNING)
    + r"\s*(.*?)\s*</external_content>",
    re.DOTALL,
)


def _unescape_tags(content: str) -> str:
    """Reverse the escaping done by _escape_tags."""
    content = content.replace("&lt;external_content", "<external_content")
    content = content.replace("&lt;/external_content&gt;", "</external_content>")
    return content


# =============================================================================
# Injection-pattern detection (surveillance, never sanitisation)
# =============================================================================

# Marking third-party content as data is the primary defence; this scanner is
# the secondary one. It NEVER rewrites the content — a sanitiser that strips
# "ignore previous instructions" only teaches the next attacker to spell it
# differently, and it would corrupt legitimate text (a user forwarding a
# security advisory). It reports, so the model gets an explicit heads-up on the
# one item that warrants it and operators get a signal.
#
# Detection is bounded to the first _SCAN_MAX_CHARS: an injection has to appear
# early enough for the model to still be reading it, and an unbounded scan on a
# 5 MB page would be a latency footgun on the response path.
_SCAN_MAX_CHARS = 20_000

# Imperative "ignore what you were told" verbs across the 6 supported locales.
# English-only detection would be a hole on a product that serves fr/es/de/it/zh:
# the attacker writes in the language of their target, not of the framework.
_HIJACK_VERBS = (
    r"ignore[sz]?|disregard|override|forget|"  # en
    r"oublie[sz]?|ignorez|négligez|"  # fr
    r"olvida|ignora|"  # es
    r"vergiss|ignoriere|"  # de
    r"dimentica|ignora"  # it
)
_HIJACK_TARGETS = (
    r"previous|prior|above|earlier|your|"  # en
    r"précédentes?|precedentes?|ci-dessus|tes|vos|"  # fr
    r"anteriores|"  # es
    r"vorherigen|obigen|"  # de
    r"precedenti"  # it
)
_HIJACK_NOUNS = (
    r"instructions?|rules?|directives?|guidelines?|prompt|"  # en/fr
    r"consignes?|règles?|"  # fr
    r"reglas|instrucciones|"  # es
    r"anweisungen|regeln|"  # de
    r"istruzioni|regole|"  # it
    r"指令|规则"  # zh
)

_INJECTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # A conversation role announced inside data: the classic way to make the
    # model believe the block it is reading is a new system turn.
    (
        re.compile(
            # A role marker at the start of a line, OR opening a new sentence
            # mid-paragraph ("… la facture. SYSTEM: nouvelle consigne"). Anchoring
            # on line start alone missed the mid-paragraph form, which is exactly
            # how an injection hides inside an otherwise plausible email body.
            r"(?:(?:^|\n)\s*|[.!?]\s+)(?:SYSTEM|ASSISTANT)\s*:"
            r"|(?:^|\n)\s*(?:### *(?:System|Assistant)|\[SYSTEM[ _]MESSAGE\])"
            r"|\[INST\]|<\|system\|>|<\|im_start\|>",
            re.IGNORECASE,
        ),
        "role_override",
    ),
    (
        re.compile(
            # Space-separated languages (en/fr/es/de/it): verb, up to two filler
            # words, an optional "previous"-style target, then the noun.
            rf"(?:{_HIJACK_VERBS})\s+(?:\w+\s+){{0,2}}(?:{_HIJACK_TARGETS})?\s*"
            rf"(?:{_HIJACK_NOUNS})"
            # Chinese writes without spaces, so the space-separated branch can
            # never fire on it: a dedicated branch allows any short run of
            # characters between the verb and the noun.
            r"|(?:忽略|無視|无视|忘记|忘記|ignore)[^\n]{0,12}(?:指令|指示|規則|规则|提示)",
            re.IGNORECASE,
        ),
        "instruction_hijack",
    ),
    (
        re.compile(
            # Accents are optional throughout: attacker text routinely arrives
            # unaccented (transliterated, or typed on a foreign keyboard), and a
            # pattern that only matches the well-formed spelling is a free bypass.
            r"(?:new\s+(?:instructions|system\s+prompt|rules)|you\s+are\s+now|"
            r"act\s+as\s+if\s+you\s+(?:are|were)|from\s+now\s+on\s+you|"
            r"tu\s+es\s+(?:maintenant|d[ée]sormais)|"
            r"[àa]\s+partir\s+de\s+maintenant\s*,?\s*(?:tu|vous)|"
            r"ahora\s+eres|du\s+bist\s+(?:jetzt|nun)|ora\s+sei|"
            r"你现在是|你現在是)",
            re.IGNORECASE,
        ),
        "persona_switch",
    ),
    # Asking the assistant to move the user's data somewhere.
    (
        re.compile(
            r"(?:base64\s+encode\s+(?:and\s+)?send|"
            r"(?:forward|send|post|exfiltrate|transfère|transfere|envoie|"
            r"reenvía|weiterleite|inoltra)\w*\s+(?:all\s+|tous?\s+les?\s+|toutes?\s+les?\s+)?"
            r"(?:data|content|conversation|history|memories|emails?|files?|"
            r"données|courriels?|mails?|fichiers?|souvenirs?|mémoires?)\s+"
            r"(?:to|vers|à|a|an|nach))",
            re.IGNORECASE,
        ),
        "data_exfiltration",
    ),
    # Naming a LIA tool inside third-party text is never legitimate data: the
    # tool namespace is ours, so its appearance is an attempt to drive the loop.
    (re.compile(r"\b[a-z_]{3,40}_tool\b"), "tool_coercion"),
    # Characters the user cannot see but the tokenizer feeds to the model:
    # zero-width joiners, BOM, and bidirectional overrides/isolates that can
    # visually reverse a sentence's meaning.
    (
        re.compile("[​‌‍⁠﻿‪-‮⁦-⁩]"),
        "invisible_unicode",
    ),
    # An HTML comment is invisible in a rendered page but survives extraction.
    (
        re.compile(
            r"<!--(?:(?!-->).)*?(?:ignore|system|instruction|inject|override|"
            r"assistant|prompt)(?:(?!-->).)*?-->",
            re.IGNORECASE | re.DOTALL,
        ),
        "hidden_html_directive",
    ),
)


def scan_injection_patterns(content: str) -> tuple[str, ...]:
    """Report injection-shaped patterns found in untrusted content.

    Pure detection: the caller decides what to do with the verdict, and the
    content is returned to the model unchanged either way.

    Args:
        content: Third-party text about to be shown to the LLM.

    Returns:
        Deduplicated family names in declaration order; empty when clean.
    """
    if not content or len(content) < 10:
        return ()
    sample = content[:_SCAN_MAX_CHARS]
    return tuple(family for pattern, family in _INJECTION_PATTERNS if pattern.search(sample))


def injection_notice(content: str, *, item_type: str, surface: str) -> str:
    """Scan third-party content and return a compact notice for the LLM.

    Emits one counter sample per matched family and one structured log line.
    Neither carries the content: the offending text is by construction attacker
    controlled and routinely holds the user's own data (an email body), so it
    stays out of logs entirely — only the pattern family, the registry type and
    the surface are recorded.

    Args:
        content: The third-party text about to be shown to the LLM.
        item_type: Registry type of the item, for the log dimension.
        surface: ``"pipeline"`` or ``"react"``.

    Returns:
        A leading-space notice to append to the item's line, or ``""`` when
        the content is clean.
    """
    families = scan_injection_patterns(content)
    if not families:
        return ""

    # Best-effort observability: a registry/collector hiccup must never break a
    # user turn over a diagnostic counter. Same posture as the metrics emission
    # in infrastructure/database/session.py.
    with suppress(ValueError, KeyError, AttributeError):
        from src.infrastructure.observability.metrics import (
            prompt_injection_patterns_total,
        )

        for family in families:
            prompt_injection_patterns_total.labels(surface=surface, family=family).inc()

    logger.warning(
        "external_content_injection_pattern_detected",
        surface=surface,
        item_type=item_type,
        families=list(families),
        content_chars=len(content),
    )
    return f" {REGISTRY_INJECTION_NOTICE_PREFIX}{', '.join(families)}]"


def strip_external_markers(content: str) -> str:
    """Remove external content wrapping markers, returning original content.

    Useful for display, storage, or contexts where safety markers are not needed.
    Handles multiple wrapped blocks within a single string.

    Args:
        content: Content potentially containing external_content markers.

    Returns:
        Content with markers removed and tag escaping reversed.
    """
    if not content:
        return content

    def _replace_match(match: re.Match) -> str:
        inner = match.group(1)
        return _unescape_tags(inner)

    return _STRIP_PATTERN.sub(_replace_match, content)
