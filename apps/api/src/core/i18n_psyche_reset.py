"""Exact source reset levels explicitly distinguish retained history and future reconstruction."""

from src.core.i18n_types import Language

PSYCHE_RESET_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Réinitialisation de la psyché",
        "Légère : humeur, émotions, dernière analyse et moteurs. Complète : aussi relation, efficacité et récit, en conservant les traits. Purge : état et tout l’historique. Les réglages et conversations restent ; des interactions ou analyses déjà commencées peuvent reconstruire des données. Légère/complète ajoutent une trace de réinitialisation si un état existe.",
    ),
    "en": (
        "Psyche reset",
        "Soft: mood, emotions, last appraisal and drives. Full: also relationship, efficacy and narrative, retaining traits. Purge: state and all history. Settings and conversations remain; interactions or analyses already started may rebuild data. Soft/full add a reset snapshot when state exists.",
    ),
    "de": (
        "Psyche zurücksetzen",
        "Soft: Stimmung, Emotionen, letzte Bewertung und Antriebe. Full: auch Beziehung, Wirksamkeit und Erzählung; Merkmale bleiben. Purge: Zustand und gesamter Verlauf. Einstellungen und Gespräche bleiben; begonnene Interaktionen oder Analysen können Daten neu aufbauen. Soft/full ergänzen bei vorhandenem Zustand einen Reset-Eintrag.",
    ),
    "es": (
        "Reiniciar la psique",
        "Soft: ánimo, emociones, última evaluación e impulsos. Full: también relación, eficacia y relato; conserva los rasgos. Purge: estado y todo el historial. Se conservan ajustes y conversaciones; interacciones o análisis ya iniciados pueden reconstruir datos. Soft/full añaden una entrada de reinicio si existe un estado.",
    ),
    "it": (
        "Reimposta la psiche",
        "Soft: umore, emozioni, ultima valutazione e impulsi. Full: anche relazione, efficacia e narrazione, conservando i tratti. Purge: stato e intera cronologia. Impostazioni e conversazioni restano; interazioni o analisi già iniziate possono ricreare dati. Soft/full aggiungono un evento di reset se esiste uno stato.",
    ),
    "zh-CN": (
        "重置心理状态",
        "soft：重置情绪、情感、最近评估与驱动力。full：另重置关系、自我效能与叙事，保留人格特质。purge：删除状态与全部历史。保留设置和对话；已开始的互动或分析可能重新生成数据。有状态时，soft/full会新增重置记录。",
    ),
}
