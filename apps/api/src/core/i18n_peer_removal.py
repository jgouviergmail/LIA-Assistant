"""Connection removal revokes both share directions and states best-effort consequences."""

from src.core.i18n_types import Language

PEER_REMOVAL_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Suppression de cette connexion",
        "Confirmer retire cette connexion et tous les partages affichés, dans les deux sens. Le parcours existant tente de rendre à leurs propriétaires les tickets partagés au moment de l’exécution ; un échec de cette restitution ne bloque pas la suppression. Les notifications des deux personnes sont tentées après enregistrement. Les contenus privés des tickets ne sont pas exposés. Aucun blocage n’est ajouté.",
    ),
    "en": (
        "Remove this connection",
        "Confirmation removes this connection and all displayed shares in both directions. The existing workflow attempts to return work shared at execution to its owners; a failed return does not prevent removal. Both people's notifications are attempted after saving. Private ticket content is not exposed. No block is added.",
    ),
    "de": (
        "Diese Verbindung entfernen",
        "Die Bestätigung entfernt die Verbindung und alle angezeigten Freigaben in beide Richtungen. Der bestehende Ablauf versucht, die bei der Ausführung gemeinsam bearbeiteten Tickets an ihre Eigentümer zurückzugeben; ein Fehlschlag verhindert die Entfernung nicht. Benachrichtigungen beider Personen werden nach dem Speichern versucht. Private Ticketinhalte werden nicht offengelegt. Es wird keine Sperre gesetzt.",
    ),
    "es": (
        "Eliminar esta conexión",
        "La confirmación elimina la conexión y todos los permisos mostrados en ambas direcciones. El proceso existente intenta devolver a sus propietarios los tickets compartidos al ejecutarse; un fallo no impide eliminar la conexión. Se intentan las notificaciones de ambas personas después de guardar. No se expone el contenido privado de los tickets ni se añade un bloqueo.",
    ),
    "it": (
        "Rimuovi questa connessione",
        "La conferma rimuove la connessione e tutte le condivisioni mostrate in entrambe le direzioni. Il percorso esistente tenta di restituire ai proprietari i ticket condivisi al momento dell’esecuzione; un errore non impedisce la rimozione. Le notifiche a entrambe le persone vengono tentate dopo il salvataggio. Il contenuto privato dei ticket non viene esposto e non viene aggiunto alcun blocco.",
    ),
    "zh-CN": (
        "删除此连接",
        "确认后删除此连接及所示的双向共享。现有流程会尝试将执行时双方共享的工单归还给各自所有者；归还失败不会阻止删除连接。保存后尝试通知双方。不公开工单的私人内容，也不添加屏蔽。",
    ),
}
