"""Wordings of the human-readable consultation register (ADR-263, lot 4).

A treatment row records WHICH capability answered and never what was asked, so
its wording carries no placeholder: it is a noun, the name of the domain the
capability belongs to. Thirty-one nouns cover every tool the assistant has and
every tool it will ever have, because a new capability joins an existing
domain — which is exactly why the domain, rather than the tool, is what a
reader is shown. The tool name is displayed beside it, so nothing is hidden.

Data module (exempt from the size ratchet, like ``i18n_effects``): one table
per language, the SAME key set under each, checked by
``tests/unit/domains/agents/effects/test_treatment_labels.py``.

The frontend resolves the same domain keys from its own locales for the live
list — the API ships keys, never translated strings (``apps/web`` conventions).
This table exists for the register EXPORTS, which are files rather than pages
and therefore have no client to translate them.
"""

from src.core.i18n import normalize_language

#: The six languages every wording must exist in (backend canonical codes).
SUPPORTED_LABEL_LANGUAGES: tuple[str, ...] = ("fr", "en", "de", "es", "it", "zh-CN")

#: Read when a domain has no wording. A register that cannot name a capability
#: still records that it was consulted — it never falls back to a tool name.
UNKNOWN_DOMAIN_KEY = "unknown"

#: language -> {domain -> noun}. No placeholders: a consultation has no target.
TREATMENT_DOMAIN_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "automation": "Automatisations",
        "brave": "Recherche Brave",
        "browser": "Navigateur web",
        "contact": "Contacts",
        "context": "Contexte de conversation",
        "devops": "Administration du serveur",
        "document": "Documents",
        "document_generation": "Génération de documents",
        "email": "E-mails",
        "event": "Agenda",
        "file": "Fichiers",
        "health": "Données de santé",
        "hue": "Éclairage connecté",
        "image_generation": "Génération d'images",
        "mcp": "Serveur externe (MCP)",
        "peer": "Pairs",
        "perplexity": "Recherche Perplexity",
        "place": "Lieux",
        "python_sandbox": "Calcul Python isolé",
        "query": "Recherche dans vos données",
        "reminder": "Rappels",
        "route": "Itinéraires",
        "skill": "Compétences",
        "sub_agent": "Sous-agent",
        "task": "Tâches",
        "telephony": "Téléphonie",
        "weather": "Météo",
        "web_fetch": "Page web",
        "web_search": "Recherche web",
        "wikipedia": "Wikipédia",
        "unknown": "Capacité non identifiée",
    },
    "en": {
        "automation": "Automations",
        "brave": "Brave search",
        "browser": "Web browser",
        "contact": "Contacts",
        "context": "Conversation context",
        "devops": "Server administration",
        "document": "Documents",
        "document_generation": "Document generation",
        "email": "Emails",
        "event": "Calendar",
        "file": "Files",
        "health": "Health data",
        "hue": "Smart lighting",
        "image_generation": "Image generation",
        "mcp": "External server (MCP)",
        "peer": "Peers",
        "perplexity": "Perplexity search",
        "place": "Places",
        "python_sandbox": "Sandboxed Python",
        "query": "Search in your data",
        "reminder": "Reminders",
        "route": "Routes",
        "skill": "Skills",
        "sub_agent": "Sub-agent",
        "task": "Tasks",
        "telephony": "Telephony",
        "weather": "Weather",
        "web_fetch": "Web page",
        "web_search": "Web search",
        "wikipedia": "Wikipedia",
        "unknown": "Unidentified capability",
    },
    "de": {
        "automation": "Automatisierungen",
        "brave": "Brave-Suche",
        "browser": "Webbrowser",
        "contact": "Kontakte",
        "context": "Gesprächskontext",
        "devops": "Serververwaltung",
        "document": "Dokumente",
        "document_generation": "Dokumentenerstellung",
        "email": "E-Mails",
        "event": "Kalender",
        "file": "Dateien",
        "health": "Gesundheitsdaten",
        "hue": "Intelligente Beleuchtung",
        "image_generation": "Bilderzeugung",
        "mcp": "Externer Server (MCP)",
        "peer": "Peers",
        "perplexity": "Perplexity-Suche",
        "place": "Orte",
        "python_sandbox": "Isoliertes Python",
        "query": "Suche in Ihren Daten",
        "reminder": "Erinnerungen",
        "route": "Routen",
        "skill": "Fähigkeiten",
        "sub_agent": "Sub-Agent",
        "task": "Aufgaben",
        "telephony": "Telefonie",
        "weather": "Wetter",
        "web_fetch": "Webseite",
        "web_search": "Websuche",
        "wikipedia": "Wikipedia",
        "unknown": "Nicht identifizierte Fähigkeit",
    },
    "es": {
        "automation": "Automatizaciones",
        "brave": "Búsqueda Brave",
        "browser": "Navegador web",
        "contact": "Contactos",
        "context": "Contexto de conversación",
        "devops": "Administración del servidor",
        "document": "Documentos",
        "document_generation": "Generación de documentos",
        "email": "Correos electrónicos",
        "event": "Calendario",
        "file": "Archivos",
        "health": "Datos de salud",
        "hue": "Iluminación conectada",
        "image_generation": "Generación de imágenes",
        "mcp": "Servidor externo (MCP)",
        "peer": "Pares",
        "perplexity": "Búsqueda Perplexity",
        "place": "Lugares",
        "python_sandbox": "Python aislado",
        "query": "Búsqueda en tus datos",
        "reminder": "Recordatorios",
        "route": "Rutas",
        "skill": "Habilidades",
        "sub_agent": "Subagente",
        "task": "Tareas",
        "telephony": "Telefonía",
        "weather": "Meteorología",
        "web_fetch": "Página web",
        "web_search": "Búsqueda web",
        "wikipedia": "Wikipedia",
        "unknown": "Capacidad no identificada",
    },
    "it": {
        "automation": "Automazioni",
        "brave": "Ricerca Brave",
        "browser": "Browser web",
        "contact": "Contatti",
        "context": "Contesto della conversazione",
        "devops": "Amministrazione del server",
        "document": "Documenti",
        "document_generation": "Generazione di documenti",
        "email": "E-mail",
        "event": "Calendario",
        "file": "File",
        "health": "Dati sulla salute",
        "hue": "Illuminazione smart",
        "image_generation": "Generazione di immagini",
        "mcp": "Server esterno (MCP)",
        "peer": "Peer",
        "perplexity": "Ricerca Perplexity",
        "place": "Luoghi",
        "python_sandbox": "Python isolato",
        "query": "Ricerca nei tuoi dati",
        "reminder": "Promemoria",
        "route": "Itinerari",
        "skill": "Competenze",
        "sub_agent": "Sotto-agente",
        "task": "Attività",
        "telephony": "Telefonia",
        "weather": "Meteo",
        "web_fetch": "Pagina web",
        "web_search": "Ricerca web",
        "wikipedia": "Wikipedia",
        "unknown": "Capacità non identificata",
    },
    "zh-CN": {
        "automation": "自动化",
        "brave": "Brave 搜索",
        "browser": "网页浏览器",
        "contact": "联系人",
        "context": "对话上下文",
        "devops": "服务器管理",
        "document": "文档",
        "document_generation": "文档生成",
        "email": "电子邮件",
        "event": "日历",
        "file": "文件",
        "health": "健康数据",
        "hue": "智能照明",
        "image_generation": "图像生成",
        "mcp": "外部服务器（MCP）",
        "peer": "联结伙伴",
        "perplexity": "Perplexity 搜索",
        "place": "地点",
        "python_sandbox": "隔离的 Python 计算",
        "query": "在你的数据中搜索",
        "reminder": "提醒",
        "route": "路线",
        "skill": "技能",
        "sub_agent": "子代理",
        "task": "任务",
        "telephony": "电话",
        "weather": "天气",
        "web_fetch": "网页",
        "web_search": "网页搜索",
        "wikipedia": "维基百科",
        "unknown": "未识别的能力",
    },
}


#: Heading of the exported consultation register.
TREATMENT_REGISTER_HEADING: dict[str, str] = {
    "fr": "Journal des consultations",
    "en": "Consultation journal",
    "de": "Abrufprotokoll",
    "es": "Registro de consultas",
    "it": "Registro delle consultazioni",
    "zh-CN": "查阅记录",
}


#: Marker appended to a consultation that did not answer. Six languages, like
#: every other string a reader sees: an inline "[échec]" would have shipped a
#: French word into a German export.
TREATMENT_FAILED_MARKER: dict[str, str] = {
    "fr": "échec",
    "en": "failed",
    "de": "fehlgeschlagen",
    "es": "fallo",
    "it": "non riuscita",
    "zh-CN": "失败",
}


def render_treatment_failure(language: str) -> str:
    """Say, in the reader's language, that a consultation did not answer.

    Args:
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The marker.
    """
    return TREATMENT_FAILED_MARKER.get(normalize_language(language), TREATMENT_FAILED_MARKER["en"])


def render_treatment_heading(language: str) -> str:
    """Title the exported consultation register in the reader's language.

    Args:
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The heading.
    """
    return TREATMENT_REGISTER_HEADING.get(
        normalize_language(language), TREATMENT_REGISTER_HEADING["en"]
    )


def render_treatment_domain(domain: str, language: str) -> str:
    """Name a consulted domain in the reader's language.

    Never raises: an export must not fail because a domain was added to the
    taxonomy and its wording has not landed yet — the boot guard is what makes
    that case loud, and it is the right place for it.

    Args:
        domain: The domain key, as resolved by ``treatment_domain``.
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The domain's noun, or the unknown wording.
    """
    table = TREATMENT_DOMAIN_LABELS.get(normalize_language(language), TREATMENT_DOMAIN_LABELS["en"])
    return table.get(domain) or table[UNKNOWN_DOMAIN_KEY]


#: The chain attestation carried by an account archive (ADR-263, lot 5). One
#: paragraph rather than a table of hashes: what a person can act on is how
#: much is sealed, until when, and the single value to write down.
CHAIN_ATTESTATION: dict[str, str] = {
    "fr": (
        "# Scellement des journaux\n\n"
        "{entries} entrées de scellement couvrent vos journaux d'actions et de "
        "consultations, jusqu'au {sealed_until}.\n\n"
        "Empreinte finale : `{head_hash}`\n\n"
        "Notez cette empreinte : la comparer plus tard suffit à détecter une "
        "réécriture, même si la ligne modifiée et son entrée de scellement "
        "l'étaient ensemble."
    ),
    "en": (
        "# Register sealing\n\n"
        "{entries} sealing entries cover your action and consultation "
        "journals, up to {sealed_until}.\n\n"
        "Final fingerprint: `{head_hash}`\n\n"
        "Write this fingerprint down: comparing it later is enough to detect a "
        "rewrite, even one where the altered row and its sealing entry were "
        "changed together."
    ),
    "de": (
        "# Versiegelung der Protokolle\n\n"
        "{entries} Versiegelungseinträge decken Ihre Aktions- und "
        "Abrufprotokolle bis zum {sealed_until} ab.\n\n"
        "Endgültiger Fingerabdruck: `{head_hash}`\n\n"
        "Notieren Sie diesen Fingerabdruck: Ein späterer Vergleich genügt, um "
        "eine Änderung zu erkennen — selbst wenn die geänderte Zeile und ihr "
        "Versiegelungseintrag gemeinsam geändert wurden."
    ),
    "es": (
        "# Sellado de los registros\n\n"
        "{entries} entradas de sellado cubren sus registros de acciones y de "
        "consultas, hasta el {sealed_until}.\n\n"
        "Huella final: `{head_hash}`\n\n"
        "Anote esta huella: compararla más adelante basta para detectar una "
        "reescritura, incluso si la fila alterada y su entrada de sellado se "
        "modificaron a la vez."
    ),
    "it": (
        "# Sigillatura dei registri\n\n"
        "{entries} voci di sigillatura coprono i suoi registri delle azioni e "
        "delle consultazioni, fino al {sealed_until}.\n\n"
        "Impronta finale: `{head_hash}`\n\n"
        "Annoti questa impronta: confrontarla in seguito basta a rilevare una "
        "riscrittura, anche se la riga alterata e la sua voce di sigillatura "
        "sono state modificate insieme."
    ),
    "zh-CN": (
        "# 记录封存\n\n"
        "{entries} 条封存记录覆盖了您的操作与查阅记录，截至 {sealed_until}。\n\n"
        "最终指纹：`{head_hash}`\n\n"
        "请记下该指纹：日后比对即可发现篡改，即使被修改的行与其封存记录被一并改动。"
    ),
}

#: What the attestation says when the notary has not sealed anything yet. An
#: empty chain is not a failure — it is an account that has done nothing, or a
#: sealing that is switched off — and saying so is more honest than a
#: paragraph with three blanks in it.
CHAIN_ATTESTATION_EMPTY: dict[str, str] = {
    "fr": (
        "# Scellement des journaux\n\n"
        "Aucune entrée de scellement : vos journaux ne sont pas encore scellés."
    ),
    "en": ("# Register sealing\n\n" "No sealing entries: your journals are not sealed yet."),
    "de": (
        "# Versiegelung der Protokolle\n\n"
        "Keine Versiegelungseinträge: Ihre Protokolle sind noch nicht versiegelt."
    ),
    "es": (
        "# Sellado de los registros\n\n"
        "Ninguna entrada de sellado: sus registros aún no están sellados."
    ),
    "it": (
        "# Sigillatura dei registri\n\n"
        "Nessuna voce di sigillatura: i suoi registri non sono ancora sigillati."
    ),
    "zh-CN": "# 记录封存\n\n暂无封存记录：您的记录尚未封存。",
}


def render_chain_attestation(
    language: str, *, entries: int, sealed_until: str, head_hash: str
) -> str:
    """State what the chain seals, in the reader's language.

    Args:
        language: Any locale spelling; normalised to the backend canon.
        entries: How many links the chain holds.
        sealed_until: When the last one was appended.
        head_hash: The chain's last hash.

    Returns:
        The attestation. An empty chain gets its own sentence rather than the
        normal one with blanks in it — « sealed up to  » would read as a bug.
    """
    canonical = normalize_language(language)
    if not entries or not head_hash:
        return CHAIN_ATTESTATION_EMPTY.get(canonical, CHAIN_ATTESTATION_EMPTY["en"]) + "\n"
    template = CHAIN_ATTESTATION.get(canonical, CHAIN_ATTESTATION["en"])
    return template.format(entries=entries, sealed_until=sealed_until, head_hash=head_hash) + "\n"


#: Title of the exported turn register (ADR-263, lot 6).
DECISION_REGISTER_HEADING: dict[str, str] = {
    "fr": "Journal des échanges",
    "en": "Turn journal",
    "de": "Verlaufsprotokoll",
    "es": "Registro de intercambios",
    "it": "Registro degli scambi",
    "zh-CN": "对话记录",
}

#: How a turn ended, in the reader's language. The third value is the one that
#: matters: a turn stopped for a confirmation, or abandoned, is a fact — and it
#: is precisely the one a conversation transcript shows badly.
DECISION_OUTCOME_WORDING: dict[str, dict[str, str]] = {
    "fr": {
        "answered": "répondu",
        "failed": "échoué",
        "interrupted": "interrompu",
    },
    "en": {"answered": "answered", "failed": "failed", "interrupted": "interrupted"},
    "de": {
        "answered": "beantwortet",
        "failed": "fehlgeschlagen",
        "interrupted": "unterbrochen",
    },
    "es": {
        "answered": "respondido",
        "failed": "fallado",
        "interrupted": "interrumpido",
    },
    "it": {
        "answered": "risposto",
        "failed": "fallito",
        "interrupted": "interrotto",
    },
    "zh-CN": {"answered": "已回复", "failed": "失败", "interrupted": "中断"},
}


#: Why a turn stopped short, in the reader's language. Operator codes
#: (``max_iterations``, ``compute_budget``) mean nothing to the person whose
#: turn it was, and showing « interrupted » without the reason would be the
#: half-truth this programme exists to remove.
STOP_REASON_WORDING: dict[str, dict[str, str]] = {
    "fr": {
        "max_iterations": "trop d'étapes",
        "compute_budget": "budget de calcul atteint",
        "tool_budget": "budget d'outils atteint",
    },
    "en": {
        "max_iterations": "too many steps",
        "compute_budget": "compute budget reached",
        "tool_budget": "tool budget reached",
    },
    "de": {
        "max_iterations": "zu viele Schritte",
        "compute_budget": "Rechenbudget erreicht",
        "tool_budget": "Werkzeugbudget erreicht",
    },
    "es": {
        "max_iterations": "demasiadas etapas",
        "compute_budget": "presupuesto de cálculo alcanzado",
        "tool_budget": "presupuesto de herramientas alcanzado",
    },
    "it": {
        "max_iterations": "troppe tappe",
        "compute_budget": "budget di calcolo raggiunto",
        "tool_budget": "budget degli strumenti raggiunto",
    },
    "zh-CN": {
        "max_iterations": "步骤过多",
        "compute_budget": "已达算力预算",
        "tool_budget": "已达工具预算",
    },
}


def assert_stop_reason_wording_completeness() -> None:
    """Refuse the boot when a stop condition has no wording.

    An ADR-085 guard reading the PREDICATE rather than a list: the stop
    conditions live in ``react_exit_reason`` (ADR-248 invariant 2 — one
    predicate, two readers), and a third one shipped there without a wording
    would print its raw code at a user, in five languages out of six, and only
    to the people whose turn hit it. Which is exactly what happened: the table
    covered two of the three that already existed.

    Raises:
        AssertionError: When a returned condition has no wording.
    """
    import ast
    import inspect

    from src.domains.agents.utils import react_budget

    tree = ast.parse(inspect.getsource(react_budget.react_exit_reason))
    conditions = {
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    assert conditions, "the stop predicate returns no readable condition"

    missing = [
        f"{language}/{condition}"
        for language in SUPPORTED_LABEL_LANGUAGES
        for condition in sorted(conditions - set(STOP_REASON_WORDING.get(language, {})))
    ]
    assert not missing, (
        "stop conditions with no wording: "
        + ", ".join(missing)
        + ". Add them to STOP_REASON_WORDING — an archive must not print a "
        "stored code at the person whose turn it was."
    )


def render_stop_reason(reason: str, language: str) -> str:
    """Say why a turn stopped short, in the reader's language.

    Never raises, and never blanks: a stop condition added tomorrow reads as
    its stored code rather than disappearing — honest, and legible enough that
    someone can look it up.

    Args:
        reason: The stored code.
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The wording.
    """
    table = STOP_REASON_WORDING.get(normalize_language(language), STOP_REASON_WORDING["en"])
    return table.get(reason, reason)


def render_decision_heading(language: str) -> str:
    """Title the exported turn register in the reader's language.

    Args:
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The heading.
    """
    return DECISION_REGISTER_HEADING.get(
        normalize_language(language), DECISION_REGISTER_HEADING["en"]
    )


def render_decision_outcome(outcome: str, language: str) -> str:
    """Say how a turn ended, in the reader's language.

    Never raises: an export must not fail because an outcome was added and its
    wording has not landed yet. The unknown value is returned as it is stored,
    which is honest and readable, rather than replaced by a blank.

    Args:
        outcome: The stored value (``answered`` | ``failed`` | ``interrupted``).
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The wording.
    """
    table = DECISION_OUTCOME_WORDING.get(
        normalize_language(language), DECISION_OUTCOME_WORDING["en"]
    )
    return table.get(outcome, outcome)


def assert_decision_wording_completeness() -> None:
    """Refuse the boot when a turn outcome has no wording.

    An ADR-085 guard, for the same reason as its neighbours: a value added to
    ``DecisionOutcome`` without a wording would render as its raw stored code in
    an account archive — silently, in five languages out of six, and only for
    the users unlucky enough to hit that outcome.

    Raises:
        AssertionError: When a value or a language is missing.
    """
    from src.domains.agents.effects.models import DecisionOutcome

    expected = {member.value for member in DecisionOutcome}
    missing: list[str] = []
    for language in SUPPORTED_LABEL_LANGUAGES:
        table = DECISION_OUTCOME_WORDING.get(language)
        if table is None:
            missing.append(f"language {language}")
            continue
        for value in sorted(expected - set(table)):
            missing.append(f"{language}/{value}")

    assert not missing, (
        "decision outcomes with no wording: "
        + ", ".join(missing)
        + ". Add them to DECISION_OUTCOME_WORDING — an archive must not print a "
        "stored code at a reader."
    )
