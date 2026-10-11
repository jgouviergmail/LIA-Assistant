"""Current-memory export scope is distinct from the supersession trail."""

from src.core.i18n_application import ApplicationExportCopy
from src.core.i18n_types import Language

MEMORY_EXPORT_COPY: dict[Language, ApplicationExportCopy] = {
    "fr": ApplicationExportCopy(
        "Exporter toutes vos mémoires actuelles au format indiqué, y compris celles épinglées. Les anciennes versions remplacées sont exclues. Les scores éventuels correspondent à la date affichée. Le navigateur d’origine lancera une demande après confirmation ; des données modifiées nécessitent un nouvel accord. LIA confirme la demande, pas le fichier enregistré sur votre appareil.",
        "Mémoires actuelles à exporter",
    ),
    "en": ApplicationExportCopy(
        "Export all your current memories in the displayed format, including pinned memories. Superseded versions are excluded. Any scores are observed at the displayed date. The original browser starts one request after confirmation; changed data requires fresh approval. LIA confirms the request, not a file saved to your device.",
        "Current memories to export",
    ),
    "de": ApplicationExportCopy(
        "Alle aktuellen Erinnerungen im angezeigten Format exportieren, einschließlich angehefteter Erinnerungen. Ersetzte Versionen sind ausgeschlossen. Werte gelten zum angezeigten Zeitpunkt. Nach Bestätigung startet der ursprüngliche Browser eine Anfrage; geänderte Daten benötigen eine neue Zustimmung. LIA bestätigt die Anfrage, nicht die gespeicherte Datei.",
        "Aktuelle Erinnerungen zum Export",
    ),
    "es": ApplicationExportCopy(
        "Exportar todos tus recuerdos actuales en el formato indicado, incluidos los fijados. Se excluyen las versiones sustituidas. Las puntuaciones corresponden a la fecha mostrada. El navegador original inicia una solicitud tras confirmar; los datos modificados requieren otra aprobación. LIA confirma la solicitud, no el archivo guardado en tu dispositivo.",
        "Recuerdos actuales que se exportarán",
    ),
    "it": ApplicationExportCopy(
        "Esportare tutti i ricordi attuali nel formato indicato, inclusi quelli fissati. Le versioni sostituite sono escluse. I punteggi corrispondono alla data mostrata. Il browser originale avvia una richiesta dopo la conferma; i dati modificati richiedono un nuovo consenso. LIA conferma la richiesta, non il file salvato sul dispositivo.",
        "Ricordi attuali da esportare",
    ),
    "zh-CN": ApplicationExportCopy(
        "按显示的格式导出您的全部当前记忆，包括已固定的记忆。被替代的旧版本不在其中。评分以所示时间为准。确认后，原浏览器发起一次请求；数据变化时需要重新批准。LIA可确认请求，但无法确认文件已保存到设备。",
        "待导出的当前记忆",
    ),
}
