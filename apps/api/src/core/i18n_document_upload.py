"""Browser-selected bytes require their own explicit confirmation after destination approval."""

from src.core.i18n_types import Language

DOCUMENT_UPLOAD_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Document à importer",
        "Après cette confirmation, choisis un fichier dans le navigateur d’origine puis confirme son nom, sa taille et l’espace de destination avant l’envoi. Les limites, droits, capacités et délai sont recontrôlés. L’indexation asynchrone utilise les quotas de la plateforme et peut engendrer des coûts ; ses tokens et coûts réels sont consultables dans l’espace. Un import accepté ne signifie pas une indexation terminée. Un espace inactif reste exclu de la recherche. Aucun contenu ni chemin de stockage n’entre dans le chat. Un résultat incertain ne déclenche aucune relance automatique.",
    ),
    "en": (
        "Document to import",
        "After this confirmation, choose a file in the original browser and confirm its name, size and destination space before sending it. Limits, permissions, capabilities and expiry are checked again. Asynchronous indexing uses platform quotas and may incur costs; actual tokens and costs are visible in the space. An accepted upload does not mean completed indexing. An inactive space remains excluded from retrieval. No file content or storage path enters chat. Uncertain completion never triggers an automatic retry.",
    ),
    "de": (
        "Zu importierendes Dokument",
        "Wähle nach dieser Bestätigung eine Datei im ursprünglichen Browser und bestätige vor dem Senden Name, Größe und Zielbereich. Grenzen, Berechtigungen, Funktionen und Ablaufzeit werden erneut geprüft. Die asynchrone Indexierung nutzt Plattformkontingente und kann Kosten verursachen; tatsächliche Tokens und Kosten stehen im Bereich. Ein angenommener Upload bedeutet keine abgeschlossene Indexierung. Inaktive Bereiche bleiben von der Suche ausgeschlossen. Inhalt und Speicherpfad gelangen nicht in den Chat. Ungewisse Ergebnisse werden nicht automatisch wiederholt.",
    ),
    "es": (
        "Documento que se importará",
        "Tras esta confirmación, elige un archivo en el navegador original y confirma su nombre, tamaño y espacio de destino antes de enviarlo. Se comprueban límites, permisos, capacidades y caducidad. La indexación asíncrona usa las cuotas de la plataforma y puede generar costes; los tokens y costes reales se consultan en el espacio. Una carga aceptada no significa que la indexación haya terminado. Un espacio inactivo sigue excluido de las búsquedas. El contenido y la ruta de almacenamiento no entran en el chat. Un resultado incierto nunca se reintenta automáticamente.",
    ),
    "it": (
        "Documento da importare",
        "Dopo questa conferma, scegli un file nel browser originale e conferma nome, dimensione e spazio di destinazione prima dell’invio. Limiti, autorizzazioni, funzionalità e scadenza vengono ricontrollati. L’indicizzazione asincrona usa le quote della piattaforma e può generare costi; token e costi effettivi sono visibili nello spazio. Un caricamento accettato non significa indicizzazione completata. Uno spazio inattivo rimane escluso dalla ricerca. Contenuto e percorso di archiviazione non entrano nella chat. Un risultato incerto non viene riprovato automaticamente.",
    ),
    "zh-CN": (
        "待导入的文档",
        "确认后，请在原始浏览器中选择文件，并在发送前确认文件名、大小和目标空间。系统会再次检查限制、权限、功能和有效期。异步索引使用平台配额并可能产生费用；实际令牌用量和费用可在空间中查看。上传已接受不代表索引已完成。未启用的空间仍不参与检索。文件内容和存储路径不会进入聊天。结果不确定时不会自动重试。",
    ),
}
