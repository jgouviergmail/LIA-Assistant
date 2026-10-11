"""Creation consent names the empty active source space and its actual scope."""

from src.core.i18n_types import Language

SPACE_CREATE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Espace de connaissance à créer",
        "La confirmation crée un seul espace personnel vide et actif, avec ce nom et ce descriptif. Aucun document n’est ajouté ni indexé et aucun fournisseur n’est appelé. L’activation permettra d’utiliser les futurs documents prêts dans les réponses. Le quota d’espaces et l’unicité du nom sont recontrôlés. Aucune création avant confirmation.",
    ),
    "en": (
        "Knowledge space to create",
        "Confirmation creates one empty active personal space with this name and description. No document is added or indexed and no provider is called. Activation permits future ready documents to enrich answers. The space quota and unique name are checked again. No creation before confirmation.",
    ),
    "de": (
        "Zu erstellender Wissensbereich",
        "Die Bestätigung erstellt genau einen leeren aktiven persönlichen Bereich mit diesem Namen und dieser Beschreibung. Kein Dokument wird hinzugefügt oder indexiert und kein Anbieter aufgerufen. Künftige fertige Dokumente können Antworten ergänzen. Bereichslimit und eindeutiger Name werden erneut geprüft. Keine Erstellung vor der Bestätigung.",
    ),
    "es": (
        "Espacio de conocimiento que se creará",
        "La confirmación crea un único espacio personal vacío y activo con este nombre y descripción. No se añade ni indexa ningún documento ni se llama a ningún proveedor. Los documentos futuros ya procesados podrán enriquecer las respuestas. Se comprueban de nuevo el límite de espacios y la unicidad del nombre. No se crea nada antes de confirmar.",
    ),
    "it": (
        "Spazio di conoscenza da creare",
        "La conferma crea un solo spazio personale vuoto e attivo con questo nome e descrizione. Nessun documento viene aggiunto o indicizzato e nessun fornitore viene chiamato. I futuri documenti pronti potranno arricchire le risposte. Il limite degli spazi e l’unicità del nome vengono ricontrollati. Nessuna creazione prima della conferma.",
    ),
    "zh-CN": (
        "待创建的知识空间",
        "确认后将创建一个具有此名称和说明的空白、已启用的个人空间。不会添加或索引任何文档，也不会调用供应商。今后准备就绪的文档可用于丰富回答。创建前将再次检查空间配额和名称唯一性。确认前不会创建。",
    ),
}
