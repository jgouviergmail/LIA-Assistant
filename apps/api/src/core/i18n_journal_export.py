"""Portability explicitly distinguishes the stored portrait from the authorized current one."""

from src.core.i18n_application import ApplicationExportCopy
from src.core.i18n_types import Language

JOURNAL_EXPORT_COPY: dict[Language, ApplicationExportCopy] = {
    "fr": ApplicationExportCopy(
        "Exporter toutes vos entrées actives et archivées. Le JSON inclut le portrait stocké, même ancien ou si l’apprentissage personnel est désactivé ; le CSV contient les entrées seules. Aucune génération payante. Après confirmation, le navigateur d’origine peut lancer une demande unique. Des données modifiées nécessitent un nouvel accord. LIA confirme la demande, pas l’enregistrement du fichier.",
        "Entrées du journal à exporter",
    ),
    "en": ApplicationExportCopy(
        "Export every active and archived entry. JSON includes the stored portrait, even if stale or personal learning is disabled; CSV contains entries only. No paid generation. After confirmation, the original browser may start one request. Changed data requires fresh approval. LIA confirms the request, not that the file was saved.",
        "Journal entries to export",
    ),
    "de": ApplicationExportCopy(
        "Alle aktiven und archivierten Einträge exportieren. JSON enthält das gespeicherte Porträt, auch wenn es veraltet oder persönliches Lernen deaktiviert ist; CSV enthält nur Einträge. Keine kostenpflichtige Generierung. Nach Bestätigung kann der ursprüngliche Browser eine Anfrage starten. Änderungen erfordern eine neue Zustimmung. LIA bestätigt die Anfrage, nicht die gespeicherte Datei.",
        "Zu exportierende Journaleinträge",
    ),
    "es": ApplicationExportCopy(
        "Exportar todas las entradas activas y archivadas. JSON incluye el retrato almacenado, aunque esté desactualizado o el aprendizaje personal esté desactivado; CSV contiene solo entradas. Sin generación de pago. Tras confirmar, el navegador original puede iniciar una solicitud única. Los cambios requieren nueva aprobación. LIA confirma la solicitud, no que el archivo se haya guardado.",
        "Entradas del diario que se exportarán",
    ),
    "it": ApplicationExportCopy(
        "Esportare tutte le voci attive e archiviate. JSON include il ritratto memorizzato, anche se obsoleto o se l’apprendimento personale è disattivato; CSV contiene solo le voci. Nessuna generazione a pagamento. Dopo la conferma, il browser originale può avviare una sola richiesta. Le modifiche richiedono un nuovo consenso. LIA conferma la richiesta, non il salvataggio del file.",
        "Voci del diario da esportare",
    ),
    "zh-CN": ApplicationExportCopy(
        "导出全部当前和已归档条目。JSON还包含已存储的画像，即使它已过时或个人学习已关闭；CSV仅包含条目。不会进行付费生成。确认后原浏览器可发起一次下载请求；数据变化需要重新批准。LIA确认的是请求，而非文件已保存。",
        "待导出的日志条目",
    ),
}
