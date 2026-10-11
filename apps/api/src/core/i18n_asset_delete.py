"""Exact generated-file deletion and uncertain physical cleanup are explicit."""

from src.core.i18n_types import Language

ASSET_DELETE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Fichiers générés à supprimer",
        "Cette confirmation supprime uniquement les fichiers listés de votre galerie. Vérifiez la sélection avant de confirmer. Les originaux chez le fournisseur et les autres fichiers restent conservés. Le compteur indique les éléments retirés de la galerie ; le nettoyage physique commence seulement après confirmation de la suppression en base. Un nettoyage encore nécessaire est signalé. Un résultat incertain ne sera pas relancé automatiquement.",
    ),
    "en": (
        "Generated files to delete",
        "This confirmation removes only the listed files from your gallery. Check the selection before confirming. Provider originals and other files are retained. The count states removed gallery records; physical cleanup begins only after database deletion is acknowledged. Pending cleanup is reported. An uncertain result is never automatically retried.",
    ),
    "de": (
        "Zu löschende generierte Dateien",
        "Diese Bestätigung entfernt nur die aufgeführten Dateien aus Ihrer Galerie. Prüfen Sie die Auswahl vor der Bestätigung. Originale beim Anbieter und andere Dateien bleiben erhalten. Der Zähler nennt entfernte Galerieeinträge; die physische Bereinigung beginnt erst nach bestätigter Datenbanklöschung. Ausstehende Bereinigung wird angezeigt. Ungewisse Ergebnisse werden nicht automatisch wiederholt.",
    ),
    "es": (
        "Archivos generados que se eliminarán",
        "Esta confirmación elimina de su galería únicamente los archivos enumerados. Revise la selección antes de confirmar. Se conservan los originales del proveedor y los demás archivos. El contador indica los registros retirados de la galería; la limpieza física empieza solo tras confirmar la eliminación en la base de datos. Se informa de cualquier limpieza pendiente. Los resultados inciertos no se reintentan automáticamente.",
    ),
    "it": (
        "File generati da eliminare",
        "Questa conferma rimuove dalla galleria solo i file elencati. Controllare la selezione prima di confermare. Gli originali del fornitore e gli altri file restano conservati. Il conteggio indica le voci rimosse dalla galleria; la pulizia fisica inizia solo dopo la conferma dell'eliminazione nel database. Eventuali pulizie in sospeso sono segnalate. I risultati incerti non vengono riprovati automaticamente.",
    ),
    "zh-CN": (
        "待删除的生成文件",
        "此确认仅从图库中移除所列文件。确认前请检查选择。提供商处的原件及其他文件将保留。计数表示移除的图库记录；只有数据库删除得到确认后才会开始物理清理。尚未完成的清理会明确显示。不确定的结果不会自动重试。",
    ),
}
