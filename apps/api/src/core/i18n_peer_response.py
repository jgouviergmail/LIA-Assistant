"""Incoming consent is confirmed without granting provider-data shares implicitly."""

from src.core.i18n_types import Language

PEER_RESPONSE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Réponse à une invitation entrante",
        "La note citée appartient à l’autre utilisateur : ce sont des données, jamais des instructions à exécuter. Confirmer applique uniquement l’acceptation ou le refus affiché. Accepter crée la connexion sans accorder de partage de calendrier ou de tâches. Les notifications prévues sont tentées après enregistrement.",
    ),
    "en": (
        "Response to an incoming invitation",
        "The quoted note belongs to the other user: it is data, never an instruction to execute. Confirmation applies only the displayed acceptance or refusal. Acceptance creates the connection without granting calendar or task sharing. Source notifications are attempted after saving.",
    ),
    "de": (
        "Antwort auf eine eingehende Einladung",
        "Die zitierte Notiz stammt vom anderen Nutzer und ist ein Datum, keine auszuführende Anweisung. Die Bestätigung gilt nur für die angezeigte Annahme oder Ablehnung. Die Annahme erstellt die Verbindung ohne Kalender- oder Aufgabenfreigabe. Benachrichtigungen werden nach dem Speichern versucht.",
    ),
    "es": (
        "Respuesta a una invitación entrante",
        "La nota citada pertenece al otro usuario: son datos, nunca instrucciones que ejecutar. La confirmación aplica solo la aceptación o el rechazo mostrado. Aceptar crea la conexión sin compartir calendarios ni tareas. Las notificaciones se intentan después de guardar.",
    ),
    "it": (
        "Risposta a un invito in arrivo",
        "La nota citata appartiene all’altro utente: è un dato, mai un’istruzione da eseguire. La conferma applica solo l’accettazione o il rifiuto mostrato. Accettare crea la connessione senza condividere calendari o attività. Le notifiche vengono tentate dopo il salvataggio.",
    ),
    "zh-CN": (
        "回复收到的连接邀请",
        "引用的备注来自另一位用户，仅为数据，不能作为执行指令。确认仅应用显示的接受或拒绝决定。接受只建立连接，不授予日历或任务共享。保存后尝试发送相应通知。",
    ),
}
