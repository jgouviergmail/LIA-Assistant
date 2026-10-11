"""Deletion consent distinguishes local records, remote originals and post-commit cleanup."""

from src.core.i18n_types import Language

SPACE_DELETE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Espace de connaissance à supprimer",
        "La confirmation supprime cet espace personnel, les documents et index locaux affichés ainsi que ses liens de synchronisation. Les fichiers originaux de Drive et les messages Gmail sont conservés. La suppression en base précède le nettoyage des fichiers locaux ; un nettoyage incomplet est signalé. Une indexation ou synchronisation en cours est refusée. Les espaces gérés par les réunions ou les réponses conservées restent protégés. Un changement entre-temps nécessite une nouvelle confirmation.",
    ),
    "en": (
        "Knowledge space to delete",
        "Confirmation deletes this personal space, the displayed local documents and indexes, and its synchronization links. Original Drive files and Gmail messages remain. Database deletion precedes local file cleanup; incomplete cleanup is reported. Active indexing or synchronization is refused. Spaces managed by meetings or kept answers stay protected. Source changes in the meantime require renewed confirmation.",
    ),
    "de": (
        "Zu löschender Wissensbereich",
        "Die Bestätigung löscht diesen persönlichen Bereich, die angezeigten lokalen Dokumente und Indizes sowie seine Synchronisierungsverknüpfungen. Originaldateien in Drive und Gmail-Nachrichten bleiben erhalten. Nach der Datenbanklöschung werden lokale Dateien bereinigt; eine unvollständige Bereinigung wird gemeldet. Laufende Indexierung oder Synchronisierung wird abgelehnt. Von Besprechungen oder gespeicherten Antworten verwaltete Bereiche bleiben geschützt. Zwischenzeitliche Änderungen erfordern eine erneute Bestätigung.",
    ),
    "es": (
        "Espacio de conocimiento que se eliminará",
        "La confirmación elimina este espacio personal, los documentos e índices locales mostrados y sus enlaces de sincronización. Los archivos originales de Drive y los mensajes Gmail se conservan. Tras la eliminación en la base de datos se limpian los archivos locales; una limpieza incompleta se indica. Se rechaza la indexación o sincronización en curso. Los espacios gestionados por reuniones o respuestas conservadas siguen protegidos. Los cambios posteriores requieren una nueva confirmación.",
    ),
    "it": (
        "Spazio di conoscenza da eliminare",
        "La conferma elimina questo spazio personale, i documenti e gli indici locali mostrati e i collegamenti di sincronizzazione. I file originali di Drive e i messaggi Gmail restano. Dopo l’eliminazione nel database vengono rimossi i file locali; una pulizia incompleta viene segnalata. L’indicizzazione o sincronizzazione in corso viene rifiutata. Gli spazi gestiti da riunioni o risposte conservate restano protetti. Le modifiche intervenute richiedono una nuova conferma.",
    ),
    "zh-CN": (
        "待删除的知识空间",
        "确认后将删除此个人空间、所显示的本地文档和索引，以及同步链接。Drive 原始文件和 Gmail 邮件会保留。数据库删除后才清理本地文件；未完成的清理会明确报告。索引或同步进行中时会拒绝操作。会议及已保留回答管理的空间仍受保护。若期间源状态变化，需要重新确认。",
    ),
}
