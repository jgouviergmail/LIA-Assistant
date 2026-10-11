"""Paid debrief approval names the scoped reads, reuse and spend consequences."""

from src.core.i18n_types import Language

RELATION_DEBRIEF_BUILD_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Génération du débrief relationnel",
        "LIA lit les sources sélectionnées pour cette relation et peut générer une synthèse payante. Les plafonds du compte et de la plateforme s’appliquent. Sans changement des données, le texte existant peut être réutilisé. Une génération échouée conserve le texte précédent lorsqu’il existe. Confirmer autorise cette tentative uniquement.",
    ),
    "en": (
        "Relationship debrief generation",
        "LIA reads the selected sources for this relationship and may generate a paid synthesis. Account and platform limits apply. Unchanged evidence may reuse existing text. A failed build retains previous text when available. Confirmation authorizes this attempt only.",
    ),
    "de": (
        "Beziehungsdebriefing erstellen",
        "LIA liest die gewählten Quellen für diese Beziehung und kann eine kostenpflichtige Zusammenfassung erstellen. Konto- und Plattformlimits gelten. Bei unveränderten Daten kann der vorhandene Text wiederverwendet werden. Bei einem Fehler bleibt vorhandener Text erhalten. Die Bestätigung erlaubt nur diesen Versuch.",
    ),
    "es": (
        "Generación del resumen de relación",
        "LIA lee las fuentes seleccionadas para esta relación y puede generar una síntesis de pago. Se aplican los límites de la cuenta y la plataforma. Los datos sin cambios pueden reutilizar el texto existente. Un fallo conserva el texto anterior si existe. La confirmación autoriza solo este intento.",
    ),
    "it": (
        "Generazione del riepilogo della relazione",
        "LIA legge le fonti selezionate per questa relazione e può generare una sintesi a pagamento. Si applicano i limiti dell’account e della piattaforma. Dati invariati possono riutilizzare il testo esistente. Un errore conserva il testo precedente se presente. La conferma autorizza solo questo tentativo.",
    ),
    "zh-CN": (
        "生成关系简报",
        "LIA读取为此关系选择的来源，并可能生成付费总结。适用账户和平台限额。数据未变时可复用已有文本。生成失败时保留已有文本。确认仅授权本次尝试。",
    ),
}
