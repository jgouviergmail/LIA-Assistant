"""An assignment to LIA permits later work and must be explicit in the creation consent."""

from src.core.i18n_types import Language

WORKBOARD_CREATE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Ticket à créer",
        "La confirmation crée exactement ce ticket et son affectation. Affecter le ticket à LIA permet son exécution ultérieure, dans le mode choisi et sous les quotas et coûts habituels ; le descriptif devient son brief. Le parent et la personne affectée sont recontrôlés. Aucune création ni exécution avant confirmation.",
    ),
    "en": (
        "Ticket to create",
        "Confirmation creates this exact ticket and assignment. Assigning it to LIA permits later execution in the chosen mode, under the usual quotas and costs; its description becomes the brief. The parent and assigned person are checked again. No creation or execution before confirmation.",
    ),
    "de": (
        "Zu erstellendes Ticket",
        "Die Bestätigung erstellt genau dieses Ticket und seine Zuweisung. Eine Zuweisung an LIA erlaubt eine spätere Ausführung im gewählten Modus mit den üblichen Kontingenten und Kosten; die Beschreibung wird zum Arbeitsauftrag. Übergeordnetes Ticket und zugewiesene Person werden erneut geprüft. Keine Erstellung oder Ausführung vor der Bestätigung.",
    ),
    "es": (
        "Ticket que se creará",
        "La confirmación crea exactamente este ticket y su asignación. Asignarlo a LIA permite ejecutarlo más adelante en el modo elegido, sujeto a las cuotas y costes habituales; la descripción será su encargo. Se verifican de nuevo el padre y la persona asignada. No se crea ni ejecuta antes de confirmar.",
    ),
    "it": (
        "Ticket da creare",
        "La conferma crea esattamente questo ticket e la sua assegnazione. Assegnarlo a LIA consente una successiva esecuzione nella modalità scelta, con le quote e i costi abituali; la descrizione diventa il suo incarico. Il ticket padre e la persona assegnata vengono ricontrollati. Nessuna creazione o esecuzione prima della conferma.",
    ),
    "zh-CN": (
        "待创建的工单",
        "确认后按所示配置创建此工单及分配。分配给 LIA 后，允许其按所选模式稍后执行，并适用通常的配额和费用；描述成为执行任务说明。将重新核验父工单和被分配人。确认前不会创建或执行。",
    ),
}
