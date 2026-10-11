"""ZIP consent distinguishes original names, safe members, missing files and actual delivery."""

from src.core.i18n_types import Language

DOCUMENT_ARCHIVE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Documents à archiver",
        "Après confirmation, le navigateur d’origine peut demander une seule fois une archive ZIP des documents personnels affichés. Les noms d’entrée sont sécurisés et dédoublonnés ; les fichiers absents figurent dans un bilan. Les identités, droits, capacités et tailles sont recontrôlés. Les octets sont copiés temporairement après accord, sans contenu ni chemin dans le chat. Demander le téléchargement ne prouve ni réception ni enregistrement.",
    ),
    "en": (
        "Documents to archive",
        "After confirmation, the original browser may request a ZIP of the displayed personal documents once. Entry names are made safe and unique; missing files appear in a report. Identities, permissions, capabilities and sizes are checked again. Bytes are temporarily copied after approval, without content or paths in chat. Requesting a download proves neither receipt nor saving.",
    ),
    "de": (
        "Zu archivierende Dokumente",
        "Nach der Bestätigung kann der ursprüngliche Browser einmal ein ZIP der angezeigten persönlichen Dokumente anfordern. Eintragsnamen werden sicher und eindeutig; fehlende Dateien stehen im Bericht. Identitäten, Berechtigungen, Funktionen und Größen werden erneut geprüft. Bytes werden erst nach Zustimmung temporär kopiert, ohne Inhalte oder Pfade im Chat. Eine Download-Anfrage bestätigt weder Empfang noch Speicherung.",
    ),
    "es": (
        "Documentos que se archivarán",
        "Tras confirmar, el navegador original puede solicitar una sola vez un ZIP de los documentos personales mostrados. Los nombres de las entradas son seguros y únicos; un informe enumera los archivos ausentes. Se comprueban de nuevo identidades, permisos, capacidades y tamaños. Los bytes se copian temporalmente tras aprobar, sin contenido ni rutas en el chat. Solicitar la descarga no demuestra recepción ni almacenamiento.",
    ),
    "it": (
        "Documenti da archiviare",
        "Dopo la conferma, il browser originale può richiedere una sola volta uno ZIP dei documenti personali mostrati. I nomi delle voci sono sicuri e univoci; i file mancanti figurano in un rapporto. Identità, permessi, funzionalità e dimensioni vengono ricontrollati. I byte sono copiati temporaneamente dopo l’approvazione, senza contenuto o percorsi nella chat. Richiedere il download non prova ricezione né salvataggio.",
    ),
    "zh-CN": (
        "待归档的文档",
        "确认后，原始浏览器可请求一次所显示个人文档的 ZIP。条目名称会安全化并去重；缺失文件列在报告中。将再次检查身份、权限、功能和大小。字节仅在批准后临时复制，内容和路径不会进入聊天。请求下载不代表已接收或保存。",
    ),
}
