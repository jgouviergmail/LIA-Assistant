"""Exact generated-file browser transfer; requesting is never proof of saving."""

from src.core.i18n_types import Language

ASSET_DOWNLOAD_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Fichier généré à télécharger",
        "Après confirmation, le navigateur d’origine peut demander une seule fois ce fichier de votre galerie. Les droits, les métadonnées et l’identité du fichier sont recontrôlés. Aucun contenu ni chemin de stockage n’entre dans le chat. Une copie temporaire bornée protège le transfert. La demande ne prouve pas que le fichier a été reçu ou enregistré.",
    ),
    "en": (
        "Generated file to download",
        "After confirmation, the original browser may request this gallery file once. Permissions, metadata and file identity are checked again. No content or storage path enters chat. A bounded temporary copy protects the transfer. The request does not prove the file was received or saved.",
    ),
    "de": (
        "Generierte Datei zum Download",
        "Nach der Bestätigung kann der ursprüngliche Browser diese Galeriedatei einmal anfordern. Berechtigungen, Metadaten und Dateiidentität werden erneut geprüft. Inhalt und Speicherpfad gelangen nicht in den Chat. Eine begrenzte temporäre Kopie schützt die Übertragung. Die Anfrage bestätigt weder Empfang noch Speicherung.",
    ),
    "es": (
        "Archivo generado para descargar",
        "Tras confirmar, el navegador original puede solicitar este archivo de la galería una sola vez. Se comprueban de nuevo los permisos, metadatos e identidad. El contenido y la ruta de almacenamiento no entran en el chat. Una copia temporal limitada protege la transferencia. La solicitud no demuestra la recepción ni el guardado.",
    ),
    "it": (
        "File generato da scaricare",
        "Dopo la conferma, il browser originale può richiedere questo file della galleria una sola volta. Permessi, metadati e identità vengono ricontrollati. Contenuto e percorso di archiviazione non entrano nella chat. Una copia temporanea limitata protegge il trasferimento. La richiesta non prova la ricezione o il salvataggio.",
    ),
    "zh-CN": (
        "待下载的生成文件",
        "确认后，原始浏览器可以请求下载此图库文件一次。权限、元数据和文件身份将再次检查。文件内容和存储路径不会进入聊天。大小受限的临时副本用于保护传输。下载请求并不证明文件已经收到或保存。",
    ),
}
