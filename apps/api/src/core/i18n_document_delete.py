"""Document removal names the exact local scope and the limits of source/file cleanup."""

from src.core.i18n_types import Language

DOCUMENT_DELETE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Documents à supprimer",
        "La confirmation supprime uniquement les documents personnels affichés et leurs fragments indexés. L’espace et les documents voisins restent présents. Les documents et fichiers sont revérifiés ; un changement exige un nouvel accord. Les réponses conservées se suppriment depuis leur enregistrement. Les originaux Drive/Gmail/réunion et les sources liées restent présents et peuvent recréer leur projection lors d’une synchronisation. Les fichiers locaux sont nettoyés après la suppression ; ce nettoyage peut rester en attente en cas de coupure. Aucun appel modèle ni indexation ; les coûts passés ne sont pas remboursés. Un résultat indéterminé n’est jamais rejoué automatiquement.",
    ),
    "en": (
        "Documents to delete",
        "Confirmation removes only the displayed personal documents and their indexed chunks. The space and neighboring documents remain. Documents and files are checked again; changes require new approval. Saved answers must be removed through their own record. Drive/Gmail/meeting originals and linked sources remain and may recreate projections during synchronization. Local files are cleaned after deletion; cleanup may remain pending if interrupted. No model call or indexing; past usage is not refunded. Unknown completion is never automatically retried.",
    ),
    "de": (
        "Zu löschende Dokumente",
        "Die Bestätigung entfernt nur die angezeigten persönlichen Dokumente und ihre indexierten Textabschnitte. Bereich und andere Dokumente bleiben erhalten. Dokumente und Dateien werden erneut geprüft; Änderungen erfordern neue Zustimmung. Gespeicherte Antworten werden über ihren eigenen Datensatz entfernt. Drive/Gmail/Besprechungsoriginale und verknüpfte Quellen bleiben und können Projektionen bei einer Synchronisierung neu erzeugen. Lokale Dateien werden nach der Löschung bereinigt; bei einer Unterbrechung kann die Bereinigung ausstehen. Kein Modellaufruf oder Indexierung; frühere Kosten werden nicht erstattet. Ein unbestimmtes Ergebnis wird nie automatisch wiederholt.",
    ),
    "es": (
        "Documentos que se eliminarán",
        "La confirmación elimina solo los documentos personales mostrados y sus fragmentos indexados. El espacio y los otros documentos permanecen. Se comprueban de nuevo documentos y archivos; los cambios requieren otra aprobación. Las respuestas guardadas se eliminan desde su propio registro. Los originales de Drive/Gmail/reuniones y las fuentes vinculadas permanecen y pueden recrear proyecciones al sincronizar. Los archivos locales se limpian tras la eliminación; la limpieza puede quedar pendiente si se interrumpe. Sin llamadas al modelo ni indexación; no se reembolsa el consumo anterior. Un resultado indeterminado nunca se reintenta automáticamente.",
    ),
    "it": (
        "Documenti da eliminare",
        "La conferma rimuove solo i documenti personali mostrati e i frammenti indicizzati. Lo spazio e gli altri documenti restano presenti. Documenti e file vengono ricontrollati; le modifiche richiedono una nuova approvazione. Le risposte conservate si rimuovono dal proprio record. Gli originali Drive/Gmail/riunioni e le fonti collegate restano e possono ricreare le proiezioni durante la sincronizzazione. I file locali vengono rimossi dopo la cancellazione; la pulizia può restare in attesa se interrotta. Nessuna chiamata al modello o indicizzazione; i costi precedenti non vengono rimborsati. Un esito indeterminato non viene mai ripetuto automaticamente.",
    ),
    "zh-CN": (
        "待删除的文档",
        "确认仅删除所显示的个人文档及其索引片段。知识空间和其他文档保留。将再次检查文档和文件；发生变化须重新批准。已保存的回答须从其自身记录删除。Drive/Gmail/会议原件及关联来源保留，同步时可能重新创建投影。删除后清理本地文件；清理中断时可能仍待处理。不调用模型或建立索引；既往使用费用不退还。结果不确定时绝不自动重试。",
    ),
}
