"""Explicit destructive source scope and honest post-commit file cleanup."""

from src.core.i18n_types import Language

SOURCE_DELETE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Source et documents à supprimer",
        "Cette confirmation retire la source et supprime tous ses documents listés dans cet espace. Les originaux chez le fournisseur et les autres documents restent conservés. Vérifiez la liste avant de confirmer. Les fichiers ne sont nettoyés qu’après confirmation de la suppression en base ; un nettoyage restant à faire est signalé. Un résultat incertain ne sera pas relancé automatiquement.",
    ),
    "en": (
        "Source and documents to delete",
        "This confirmation removes the source and deletes all its listed documents from this space. Provider originals and other documents are retained. Check the list before confirming. Files are cleaned only after database deletion is acknowledged; pending cleanup is reported. An uncertain result is never automatically retried.",
    ),
    "de": (
        "Zu löschende Quelle und Dokumente",
        "Diese Bestätigung entfernt die Quelle und löscht alle ihre aufgeführten Dokumente aus diesem Bereich. Originale beim Anbieter und andere Dokumente bleiben erhalten. Prüfen Sie die Liste vor der Bestätigung. Dateien werden erst nach bestätigter Datenbanklöschung bereinigt; ausstehende Bereinigung wird angezeigt. Ein ungewisses Ergebnis wird nicht automatisch wiederholt.",
    ),
    "es": (
        "Fuente y documentos que se eliminarán",
        "Esta confirmación retira la fuente y elimina todos sus documentos enumerados de este espacio. Se conservan los originales del proveedor y los demás documentos. Revise la lista antes de confirmar. Los archivos solo se limpian tras confirmar la eliminación en la base de datos; se indica cualquier limpieza pendiente. Un resultado incierto nunca se reintenta automáticamente.",
    ),
    "it": (
        "Fonte e documenti da eliminare",
        "Questa conferma rimuove la fonte ed elimina tutti i suoi documenti elencati da questo spazio. Gli originali del fornitore e gli altri documenti restano conservati. Controllare l'elenco prima di confermare. I file vengono rimossi solo dopo la conferma dell'eliminazione nel database; eventuali pulizie in sospeso sono segnalate. Un risultato incerto non viene riprovato automaticamente.",
    ),
    "zh-CN": (
        "待删除的来源和文档",
        "此确认将移除来源，并从该空间删除其所有列出的文档。提供商处的原件及其他文档将保留。确认前请检查列表。只有数据库删除得到确认后才会清理文件；尚未完成的清理会明确显示。不确定的结果不会自动重试。",
    ),
}
