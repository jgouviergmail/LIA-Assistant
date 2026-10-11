"""Manual entry effects and platform embedding cost are visible before approval."""

from src.core.i18n_types import Language

JOURNAL_CREATION_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Entrée du journal à créer",
        "Une entrée manuelle active sera créée avec le contenu complet affiché et les valeurs de preuve initiales du service. Après confirmation, jusqu’à deux embeddings pourront consommer des tokens plateforme sous quotas. Le portrait sera invalidé sans régénération. Un échec d’embedding peut laisser une entrée sans vecteur sémantique. Aucun modèle de consolidation n’est appelé.",
    ),
    "en": (
        "Journal entry to create",
        "An active manual entry will be created with the complete displayed content and source initial evidence values. After confirmation, up to two embeddings may consume platform tokens under quotas. The portrait is invalidated without regeneration. Embedding failure may leave an entry without a semantic vector. No consolidation model is called.",
    ),
    "de": (
        "Zu erstellender Journaleintrag",
        "Ein aktiver manueller Eintrag mit vollständigem Inhalt und anfänglichen Belegwerten wird erstellt. Nach Bestätigung können bis zu zwei Embeddings Plattform-Token unter Quoten verbrauchen. Das Porträt wird ungültig, ohne Neugenerierung. Bei Embedding-Fehlern kann der semantische Vektor fehlen. Kein Konsolidierungsmodell wird aufgerufen.",
    ),
    "es": (
        "Entrada del diario que se creará",
        "Se creará una entrada manual activa con todo el contenido mostrado y los valores iniciales de prueba del servicio. Tras confirmar, hasta dos embeddings pueden consumir tokens de plataforma con cuotas. Se invalida el retrato sin regenerarlo. Un fallo puede dejar la entrada sin vector semántico. No se llama al modelo de consolidación.",
    ),
    "it": (
        "Voce del diario da creare",
        "Verrà creata una voce manuale attiva con l’intero contenuto mostrato e i valori iniziali di prova del servizio. Dopo conferma, fino a due embedding possono consumare token della piattaforma con quote. Il ritratto viene invalidato senza rigenerazione. Un errore può lasciare la voce senza vettore semantico. Nessun modello di consolidamento viene chiamato.",
    ),
    "zh-CN": (
        "待创建的日志条目",
        "将按显示的完整内容及服务初始证据值创建一条启用的手动日志。确认后，最多两次嵌入调用可能在配额限制下消耗平台令牌。使画像失效但不重新生成。嵌入失败时，条目可能没有语义向量。不调用整合模型。",
    ),
}
