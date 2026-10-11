"""Removing a source preserves documents and never requests provider work."""

from src.core.i18n_types import Language

SOURCE_UNLINK_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Source à retirer",
        "Cette confirmation retire uniquement le dossier Drive ou le label Gmail de cet espace. Les documents, leurs extraits indexés et leurs fichiers restent conservés. Aucune synchronisation, indexation ou suppression de contenu n’est demandée. Les droits, capacités, délai et périmètre sont recontrôlés ; une synchronisation en cours bloque le retrait. Un résultat de commit incertain ne déclenche aucune relance automatique.",
    ),
    "en": (
        "Source to unlink",
        "This confirmation removes only the Drive folder or Gmail label source from this space. Documents, indexed chunks and stored files are retained. No synchronization, indexing or content deletion is requested. Authority, capabilities, expiry and exact scope are checked again; a running sync blocks removal. An uncertain commit never triggers an automatic retry.",
    ),
    "de": (
        "Zu entfernende Quelle",
        "Diese Bestätigung entfernt nur den Drive-Ordner oder die Gmail-Label-Quelle aus diesem Bereich. Dokumente, indexierte Abschnitte und gespeicherte Dateien bleiben erhalten. Es wird keine Synchronisierung, Indexierung oder Inhaltslöschung angefordert. Berechtigungen, Funktionen, Ablaufzeit und genauer Umfang werden erneut geprüft; eine laufende Synchronisierung blockiert das Entfernen. Ein ungewisser Commit wird nicht automatisch wiederholt.",
    ),
    "es": (
        "Fuente que se desvinculará",
        "Esta confirmación retira solo la fuente de carpeta Drive o etiqueta Gmail de este espacio. Se conservan documentos, fragmentos indexados y archivos almacenados. No se solicita sincronización, indexación ni eliminación de contenido. Se vuelven a comprobar permisos, capacidades, caducidad y alcance exacto; una sincronización activa bloquea la retirada. Un commit incierto nunca se reintenta automáticamente.",
    ),
    "it": (
        "Fonte da scollegare",
        "Questa conferma rimuove solo la fonte cartella Drive o etichetta Gmail da questo spazio. Documenti, frammenti indicizzati e file archiviati vengono conservati. Non vengono richieste sincronizzazione, indicizzazione o eliminazione dei contenuti. Autorizzazioni, funzionalità, scadenza e ambito esatto vengono ricontrollati; una sincronizzazione in corso impedisce la rimozione. Un commit incerto non viene riprovato automaticamente.",
    ),
    "zh-CN": (
        "待解除关联的来源",
        "此确认仅从该空间解除 Drive 文件夹或 Gmail 标签来源的关联。文档、已索引的片段和存储的文件都会保留。不会请求同步、索引或删除内容。系统会再次检查权限、功能、有效期和准确范围；正在同步的来源无法移除。提交结果不确定时不会自动重试。",
    ),
}
