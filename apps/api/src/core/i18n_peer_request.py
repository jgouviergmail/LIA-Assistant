"""Invitation approval explicitly names crossing acceptance and unchanged outgoing notes."""

from src.core.i18n_types import Language

PEER_REQUEST_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Invitation de connexion",
        "Une nouvelle invitation envoie la note affichée. Une demande entrante croisée accepte directement la connexion ; aucune nouvelle note n’est envoyée. Une demande sortante existante reste inchangée. LIA demande votre accord pour l’état et la personne affichés, puis tente les notifications prévues après enregistrement.",
    ),
    "en": (
        "Connection invitation",
        "A new invitation sends the displayed note. A crossing incoming request accepts the connection directly; no new note is sent. An existing outgoing request stays unchanged. Approval applies to the displayed person and state; source notifications are attempted after saving.",
    ),
    "de": (
        "Verbindungseinladung",
        "Eine neue Einladung sendet die angezeigte Notiz. Eine gekreuzte eingehende Anfrage akzeptiert die Verbindung direkt; es wird keine neue Notiz gesendet. Eine bestehende ausgehende Anfrage bleibt unverändert. Die Bestätigung gilt für die angezeigte Person und den Zustand; Benachrichtigungen werden nach dem Speichern versucht.",
    ),
    "es": (
        "Invitación de conexión",
        "Una nueva invitación envía la nota mostrada. Una solicitud entrante cruzada acepta directamente la conexión; no se envía una nueva nota. Una solicitud saliente existente no cambia. La confirmación se aplica a la persona y al estado mostrados; las notificaciones se intentan después de guardar.",
    ),
    "it": (
        "Invito di connessione",
        "Un nuovo invito invia la nota mostrata. Una richiesta in arrivo incrociata accetta direttamente la connessione; non viene inviata una nuova nota. Una richiesta in uscita esistente rimane invariata. La conferma riguarda la persona e lo stato mostrati; le notifiche vengono tentate dopo il salvataggio.",
    ),
    "zh-CN": (
        "连接邀请",
        "新邀请发送显示的备注。相互交叉的邀请会直接接受连接，不发送新备注。已有的发出请求保持不变。确认仅适用于显示的人和状态，保存后尝试发送相应通知。",
    ),
}
