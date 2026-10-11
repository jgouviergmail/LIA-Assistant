"""Exact refresh confirmation explains external quota and partial source statuses."""

from src.core.i18n_types import Language

RELATION_CONTEXT_REFRESH_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Rafraîchissement des fiches Relations",
        "LIA relit les sections fournisseurs sélectionnées pour ce nom en contournant leur cache. Les quotas externes s’appliquent. Chaque section indique son résultat ou son indisponibilité ; aucune synthèse n’est générée. Confirmer autorise cette tentative uniquement.",
    ),
    "en": (
        "Refresh relationship provider cards",
        "LIA rereads the selected provider sections for this name, bypassing their caches. External quotas apply. Each section states its result or unavailability; no synthesis is generated. Confirmation authorizes this attempt only.",
    ),
    "de": (
        "Beziehungskarten aktualisieren",
        "LIA liest die ausgewählten Anbieterbereiche für diesen Namen erneut und umgeht deren Cache. Externe Kontingente gelten. Jeder Bereich zeigt sein Ergebnis oder seine Nichtverfügbarkeit; es wird keine Zusammenfassung erstellt. Die Bestätigung erlaubt nur diesen Versuch.",
    ),
    "es": (
        "Actualizar las fichas de relación",
        "LIA vuelve a leer las secciones de proveedores seleccionadas para este nombre omitiendo su caché. Se aplican cuotas externas. Cada sección indica su resultado o indisponibilidad; no se genera una síntesis. La confirmación autoriza solo este intento.",
    ),
    "it": (
        "Aggiornare le schede della relazione",
        "LIA rilegge le sezioni dei fornitori selezionate per questo nome ignorando la loro cache. Si applicano quote esterne. Ogni sezione indica il risultato o l’indisponibilità; non viene generata una sintesi. La conferma autorizza solo questo tentativo.",
    ),
    "zh-CN": (
        "刷新关系资料",
        "LIA绕过缓存，重新读取此姓名所选的服务提供方资料。适用外部配额。每个部分显示结果或不可用状态，不生成总结。确认仅授权本次尝试。",
    ),
}
