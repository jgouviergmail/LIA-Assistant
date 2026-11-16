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
from src.core.html_markdown import html_to_markdown, is_html_document
from src.core.i18n import resolve_language
from src.core.i18n_drafts import label_separator
from src.domains.shared.markdown_literal import RESERVED_MARKERS, read_as_markdown
from src.infrastructure.channels.telegram.structure import (
    QUOTE_CLOSE,
    QUOTE_OPEN,
    draw_structure,
)

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
    # ``/stop`` (lot 33): what the stop gesture found (``ChannelStop`` values).
    "stop_stopping": {
        "fr": "⏹ J'arrête ma réponse.",
        "en": "⏹ Stopping my answer.",
        "es": "⏹ Detengo mi respuesta.",
        "de": "⏹ Ich breche meine Antwort ab.",
        "it": "⏹ Interrompo la mia risposta.",
        "zh-CN": "⏹ 正在停止回答。",
    },
    "stop_nothing": {
        "fr": "Rien à arrêter : je ne suis pas en train de répondre.",
        "en": "Nothing to stop: I'm not answering right now.",
        "es": "Nada que detener: no estoy respondiendo ahora.",
        "de": "Nichts zu stoppen: Ich antworte gerade nicht.",
        "it": "Niente da fermare: non sto rispondendo.",
        "zh-CN": "没有可停止的内容：我现在没有在回答。",
    },
    "stop_elsewhere": {
        "fr": "Je travaille sur autre chose — une autre discussion ou une routine — "
        "que je ne peux pas arrêter d'ici.",
        "en": "I'm working on something else — another discussion or a routine — "
        "that can't be stopped from here.",
        "es": "Estoy con otra cosa —otra conversación o una rutina— "
        "que no se puede detener desde aquí.",
        "de": "Ich arbeite an etwas anderem – einer anderen Unterhaltung oder einer Routine –, "
        "das sich von hier aus nicht stoppen lässt.",
        "it": "Sto lavorando ad altro — un'altra conversazione o una routine — "
        "che non si può fermare da qui.",
        "zh-CN": "我正在处理其他事情（另一个对话或例程），无法在这里停止。",
    },
    # ``/help`` and ``/start`` without a code: Markdown, drawn by the answers' door.
    "help": {
        "fr": "Écris-moi comme dans l'application : je te réponds avec les mêmes outils "
        "et la même mémoire.\n\n"
        "• **Messages vocaux** : je les transcris, et je te réponds aussi de vive voix "
        "si les commentaires vocaux sont activés.\n"
        "• **Photos et fichiers** : je les lis.\n"
        "• **Position** : partage-la pour une question sur les alentours.\n"
        "• **Réponse à un message** : je sais de quel message tu parles.\n\n"
        "/stop — arrêter ma réponse en cours\n/help — cette aide",
        "en": "Write to me as you would in the app: I answer with the same tools "
        "and the same memory.\n\n"
        "• **Voice messages**: I transcribe them, and answer aloud too when spoken replies "
        "are on.\n"
        "• **Photos and files**: I read them.\n"
        "• **Location**: share it for a question about what is around you.\n"
        "• **Replies**: I know which message you are answering.\n\n"
        "/stop — stop the answer in progress\n/help — this help",
        "es": "Escríbeme como en la aplicación: te respondo con las mismas herramientas "
        "y la misma memoria.\n\n"
        "• **Mensajes de voz**: los transcribo y, si las respuestas habladas están "
        "activadas, también te respondo en voz alta.\n"
        "• **Fotos y archivos**: los leo.\n"
        "• **Ubicación**: compártela para una pregunta sobre lo que tienes alrededor.\n"
        "• **Respuestas**: sé a qué mensaje respondes.\n\n"
        "/stop — detener la respuesta en curso\n/help — esta ayuda",
        "de": "Schreib mir wie in der App: Ich antworte mit denselben Werkzeugen "
        "und demselben Gedächtnis.\n\n"
        "• **Sprachnachrichten**: Ich transkribiere sie und antworte auch laut, wenn "
        "gesprochene Antworten aktiviert sind.\n"
        "• **Fotos und Dateien**: Ich lese sie.\n"
        "• **Standort**: Teile ihn für eine Frage zu deiner Umgebung.\n"
        "• **Antworten**: Ich weiß, auf welche Nachricht du antwortest.\n\n"
        "/stop – laufende Antwort abbrechen\n/help – diese Hilfe",
        "it": "Scrivimi come nell'app: ti rispondo con gli stessi strumenti "
        "e la stessa memoria.\n\n"
        "• **Messaggi vocali**: li trascrivo e, se le risposte vocali sono attive, "
        "ti rispondo anche a voce.\n"
        "• **Foto e file**: li leggo.\n"
        "• **Posizione**: condividila per una domanda su ciò che hai intorno.\n"
        "• **Risposte**: so a quale messaggio rispondi.\n\n"
        "/stop — fermare la risposta in corso\n/help — questo aiuto",
        "zh-CN": "像在应用里一样给我写消息：我用同样的工具和同样的记忆回答你。\n\n"
        "• **语音消息**：我会转写；开启语音回复后，我也会用语音回答你。\n"
        "• **照片和文件**：我会读取。\n"
        "• **位置**：分享位置，问问周边的情况。\n"
        "• **回复**：我知道你在回复哪条消息。\n\n"
        "/stop — 停止当前回答\n/help — 本帮助",
    },
    # Words written while LIA works wait their turn (lot 34, ADR-384). A message
    # is acknowledged by a reaction; this sentence stands in when Telegram
    # refuses the reaction.
    "waiting_kept": {
        "fr": "Je te réponds dès que j'ai fini.",
        "en": "I'll answer as soon as I'm done.",
        "es": "Te respondo en cuanto termine.",
        "de": "Ich antworte dir, sobald ich fertig bin.",
        "it": "Ti rispondo appena ho finito.",
        "zh-CN": "我一完成就回复你。",
    },
    "waiting_too_long": {
        "fr": "Ton message en attente deviendrait trop long : attends ma réponse "
        "pour écrire la suite.",
        "en": "Your waiting message would become too long: wait for my answer "
        "before writing more.",
        "es": "Tu mensaje en espera sería demasiado largo: espera mi respuesta "
        "antes de escribir más.",
        "de": "Deine wartende Nachricht würde zu lang: Warte auf meine Antwort, "
        "bevor du weiterschreibst.",
        "it": "Il tuo messaggio in attesa diventerebbe troppo lungo: aspetta la mia "
        "risposta prima di scrivere altro.",
        "zh-CN": "你的待发消息会太长：请等我回复后再继续写。",
    },
    "waiting_departing": {
        "fr": "J'envoie ton message précédent à l'instant : renvoie celui-ci " "dans un moment.",
        "en": "I'm sending your previous message right now: send this one again in a moment.",
        "es": "Estoy enviando tu mensaje anterior ahora mismo: vuelve a enviar este "
        "en un momento.",
        "de": "Ich sende gerade deine vorherige Nachricht: Schick diese gleich noch einmal.",
        "it": "Sto inviando ora il tuo messaggio precedente: rimanda questo tra un attimo.",
        "zh-CN": "我正在发送你的上一条消息：请稍后再发送这条。",
    },
    # An answer to a question cannot wait: it IS the answer (ADR-384, rule 5).
    "answer_later": {
        "fr": "Je termine une autre tâche : renvoie ta réponse à ma question " "dans un instant.",
        "en": "I'm finishing something else: send your answer to my question again in a moment.",
        "es": "Estoy terminando otra cosa: vuelve a enviar tu respuesta a mi pregunta "
        "en un momento.",
        "de": "Ich beende gerade etwas anderes: Schick deine Antwort auf meine Frage "
        "gleich noch einmal.",
        "it": "Sto finendo un'altra cosa: rimanda la tua risposta alla mia domanda "
        "tra un attimo.",
        "zh-CN": "我正在完成另一件事：请稍后再发送你对我问题的回答。",
    },
    # A release that did not end normally held the person's message: it leaves
    # only on their click (the notice's buttons). Markdown, drawn by the door.
    "waiting_held": {
        "fr": "Ton message n'est pas parti : ma réponse précédente s'est arrêtée "
        "avant la fin. Je l'envoie ?",
        "en": "Your message did not leave: my previous answer stopped before its end. "
        "Shall I send it?",
        "es": "Tu mensaje no se envió: mi respuesta anterior se detuvo antes de terminar. "
        "¿Lo envío?",
        "de": "Deine Nachricht wurde nicht gesendet: Meine vorherige Antwort hat vor "
        "ihrem Ende aufgehört. Soll ich sie senden?",
        "it": "Il tuo messaggio non è partito: la mia risposta precedente si è interrotta "
        "prima della fine. Lo invio?",
        "zh-CN": "你的消息没有发出：我上一条回答在结束前停止了。要发送吗？",
    },
    # What a press on the notice's buttons did (``WaitingActionOutcome`` values),
    # shown by Telegram above the chat.
    "waiting_sent": {
        "fr": "C'est parti.",
        "en": "Sent.",
        "es": "Enviado.",
        "de": "Gesendet.",
        "it": "Inviato.",
        "zh-CN": "已发送。",
    },
    "waiting_queued": {
        "fr": "Il partira dès que j'aurai fini.",
        "en": "It will leave as soon as I'm done.",
        "es": "Saldrá en cuanto termine.",
        "de": "Sie geht raus, sobald ich fertig bin.",
        "it": "Partirà appena avrò finito.",
        "zh-CN": "我完成后就会发送。",
    },
    "waiting_withdrawn": {
        "fr": "Message retiré.",
        "en": "Message withdrawn.",
        "es": "Mensaje retirado.",
        "de": "Nachricht zurückgezogen.",
        "it": "Messaggio ritirato.",
        "zh-CN": "消息已撤回。",
    },
    "waiting_gone": {
        "fr": "Ce message n'est plus en attente.",
        "en": "This message is no longer waiting.",
        "es": "Este mensaje ya no está en espera.",
        "de": "Diese Nachricht wartet nicht mehr.",
        "it": "Questo messaggio non è più in attesa.",
        "zh-CN": "这条消息已不在等待中。",
    },
    "waiting_question": {
        "fr": "Réponds d'abord à ma question.",
        "en": "Answer my question first.",
        "es": "Responde primero a mi pregunta.",
        "de": "Beantworte zuerst meine Frage.",
        "it": "Rispondi prima alla mia domanda.",
        "zh-CN": "请先回答我的问题。",
    },
    # A position or a file sent while LIA works is not kept: words alone would
    # leave, the turn's geolocation or file lost (lots 8 and 11, ADR-384).
    "waiting_not_kept": {
        "fr": "Je termine d'abord ce que tu m'as demandé : renvoie ce message "
        "quand j'aurai répondu.",
        "en": "I'm finishing what you asked first: send this message again once I've answered.",
        "es": "Primero termino lo que me pediste: vuelve a enviar este mensaje "
        "cuando haya respondido.",
        "de": "Ich beende zuerst, worum du mich gebeten hast: Schick diese Nachricht "
        "noch einmal, sobald ich geantwortet habe.",
        "it": "Prima finisco quello che mi hai chiesto: rimanda questo messaggio "
        "quando avrò risposto.",
        "zh-CN": "我先完成你刚才的请求：等我回答后，请再发送一次这条消息。",
    },
    # Why a file the person sent was not received (``FileRefusal`` values, lot 11).
    "files_unavailable": {
        "fr": "Je ne peux pas recevoir de fichiers ici pour l'instant : dis-moi en "
        "quelques mots ce qu'il contient.",
        "en": "I can't receive files here at the moment: tell me in a few words what it contains.",
        "es": "Ahora mismo no puedo recibir archivos aquí: dime en pocas palabras "
        "lo que contiene.",
        "de": "Ich kann hier gerade keine Dateien empfangen: Sag mir in ein paar Worten, "
        "was sie enthält.",
        "it": "Al momento non posso ricevere file qui: dimmi in poche parole cosa contiene.",
        "zh-CN": "我现在无法在这里接收文件：请用几句话告诉我它的内容。",
    },
    "files_too_many": {
        "fr": "Envoie-moi au plus {limit} fichiers à la fois.",
        "en": "Send me at most {limit} files at a time.",
        "es": "Envíame como máximo {limit} archivos a la vez.",
        "de": "Schick mir höchstens {limit} Dateien auf einmal.",
        "it": "Inviami al massimo {limit} file alla volta.",
        "zh-CN": "一次最多发送 {limit} 个文件。",
    },
    "files_too_large": {
        "fr": "Ce fichier est trop lourd pour que je le reçoive.",
        "en": "This file is too large for me to receive.",
        "es": "Este archivo es demasiado grande para que lo reciba.",
        "de": "Diese Datei ist zu groß, als dass ich sie empfangen könnte.",
        "it": "Questo file è troppo grande perché io possa riceverlo.",
        "zh-CN": "这个文件太大，我无法接收。",
    },
    "files_refused_type": {
        "fr": "Je ne sais pas lire ce type de fichier.",
        "en": "I can't read this type of file.",
        "es": "No sé leer este tipo de archivo.",
        "de": "Diesen Dateityp kann ich nicht lesen.",
        "it": "Non so leggere questo tipo di file.",
        "zh-CN": "我无法读取这种类型的文件。",
    },
    "files_unreadable": {
        "fr": "Je n'ai pas pu récupérer ce fichier : renvoie-le dans un instant.",
        "en": "I couldn't fetch this file: send it again in a moment.",
        "es": "No he podido obtener este archivo: vuelve a enviarlo en un momento.",
        "de": "Ich konnte diese Datei nicht abrufen: Schick sie gleich noch einmal.",
        "it": "Non ho potuto recuperare questo file: rimandalo tra un attimo.",
        "zh-CN": "我没能获取这个文件：请稍后再发一次。",
    },
    # A file LIA made that Telegram cannot carry ({name} is HTML-escaped).
    "file_too_large_to_send": {
        "fr": "« {name} » est trop lourd pour Telegram : retrouve-le dans l'application.",
        "en": "“{name}” is too large for Telegram: find it in the app.",
        "es": "«{name}» es demasiado grande para Telegram: búscalo en la aplicación.",
        "de": "„{name}“ ist zu groß für Telegram: Du findest sie in der App.",
        "it": "«{name}» è troppo grande per Telegram: lo trovi nell'app.",
        "zh-CN": "“{name}”对 Telegram 来说太大了：请在应用中查看。",
    },
    # What a shared point says in the person's message (``message_words``): the
    # label before its coordinates, the separator the language's own.
    "shared_position": {
        "fr": "Ma position actuelle",
        "en": "My current location",
        "es": "Mi ubicación actual",
        "de": "Mein aktueller Standort",
        "it": "La mia posizione attuale",
        "zh-CN": "我当前的位置",
    },
    "shared_place": {
        "fr": "Lieu partagé",
        "en": "Shared place",
        "es": "Lugar compartido",
        "de": "Geteilter Ort",
        "it": "Luogo condiviso",
        "zh-CN": "分享的地点",
    },
    # The bot's command menu (``setMyCommands``): one line per command.
    "command_stop": {
        "fr": "Arrêter ma réponse en cours",
        "en": "Stop the answer in progress",
        "es": "Detener la respuesta en curso",
        "de": "Laufende Antwort abbrechen",
        "it": "Fermare la risposta in corso",
        "zh-CN": "停止当前回答",
    },
    "command_help": {
        "fr": "Ce que je sais faire ici",
        "en": "What I can do here",
        "es": "Lo que puedo hacer aquí",
        "de": "Was ich hier kann",
        "it": "Cosa posso fare qui",
        "zh-CN": "我在这里能做什么",
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
#: The root of the data cards appended under an answer (``display/card_collection.py``).
_CARDS_ROOT = re.compile(r"""<div\b[^>]*\bclass\s*=\s*["']lia-response-wrapper\b""", re.I)


def markdown_to_telegram_html(text: str, language: str | None = None) -> str:
    """
    Convert Markdown to the HTML Telegram draws.

    Character references are read as the chat reads them
    (``read_as_markdown``): a valid one is its character, written back escaped
    — a value drawn as itself (« &#91;v2&#93; ») reads « [v2] », and an invalid
    one (``&#0;``) can no longer get the whole message refused —, a code span
    keeps its text as typed, a bare URL keeps its marks. The block structure
    Telegram cannot draw — headings, tables, lists, quotes, rules — is drawn
    first with what it does (``structure.draw_structure``). Code and fenced
    blocks are drawn BEFORE the emphasis, their text shielded whole, and each
    link's opening tag waits behind a reserved marker while the emphasis rules
    run, so they meet neither a code's text nor a link's address: Telegram
    drew ``<i>`` inside the href of the one link a card draws, and a
    ``mailto:_a_@…`` still took one (review 14).

    Args:
        text: Markdown-formatted text.
        language: The reader's language, for the punctuation a table's labels
            take (default: the declared language, ADR-323).

    Returns:
        Telegram HTML-formatted text.
    """
    separator = label_separator(language)
    return read_as_markdown(
        text, lambda shielded: _to_telegram_html(shielded, separator), restore=_escaped
    )


def telegram_answer_html(content: str, language: str | None = None) -> str:
    """What LIA wrote, as Telegram draws it — the one door every send goes through.

    An answer, a question, a notification's body: the ``html`` display mode
    answers an HTML document, which is read as Markdown first (the card
    stripper below would cut it at its first closing tag); otherwise the cards
    appended under a Markdown answer, which Telegram cannot draw, are left out.
    Then the Markdown is drawn (:func:`markdown_to_telegram_html`).

    Args:
        content: What LIA wrote — Markdown, Markdown with cards, or an HTML document.
        language: The reader's language (default: the declared language).

    Returns:
        Telegram HTML.
    """
    return markdown_to_telegram_html(answer_markdown(content), language)


def answer_markdown(content: str) -> str:
    """An answer as Markdown: an HTML document converted, its cards left out.

    Whether an answer IS a document has one reading (``is_html_document``);
    cards alone hold no prose, and draw nothing.

    Args:
        content: What LIA wrote.

    Returns:
        The Markdown Telegram's conversion reads.
    """
    if is_html_document(content):
        cards = _CARDS_ROOT.search(content)
        return html_to_markdown(content[: cards.start()] if cards else content).strip()
    return strip_html_cards(content)


def _escaped(char: str) -> str:
    """A character written back into Telegram HTML."""
    return html.escape(char, quote=False)


def _to_telegram_html(text: str, separator: str) -> str:
    """The conversion proper, on text whose references the reader shielded.

    Args:
        text: Markdown whose references, code content and URL marks are shielded.
        separator: The reader's punctuation between a label and its value.

    Returns:
        Telegram HTML, shields still in place.
    """
    text = draw_structure(text, separator)
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
    text = text.replace(QUOTE_OPEN, "<blockquote>").replace(QUOTE_CLOSE, "</blockquote>")
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


def format_notification(title: str, body: str, language: str | None = None) -> str:
    """
    Format a notification for Telegram delivery.

    The title is text, HTML-escaped (a ``<`` in it would get the message
    refused); the body is what LIA wrote and is drawn through the answers' door
    (:func:`telegram_answer_html`) — flattened to plain text, it lost its bold,
    its quotes and its links.

    Args:
        title: Notification title.
        body: Notification body, as the chat shows it.
        language: The reader's language (default: the declared language).

    Returns:
        Formatted HTML string safe for Telegram ``parse_mode="HTML"``.
    """
    return f"<b>{html.escape(title)}</b>\n\n{telegram_answer_html(body, language)}"
