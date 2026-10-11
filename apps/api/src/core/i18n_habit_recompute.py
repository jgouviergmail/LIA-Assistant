"""Confirm evaluation of current source data without forecasting its learned verdict."""

from src.core.i18n_types import Language

HABIT_RECOMPUTE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Recalcul des habitudes et du rythme",
        "Le recalcul utilisera les observations et l’historique conservés au moment de son exécution. Le résultat peut rester insuffisant ou ne montrer aucune activité. Les habitudes en pause et les blocages sont conservés ; l’apprentissage automatique reste réglé comme avant. Aucun message ni aucune automatisation ne sera créé.",
    ),
    "en": (
        "Recompute habits and rhythm",
        "Recomputation uses retained observations and history at execution time. Its result may remain insufficient or show no activity. Paused habits and blocks are retained; automatic learning stays as configured. No message or automation is created.",
    ),
    "de": (
        "Gewohnheiten und Rhythmus neu berechnen",
        "Die Neuberechnung verwendet die zum Ausführungszeitpunkt gespeicherten Beobachtungen und den Verlauf. Das Ergebnis kann unzureichend bleiben oder keine Aktivität zeigen. Pausierte Gewohnheiten und Blockierungen bleiben erhalten; automatisches Lernen bleibt unverändert. Es wird keine Nachricht oder Automatisierung erstellt.",
    ),
    "es": (
        "Recalcular hábitos y ritmo",
        "El cálculo utiliza las observaciones y el historial conservados al ejecutarse. El resultado puede seguir siendo insuficiente o no mostrar actividad. Se conservan los hábitos en pausa y los bloqueos; el aprendizaje automático no cambia. No se crea ningún mensaje ni automatización.",
    ),
    "it": (
        "Ricalcolare abitudini e ritmo",
        "Il ricalcolo usa le osservazioni e la cronologia conservate al momento dell’esecuzione. Il risultato può restare insufficiente o non mostrare attività. Abitudini in pausa e blocchi restano conservati; l’apprendimento automatico non cambia. Non vengono creati messaggi o automazioni.",
    ),
    "zh-CN": (
        "重新计算习惯与节奏",
        "重新计算会使用执行时保留的观察与历史记录。结果可能仍不足或没有活动。暂停的习惯与屏蔽记录会保留，自动学习设置不变；不会创建消息或自动化。",
    ),
}
