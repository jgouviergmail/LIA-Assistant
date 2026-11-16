"""A memories export imported from the chat: what the confirmation card says, in six languages."""

from src.core.i18n_types import Language

MEMORY_IMPORT_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Souvenirs à importer depuis le fichier joint",
        "Crée les souvenirs nouveaux de cet export, tous à la fois ou aucun. Un souvenir que tu as déjà est laissé tel quel ; les doublons du fichier et les entrées invalides sont comptés, jamais créés. Le calcul de leurs vecteurs est imputé à ton compte. Un fichier modifié depuis demande une nouvelle proposition.",
    ),
    "en": (
        "Memories to import from the attached file",
        "Creates the new memories of this export, all at once or none. A memory you already have is left as it is; duplicates inside the file and invalid entries are counted, never created. Computing their vectors is billed to your account. A file changed since needs a new proposal.",
    ),
    "de": (
        "Aus der angehängten Datei zu importierende Erinnerungen",
        "Legt die neuen Erinnerungen dieses Exports an, alle auf einmal oder keine. Eine Erinnerung, die du schon hast, bleibt unverändert; Duplikate in der Datei und ungültige Einträge werden gezählt, nie angelegt. Die Berechnung ihrer Vektoren wird deinem Konto berechnet. Eine inzwischen geänderte Datei braucht einen neuen Vorschlag.",
    ),
    "es": (
        "Recuerdos que importar del archivo adjunto",
        "Crea los recuerdos nuevos de esta exportación, todos a la vez o ninguno. Un recuerdo que ya tienes se deja tal cual; los duplicados del archivo y las entradas no válidas se cuentan, nunca se crean. El cálculo de sus vectores se carga a tu cuenta. Un archivo modificado desde entonces requiere una nueva propuesta.",
    ),
    "it": (
        "Ricordi da importare dal file allegato",
        "Crea i ricordi nuovi di questa esportazione, tutti insieme o nessuno. Un ricordo che hai già resta com'è; i duplicati nel file e le voci non valide vengono contati, mai creati. Il calcolo dei loro vettori è addebitato al tuo account. Un file modificato nel frattempo richiede una nuova proposta.",
    ),
    "zh-CN": (
        "从附件导入的记忆",
        "一次性创建此导出文件中的新记忆，要么全部创建，要么都不创建。你已有的记忆保持不变；文件内的重复项和无效条目只计数，从不创建。计算其向量的费用记入你的账户。此后被修改的文件需要重新提议。",
    ),
}
