"""Wizard terminal messages (en/fr).

Every id carries BOTH wizard languages with identical placeholders — pinned
by ``tests/test_i18n.py``. Application (6-language) i18n is a backend/web
concern; this table only speaks to the installing operator.
"""

from __future__ import annotations

MESSAGES: dict[str, dict[str, str]] = {
    "question.wizard_language": {
        "en": "Installer language (en/fr)",
        "fr": "Langue de l'installateur (en/fr)",
    },
    "question.exposure": {
        "en": "How will LIA be reached? lan = plain LAN ports, proxy = behind your own reverse proxy, caddy = managed HTTPS with Caddy",
        "fr": "Comment LIA sera-t-il accessible ? lan = ports LAN simples, proxy = derrière votre propre reverse proxy, caddy = HTTPS géré par Caddy",
    },
    "question.server_host": {
        "en": "Server hostname or IP the browsers will use (e.g. 192.168.1.50)",
        "fr": "Nom d'hôte ou IP du serveur vu par les navigateurs (ex. 192.168.1.50)",
    },
    "question.web_domain": {
        "en": "Public web domain (e.g. lia.example.org)",
        "fr": "Domaine web public (ex. lia.example.org)",
    },
    "question.api_domain": {
        "en": "Public API domain (e.g. api.example.org)",
        "fr": "Domaine API public (ex. api.example.org)",
    },
    "question.caddy_email": {
        "en": "Email for Let's Encrypt/ACME notifications",
        "fr": "Email pour les notifications Let's Encrypt/ACME",
    },
    "question.admin_email": {
        "en": "Administrator email address",
        "fr": "Adresse email de l'administrateur",
    },
    "question.admin_name": {
        "en": "Administrator display name",
        "fr": "Nom affiché de l'administrateur",
    },
    "question.default_language": {
        "en": "Default application language",
        "fr": "Langue par défaut de l'application",
    },
    "question.observability": {
        "en": "Enable the observability stack (Prometheus/Grafana)? yes/no",
        "fr": "Activer la pile d'observabilité (Prometheus/Grafana) ? yes/no",
    },
    "question.self_diagnostics": {
        "en": "Enable LIA's self-diagnostics? The assistant checks its own health, keeps an incident history and, with the observability profile, turns alerts into in-app incidents (yes/no)",
        "fr": "Activer l'auto-diagnostic de LIA ? L'assistante surveille sa propre santé, tient un historique d'incidents et, avec le profil observabilité, transforme les alertes en incidents dans l'application (yes/no)",
    },
    "question.skill_sandbox": {
        "en": "Enable the script sandbox (mounts the Docker socket; also starts the egress proxy through which a script the assistant writes may reach the web with the person's own connector keys — switchable off in the admin panel)? yes/no",
        "fr": "Activer le bac à sable des scripts (monte la socket Docker ; démarre aussi le proxy de sortie par lequel un script écrit par l'assistante peut atteindre le web avec les clés des connecteurs de la personne — désactivable dans le panneau d'administration) ? yes/no",
    },
    "question.live_mode": {
        "en": "Enable the Live voice mode? Each person talks with LIA in real time on a live model they connect with their OWN Gemini, OpenAI or ElevenLabs key; the instance pays only what LIA itself spends inside a session (yes/no)",
        "fr": "Activer le mode Live vocal ? Chaque personne parle avec LIA en temps réel sur un modèle live qu'elle connecte avec SA PROPRE clé Gemini, OpenAI ou ElevenLabs ; l'instance ne paie que ce que LIA elle-même dépense dans une session (yes/no)",
    },
    "question.admin_password": {
        "en": "Administrator password (min {min_length} chars, {min_uppercase} uppercase, {min_digits} digits, {min_special} special; input hidden)",
        "fr": "Mot de passe administrateur (min {min_length} caractères, {min_uppercase} majuscules, {min_digits} chiffres, {min_special} spéciaux ; saisie masquée)",
    },
    "question.provider_key": {
        "en": "API key for {provider} (required by the seeded core; input hidden)",
        "fr": "Clé API pour {provider} (requise par le cœur seedé ; saisie masquée)",
    },
    "error.invalid_value": {
        "en": "Invalid value for [{key}], please retry.",
        "fr": "Valeur invalide pour [{key}], veuillez réessayer.",
    },
    "info.key_unverified": {
        "en": "Could not verify the {provider} key over the network; continuing (it will be exercised after start).",
        "fr": "Impossible de vérifier la clé {provider} sur le réseau ; on continue (elle sera exercée après le démarrage).",
    },
    "info.key_invalid": {
        "en": "The {provider} endpoint rejected this key (HTTP 401/403). You can still continue and fix it later in the Admin UI.",
        "fr": "Le point d'accès {provider} a rejeté cette clé (HTTP 401/403). Vous pouvez continuer et la corriger ensuite dans l'interface d'administration.",
    },
}


def msg(message_id: str, language: str, **kwargs: object) -> str:
    """Render one message; unknown ids raise (completeness is a contract)."""
    return MESSAGES[message_id][language].format(**kwargs)
