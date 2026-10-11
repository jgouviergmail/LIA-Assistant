"""Source issuance effects and one-time browser secret delivery in every supported language."""

from src.core.i18n_types import Language

HEALTH_TOKEN_CREATION_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Jeton d’ingestion santé à créer",
        "Créer un seul jeton au libellé affiché après cette confirmation puis une action explicite dans le navigateur authentifié d’origine. Sa valeur secrète n’est affichée qu’une fois dans ce navigateur ; elle ne passe jamais par le modèle, le chat ou les registres. Les mesures et autres jetons restent conservés. Aucun appel de modèle. Un accord expiré ou des droits retirés invalident l’action. Ne pas répéter une réponse perdue pour retrouver le secret : consulter les métadonnées, révoquer le jeton créé puis demander séparément un autre jeton.",
    ),
    "en": (
        "Health ingestion token to create",
        "Create one token with the displayed label after confirmation and an explicit action in the authenticated originating browser. Its secret appears once in that browser and never enters the model, chat or registers. Existing measurements and other tokens remain. No model call. Expired approval or withdrawn rights invalidate the action. Never repeat a lost response to recover the secret: inspect metadata, revoke the created token, then separately request another.",
    ),
    "de": (
        "Zu erstellender Gesundheits-Token",
        "Einen Token mit der angezeigten Bezeichnung nach Bestätigung und ausdrücklicher Aktion im authentifizierten Ursprungsbrowser erstellen. Sein Geheimwert erscheint dort einmalig, niemals im Modell, Chat oder Register. Messungen und andere Token bleiben. Kein Modellaufruf. Ablauf oder entzogene Rechte verhindern die Aktion. Eine verlorene Antwort nicht wiederholen: Metadaten prüfen, erstellten Token widerrufen und gesondert einen neuen anfordern.",
    ),
    "es": (
        "Token de salud que crear",
        "Crear un token con la etiqueta mostrada tras confirmar y continuar explícitamente en el navegador autenticado original. Su secreto se muestra una sola vez allí, nunca en el modelo, chat o registros. Se conservan medidas y otros tokens. Sin llamada al modelo. La caducidad o permisos retirados invalidan la acción. No repetir una respuesta perdida: consultar metadatos, revocar el token creado y solicitar otro por separado.",
    ),
    "it": (
        "Token salute da creare",
        "Creare un token con l’etichetta mostrata dopo conferma e azione esplicita nel browser autenticato originale. Il segreto appare una volta solo lì, mai nel modello, chat o registri. Misure e altri token restano. Nessuna chiamata al modello. Consenso scaduto o permessi revocati invalidano l’azione. Non ripetere una risposta persa: verificare i metadati, revocare il token creato e richiederne uno nuovo separatamente.",
    ),
    "zh-CN": (
        "待创建健康接收令牌",
        "确认后，在原始认证浏览器中明确继续，创建一个使用所示标签的令牌。秘密值仅在该浏览器显示一次，绝不进入模型、聊天或记录。已有测量和其他令牌保留。不调用模型。批准过期或权限撤销将阻止操作。不得重放丢失的响应来恢复秘密；应查看元数据，撤销已创建令牌，再单独申请新令牌。",
    ),
}
