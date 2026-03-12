"""
Telegram message formatter.

Handles:
- Markdown → Telegram HTML conversion
- Message splitting for the 4096-char Telegram limit
- Notification formatting (title + body)
- Localized bot messages (OTP success, errors, etc.)

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import html
import re

from src.core.config import settings
from src.core.constants import TELEGRAM_MESSAGE_MAX_LENGTH_DEFAULT

# ============================================================================
# Localized Bot Messages (6 languages)
# ============================================================================

TELEGRAM_BOT_MESSAGES: dict[str, dict[str, str]] = {
    "otp_success": {
        "fr": "Compte lié avec succès ! Vous pouvez maintenant discuter avec LIA ici.",
        "en": "Account linked successfully! You can now chat with LIA here.",
        "es": "¡Cuenta vinculada con éxito! Ahora puedes chatear con LIA aquí.",
        "de": "Konto erfolgreich verknüpft! Sie können jetzt hier mit LIA chatten.",
        "it": "Account collegato con successo! Ora puoi chattare con LIA qui.",
        "zh": "账户绑定成功！现在可以在这里与LIA聊天。",
    },
    "otp_invalid": {
        "fr": "Code invalide ou expiré. Générez un nouveau code depuis l'application.",
        "en": "Invalid or expired code. Generate a new code from the app.",
        "es": "Código inválido o expirado. Genera un nuevo código desde la app.",
        "de": "Ungültiger oder abgelaufener Code. Generieren Sie einen neuen Code in der App.",
        "it": "Codice non valido o scaduto. Genera un nuovo codice dall'app.",
        "zh": "验证码无效或已过期。请从应用中生成新验证码。",
    },
    "otp_blocked": {
        "fr": "Trop de tentatives. Réessayez dans quelques minutes.",
        "en": "Too many attempts. Please try again in a few minutes.",
        "es": "Demasiados intentos. Inténtalo de nuevo en unos minutos.",
        "de": "Zu viele Versuche. Bitte versuchen Sie es in ein paar Minuten erneut.",
        "it": "Troppi tentativi. Riprova tra qualche minuto.",
        "zh": "尝试次数过多。请稍后重试。",
    },
    "processing": {
        "fr": "Je traite votre message...",
        "en": "Processing your message...",
        "es": "Procesando tu mensaje...",
        "de": "Ihre Nachricht wird verarbeitet...",
        "it": "Sto elaborando il tuo messaggio...",
        "zh": "正在处理您的消息...",
    },
    "busy": {
        "fr": "Je traite encore votre message précédent. Un instant...",
        "en": "I'm still processing your previous message. One moment...",
        "es": "Aún estoy procesando tu mensaje anterior. Un momento...",
        "de": "Ich verarbeite noch Ihre vorherige Nachricht. Einen Moment...",
        "it": "Sto ancora elaborando il tuo messaggio precedente. Un momento...",
        "zh": "我还在处理您之前的消息，请稍候...",
    },
    "unbound": {
        "fr": "Envoyez /start suivi de votre code pour lier votre compte.",
        "en": "Send /start followed by your code to link your account.",
        "es": "Envía /start seguido de tu código para vincular tu cuenta.",
        "de": "Senden Sie /start gefolgt von Ihrem Code, um Ihr Konto zu verknüpfen.",
        "it": "Invia /start seguito dal tuo codice per collegare il tuo account.",
        "zh": "发送 /start 加验证码来绑定您的账户。",
    },
    "error": {
        "fr": "Une erreur est survenue. Réessayez ou consultez l'application web.",
        "en": "An error occurred. Please try again or check the web app.",
        "es": "Ocurrió un error. Inténtalo de nuevo o consulta la app web.",
        "de": "Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut oder prüfen Sie die Web-App.",
        "it": "Si è verificato un errore. Riprova o consulta l'app web.",
        "zh": "发生错误。请重试或查看网页应用。",
    },
    "voice_empty": {
        "fr": "Je n'ai pas pu comprendre votre message vocal. Réessayez ou envoyez du texte.",
        "en": "I couldn't understand your voice message. Please try again or send text.",
        "es": "No pude entender tu mensaje de voz. Inténtalo de nuevo o envía texto.",
        "de": "Ich konnte Ihre Sprachnachricht nicht verstehen. Versuchen Sie es erneut oder senden Sie Text.",
        "it": "Non sono riuscito a capire il tuo messaggio vocale. Riprova o invia un testo.",
        "zh": "无法理解您的语音消息。请重试或发送文字。",
    },
    "voice_too_long": {
        "fr": "Message vocal trop long (max 2 minutes). Envoyez un message plus court.",
        "en": "Voice message too long (max 2 minutes). Please send a shorter message.",
        "es": "Mensaje de voz demasiado largo (máx. 2 minutos). Envía un mensaje más corto.",
        "de": "Sprachnachricht zu lang (max. 2 Minuten). Bitte senden Sie eine kürzere Nachricht.",
        "it": "Messaggio vocale troppo lungo (max 2 minuti). Invia un messaggio più breve.",
        "zh": "语音消息太长（最长2分钟）。请发送更短的消息。",
    },
}


def get_bot_message(key: str, language: str = "fr") -> str:
    """
    Get a localized bot message.

    Args:
        key: Message key (e.g., 'otp_success').
        language: ISO language code (default: 'fr').

    Returns:
        Localized message string, falling back to French.
    """
    messages = TELEGRAM_BOT_MESSAGES.get(key, {})
    return messages.get(language, messages.get("fr", ""))


# ============================================================================
# Markdown → Telegram HTML Conversion
# ============================================================================

# Telegram HTML supports: <b>, <i>, <u>, <s>, <code>, <pre>, <a href="...">
_MD_TO_HTML_PATTERNS: list[tuple[str, str]] = [
    # Bold: **text** or __text__
    (r"\*\*(.*?)\*\*", r"<b>\1</b>"),
    (r"__(.*?)__", r"<b>\1</b>"),
    # Italic: *text* or _text_ (single)
    (r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)", r"<i>\1</i>"),
    (r"(?<!_)_(?!_)(.*?)(?<!_)_(?!_)", r"<i>\1</i>"),
    # Strikethrough: ~~text~~
    (r"~~(.*?)~~", r"<s>\1</s>"),
    # Code inline: `text`
    (r"`([^`]+)`", r"<code>\1</code>"),
    # Links: [text](url)
    (r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>'),
]


def markdown_to_telegram_html(text: str) -> str:
    """
    Convert basic Markdown to Telegram-supported HTML.

    Handles bold, italic, strikethrough, inline code, and links.
    Does NOT handle code blocks (``` ... ```) — those are passed through.

    Args:
        text: Markdown-formatted text.

    Returns:
        Telegram HTML-formatted text.
    """
    # Escape existing HTML entities first
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Apply markdown → HTML patterns
    for pattern, replacement in _MD_TO_HTML_PATTERNS:
        text = re.sub(pattern, replacement, text)

    return text


# ============================================================================
# Message Splitting
# ============================================================================


def split_message(text: str, max_length: int | None = None) -> list[str]:
    """
    Split a message into chunks that fit within Telegram's character limit.

    Tries to split at paragraph boundaries, then sentence boundaries,
    then at the max_length if no good split point is found.

    Args:
        text: Full message text.
        max_length: Maximum characters per chunk (default from settings).

    Returns:
        List of message chunks.
    """
    if max_length is None:
        max_length = getattr(
            settings,
            "telegram_message_max_length",
            TELEGRAM_MESSAGE_MAX_LENGTH_DEFAULT,
        )

    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to split at paragraph boundary
        split_pos = remaining.rfind("\n\n", 0, max_length)
        if split_pos == -1:
            # Try to split at line boundary
            split_pos = remaining.rfind("\n", 0, max_length)
        if split_pos == -1:
            # Try to split at sentence boundary
            split_pos = remaining.rfind(". ", 0, max_length)
            if split_pos != -1:
                split_pos += 1  # Include the period
        if split_pos == -1:
            # Hard split at max_length
            split_pos = max_length

        chunk = remaining[:split_pos].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_pos:].lstrip()

    return chunks


# ============================================================================
# Notification Formatting
# ============================================================================


def strip_html_cards(text: str) -> str:
    """
    Remove HTML card blocks from agent response text.

    The response_node injects HTML cards (weather widgets, email cards,
    contact cards, etc.) at the end of the LLM response for the web frontend.
    These are useless for Telegram — strip them before sending.

    Strategy (applied in order):

    1. Cut everything from the card injection point (``\\n\\n<div``) onwards.
    2. Cut from the first HTML **closing** tag onwards (``</div>``, ``</span>``…).
       The LLM writes Markdown — any ``</tag>`` is a leaked card fragment.
    3. Cut from the first HTML **opening** tag with attributes onwards
       (``<a href=…>``, ``<span class=…>``…).  Plain ``<b>`` without attributes
       is left alone (rare in practice, but safe).
    4. Strip remaining self-closing tags (``<img … />``, ``<br/>``).

    Args:
        text: Agent response text that may contain appended HTML cards.

    Returns:
        Clean text with HTML card blocks removed.
    """
    # 1. Remove full card block from the injection point.
    #    response_node injects: final_content + "\n\n" + <div class="lia-...">
    cleaned = re.sub(r"\n\n<div[\s>].*", "", text, flags=re.DOTALL)

    # 2. Remove from first closing tag onwards (orphaned card fragments).
    #    LLM text is Markdown — any </tag> is injected card HTML.
    cleaned = re.sub(r"</[a-zA-Z][a-zA-Z0-9]*\s*>.*", "", cleaned, flags=re.DOTALL)

    # 3. Remove from first opening tag with attributes onwards.
    #    Card components always have attributes: <a href="...">, <span class="...">.
    cleaned = re.sub(r"<[a-zA-Z][a-zA-Z0-9]*\s+[^>]*>.*", "", cleaned, flags=re.DOTALL)

    # 4. Remove self-closing tags (<img ... />, <br/>, <hr/>).
    cleaned = re.sub(r"<[a-zA-Z][^>]*/\s*>", "", cleaned)

    return cleaned.rstrip()


def format_notification(title: str, body: str) -> str:
    """
    Format a notification for Telegram delivery.

    HTML-escapes title and body to prevent Telegram ``BadRequest``
    errors from unescaped ``&``, ``<``, or ``>`` characters.

    Args:
        title: Notification title.
        body: Notification body.

    Returns:
        Formatted HTML string safe for Telegram ``parse_mode="HTML"``.
    """
    return f"<b>{html.escape(title)}</b>\n\n{html.escape(body)}"
