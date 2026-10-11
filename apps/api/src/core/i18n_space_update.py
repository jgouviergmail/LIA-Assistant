"""Consent explains exact metadata changes and the actual effect of space activation."""

from src.core.i18n_types import Language

SPACE_UPDATE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Espace de connaissance à modifier",
        "La confirmation applique uniquement les changements affichés à cet espace personnel. Un descriptif vide est effacé. L’activation permet aux documents prêts d’enrichir les réponses ; la désactivation conserve les documents et leur indexation. Aucun document n’est ajouté, supprimé ou réindexé et aucun fournisseur n’est appelé. Un état modifié entre-temps nécessite une nouvelle confirmation.",
    ),
    "en": (
        "Knowledge space to update",
        "Confirmation applies only the displayed changes to this personal space. An empty description is cleared. Activation lets ready documents enrich answers; deactivation preserves documents and their index. No document is added, deleted or reindexed and no provider is called. Source changes in the meantime require renewed confirmation.",
    ),
    "de": (
        "Zu ändernder Wissensbereich",
        "Die Bestätigung wendet nur die angezeigten Änderungen auf diesen persönlichen Bereich an. Eine leere Beschreibung wird entfernt. Die Aktivierung lässt fertige Dokumente Antworten ergänzen; die Deaktivierung erhält Dokumente und Index. Kein Dokument wird hinzugefügt, gelöscht oder neu indexiert und kein Anbieter aufgerufen. Zwischenzeitliche Änderungen erfordern eine erneute Bestätigung.",
    ),
    "es": (
        "Espacio de conocimiento que se modificará",
        "La confirmación aplica únicamente los cambios mostrados a este espacio personal. Una descripción vacía se elimina. La activación permite enriquecer las respuestas con documentos procesados; la desactivación conserva los documentos y su índice. No se añade, elimina ni reindexa ningún documento ni se llama a ningún proveedor. Los cambios posteriores requieren una nueva confirmación.",
    ),
    "it": (
        "Spazio di conoscenza da modificare",
        "La conferma applica solo le modifiche visualizzate a questo spazio personale. Una descrizione vuota viene rimossa. L’attivazione permette ai documenti pronti di arricchire le risposte; la disattivazione conserva documenti e indice. Nessun documento viene aggiunto, eliminato o reindicizzato e nessun fornitore viene chiamato. Le modifiche intervenute richiedono una nuova conferma.",
    ),
    "zh-CN": (
        "待修改的知识空间",
        "确认后仅将显示的更改应用到此个人空间。空白说明会被清除。启用后，准备就绪的文档可丰富回答；停用后仍保留文档及其索引。不会添加、删除或重新索引文档，也不会调用供应商。若期间源状态发生变化，需要重新确认。",
    ),
}
