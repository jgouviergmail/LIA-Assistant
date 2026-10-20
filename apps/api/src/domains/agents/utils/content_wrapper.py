"""
External content wrapping for prompt injection prevention.

Wraps untrusted external content (web pages, search results) in XML-like markers
that signal to the LLM that the content is data-only and should not be interpreted
as instructions.

Architecture:
    wrap_external_content(content, source_url, source_type) -> str
        Wraps content with <external_content> tags and an UNTRUSTED warning.
        Neutralises every bracket in the content that would read as the tag
        itself, however spelled (case, blanks, fullwidth forms, invisible
        characters).

    scan_injection_patterns(content) / injection_notice(...)
        Report injection-shaped patterns — detection only, never rewriting.

Security:
    - Prevents prompt injection via web-fetched content
    - Neutralises tag spellings in content to prevent marker breakout
    - The web fetch and search tools honour ``external_content_wrapping_enabled``;
      every other caller wraps unconditionally
"""

import re
import unicodedata
from contextlib import suppress

# Preserve the module's established public constants while the pure wrapper
# is shared with direct read-only source consumers.
from src.core.constants import EXTERNAL_CONTENT_CLOSE_TAG as EXTERNAL_CONTENT_CLOSE_TAG
from src.core.constants import EXTERNAL_CONTENT_OPEN_TAG as EXTERNAL_CONTENT_OPEN_TAG
from src.core.constants import EXTERNAL_CONTENT_WARNING as EXTERNAL_CONTENT_WARNING
from src.core.constants import (
    REGISTRY_INJECTION_NOTICE_PREFIX,
)
from src.core.external_content import wrap_external_content as wrap_external_content
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


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

# Joiners and zero-width spaces also occur in emoji, non-Latin writing and
# newsletter layout. Their presence alone is a low-confidence observation;
# bidi controls can reverse/reorder visible text and retain the warning.
_BIDI_CONTROL_PATTERN = re.compile("[\u202a-\u202e\u2066-\u2069]")

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
            # Chat-template control tokens of the open model families (ChatML,
            # Llama 3, Gemma): text that opens or closes a turn.
            r"|\[INST\]|<\|(?:system|user|assistant|im_start|im_end|eot_id|"
            r"start_header_id|end_header_id|endoftext)\|>|<(?:start|end)_of_turn>",
            re.IGNORECASE,
        ),
        "role_override",
    ),
    (
        re.compile(
            # Space-separated languages (en/fr/es/de/it): verb, up to four filler
            # words (« ignore all of the previous … » has three), an optional
            # "previous"-style target, then the noun.
            rf"(?:{_HIJACK_VERBS})\s+(?:\w+\s+){{0,4}}(?:{_HIJACK_TARGETS})?\s*"
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
)

# Characters the user cannot see but the tokenizer feeds to the model:
# zero-width joiners, the word joiner, the BOM, and the bidi embeddings,
# overrides and isolates that can visually reverse a sentence's meaning.
# Written as code points, so that nothing invisible sits in this file.
_INVISIBLE_PATTERN = re.compile(
    "["
    + re.escape("".join(map(chr, (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF))))
    + re.escape("".join(map(chr, range(0x202A, 0x202F))))
    + re.escape("".join(map(chr, range(0x2066, 0x206A))))
    + "]"
)
# The Tag block spells ASCII nobody sees: legitimate only inside a subdivision
# flag (a black flag, tag letters, the cancel tag) — anywhere else it is text
# smuggled past the reader.
_TAG_CHARACTER = re.compile("[" + chr(0xE0000) + "-" + chr(0xE007F) + "]")
_FLAG_TAG_SEQUENCE = re.compile(
    chr(0x1F3F4) + "[" + chr(0xE0020) + "-" + chr(0xE007E) + "]+" + chr(0xE007F)
)
# An HTML comment is invisible in a rendered page but survives extraction.
_HTML_COMMENT_DIRECTIVE = re.compile(
    r"ignore|system|instruction|inject|override|assistant|prompt", re.IGNORECASE
)


def _smuggled_text(sample: str) -> bool:
    """Tag-block characters outside a subdivision flag (text nobody sees)."""
    return _TAG_CHARACTER.search(_FLAG_TAG_SEQUENCE.sub("", sample)) is not None


def _hidden_html_directive(sample: str) -> bool:
    """An HTML comment holding a directive word, found in ONE pass.

    The regex this replaces re-read the rest of the text from every unclosed
    ``<!--``: 20 000 characters of it took 3 s on the response path (measured
    2026-10-13, point 30). Comments are read as a browser reads them: from
    ``<!--`` to the first ``-->``.

    Args:
        sample: The normalised text being scanned.

    Returns:
        True when a comment carries a directive word.
    """
    position = 0
    while (start := sample.find("<!--", position)) != -1:
        end = sample.find("-->", start + 4)
        if end == -1:
            return False
        if _HTML_COMMENT_DIRECTIVE.search(sample, start + 4, end):
            return True
        position = end + 3
    return False


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
    # Read the way a model reads it: fullwidth and compatibility forms folded
    # back (ＳＹＳＴＥＭ is SYSTEM to a tokenizer), case folded. The invisible
    # characters survive this normalisation; they are looked for in the raw
    # sample all the same.
    shadow = unicodedata.normalize("NFKC", sample).casefold()
    families = [family for pattern, family in _INJECTION_PATTERNS if pattern.search(shadow)]
    if _INVISIBLE_PATTERN.search(sample) or _smuggled_text(sample):
        families.append("invisible_unicode")
    if _hidden_html_directive(shadow):
        families.append("hidden_html_directive")
    return tuple(families)


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

    event_fields = {
        "surface": surface,
        "item_type": item_type,
        "families": list(families),
        "content_chars": len(content),
    }
    sample = content[:_SCAN_MAX_CHARS]
    if (
        families == ("invisible_unicode",)
        and not _BIDI_CONTROL_PATTERN.search(sample)
        and not _smuggled_text(sample)
    ):
        logger.info("external_content_injection_pattern_detected", **event_fields)
    else:
        logger.warning("external_content_injection_pattern_detected", **event_fields)
    return f" {REGISTRY_INJECTION_NOTICE_PREFIX}{', '.join(families)}]"
