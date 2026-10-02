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
from src.core.i18n import resolve_language
from src.domains.shared.markdown_literal import RESERVED_MARKERS, read_as_markdown

# ============================================================================
# Localized Bot Messages (6 languages)
# ============================================================================

TELEGRAM_BOT_MESSAGES: dict[str, dict[str, str]] = {
    "otp_success": {
        "fr": "Compte lié avec succès ! Tu peux maintenant discuter avec LIA ici.",
        "en": "Account linked successfully! You can now chat with LIA here.",
        "es": "¡Cuenta vinculada con éxito! Ahora puedes chatear con LIA aquí.",
        "de": "Konto erfolgreich verknüpft! Du kannst jetzt hier mit LIA chatten.",
        "it": "Account collegato con successo! Ora puoi chattare con LIA qui.",
        "zh-CN": "账户绑定成功！现在可以在这里与LIA聊天。",
    },
    "otp_invalid": {
        "fr": "Code invalide ou expiré. Génère un nouveau code depuis l'application.",
        "en": "Invalid or expired code. Generate a new code from the app.",
        "es": "Código inválido o expirado. Genera un nuevo código desde la app.",
        "de": "Ungültiger oder abgelaufener Code. Generiere einen neuen Code in der App.",
        "it": "Codice non valido o scaduto. Genera un nuovo codice dall'app.",
        "zh-CN": "验证码无效或已过期。请从应用中生成新验证码。",
    },
    "otp_blocked": {
        "fr": "Trop de tentatives. Réessaie dans quelques minutes.",
        "en": "Too many attempts. Please try again in a few minutes.",
        "es": "Demasiados intentos. Inténtalo de nuevo en unos minutos.",
        "de": "Zu viele Versuche. Bitte versuche es in ein paar Minuten erneut.",
        "it": "Troppi tentativi. Riprova tra qualche minuto.",
        "zh-CN": "尝试次数过多。请稍后重试。",
    },
    "busy": {
        "fr": "Je traite encore ton message précédent. Un instant...",
        "en": "I'm still processing your previous message. One moment...",
        "es": "Aún estoy procesando tu mensaje anterior. Un momento...",
        "de": "Ich verarbeite noch deine vorherige Nachricht. Einen Moment...",
        "it": "Sto ancora elaborando il tuo messaggio precedente. Un momento...",
        "zh-CN": "我还在处理你之前的消息，请稍候……",
    },
    "unbound": {
        "fr": "Envoie /start suivi de ton code pour lier ton compte.",
        "en": "Send /start followed by your code to link your account.",
        "es": "Envía /start seguido de tu código para vincular tu cuenta.",
        "de": "Sende /start gefolgt von deinem Code, um dein Konto zu verknüpfen.",
        "it": "Invia /start seguito dal tuo codice per collegare il tuo account.",
        "zh-CN": "发送 /start 加验证码来绑定你的账户。",
    },
    # A person the bot knows whose account an administrator deactivated: the
    # link code cannot help (generating one needs an active session).
    "account_inactive": {
        "fr": "Ton compte LIA est désactivé. Contacte l'administrateur de ton instance.",
        "en": "Your LIA account is deactivated. Contact your instance's administrator.",
        "es": "Tu cuenta de LIA está desactivada. Contacta con el administrador de tu instancia.",
        "de": "Dein LIA-Konto ist deaktiviert. Wende dich an den Administrator deiner Instanz.",
        "it": "Il tuo account LIA è disattivato. Contatta l'amministratore della tua istanza.",
        "zh-CN": "你的 LIA 账户已停用。请联系你的实例管理员。",
    },
    # A person whose binding they switched off themselves: /start cannot help
    # (the binding already exists) — the settings section that switched it off can.
    "channel_disabled": {
        "fr": "Ce canal est désactivé pour ton compte LIA. Réactive-le dans les paramètres, section « Canaux de messagerie ».",
        "en": "This channel is disabled for your LIA account. Turn it back on in the settings, under “Messaging Channels”.",
        "es": "Este canal está desactivado para tu cuenta de LIA. Vuelve a activarlo en los ajustes, sección «Canales de mensajería».",
        "de": "Dieser Kanal ist für dein LIA-Konto deaktiviert. Aktiviere ihn in den Einstellungen unter „Messaging-Kanäle“ wieder.",
        "it": "Questo canale è disattivato per il tuo account LIA. Riattivalo nelle impostazioni, sezione «Canali di messaggistica».",
        "zh-CN": "你的 LIA 账户已禁用此通道。请在设置的“消息通道”中重新启用。",
    },
    "error": {
        "fr": "Une erreur est survenue. Réessaie ou consulte l'application web.",
        "en": "An error occurred. Please try again or check the web app.",
        "es": "Ocurrió un error. Inténtalo de nuevo o consulta la app web.",
        "de": "Ein Fehler ist aufgetreten. Bitte versuche es erneut oder prüfe die Web-App.",
        "it": "Si è verificato un errore. Riprova o consulta l'app web.",
        "zh-CN": "发生错误。请重试或查看网页应用。",
    },
    "voice_empty": {
        "fr": "Je n'ai pas pu comprendre ton message vocal. Réessaie ou envoie du texte.",
        "en": "I couldn't understand your voice message. Please try again or send text.",
        "es": "No pude entender tu mensaje de voz. Inténtalo de nuevo o envía texto.",
        "de": "Ich konnte deine Sprachnachricht nicht verstehen. Versuche es erneut oder sende Text.",
        "it": "Non sono riuscito a capire il tuo messaggio vocale. Riprova o invia un testo.",
        "zh-CN": "无法理解你的语音消息。请重试或发送文字。",
    },
    "hitl_expired": {
        "fr": "Cette question a expiré ou a déjà reçu une réponse.",
        "en": "This question has expired or was already answered.",
        "es": "Esta pregunta ha caducado o ya se respondió.",
        "de": "Diese Frage ist abgelaufen oder wurde schon beantwortet.",
        "it": "Questa domanda è scaduta o ha già ricevuto una risposta.",
        "zh-CN": "这个问题已过期或已经回答过了。",
    },
    # ``{max_seconds}`` is filled from the enforced cap, never written here — in
    # seconds, because the STT's own cap may be any number of them.
    "voice_too_long": {
        "fr": "Message vocal trop long (max. {max_seconds} s). Envoie un message plus court.",
        "en": "Voice message too long (max {max_seconds} s). Please send a shorter message.",
        "es": "Mensaje de voz demasiado largo (máx. {max_seconds} s). Envía un mensaje más corto.",
        "de": "Sprachnachricht zu lang (max. {max_seconds} Sek.). Bitte sende eine kürzere Nachricht.",
        "it": "Messaggio vocale troppo lungo (max {max_seconds} s). Invia un messaggio più breve.",
        "zh-CN": "语音消息太长（最长 {max_seconds} 秒）。请发送更短的消息。",
    },
}


def get_bot_message(key: str, language: str | None = None) -> str:
    """
    Get a localized bot message.

    Args:
        key: Message key (e.g., 'otp_success').
        language: Language code in any spelling; the declared language when
            absent (ADR-323).

    Returns:
        Localized message string ("" for an unknown key).
    """
    messages = TELEGRAM_BOT_MESSAGES.get(key)
    return messages[resolve_language(language)] if messages else ""


# ============================================================================
# Markdown → Telegram HTML Conversion
# ============================================================================

# Telegram HTML supports: <b>, <i>, <u>, <s>, <code>, <pre>, <a href="...">

#: A fenced block: its body, which the reader keeps as typed, drawn as-is.
_FENCED_CODE = re.compile(
    r"^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n([\s\S]*?)(?:^[ \t]{0,3}\1[ \t]*(?:\n|$)|\Z)",
    re.MULTILINE,
)
#: A code span, closed by a backtick run of its own length.
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)([\s\S]+?)(?<!`)\1(?!`)")
#: A link LIA wrote, to a web or mail address: Telegram refuses a message whose
#: link has a scheme it does not draw, and `javascript:` is no link at all.
_LINK = re.compile(r"\[([^\]\n]+)\]\(((?:https?://|mailto:)[^)\s]+)\)")
#: Emphasis, once code and links are drawn. An ``_`` opens or closes nothing
#: inside a word, as in CommonMark: ``max_results, page_token`` stays as typed.
_EMPHASIS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<![^\W_])__(?=\S)(.+?)(?<=\S)__(?![^\W_])"), r"<b>\1</b>"),
    (re.compile(r"(?<!\*)\*(?![*\s])(.+?)(?<![*\s])\*(?!\*)"), r"<i>\1</i>"),
    (re.compile(r"(?<![^\W_])_(?![_\s])(.+?)(?<![_\s])_(?![^\W_])"), r"<i>\1</i>"),
    (re.compile(r"~~(?=\S)(.+?)(?<=\S)~~"), r"<s>\1</s>"),
]
#: Where a drawn link's opening tag waits while the emphasis rules run.
_ANCHOR = RESERVED_MARKERS[0]


def markdown_to_telegram_html(text: str) -> str:
    """
    Convert Markdown to the HTML Telegram draws.

    Character references are read as the chat reads them
    (``read_as_markdown``): a valid one is its character, written back escaped
    — a value drawn as itself (« &#91;v2&#93; ») reads « [v2] », and an invalid
    one (``&#0;``) can no longer get the whole message refused —, a code span
    keeps its text as typed, a bare URL keeps its marks. Code and fenced
    blocks are drawn BEFORE the emphasis, their text shielded whole, and each
    link's opening tag waits behind a reserved marker while the emphasis rules
    run, so they meet neither a code's text nor a link's address: Telegram
    drew ``<i>`` inside the href of the one link a card draws, and a
    ``mailto:_a_@…`` still took one (review 14).

    Args:
        text: Markdown-formatted text.

    Returns:
        Telegram HTML-formatted text.
    """
    return read_as_markdown(text, _to_telegram_html, restore=_escaped)


def _escaped(char: str) -> str:
    """A character written back into Telegram HTML."""
    return html.escape(char, quote=False)


def _to_telegram_html(text: str) -> str:
    """The conversion proper, on text whose references the reader shielded.

    Args:
        text: Markdown whose references, code content and URL marks are shielded.

    Returns:
        Telegram HTML, shields still in place.
    """
    text = html.escape(text, quote=False)
    text = _FENCED_CODE.sub(lambda match: f"<pre>{match.group(2)}</pre>", text)
    text = _INLINE_CODE.sub(r"<code>\2</code>", text)
    anchors: list[str] = []

    def _held(match: re.Match[str]) -> str:
        """A Markdown link drawn as Telegram's anchor, its opening tag held back."""
        href = match.group(2).replace('"', "&quot;")
        anchors.append(f'<a href="{href}">')
        return f"{_ANCHOR}{match.group(1)}</a>"

    text = _LINK.sub(_held, text)
    for pattern, replacement in _EMPHASIS:
        text = pattern.sub(replacement, text)
    head, *tails = text.split(_ANCHOR)
    return head + "".join(anchor + tail for anchor, tail in zip(anchors, tails, strict=True))


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
        max_length = settings.telegram_message_max_length

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
