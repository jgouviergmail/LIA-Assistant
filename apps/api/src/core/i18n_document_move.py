"""Literal document movement approval explains capacity, retrieval and interrupted cleanup."""

from src.core.i18n_types import Language

DOCUMENT_MOVE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Documents à déplacer",
        "La confirmation déplace uniquement les documents affichés et leurs fragments vers l’espace personnel indiqué. Les autres documents restent en place. La capacité, les documents et les fichiers sont revérifiés ; un changement exige un nouvel accord. Les documents gérés par Drive/Gmail/réunion ou les réponses conservées se déplacent depuis leur fonction dédiée. Un espace cible inactif retire ces documents de la recherche de LIA. Les fichiers déjà absents restent absents. La préparation utilise de l’espace disque temporaire ; l’original reste disponible si le résultat est indéterminé. Son nettoyage peut rester en attente après déplacement. Aucun appel fournisseur/modèle ou réindexation ; pas de remboursement des coûts passés. Aucun rejeu automatique d’un résultat indéterminé.",
    ),
    "en": (
        "Documents to move",
        "Confirmation moves only the displayed documents and indexed chunks into the named personal space. Other documents remain. Capacity, documents and files are checked again; changes require new approval. Drive/Gmail/meeting and saved-answer projections are managed through their owning features. An inactive destination removes these documents from LIA retrieval. Already missing files remain missing. Preparation uses temporary disk space; originals remain available if completion is uncertain. Original cleanup may remain pending after the move. No provider/model call or reindexing; no refund of past usage. Uncertain completion is never automatically retried.",
    ),
    "de": (
        "Zu verschiebende Dokumente",
        "Die Bestätigung verschiebt nur die angezeigten Dokumente und indexierten Textabschnitte in den benannten persönlichen Bereich. Andere Dokumente bleiben. Kapazität, Dokumente und Dateien werden erneut geprüft; Änderungen erfordern neue Zustimmung. Drive/Gmail/Besprechungen und gespeicherte Antworten werden über ihre jeweilige Funktion verwaltet. Ein inaktives Ziel nimmt diese Dokumente aus der LIA-Suche. Fehlende Dateien bleiben fehlend. Die Vorbereitung benötigt temporären Speicher; bei ungewissem Ergebnis bleiben Originale verfügbar. Ihre Bereinigung kann ausstehen. Kein Anbieter-/Modellaufruf oder Neuindexierung; frühere Kosten werden nicht erstattet. Ungewisse Ergebnisse werden nie automatisch wiederholt.",
    ),
    "es": (
        "Documentos que se moverán",
        "La confirmación mueve solo los documentos mostrados y sus fragmentos indexados al espacio personal indicado. Los otros documentos permanecen. Se comprueban otra vez capacidad, documentos y archivos; los cambios requieren otra aprobación. Drive/Gmail/reuniones y respuestas guardadas se gestionan desde sus funciones. Un destino inactivo excluye estos documentos de las búsquedas de LIA. Los archivos ausentes siguen ausentes. La preparación usa disco temporal; los originales se conservan si el resultado es incierto. Su limpieza puede quedar pendiente. Sin llamadas al proveedor/modelo ni reindexación; sin reembolso del consumo previo. No se reintentan automáticamente resultados inciertos.",
    ),
    "it": (
        "Documenti da spostare",
        "La conferma sposta solo i documenti mostrati e i frammenti indicizzati nello spazio personale indicato. Gli altri documenti restano. Capacità, documenti e file vengono ricontrollati; le modifiche richiedono una nuova approvazione. Drive/Gmail/riunioni e risposte conservate si gestiscono dalle rispettive funzioni. Una destinazione inattiva esclude questi documenti dalle ricerche di LIA. I file mancanti restano mancanti. La preparazione usa disco temporaneo; gli originali restano disponibili se il risultato è incerto. La loro pulizia può restare in attesa. Nessuna chiamata a provider/modello o reindicizzazione; nessun rimborso del consumo passato. Nessuna ripetizione automatica dei risultati incerti.",
    ),
    "zh-CN": (
        "待移动的文档",
        "确认仅将所显示的文档及索引片段移至指定的个人知识空间，其他文档保持原位。将重新检查容量、文档和文件，发生变化须重新批准。Drive/Gmail/会议及已保存回答的投影须通过相应功能管理。停用的目标空间使这些文档不再参与LIA检索。缺失的文件仍然缺失。准备过程需要临时磁盘空间；结果不确定时保留原文件，移动后原文件清理可能仍待处理。不调用供应商或模型，不重新建立索引，不退还既往费用。结果不确定时绝不自动重试。",
    ),
}
