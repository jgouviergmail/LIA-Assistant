"""Exact file consent names the browser transfer and never claims a saved file."""

from src.core.i18n_types import Language

DOCUMENT_DOWNLOAD_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Document à télécharger",
        "Après confirmation, le navigateur d’origine peut demander une seule fois le document personnel affiché. Son identité, les droits et les capacités sont recontrôlés. Aucun contenu ni chemin de stockage n’entre dans le chat. Le transfert utilise une copie temporaire bornée ; demander le téléchargement ne prouve pas que le fichier a été reçu ou enregistré.",
    ),
    "en": (
        "Document to download",
        "After confirmation, the original browser may request the displayed personal document once. Its identity, permissions and capabilities are checked again. No content or storage path enters chat. Transfer uses a bounded temporary copy; requesting a download does not prove the file was received or saved.",
    ),
    "de": (
        "Herunterzuladendes Dokument",
        "Nach der Bestätigung kann der ursprüngliche Browser das angezeigte persönliche Dokument einmal anfordern. Identität, Berechtigungen und Funktionen werden erneut geprüft. Inhalt und Speicherpfad gelangen nicht in den Chat. Die Übertragung verwendet eine begrenzte temporäre Kopie; eine Download-Anfrage bestätigt weder Empfang noch Speicherung.",
    ),
    "es": (
        "Documento que se descargará",
        "Tras confirmar, el navegador original puede solicitar una sola vez el documento personal mostrado. Se comprueban de nuevo su identidad, los permisos y las capacidades. El contenido y la ruta de almacenamiento no entran en el chat. La transferencia usa una copia temporal limitada; solicitar la descarga no demuestra que el archivo se haya recibido o guardado.",
    ),
    "it": (
        "Documento da scaricare",
        "Dopo la conferma, il browser originale può richiedere una sola volta il documento personale mostrato. Identità, permessi e funzionalità vengono ricontrollati. Contenuto e percorso di archiviazione non entrano nella chat. Il trasferimento usa una copia temporanea limitata; richiedere il download non prova che il file sia stato ricevuto o salvato.",
    ),
    "zh-CN": (
        "待下载的文档",
        "确认后，原始浏览器可请求下载一次所显示的个人文档。将再次检查文件身份、权限和功能开关。文档内容和存储路径不会进入聊天。传输使用大小受限的临时副本；请求下载并不代表文件已收到或保存。",
    ),
}
