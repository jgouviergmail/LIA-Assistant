"""Explicit whole-source changes, resource costs and asynchronous sync acceptance."""

from src.core.i18n_types import Language

SOURCE_SYNC_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Source à synchroniser",
        "Cette confirmation lance la synchronisation de cette source dans cet espace : import des nouveaux contenus, remplacement des versions modifiées et retrait des contenus absents après une liste complète. Les quotas du fournisseur et des coûts d’indexation peuvent s’appliquer, dans les limites affichées. L’acceptation ne signifie pas que l’indexation est terminée : consultez ensuite les états des documents. Une liste incomplète ne justifie aucun retrait. Un résultat incertain ou un travail interrompu ne sera pas relancé automatiquement ; une nouvelle synchronisation nécessite une nouvelle confirmation.",
    ),
    "en": (
        "Source to synchronize",
        "This confirmation starts synchronization of this source into this space: importing new content, replacing changed versions and removing content absent from a complete listing. Provider quotas and indexing costs can apply within the displayed bounds. Acceptance does not mean indexing has finished: check document statuses afterward. An incomplete listing never justifies removal. Uncertain results or interrupted work are not automatically retried; a new synchronization needs fresh confirmation.",
    ),
    "de": (
        "Zu synchronisierende Quelle",
        "Diese Bestätigung startet die Synchronisierung dieser Quelle mit diesem Bereich: neue Inhalte importieren, geänderte Versionen ersetzen und Inhalte entfernen, die in einer vollständigen Liste fehlen. Anbieterkontingente und Indexierungskosten können innerhalb der angezeigten Grenzen anfallen. Die Annahme bedeutet nicht, dass die Indexierung abgeschlossen ist: Prüfen Sie danach die Dokumentzustände. Eine unvollständige Liste rechtfertigt keine Entfernung. Ungewisse Ergebnisse oder unterbrochene Arbeit werden nicht automatisch wiederholt; eine neue Synchronisierung benötigt eine neue Bestätigung.",
    ),
    "es": (
        "Fuente que se sincronizará",
        "Esta confirmación inicia la sincronización de esta fuente con este espacio: importar contenido nuevo, sustituir versiones modificadas y retirar contenido ausente de una lista completa. Pueden aplicarse cuotas del proveedor y costes de indexación dentro de los límites mostrados. La aceptación no significa que la indexación haya terminado: consulte después el estado de los documentos. Una lista incompleta nunca justifica retiradas. Los resultados inciertos o trabajos interrumpidos no se reintentan automáticamente; una nueva sincronización requiere otra confirmación.",
    ),
    "it": (
        "Fonte da sincronizzare",
        "Questa conferma avvia la sincronizzazione di questa fonte nello spazio: importare nuovi contenuti, sostituire versioni modificate e rimuovere contenuti assenti da un elenco completo. Possono applicarsi quote del fornitore e costi di indicizzazione entro i limiti mostrati. L'accettazione non significa che l'indicizzazione sia terminata: controllare poi lo stato dei documenti. Un elenco incompleto non giustifica rimozioni. Risultati incerti o lavori interrotti non vengono riprovati automaticamente; una nuova sincronizzazione richiede una nuova conferma.",
    ),
    "zh-CN": (
        "待同步的来源",
        "此确认将在该空间同步此来源：导入新内容、替换已修改的版本，并移除完整列表中已不存在的内容。在显示的限制内，可能消耗提供商配额并产生索引费用。接受任务不意味着索引已完成，请随后查看文档状态。不完整的列表不能作为移除依据。不确定的结果或中断的任务不会自动重试；再次同步需要重新确认。",
    ),
}
