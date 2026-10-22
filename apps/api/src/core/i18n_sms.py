"""Exact SMS approval copy in the application's six prompt languages."""

SMS_APPROVAL_NOTE = {
    "fr": "Mes SMS : cette confirmation autorise uniquement le changement affiché. Un jeton sera remis une seule fois dans le navigateur d’origine, jamais dans la discussion. Effacement : les exports hébergés sont invalidés ; les copies téléchargées et les discussions antérieures restent indépendantes.",
    "en": "My SMS: this confirmation authorizes only the displayed change. A token is delivered once in the originating browser, never in chat. Erasure invalidates hosted exports; downloaded copies and earlier conversations have separate retention.",
    "de": "Meine SMS: Diese Bestätigung erlaubt nur die angezeigte Änderung. Ein Token wird einmal im ursprünglichen Browser übermittelt, niemals im Chat. Löschen macht gehostete Exporte ungültig; heruntergeladene Kopien und frühere Chats bleiben unabhängig.",
    "es": "Mis SMS: esta confirmación autoriza solo el cambio mostrado. El token se entrega una vez en el navegador original, nunca en el chat. El borrado invalida las exportaciones alojadas; las copias descargadas y los chats anteriores tienen conservación independiente.",
    "it": "I miei SMS: questa conferma autorizza solo la modifica mostrata. Il token viene consegnato una volta nel browser originale, mai nella chat. La cancellazione invalida le esportazioni ospitate; le copie scaricate e le chat precedenti hanno conservazione separata.",
    "zh-CN": "我的短信：此确认仅授权所示更改。令牌仅在原始浏览器中显示一次，绝不进入聊天。删除会使托管导出失效；已下载的副本和以前的聊天独立保留。",
}


SMS_CARD_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "provided_time": "Heure fournie par le téléphone",
        "more": "Lire la suite dans Mes SMS.",
    },
    "en": {
        "provided_time": "Time supplied by the phone",
        "more": "Read the rest in My SMS.",
    },
    "de": {
        "provided_time": "Vom Telefon angegebene Zeit",
        "more": "Lies den Rest unter Meine SMS.",
    },
    "es": {
        "provided_time": "Hora indicada por el teléfono",
        "more": "Lee el resto en Mis SMS.",
    },
    "it": {
        "provided_time": "Ora fornita dal telefono",
        "more": "Leggi il resto in I miei SMS.",
    },
    "zh-CN": {"provided_time": "手机提供的时间", "more": "在“我的短信”中查看完整内容。"},
}
