"""Subtree loss and in-flight work are explicit consequences of deletion."""

from src.core.i18n_types import Language

WORKBOARD_DELETE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Tickets à supprimer",
        "La confirmation supprime définitivement les tickets nommés, leurs commentaires et leur historique. Toute modification du périmètre impose une nouvelle proposition. La suppression du ticket ne garantit pas l’arrêt d’une action déjà en cours ; le nombre de runs actifs est indiqué.",
    ),
    "en": (
        "Tickets to delete",
        "Confirmation permanently removes the named tickets, their comments and history. A changed scope requires a new proposal. Deleting a ticket does not guarantee stopping an action already in flight; the active-run count is shown.",
    ),
    "de": (
        "Zu löschende Tickets",
        "Die Bestätigung entfernt die genannten Tickets, ihre Kommentare und den Verlauf endgültig. Ein geänderter Umfang erfordert einen neuen Vorschlag. Das Löschen stoppt eine bereits laufende Aktion nicht garantiert; die Anzahl aktiver Läufe wird angezeigt.",
    ),
    "es": (
        "Tickets que se eliminarán",
        "La confirmación elimina definitivamente los tickets indicados, sus comentarios y su historial. Un cambio de alcance exige una nueva propuesta. Eliminar un ticket no garantiza detener una acción ya en curso; se muestra el número de ejecuciones activas.",
    ),
    "it": (
        "Ticket da eliminare",
        "La conferma elimina definitivamente i ticket indicati, i commenti e la cronologia. Un ambito cambiato richiede una nuova proposta. Eliminare un ticket non garantisce l’arresto di un’azione già in corso; viene mostrato il numero di esecuzioni attive.",
    ),
    "zh-CN": (
        "将删除的工单",
        "确认会永久删除列出的工单、评论和历史记录。范围有变化时必须重新提出确认。删除工单不能保证停止已在执行的操作；预览会显示当前运行数量。",
    ),
}
