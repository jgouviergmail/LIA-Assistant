"""The full saved-copy export reaches its original browser without entering the chat."""

from src.core.i18n_types import Language

BOOKMARK_DOWNLOAD_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Réponse enregistrée à télécharger",
        "La demande, la réponse complète et sa date sont exportées en Markdown dans le navigateur d’origine. Les extraits n’en limitent pas le contenu. Un changement exige une nouvelle confirmation. La demande de téléchargement ne prouve ni sa réception ni son enregistrement. Un résultat incertain n’est pas relancé automatiquement.",
    ),
    "en": (
        "Saved answer to download",
        "The complete request, answer and date export as Markdown in the original browser. Excerpts never truncate the file. Changes require new confirmation. Requesting a download does not prove reception or saving. Uncertain results are never automatically replayed.",
    ),
    "de": (
        "Gespeicherte Antwort zum Herunterladen",
        "Die vollständige Anfrage, Antwort und ihr Datum werden als Markdown im ursprünglichen Browser exportiert. Auszüge kürzen die Datei nicht. Änderungen erfordern eine neue Bestätigung. Eine Download-Anfrage bestätigt weder Empfang noch Speicherung. Ungewisse Ergebnisse werden nicht automatisch wiederholt.",
    ),
    "es": (
        "Respuesta guardada para descargar",
        "La solicitud, la respuesta completa y su fecha se exportan como Markdown en el navegador original. Los extractos no recortan el archivo. Los cambios requieren nueva confirmación. Solicitar una descarga no acredita recepción ni guardado. Los resultados inciertos no se repiten automáticamente.",
    ),
    "it": (
        "Risposta salvata da scaricare",
        "La richiesta, la risposta completa e la data vengono esportate in Markdown nel browser originale. Gli estratti non limitano il file. Le modifiche richiedono una nuova conferma. Richiedere il download non conferma ricezione o salvataggio. I risultati incerti non vengono ripetuti automaticamente.",
    ),
    "zh-CN": (
        "待下载的已保存回答",
        "完整请求、回答及其日期将以 Markdown 导出到原始浏览器。摘录不会截断文件。任何变化都需要重新确认。发起下载不证明已经接收或保存。不确定的结果不会自动重试。",
    ),
}
