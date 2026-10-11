"""A directional block is silent; lifting it restores no previous permission."""

from src.core.i18n_types import Language

PEER_BLOCK_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Mon blocage de cette personne",
        "Bloquer coupe silencieusement la connexion en attente ou acceptée et ses partages dans les deux sens. Pour une connexion acceptée, le parcours existant tente de rendre les tickets partagés à leurs propriétaires ; un échec ne bloque pas le blocage. Débloquer retire uniquement mon blocage : cela ne restaure aucune connexion, aucun partage ni aucune affectation, et ne retire pas le blocage de l’autre personne. Aucun message ni notification n’est envoyé.",
    ),
    "en": (
        "My block of this person",
        "Blocking silently severs a pending or accepted connection and both sharing directions. For an accepted connection, the existing workflow attempts to return shared work to its owners; failure does not prevent blocking. Unblocking lifts only my block: it restores no connection, sharing or assignment and does not lift the other person's block. No message or notification is sent.",
    ),
    "de": (
        "Meine Sperre dieser Person",
        "Sperren beendet still eine ausstehende oder angenommene Verbindung und alle Freigaben in beide Richtungen. Bei einer angenommenen Verbindung versucht der bestehende Ablauf, gemeinsame Tickets an ihre Eigentümer zurückzugeben; ein Fehlschlag verhindert die Sperre nicht. Entsperren hebt nur meine Sperre auf und stellt weder Verbindung noch Freigaben oder Zuweisungen wieder her; die Sperre der anderen Person bleibt bestehen. Es wird keine Nachricht oder Benachrichtigung versendet.",
    ),
    "es": (
        "Mi bloqueo de esta persona",
        "Bloquear corta silenciosamente una conexión pendiente o aceptada y sus permisos en ambas direcciones. En una conexión aceptada, el proceso existente intenta devolver el trabajo compartido a sus propietarios; un fallo no impide bloquear. Desbloquear retira solo mi bloqueo: no restaura conexión, permisos ni asignaciones y no retira el bloqueo de la otra persona. No se envían mensajes ni notificaciones.",
    ),
    "it": (
        "Il mio blocco di questa persona",
        "Bloccare interrompe senza notifiche una connessione in attesa o accettata e le condivisioni in entrambe le direzioni. Per una connessione accettata, il percorso esistente tenta di restituire il lavoro condiviso ai proprietari; un errore non impedisce il blocco. Sbloccare rimuove solo il mio blocco: non ripristina connessione, condivisioni o assegnazioni e non rimuove il blocco dell’altra persona. Non vengono inviati messaggi né notifiche.",
    ),
    "zh-CN": (
        "我对此人的屏蔽",
        "屏蔽会静默断开待处理或已接受的连接，并撤销双向共享。对于已接受的连接，现有流程尝试将共享工单归还各自所有者；归还失败不阻止屏蔽。解除屏蔽仅移除我设置的屏蔽，不恢复连接、共享或分配，也不会移除对方的屏蔽。不发送消息或通知。",
    ),
}
