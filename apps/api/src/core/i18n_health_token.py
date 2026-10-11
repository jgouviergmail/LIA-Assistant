"""A token revocation disables future ingestion while preserving existing measurements."""

from src.core.i18n_types import Language

HEALTH_TOKEN_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Jeton d’ingestion santé à révoquer",
        "Révoquer définitivement le jeton affiché, sans révéler sa valeur secrète ni son hash. Ses envois futurs sont refusés, y compris un envoi authentifié avant la révocation qui commence ensuite à écrire. Les mesures déjà enregistrées sont conservées ; les autres jetons restent actifs. Les dates d’usage peuvent évoluer sans changer le jeton sélectionné. Une identité ou un libellé modifié, des droits retirés ou un accord expiré invalident cette confirmation. Un jeton déjà révoqué est une absence de changement constatée. Aucun appel de modèle. Ne pas rejouer automatiquement un résultat incertain.",
    ),
    "en": (
        "Health ingestion token to revoke",
        "Permanently revoke the displayed token without revealing its secret or hash. Future ingestion is refused, including a request authenticated earlier that starts writing after revocation. Existing measurements remain; other tokens stay active. Use dates may change without retargeting this token. Changed identity/label, withdrawn rights or expired approval invalidate consent. An already revoked token is an observed no-op. No model call. Never automatically replay uncertain completion.",
    ),
    "de": (
        "Zu widerrufender Gesundheits-Token",
        "Den angezeigten Token endgültig widerrufen, ohne Geheimwert oder Hash offenzulegen. Weitere Eingaben werden verweigert, auch zuvor authentifizierte Anfragen, die erst danach schreiben. Vorhandene Messungen und andere Token bleiben erhalten. Nutzungsdaten können sich ohne Identitätswechsel ändern. Geänderte Identität oder Bezeichnung, entzogene Rechte oder abgelaufene Zustimmung machen die Bestätigung ungültig. Ein bereits widerrufener Token ist ein bestätigter Nicht-Eingriff. Kein Modellaufruf; unsicheren Abschluss nie automatisch wiederholen.",
    ),
    "es": (
        "Token de salud que revocar",
        "Revocar permanentemente el token mostrado sin revelar su secreto ni hash. Se rechazan futuros envíos, incluso una solicitud autenticada antes que empiece a escribir después. Se conservan medidas anteriores y otros tokens. Las fechas de uso pueden cambiar sin cambiar la identidad. Identidad o etiqueta modificadas, permisos retirados o aprobación caducada invalidan el consentimiento. Un token ya revocado no requiere cambios. Sin llamada al modelo; no repetir automáticamente resultados inciertos.",
    ),
    "it": (
        "Token salute da revocare",
        "Revocare definitivamente il token mostrato senza rivelare segreto o hash. Gli invii successivi sono rifiutati, anche se autenticati prima ma avviati in scrittura dopo. Misure precedenti e altri token restano. Le date d’uso possono cambiare senza cambiare identità. Identità o etichetta modificate, permessi revocati o consenso scaduto invalidano la conferma. Un token già revocato non richiede modifiche. Nessuna chiamata al modello; mai ripetere automaticamente risultati incerti.",
    ),
    "zh-CN": (
        "待撤销健康接收令牌",
        "永久撤销显示的令牌，不披露秘密值或哈希。后续写入将被拒绝，包括先前已认证但撤销后才开始写入的请求。已有测量和其他令牌保留。使用日期变化不会改变所选令牌。身份、标签变化、权限撤销或批准过期会使确认失效。已撤销令牌属于确认后的无变更。不调用模型，不得自动重放结果不确定的操作。",
    ),
}
