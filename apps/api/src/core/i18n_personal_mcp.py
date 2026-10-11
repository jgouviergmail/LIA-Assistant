"""Six-language exact personal MCP state consent, separate from server tool execution."""

from src.core.i18n_types import Language

PERSONAL_MCP_OAUTH_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Autorisation OAuth du MCP personnel",
        "Après confirmation, ouvrez la page privée du fournisseur puis terminez l’enregistrement dans le navigateur d’origine. Le retour du fournisseur seul n’enregistre rien et ne vérifie pas la connexion. Un réglage modifié exige une nouvelle confirmation. Ne transmettez aucun code ni jeton dans le chat.",
    ),
    "en": (
        "Personal MCP OAuth authorization",
        "After confirmation, open the private provider page, then complete saving in the original browser. Provider return alone saves nothing and does not verify the connection. Changed settings require fresh confirmation. Never send codes or tokens in chat.",
    ),
    "es": (
        "Autorización OAuth del MCP personal",
        "Tras confirmar, abre la página privada del proveedor y completa el guardado en el navegador original. El retorno del proveedor no guarda nada ni verifica la conexión. Los cambios requieren nueva confirmación. Nunca envíes códigos o tokens al chat.",
    ),
    "de": (
        "Persönliche MCP-OAuth-Autorisierung",
        "Nach Bestätigung die private Anbieterseite öffnen und im ursprünglichen Browser speichern. Die Anbieterrückkehr allein speichert nichts und prüft keine Verbindung. Änderungen erfordern neue Bestätigung. Keine Codes oder Tokens im Chat senden.",
    ),
    "it": (
        "Autorizzazione OAuth del MCP personale",
        "Dopo la conferma, apri la pagina privata del fornitore e completa il salvataggio nel browser originale. Il ritorno del fornitore non salva nulla né verifica la connessione. Le modifiche richiedono una nuova conferma. Non inviare codici o token nella chat.",
    ),
    "zh-CN": (
        "个人 MCP OAuth 授权",
        "确认后打开供应商的私密授权页面，然后在原浏览器中完成保存。供应商返回本身不会保存任何内容，也不会验证连接。设置发生变化时须重新确认。请勿在聊天中发送授权码或令牌。",
    ),
}

PERSONAL_MCP_CONFIGURATION_COPY: dict[Language, tuple[str, str]] = {
    "en": (
        "Secure personal MCP configuration",
        "Opens a private form in the originating authenticated browser to create or modify this personal server. Enter endpoint and credentials there, never in chat, then explicitly save. Approval alone changes nothing. Changed settings require a new confirmation; saving configuration does not verify the connection.",
    ),
    "fr": (
        "Configuration MCP personnelle sécurisée",
        "Ouvre un formulaire privé dans le navigateur authentifié d’origine pour créer ou modifier ce serveur personnel. Saisissez l’adresse et les identifiants dans ce formulaire, jamais dans le chat, puis enregistrez explicitement. La confirmation seule ne modifie rien. Un changement de réglages impose une nouvelle confirmation ; l’enregistrement ne vérifie pas la connexion.",
    ),
    "es": (
        "Configuración segura del MCP personal",
        "Abre un formulario privado en el navegador autenticado de origen para crear o modificar este servidor personal. Introduce allí la dirección y las credenciales, nunca en el chat, y guarda explícitamente. La confirmación sola no cambia nada. Los cambios requieren otra confirmación; guardar no verifica la conexión.",
    ),
    "de": (
        "Sichere persönliche MCP-Konfiguration",
        "Öffnet ein privates Formular im ursprünglichen authentifizierten Browser zum Erstellen oder Ändern dieses persönlichen Servers. Adresse und Zugangsdaten dort eingeben, niemals im Chat, dann ausdrücklich speichern. Zustimmung allein ändert nichts. Geänderte Einstellungen erfordern neue Bestätigung; Speichern prüft die Verbindung nicht.",
    ),
    "it": (
        "Configurazione sicura del MCP personale",
        "Apre un modulo privato nel browser autenticato di origine per creare o modificare questo server personale. Inserisci lì indirizzo e credenziali, mai nella chat, poi salva esplicitamente. La sola conferma non modifica nulla. Impostazioni cambiate richiedono nuova conferma; salvare non verifica la connessione.",
    ),
    "zh-CN": (
        "安全配置个人 MCP",
        "在原始认证浏览器中打开私人表单以创建或修改此个人服务器。在表单中填写地址和凭据，切勿放入聊天，然后明确保存。仅确认不会进行修改。设置变化时须重新确认；保存配置不表示已验证连接。",
    ),
}


PERSONAL_MCP_STATE_COPY: dict[Language, tuple[str, str]] = {
    "en": (
        "Personal MCP server state",
        "Confirm the exact enabled state for this personal MCP server. Disabling disconnects its session; enabling does not test or authorize it. Changed settings require a new confirmation.",
    ),
    "fr": (
        "État du serveur MCP personnel",
        "Confirmez l’état d’activation exact de ce serveur MCP personnel. La désactivation déconnecte sa session ; l’activation ne le teste pas et ne l’autorise pas. Un changement de réglages impose une nouvelle confirmation.",
    ),
    "es": (
        "Estado del servidor MCP personal",
        "Confirma el estado de activación exacto de este servidor MCP personal. Desactivarlo desconecta su sesión; activarlo no lo prueba ni lo autoriza. Si cambian los ajustes, se requiere otra confirmación.",
    ),
    "de": (
        "Status des persönlichen MCP-Servers",
        "Bestätigen Sie den genauen Aktivierungsstatus dieses persönlichen MCP-Servers. Deaktivieren trennt seine Sitzung; Aktivieren testet oder autorisiert ihn nicht. Geänderte Einstellungen erfordern eine neue Bestätigung.",
    ),
    "it": (
        "Stato del server MCP personale",
        "Conferma lo stato di attivazione esatto di questo server MCP personale. La disattivazione scollega la sessione; l’attivazione non lo verifica né lo autorizza. Le impostazioni modificate richiedono una nuova conferma.",
    ),
    "zh-CN": (
        "个人 MCP 服务器状态",
        "请确认此个人 MCP 服务器的具体启用状态。停用会断开其会话；启用不会测试服务器或进行授权。设置发生变化时需要重新确认。",
    ),
}

PERSONAL_MCP_CONNECTION_COPY: dict[Language, tuple[str, str]] = {
    "en": (
        "Personal MCP connection test",
        "Contacts this personal server, discovers tools and may call its read_me documentation tool. Saves connection status and metadata; may generate a missing description and compute embeddings using the platform's existing billing and limits. Changed settings require fresh consent; external work can incur cost even if saving is subsequently refused.",
    ),
    "fr": (
        "Test de connexion MCP personnel",
        "Contacte ce serveur personnel, découvre ses outils et peut appeler son outil de documentation read_me. Enregistre l’état et les métadonnées ; peut générer une description manquante et calculer des embeddings selon la facturation et les limites existantes. Un changement de réglages impose une nouvelle confirmation ; le travail externe peut être facturé même si l’enregistrement est ensuite refusé.",
    ),
    "es": (
        "Prueba de conexión MCP personal",
        "Contacta con este servidor personal, descubre herramientas y puede llamar a su herramienta de documentación read_me. Guarda el estado y los metadatos; puede generar una descripción ausente y calcular embeddings con la facturación y los límites existentes. Los cambios requieren otra confirmación; el trabajo externo puede tener coste aunque después se rechace el guardado.",
    ),
    "de": (
        "Persönliche MCP-Verbindung testen",
        "Kontaktiert diesen persönlichen Server, entdeckt Werkzeuge und kann dessen Dokumentationswerkzeug read_me aufrufen. Speichert Status und Metadaten; kann eine fehlende Beschreibung und Embeddings mit bestehender Abrechnung und Limits erzeugen. Geänderte Einstellungen erfordern neue Zustimmung; externe Arbeit kann Kosten verursachen, auch wenn das Speichern später abgelehnt wird.",
    ),
    "it": (
        "Test della connessione MCP personale",
        "Contatta questo server personale, scopre strumenti e può chiamare lo strumento di documentazione read_me. Salva stato e metadati; può generare una descrizione mancante e calcolare embeddings con fatturazione e limiti esistenti. Impostazioni modificate richiedono nuova conferma; il lavoro esterno può comportare costi anche se il salvataggio viene poi rifiutato.",
    ),
    "zh-CN": (
        "测试个人 MCP 连接",
        "连接此个人服务器，发现工具，并可能调用其 read_me 文档工具。保存连接状态和元数据；可能按现有计费和限额生成缺失的描述及嵌入。设置变化时须重新确认；即使之后拒绝保存，外部操作仍可能产生费用。",
    ),
}

PERSONAL_MCP_OAUTH_DISCONNECT_COPY: dict[Language, tuple[str, str]] = {
    "en": (
        "Disconnect personal MCP OAuth",
        "Removes this personal server’s stored connection tokens, keeps client credentials and requires authorization again. Invalidates its cached session. The provider grant is not revoked. Changed settings require new confirmation.",
    ),
    "fr": (
        "Déconnexion OAuth MCP personnel",
        "Retire les jetons de connexion enregistrés de ce serveur personnel, conserve les identifiants du client et impose une nouvelle autorisation. Invalide sa session en cache. L’autorisation chez le fournisseur n’est pas révoquée. Un changement de réglages impose une nouvelle confirmation.",
    ),
    "es": (
        "Desconectar OAuth del MCP personal",
        "Elimina los tokens de conexión guardados de este servidor personal, conserva las credenciales del cliente y requiere otra autorización. Invalida la sesión en caché. No revoca el permiso en el proveedor. Los cambios requieren otra confirmación.",
    ),
    "de": (
        "Persönliches MCP-OAuth trennen",
        "Entfernt gespeicherte Verbindungstoken dieses persönlichen Servers, behält Client-Zugangsdaten und erfordert eine neue Autorisierung. Invalidiert die Sitzung im Cache. Die Anbieterfreigabe wird nicht widerrufen. Geänderte Einstellungen erfordern neue Zustimmung.",
    ),
    "it": (
        "Disconnettere OAuth del MCP personale",
        "Rimuove i token di connessione salvati di questo server personale, mantiene le credenziali del client e richiede una nuova autorizzazione. Invalida la sessione in cache. Non revoca il consenso presso il fornitore. Impostazioni modificate richiedono nuova conferma.",
    ),
    "zh-CN": (
        "断开个人 MCP OAuth",
        "删除此个人服务器保存的连接令牌，保留客户端凭据，并要求重新授权。使缓存会话失效，但不撤销服务提供商端的授权。设置变化时须重新确认。",
    ),
}


PERSONAL_MCP_SETTINGS_COPY: dict[Language, tuple[str, str]] = {
    "en": (
        "Personal MCP server settings",
        "Changes only the displayed personal server name, description, timeout or iterative mode. Authentication and endpoint stay unchanged. Changed settings require a new confirmation.",
    ),
    "fr": (
        "Réglages du serveur MCP personnel",
        "Modifie uniquement le nom, la description, le délai d’attente ou le mode itératif du serveur personnel affiché. L’authentification et l’adresse restent inchangées. Un changement de réglages impose une nouvelle confirmation.",
    ),
    "es": (
        "Ajustes del servidor MCP personal",
        "Cambia solo el nombre, la descripción, el tiempo de espera o el modo iterativo del servidor personal mostrado. La autenticación y la dirección se mantienen. Los ajustes modificados requieren otra confirmación.",
    ),
    "de": (
        "Einstellungen des persönlichen MCP-Servers",
        "Ändert nur Name, Beschreibung, Zeitlimit oder iterativen Modus des angezeigten persönlichen Servers. Authentifizierung und Adresse bleiben unverändert. Geänderte Einstellungen erfordern eine neue Bestätigung.",
    ),
    "it": (
        "Impostazioni del server MCP personale",
        "Modifica solo nome, descrizione, timeout o modalità iterativa del server personale mostrato. Autenticazione e indirizzo restano invariati. Le impostazioni modificate richiedono una nuova conferma.",
    ),
    "zh-CN": (
        "个人 MCP 服务器设置",
        "仅更改所显示个人服务器的名称、描述、超时或迭代模式。认证和地址保持不变。设置发生变化时需要重新确认。",
    ),
}

PERSONAL_MCP_DELETE_COPY: dict[Language, tuple[str, str]] = {
    "en": (
        "Personal MCP server to delete",
        "Deletes only this personal standalone server and disconnects its session. The remote service is not deleted. Plugin servers require complete plugin uninstall. Changed settings require a new confirmation.",
    ),
    "fr": (
        "Serveur MCP personnel à supprimer",
        "Supprime uniquement ce serveur personnel autonome et déconnecte sa session. Le service distant n’est pas supprimé. Les serveurs de plugin imposent la désinstallation du plugin complet. Un changement de réglages impose une nouvelle confirmation.",
    ),
    "es": (
        "Servidor MCP personal que se eliminará",
        "Elimina solo este servidor personal independiente y desconecta su sesión. No elimina el servicio remoto. Los servidores de plugins requieren desinstalar el plugin completo. Los ajustes modificados requieren otra confirmación.",
    ),
    "de": (
        "Zu löschender persönlicher MCP-Server",
        "Löscht nur diesen eigenständigen persönlichen Server und trennt seine Sitzung. Der entfernte Dienst wird nicht gelöscht. Plugin-Server erfordern die vollständige Deinstallation des Plugins. Geänderte Einstellungen erfordern eine neue Bestätigung.",
    ),
    "it": (
        "Server MCP personale da eliminare",
        "Elimina solo questo server personale autonomo e scollega la sessione. Il servizio remoto non viene eliminato. I server dei plugin richiedono la disinstallazione completa del plugin. Le impostazioni modificate richiedono una nuova conferma.",
    ),
    "zh-CN": (
        "要删除的个人 MCP 服务器",
        "仅删除此独立的个人服务器配置并断开其会话，不删除远程服务。插件服务器需要卸载整个插件。设置发生变化时需要重新确认。",
    ),
}

PERSONAL_MCP_DESCRIPTION_COPY: dict[Language, tuple[str, str]] = {
    "en": (
        "Regenerate personal MCP description",
        "Uses cached tool metadata and overwrites the saved description. May use the platform LLM under account and instance quotas; a deterministic fallback is available. A model call may be billed even if a later conflict prevents saving.",
    ),
    "fr": (
        "Régénérer la description du MCP personnel",
        "Utilise les métadonnées d’outils en cache et remplace la description enregistrée. Peut utiliser le LLM de la plateforme sous les quotas du compte et de l’instance ; un repli déterministe est disponible. Un appel au modèle peut être facturé même si un conflit ultérieur empêche l’enregistrement.",
    ),
    "es": (
        "Regenerar la descripción del MCP personal",
        "Usa los metadatos de herramientas en caché y sustituye la descripción guardada. Puede usar el LLM de la plataforma bajo las cuotas de la cuenta y la instancia, con alternativa determinista. Una llamada al modelo puede facturarse aunque un conflicto posterior impida guardar.",
    ),
    "de": (
        "Persönliche MCP-Beschreibung neu erstellen",
        "Verwendet zwischengespeicherte Werkzeugmetadaten und ersetzt die gespeicherte Beschreibung. Kann das Plattform-LLM unter Konto- und Instanzquoten nutzen; ein deterministischer Ersatz ist verfügbar. Ein Modellaufruf kann auch bei einem späteren Speicherkonflikt berechnet werden.",
    ),
    "it": (
        "Rigenerare la descrizione del MCP personale",
        "Usa i metadati degli strumenti in cache e sostituisce la descrizione salvata. Può usare il LLM della piattaforma entro le quote dell’account e dell’istanza, con alternativa deterministica. Una chiamata al modello può essere addebitata anche se un conflitto successivo impedisce il salvataggio.",
    ),
    "zh-CN": (
        "重新生成个人 MCP 描述",
        "使用缓存的工具元数据并替换已保存的描述。可能在账户及实例额度内调用平台 LLM，也可使用确定性回退。即使后续冲突导致无法保存，已进行的模型调用仍可能计费。",
    ),
}
