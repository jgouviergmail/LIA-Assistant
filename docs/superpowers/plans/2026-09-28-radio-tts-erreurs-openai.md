# Erreurs TTS OpenAI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conserver la nature structurelle des erreurs TTS OpenAI afin d’éviter les retries d’erreurs permanentes sans diminuer le budget de récupération des erreurs transitoires.

**Architecture:** Un traducteur pur convertit les exceptions SDK en TTSProviderError. Une indication facultative de retryabilité préserve les cas spécifiques du SDK sans changer le comportement par défaut des autres adaptateurs. Le client continue d’appeler le SDK avec ses paramètres actuels.

**Tech Stack:** Python, openai SDK déjà installé, httpx MockTransport, pytest/asyncio, structlog.

**Spec:** [Conception et contraintes communes](../specs/2026-09-28-radio-tts-correctifs-cibles-design.md).

**Statut : préparation uniquement. Les étapes ci-dessous sont à réaliser ultérieurement.**

## Global Constraints

- Même fournisseur, modèle, voix, texte et paramètres de synthèse.
- Aucun changement des budgets de tentatives, timeouts, cooldown, sémaphores ou ordonnancement.
- Pas de nouvelle dépendance, aucun appel réseau payant, aucune modification frontend.
- Maintenir l’exception d’annulation et la fermeture du client.
- Les autres adaptateurs conservent leur politique quand aucune indication facultative n’est fournie.
- La baseline de classification par texte doit diminuer après retrait des six comparaisons du client actuel.

## Review Focus

1. HTTP 409 ou x-should-retry=true : conserver une possibilité de récupération — tâches A1/A3.
2. Message contenant « generate », « rate », « key » ou « timeout » avec un statut contradictoire : le texte ne décide rien — A1/A2.
3. Retry-After absent, date, millisecondes, valeur négative ou non finie : ne jamais produire un délai invalide — A1.
4. Annulation pendant le SDK ou ses retries : aucune conversion en erreur récupérable, ressources fermées — A2/A3.
5. Erreur déjà structurée et réponse vide : conserver leur identité et ne pas doubler les métriques — A2.

---

## État actuel et frontières

- openai_tts_client.py:87 construit AsyncOpenAI sans toucher à max_retries.
- synthesize appelle audio.speech.create puis récupère response.content.
- Le bloc d’exception vers la ligne 195 classe le message libre et oublie status_code et Retry-After.
- TTSProviderError.transient sait déjà distinguer une erreur HTTP permanente à condition de connaître son statut ; 409 n’est pas dans son ensemble actuel.
- La radio lit transient dans production._transient et rate_limited/retry_after_seconds dans _rate_limit_wait. Elle conserve actuellement son plafond d’attente. Ce plan transporte le délai exact mais ne supprime pas ce plafond.
- VoiceCommentService utilise aussi cette factory. Il faut qualifier ses erreurs et sa fermeture ; aucun changement de ses requêtes nominales n’est prévu.

Ne pas appeler une méthode privée du SDK pour classifier : son code local sert à caractériser le comportement, pas d’API de production à importer.

## Décision de contrat

Ajouter à TTSProviderError un argument optionnel, uniquement par mot-clé :

```python
retryable: bool | None = None
```

La propriété transient lit d’abord cette indication lorsqu’elle est définie ; sinon elle applique exactement les règles actuelles. La conserver dans un attribut privé, sans modifier le schéma des réponses publiques. rate_limited continue de décrire la nature quota de l’erreur : une erreur quota peut explicitement ne pas autoriser un retry.

Créer dans le futur module openai_tts_errors.py :

```python
def classify_openai_tts_error(
    error: Exception, *, now: datetime
) -> tuple[TTSProviderError, str]:
    """Retourner l'erreur structurée et le label de métrique existant."""

def retry_after_seconds(
    headers: Mapping[str, str], *, now: datetime
) -> float | None:
    """Durée valide, sans appliquer la politique d'attente de l'appelant."""
```

Ces signatures sont des contrats de conception ; aucune fonction n’est créée pendant cette préparation. now est UTC et conscient de son fuseau. Les en-têtes viennent de httpx.Headers, dont la recherche est insensible à la casse.

### Table de classification à implémenter

| Entrée | code | transient | label existant |
|---|---|---|---|
| APITimeoutError | provider_timeout | true | network_error |
| APIConnectionError hors timeout | provider_network_error | true | network_error |
| APIStatusError 429 | provider_rate_limited | true par défaut | rate_limit |
| APIStatusError 408 | provider_http_error + statut | true | synthesis_error |
| APIStatusError 409 | provider_http_error + statut, indication true | true | synthesis_error |
| APIStatusError 5xx | provider_http_error + statut | true par défaut | synthesis_error |
| APIStatusError 401/403 | provider_http_error + statut | false par défaut | auth_error |
| Autre APIStatusError 4xx | provider_http_error + statut | false par défaut | synthesis_error |
| Exception non classée | provider_http_error sans statut | comportement conservateur actuel : true | synthesis_error |

Tester APITimeoutError avant APIConnectionError : le premier est un sous-type du second. Un statut 401 signifie refus d’authentification, pas absence prouvée de clé dans la configuration ; api_key_missing reste réservé au refus de configuration existant.

Pour APIStatusError, x-should-retry exactement "true" ou "false" fournit l’indication prioritaire ; une autre valeur est ignorée. En son absence, seul 409 demande ici une indication explicite true ; les autres statuts utilisent le contrat existant. Cette indication ne modifie pas le nombre maximal d’essais. Le cas d’un Retry-After supérieur au maximum géré par le SDK reste gouverné par les couches actuelles ; ne pas recopier un ordonnanceur complet dans le traducteur.

details contient seulement status_code lorsqu’il existe et exception_type. La chaîne __cause__ reste conservée avec raise ... from error. Utiliser un message diagnostic borné (« OpenAI TTS HTTP 400 », par exemple), pas le corps fournisseur susceptible de reprendre le texte envoyé. Le journal existant conserve type, statut, code, longueur du texte et modèle, sans classifier ou republier str(error).

### Parsing du délai

Ordre : retry-after-ms valide, puis Retry-After numérique valide, puis Retry-After sous forme de date HTTP. Accepter les fractions numériques pour compatibilité avec le SDK. Les valeurs numériques doivent être finies et positives ou nulles. Une date passée donne 0.0 ; une date illisible donne None. Une valeur invalide dans l’en-tête millisecondes permet d’essayer l’en-tête standard. Ne pas plafonner la valeur dans le parseur.

## Task A1 — contrat et traduction purs

**Files:**

- Modify: apps/api/src/domains/voice/exceptions.py.
- Create: apps/api/src/domains/voice/openai_tts_errors.py.
- Test: apps/api/tests/unit/domains/voice/test_tts_provider_error.py.
- Create test: apps/api/tests/unit/domains/voice/test_openai_tts_errors.py.

**Interfaces:** Consomme les types publics APIStatusError, APIConnectionError, APITimeoutError du SDK ; produit les deux fonctions et l’argument optionnel définis ci-dessus.

- [ ] Écrire un test de l’indication facultative : None conserve tous les comportements actuels ; true autorise le 409 OpenAI ; false rend définitif un 429 explicitement refusé au retry.
- [ ] Construire de vraies exceptions SDK à partir de httpx.Request/httpx.Response, sans MagicMock pour leurs attributs métier.
- [ ] Couvrir toute la table et les deux valeurs de x-should-retry ; varier le texte sans modifier le résultat attendu.
- [ ] Couvrir le parseur : "7", "0", "0.5", millisecondes "1250", date UTC future et passée, absent, vide, invalide, négatif, NaN, infini ; vérifier la priorité et le repli d’un en-tête invalide.
- [ ] Exécuter les tests avant modification et conserver les échecs attendus correspondant aux défauts.
- [ ] Implémenter le traducteur pur et l’indication optionnelle. Garder les constantes et responsabilités dans le domaine voice, sans dépendre du domaine radio.
- [ ] Relancer la suite de contrat existante et la nouvelle suite ; vérifier que les autres fournisseurs sans indication gardent leurs résultats.

Exemple d’oracle à écrire :

```python
request = httpx.Request("POST", "https://api.openai.com/v1/audio/speech")
response = httpx.Response(400, request=request)
source = BadRequestError("cannot generate, rate, key, timeout", response=response, body=None)
error, metric = classify_openai_tts_error(source, now=datetime(2026, 9, 28, tzinfo=UTC))
assert error.code == "provider_http_error"
assert error.details == {"status_code": 400, "exception_type": "BadRequestError"}
assert error.transient is False
assert metric == "synthesis_error"
```

## Task A2 — branchement du client, logs et métriques

**Files:**

- Modify: apps/api/src/domains/voice/openai_tts_client.py.
- Create test: apps/api/tests/unit/domains/voice/test_openai_tts_client.py.
- Modify measured baseline: apps/api/tests/unit/domains/agents/message_classification_baseline.json.

**Interfaces:** Consomme classify_openai_tts_error ; conserve la signature publique de synthesize, synthesize_base64 et close.

- [ ] Préparer un vrai AsyncOpenAI avec httpx.AsyncClient(transport=MockTransport(...)) et une clé factice. Remplacer la construction du SDK au point d’import du module LIA ; ne pas simuler audio.speech.create.
- [ ] Capturer le corps nominal et vérifier modèle, voix, input, speed, response_format ainsi que les bytes/base64 retournés.
- [ ] Vérifier une seule émission logique des métriques d’erreur pour une erreur SDK épuisée ; utiliser un nom de voix de test propre pour lire des deltas de compteurs.
- [ ] Vérifier qu’un payload vide conserve provider_invalid_response et que l’exception TTS déjà construite n’est pas retraitée.
- [ ] Remplacer uniquement la classification du bloc except Exception ; conserver la branche except TTSProviderError et la propagation de CancelledError.
- [ ] Vérifier les logs sur une exception dont le corps comporte une chaîne sentinelle privée : seuls les champs structurés autorisés apparaissent.
- [ ] Mesurer le guard de classification par sous-chaîne puis retirer son entrée OpenAI devenue nulle. Ne changer aucune autre entrée de baseline.
- [ ] Vérifier la fermeture du client sur succès et échec, sans warning de transport.

Dans la future implémentation, le bloc d’erreur consomme le traducteur sous cette forme :

```python
failure, metric_error_type = classify_openai_tts_error(error, now=datetime.now(UTC))
# Les métriques existantes sont émises ici une seule fois.
raise failure from error
```

## Task A3 — compter les appels réellement exécutés

**Files:**

- Create test: apps/api/tests/unit/domains/radio/test_openai_tts_attempts.py.
- Reuse behavior: apps/api/src/domains/radio/production.py, sans modifier sa politique.

**Interfaces:** Un vrai client TTS OpenAI traverse la fonction de retry d’une ligne radio. MockTransport fournit les réponses HTTP et compte ses invocations. L’attente est remplacée par une horloge/attente contrôlée dans les tests seulement ; les décisions de retry ne sont pas simulées.

- [ ] Script HTTP 400 → toujours 400 : le transport est appelé une seule fois et l’erreur finale reste permanente.
- [ ] Répéter avec 401, 403, 404 et 422, sans x-should-retry=true.
- [ ] Script 500, 500, 500, puis 200 : la quatrième requête doit réussir, prouvant que la reprise par la radio après épuisement du premier cycle SDK reste possible.
- [ ] Script 409, 409, 409, puis 200 : même possibilité de récupération.
- [ ] Script 400 avec x-should-retry=true trois fois, puis 200 : l’indication explicite conserve cette récupération.
- [ ] Script 429 avec x-should-retry=false : arrêt conforme à l’indication, sans retry ajouté par LIA.
- [ ] Réponse finale 429 avec délai : vérifier les métadonnées transmises, sans présenter ce test comme une correction du plafond du cooldown.
- [ ] Annuler pendant l’attente/réponse : CancelledError se propage, aucune requête nouvelle ni coût fictif.
- [ ] Vérifier successivement un usage radio et un usage direct du client : paramètres nominaux et contrat de sortie identiques.

## Vérifications de la réalisation

Depuis apps/api, après création des fichiers :

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/domains/voice/test_tts_provider_error.py tests/unit/domains/voice/test_openai_tts_errors.py tests/unit/domains/voice/test_openai_tts_client.py tests/unit/domains/voice/test_tts_factory.py tests/unit/domains/radio/test_openai_tts_attempts.py tests/unit/domains/radio/test_production.py tests/unit/domains/agents/test_no_message_substring_classification_guard.py --no-cov -q
```

Puis portes communes de la spécification. Aucun appel au fournisseur réel n’est nécessaire. Si le SDK installé a changé, requalifier ses séquences avant de modifier une attente du test.

## Livraison et retour arrière

Un changement indépendant, sans migration ni configuration nouvelle. Vérifier les synthèses nominales, les codes d’erreur et les métriques existantes sur le candidat. Un retour au commit antérieur rétablit le comportement initial ; il ne nécessite aucun traitement de données.

Le résultat accepté est une classification exacte avec des requêtes inutiles supprimées dans les scénarios permanents vérifiés. La baisse moyenne d’appels ou de facture en production dépend de la fréquence de ces scénarios.
