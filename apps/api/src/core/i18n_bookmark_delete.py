"""Exact saved-copy destruction and pending cleanup are disclosed in every supported language."""

from src.core.i18n_types import Language

BOOKMARK_DELETE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Réponse enregistrée à supprimer",
        "La copie enregistrée et sa projection dans l’espace de connaissances sont supprimées ensemble. Les extraits identifient la copie complète. La réponse originale dans la conversation est conservée. Tout changement exige une nouvelle confirmation. Le nettoyage du fichier suit la validation certaine de la suppression ; un fichier modifié est conservé et un nettoyage en attente est signalé. Un résultat incertain n’est pas relancé automatiquement.",
    ),
    "en": (
        "Saved answer to delete",
        "The complete saved copy and its knowledge-space projection are removed together. Excerpts identify the complete copy. The original conversation answer is preserved. Any change requires new confirmation. File cleanup follows known deletion acknowledgement; changed files are retained and pending cleanup is reported. Uncertain results are never automatically replayed.",
    ),
    "de": (
        "Zu löschende gespeicherte Antwort",
        "Die vollständige gespeicherte Kopie und ihre Wissensraum-Projektion werden gemeinsam gelöscht. Auszüge kennzeichnen die vollständige Kopie. Die ursprüngliche Antwort im Gespräch bleibt erhalten. Änderungen erfordern eine neue Bestätigung. Die Dateibereinigung folgt erst auf die sichere Löschbestätigung; geänderte Dateien bleiben erhalten und ausstehende Bereinigung wird gemeldet. Ungewisse Ergebnisse werden nicht automatisch wiederholt.",
    ),
    "es": (
        "Respuesta guardada para eliminar",
        "La copia completa guardada y su proyección en el espacio de conocimiento se eliminan juntas. Los extractos identifican la copia completa. Se conserva la respuesta original de la conversación. Cualquier cambio requiere una nueva confirmación. El archivo se limpia tras confirmar la eliminación; los archivos modificados se conservan y se informa de la limpieza pendiente. Los resultados inciertos no se repiten automáticamente.",
    ),
    "it": (
        "Risposta salvata da eliminare",
        "La copia completa salvata e la sua proiezione nello spazio di conoscenza vengono eliminate insieme. Gli estratti identificano la copia completa. La risposta originale nella conversazione viene conservata. Ogni modifica richiede una nuova conferma. Il file viene rimosso dopo la conferma certa dell’eliminazione; i file modificati vengono conservati e la pulizia in attesa viene segnalata. I risultati incerti non vengono ripetuti automaticamente.",
    ),
    "zh-CN": (
        "待删除的已保存回答",
        "已保存的完整副本及其知识空间投影将一并删除。摘录用于识别完整副本，对话中的原始回答会保留。任何变化都需要重新确认。只有确定删除成功后才清理文件；已变化的文件会保留，待清理状态会明确报告。不确定的结果不会自动重试。",
    ),
}
