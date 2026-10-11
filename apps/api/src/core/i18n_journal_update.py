"""Effective evidence rules and paid preparation are explicit in edit approval."""

from src.core.i18n_types import Language

JOURNAL_UPDATE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Entrée du journal",
        "Les valeurs finales affichées suivent les règles de preuve du service : le contenu ou le niveau modifié renouvelle la révision et ses compteurs de preuve. La confiance peut être plafonnée ; aucune preuve n’est inventée. Un changement de titre, contenu ou mots-clés peut lancer jusqu’à deux embeddings plateforme après confirmation, sous quotas et hors verrous. Le portrait suit l’invalidation du service, sans régénération. Les compteurs de consultation et l’horodatage sont relus après écriture.",
    ),
    "en": (
        "Journal entry",
        "Displayed final values follow source evidence rules: changed content or level renews the rule revision and its evidence counters. Confidence may be capped; no evidence is invented. Changed title, content or hints may start up to two platform embeddings after confirmation, under quotas and outside locks. Portrait invalidation follows the source without regeneration. Exposure counters and timestamp are reread after writing.",
    ),
    "de": (
        "Journaleintrag",
        "Die Endwerte folgen den Belegregeln: geänderter Inhalt oder Ebene erneuert Revision und Belegzähler. Vertrauen kann begrenzt werden; Belege werden nicht erfunden. Titel, Inhalt oder Stichwörter können nach Bestätigung bis zu zwei Plattform-Embeddings unter Quoten und ohne Sperren auslösen. Das Porträt folgt der Quellinvalidierung ohne Neugenerierung. Nutzungszähler und Zeitstempel werden danach neu gelesen.",
    ),
    "es": (
        "Entrada del diario",
        "Los valores finales siguen las reglas de prueba: cambiar contenido o nivel renueva la revisión y sus contadores. La confianza puede limitarse; no se inventan pruebas. Cambiar título, contenido o palabras clave puede iniciar hasta dos embeddings de plataforma tras confirmar, con cuotas y sin bloqueos. El retrato sigue la invalidación del servicio sin regenerarse. Los contadores de uso y la fecha se releen después.",
    ),
    "it": (
        "Voce del diario",
        "I valori finali seguono le regole di prova: contenuto o livello modificati rinnovano revisione e contatori. La fiducia può essere limitata; nessuna prova è inventata. Titolo, contenuto o parole chiave possono avviare fino a due embedding di piattaforma dopo conferma, con quote e senza blocchi. Il ritratto segue l’invalidazione del servizio senza rigenerazione. Contatori d’uso e data vengono riletti dopo.",
    ),
    "zh-CN": (
        "日志条目",
        "显示的最终值遵循服务证据规则：内容或层级变更会更新规则版本及其证据计数。置信度可能受到限制，不虚构证据。确认后，标题、内容或关键词变更可能在配额限制及无锁状态下触发最多两次平台嵌入。按服务规则使画像失效但不重新生成。写入后重新读取使用计数和时间。",
    ),
}
