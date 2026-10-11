# Serveurs de modèles locaux : analyse et plan d’implémentation

> **Exécution future :** strictement inline, avec `superpowers:executing-plans`, sans sous-agent. Ce dossier est une proposition à examiner ; aucun code métier de cette extension n’est implémenté.

**Date :** 2026-10-06. **État :** analyse terminée ; sondes réelles des API stables Ollama, llama.cpp et LM Studio exécutées, avec limites et écarts conservés. oMLX : tests de contrat exécutés, inférence non qualifiée faute de Mac.

**Objectif :** configurer oMLX, llama.cpp et LM Studio dans les mêmes parcours d’administration et d’exécution LLM qu’Ollama, en préservant le transport natif Ollama et les contrats de capacités, contexte, comptabilité et persistance de LIA.

**Architecture proposée :** trois identités de fournisseur supplémentaires, un client Chat Completions partagé, des lecteurs de découverte propres aux serveurs et une résolution commune des connexions. Les capacités effectives résultent du modèle, du serveur, de sa configuration et du client installé ; le nom du modèle ne suffit jamais.

**Arbitrage confirmé par le propriétaire :** les quatre familles locales ont un coût fixé à zéro. Aucun tarif configurable ni mode de facturation d’endpoint local n’est introduit. L’isolation fournisseur/modèle protège leurs capacités et leur contexte ; le suivi des tokens reste distinct du coût monétaire.

**Qualification réalisée :** [rapport, versions, matrice et preuves JSON](../qualification/2026-10-06/README.md). Le propriétaire confirme ne pas disposer de Mac : aucune sonde d’inférence oMLX n’est présentée comme réussie. Les tests locaux n’ont appelé aucun fournisseur payant.

**Stack :** FastAPI, SQLAlchemy/PostgreSQL, Redis, LangChain, SDK OpenAI déjà installés ; Next.js/React/TypeScript et composants de formulaires existants. Aucune dépendance supplémentaire nécessaire au transport initial.

**Spécification :** les sections 1 à 8 de ce document. **Plan :** sections 9 à 11. Les interfaces décrites sont proposées, pas présentées comme déjà disponibles.

## 1. Alignement et décisions de périmètre

### 1.1 Intention fonctionnelle

L’administrateur doit pouvoir choisir l’infrastructure d’inférence disponible sur sa machine ou son réseau, enregistrer son adresse et son éventuel secret, consulter ses modèles, puis affecter un modèle à un poste LLM. Ce choix doit fonctionner dans les appels réellement effectués par l’assistant, au-delà d’une requête de démonstration.

Valeur attendue : autonomie d’hébergement, utilisation du matériel disponible, maîtrise des données transmises et du coût fournisseur. Un modèle local ne rend pas automatiquement toute l’application locale : recherche web, connecteurs, embeddings, voix et autres fournisseurs conservent leurs propres parcours.

Le fournisseur, le modèle, la quantification, le template de chat et les limites matérielles sont des dimensions distinctes. Une conformité HTTP OpenAI ne prouve ni la qualité des plans, ni la fiabilité des appels d’outils, ni l’acceptation de tous les schémas JSON de LIA.

### 1.2 Inclus

- Administration d’un endpoint par fournisseur et par déploiement, comme le dispositif actuel ; les quatre familles peuvent coexister.
- Identités proposées : `ollama` conservée, `omlx`, `llamacpp`, `lmstudio`. Libellés : Ollama, oMLX, llama.cpp, LM Studio.
- Texte, streaming, appels d’outils, sorties structurées ; vision seulement pour un modèle et un endpoint qui la déclarent et la passent en qualification.
- Tous les postes de nature `chat`, y compris les consommateurs hors conversation, soumis à leurs capacités requises et leurs propres délais.
- Connexion distante HTTP(S), sur le LAN, via un proxy, ou à un serveur sur l’hôte Docker.
- Découverte des modèles, saisie explicite d’un identifiant et déclaration administrateur des caractéristiques manquantes.
- Observation des paramètres envoyés, du fournisseur réellement utilisé, du modèle demandé et du modèle annoncé, des tokens, délais, reprises et coûts.

### 1.3 Limites explicites

- Plusieurs endpoints de la **même** famille, routage GPU, équilibrage ou sélection par compte : évolution distincte. Le modèle actuel possède une connexion globale par fournisseur et ne possède pas de clés LLM par utilisateur.
- Installation, téléchargement, chargement forcé ou déchargement des modèles : opérés par le serveur. La découverte LIA reste en lecture et ne déclenche pas d’inférence.
- Embeddings, rerankers, TTS/STT, images et sessions Live : pas activés par le seul ajout de ces fournisseurs chat. Leurs contrats sont différents, même si un serveur offre des routes portant ces noms.
- Un chat vocal délégué au moteur LIA peut bénéficier d’un poste chat local ; cela ne crée pas un fournisseur Live ni un moteur TTS local.
- Responses API, conversations persistées sur le serveur et MCP exécuté par le serveur : hors transport initial. LangGraph et LIA continuent de posséder l’historique, le consentement, les outils et les registres.

Ces limites sont des choix techniques dérivés du dispositif existant, pas des questions bloquantes adressées au métier.

## 2. Preuves et contre-vérifications du dispositif actuel

L’inspection a été faite sur le checkout dont HEAD est `b9f1ab77ee4c4835f7165f538fdc2534ac7df262`, avec des modifications concurrentes présentes. Les conclusions ci-dessous portent sur les fichiers réellement lus, pas sur les modèles par défaut ni sur une configuration présumée de production.

| Hypothèse initiale | Vérification et contre-vérification | Conclusion |
|---|---|---|
| Ollama utilise encore le pont OpenAI | [Adapter](../../../apps/api/src/infrastructure/llm/providers/adapter.py), dispatch dédié ; [client](../../../apps/api/src/infrastructure/llm/providers/ollama_chat.py), sous-classe de `ChatOllama` ; [ADR-267](../../architecture/ADR-267-Ollama-Native-Provider-And-Discovered-Capabilities.md) ; tests Docker | Faux dans le code actuel. Le transport natif est un invariant à conserver. |
| Ajouter une URL à OpenAI suffirait | `_get_base_url` autorise déjà des overrides de plusieurs fournisseurs ; le dispatch OpenAI sélectionne Responses pour certains noms ; lecture du SDK installé | Un contournement peut servir une requête simple, mais hérite de comportements OpenAI et d’une identité comptable incorrects. Ce n’est pas l’intégration cible. |
| La connexion contient déjà URL et secret séparés | [Modèles de configuration](../../../apps/api/src/domains/llm_config/models.py), [cache](../../../apps/api/src/domains/llm_config/cache.py), [schémas](../../../apps/api/src/domains/llm_config/schemas.py), [service](../../../apps/api/src/domains/llm_config/service.py) | La « clé » Ollama est l’URL chiffrée. Aucun couple URL + secret optionnel n’est offert par le contrat actuel. |
| Les capacités sont déjà isolées par fournisseur | [Cache des capacités](../../../apps/api/src/infrastructure/llm/model_capabilities_cache.py), `get(model_name)` et `merge_discovered` ; sonde isolée décrite ci-dessous | Faux : plusieurs dictionnaires sont indexés par nom de modèle seul. |
| Le catalogue accepte le même identifiant chez deux fournisseurs | [Modèle catalogue](../../../apps/api/src/domains/llm/models.py), `model_name` globalement unique ; [repository](../../../apps/api/src/domains/llm/repository.py) et [service](../../../apps/api/src/domains/llm/service.py), lookup par nom | Faux. Un changement de l’identité des lecteurs et de l’unicité SQL est nécessaire. |
| Les tarifs sont déjà isolés par fournisseur | [Cache tarifaire](../../../apps/api/src/infrastructure/cache/pricing_cache.py), [service tarifaire](../../../apps/api/src/domains/llm/pricing_service.py), [normalisation](../../../apps/api/src/core/llm_utils.py) | Faux : les index/lectures tarifaires utilisent le nom. Un endpoint local peut rencontrer le tarif d’un homonyme. |
| `/v1/models` fournit toutes les capacités | Comparaison avec la découverte native [Ollama](../../../apps/api/src/infrastructure/llm/providers/ollama_discovery.py) et sources officielles section 3 | Faux. Il faut distinguer identifiant découvert, métadonnées partielles et capacités éprouvées. |
| `context_window` règle tous les serveurs | [Résolution par poste](../../../apps/api/src/core/llm_config_helper.py), [ADR-278](../../architecture/ADR-278-Per-Slot-Context-Window.md), consommation dans l’adapter | Faux : ce champ est une notion LIA. Ollama l’exprime via `num_ctx` ; aucune traduction OpenAI universelle n’existe. |
| Le SDK OpenAI conservera le raisonnement local | Lecture dans `lia-api-dev` des fonctions de conversion des messages et deltas du SDK LangChain installé | Les conversions Chat Completions examinées ne conservent pas `reasoning_content`. Une adaptation du client est nécessaire. |
| `max_tokens` sera envoyé tel quel | Lecture Docker de `ChatOpenAI._get_request_payload` et de sa base | `ChatOpenAI` renomme en `max_completion_tokens` et transforme le rôle `system` pour certains noms. Le client partagé doit neutraliser ces heuristiques pour les serveurs locaux. |
| Le front est déjà générique | [Administration](../../../apps/web/src/components/settings/AdminLLMConfigSection.tsx), [helpers](../../../apps/web/src/components/settings/llm-config/configDialogHelpers.ts), [types](../../../apps/web/src/types/llm-config.ts) | La découverte, l’URL et les messages de provenance ont des branches `ollama`. Les helpers préfèrent parfois la métadonnée statique avant la découverte, contrairement à la priorité runtime. |
| Les postes configurés par l’administrateur sont bloqués sur une capacité absente | [Capability gate](../../../apps/api/src/infrastructure/llm/capability_gate.py) et mise à jour de configuration | Le runtime rapporte le désaccord et conserve le choix humain. Le front filtre ses propositions ; certains validateurs, notamment de raisonnement, refusent des valeurs invalides. Il faut préserver cette distinction. |
| Un fournisseur local dispense de quotas/comptabilité | [Usage guard](../../../apps/api/src/infrastructure/llm/usage_guard.py), [cost bearers](../../../apps/api/src/domains/usage_limits/cost_bearers.py), registre `PROVIDER_USAGE_CAPABILITIES` | Faux. Le coût fournisseur peut être nul, mais les tokens, l’attribution et les limites existantes restent significatifs. |

### 2.1 Vérification exécutée

Dans `lia-api-dev`, sans appel d’inférence réel :

```text
docker exec -w /app lia-api-dev python -m pytest
  tests/unit/infrastructure/llm/providers/test_ollama_chat.py
  tests/unit/infrastructure/llm/providers/test_ollama_urls.py
  tests/unit/infrastructure/llm/providers/test_ollama_discovered_profiles.py
  tests/unit/core/test_slot_context_window.py
  --no-cov -q -p no:cacheprovider
```

Résultat : **50 passed, 1 warning**, exit 0. L’avertissement est la dépréciation de `anyio.abc.BlockingPortal` dans Starlette TestClient. Ce résultat caractérise le socle existant ; il ne qualifie pas les nouveaux serveurs.

La sonde de collision a exécuté dans un processus Python indépendant : fusion d’un profil synthétique `shared-model` pour Ollama, fenêtre 8 192, puis du même identifiant pour LM Studio, fenêtre 32 768. La lecture unique a répondu `lmstudio / 32768`. Le premier profil n’était donc plus accessible indépendamment. Aucun réseau, aucune base ni cache du processus API servant les utilisateurs n’a été modifié.

La lecture du SDK a confirmé les comportements du payload et de conversion mentionnés dans la matrice. Il n’y a eu aucun appel fournisseur payant, aucun commit, push ou déploiement.

La contre-vérification du prix utilise aussi un processus Docker indépendant et un snapshot synthétique, sans DB ni Redis. Le calculateur réel `get_cached_cost_usd_eur`, qui n’accepte pas le fournisseur, applique le tarif payant de `shared-model` à un appel identifié comme local : 1 000 tokens d’entrée et 100 de sortie donnent un coût non nul. La [preuve](../qualification/2026-10-06/local-cost-collision.json) conserve paramètres et résultat. Le court-circuit local doit donc précéder le lookup, et l’identité doit atteindre tous les calculateurs concernés.

Le contrôle `task lint:docs:preview` a aussi terminé avec exit 0 : aucun lien cassé, chemin périmé ou document orphelin dans la documentation vivante, aucune dérive des faits contrôlés, maps cohérentes. Le rapport conserve des signalements historiques du dépôt ; ils ne constituent pas des corrections effectuées dans cette analyse.

## 3. Contrats des serveurs : sources officielles

Sources consultées le 2026-10-06. Les pages et branches amont peuvent évoluer ; leurs contrats ne valent pas qualification d’un binaire déployé. Le lot 0 fige versions/builds, modèle, quantification et template effectivement testés.

| Serveur | Transport retenu | Découverte et information utile | Conséquence pour LIA |
|---|---|---|---|
| Ollama | API native actuelle | `/api/tags`, `/api/show` ; capacités et contexte déjà intégrés | Conserver `think`, `num_ctx`, `num_predict`, `format`, usage natif et traçage. L’API OpenAI ne règle pas universellement le contexte. [Documentation Ollama](https://docs.ollama.com/api/openai-compatibility) |
| oMLX | `/v1/chat/completions` | Le code officiel de `/v1/models` expose l’identifiant, ses alias et `max_model_len` | Lecture dédiée des métadonnées présentes, sans fabriquer tools/vision. Hébergement Apple Silicon à distinguer du poste Windows hébergeant LIA. [Projet](https://github.com/jundot/omlx), [listing officiel](https://github.com/jundot/omlx/blob/main/omlx/server.py) |
| llama.cpp | `/v1/chat/completions` | `/v1/models` ; `/props` avec `n_ctx`, template, capacités du template, modalités et build ; variante router multi-modèles | Le contexte alloué, le template et les modalités appartiennent au runtime. Lire en GET uniquement ; gérer les métadonnées absentes pendant le chargement. [Serveur officiel](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) |
| LM Studio | `/v1/chat/completions` | `/v1/models` ; enrichissement `/api/v1/models` : instances chargées, contexte de l’instance, maximum du modèle, vision et entraînement aux outils | Ne pas confondre modèle disponible et instance chargée, ni maximum théorique et contexte actif. [API compatible](https://lmstudio.ai/docs/developer/openai-compat), [listing natif](https://lmstudio.ai/docs/developer/rest/list) |

oMLX propose un secret d’API et documente des contraintes supplémentaires pour une écoute réseau ; LM Studio propose aussi des tokens et peut fonctionner sans authentification suivant sa configuration. Une URL seule ne couvre donc pas les connexions supportées. [Authentification oMLX](https://github.com/jundot/omlx#cli-configuration), [authentification LM Studio](https://lmstudio.ai/docs/developer/core/authentication).

Les outils LM Studio dépendent du modèle et de son template, et ses flux fragmentent les noms et arguments. `trained_for_tool_use` n’est pas la preuve d’une boucle LIA réussie. [Tool Use](https://lmstudio.ai/docs/developer/openai-compat/tools).

LM Studio documente le JSON Schema sur Chat Completions. Le code oMLX distingue les demandes de schéma et la disponibilité d’un décodage contraint : une demande `strict` peut rencontrer une dégradation. LIA doit donc valider le résultat et qualifier le schéma réellement utilisé. [Structured Output LM Studio](https://lmstudio.ai/docs/developer/openai-compat/structured-output), [implémentation oMLX](https://github.com/jundot/omlx/blob/main/omlx/server.py).

Le schéma oMLX accepte des commandes de raisonnement propres au template ; llama.cpp expose aussi des réglages de template. Une liste d’options native ne prouve pas que le même contrôle est disponible sur Chat Completions. En particulier, les champs de l’API native LM Studio ne seront pas transposés sans preuve sur la route retenue. [Requête oMLX](https://github.com/jundot/omlx/blob/main/omlx/api/openai_models.py), [capacités de template llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/jinja/caps.h), [chat natif LM Studio](https://lmstudio.ai/docs/developer/rest/chat).

### 3.1 Arbitrages issus des sondes stables

- LM Studio, daemon stable llmster 0.0.25+1 : `tool_choice` par objet nommé est refusé ; `required` avec le seul outil visé passe en réponse complète, streaming et SDK. Le profil doit traduire ce choix en filtrant l’offre à cet outil, avec tests d’historique et sans modifier les autorisations. `json_object` est également refusé : choisir JSON Schema qualifié ou prompt + validation, sans retry du même payload refusé.
- llama.cpp 0.6.0/b11429 et ce daemon LM Studio répondent avec leur modèle chargé à une demande de modèle inexistant dans la configuration à une instance testée. La découverte vérifie l’identité avant l’appel, et la réponse est contrôlée après l’appel ; aucun fallback local implicite n’est créé par LIA.
- `max_completion_tokens` envoyé par le SDK installé a fonctionné dans ces trois combinaisons. Sa présence n’est donc pas présentée comme une panne constatée de ces API stables. Les heuristiques de famille OpenAI restent à neutraliser pour un contrat local explicite, indépendamment du nom choisi.
- Le raisonnement est présent sur les flux bruts et absent des chunks ChatOpenAI examinés sur les trois serveurs. Le client compatible doit le conserver ; le client natif Ollama reste dédié.
- Les schémas simples, imbriqués et `ParameterItem` passent sur les trois serveurs. Le replay du `ExecutionPlan` complet passe sur llama.cpp mais est rejeté par les validateurs métier sur Ollama et LM Studio : le modèle de qualification omet ou renomme la raison de clarification dans le champ libre `metadata`. La demande `strict` et un JSON syntaxiquement valide ne garantissent pas les règles métier. Aucune capacité globale de planning n’est déduite de ces sondes.
- Les trois serveurs ont refusé le dépassement du contexte alloué, et ont répondu après fermeture de flux et timeout client. Cela ne démontre ni l’arrêt immédiat du calcul serveur ni la capacité d’un GPU en production.

Les builds, poids, paramètres et résultats exacts sont conservés dans le rapport lié ci-dessus. Ces constatations deviennent des fixtures de caractérisation du lot 0 puis des exigences du client et des lecteurs de découverte.

## 4. Architecture cible et arbitrages

| Option examinée | Arbitrage |
|---|---|
| Reconfigurer le fournisseur `openai` vers chaque serveur | Écartée : identité de dépense/capacités ambiguë, coexistence limitée et heuristiques SDK OpenAI déjà constatées. |
| Ajouter un unique fournisseur générique avec une seule URL | Écartée pour cette version : il ne représente pas simultanément les trois familles selon le modèle de connexion actuel. Une abstraction interne commune suffit. |
| Copier intégralement le parcours Ollama trois fois | Écartée : endpoints/paramètres natifs incompatibles et duplication des contrôles/cache/comptabilité. |
| Utiliser des SDK natifs différents pour toutes les familles | Écartée pour le transport initial : ils introduiraient plusieurs contrats d’historique et de streaming ; la route Chat Completions est officiellement implémentée par ces serveurs. Les métadonnées natives restent exploitées en lecture. |
| Trois fournisseurs distincts, transport commun et profils serveur | Retenue : coexistence suivant les patterns d’administration, mécanismes partagés et comportement explicite par surface. Ollama conserve son client natif. |

La règle du dépôt sur les clients natifs protège les fonctions qu’un pont ne sait pas exprimer. Elle impose ici de conserver Ollama natif. Pour les trois autres familles, LIA cible une route officiellement implémentée par le serveur et ne prétend pas que ce protocole exprime ses fonctions de gestion natives. Les fonctions qui ne passent pas sur cette route restent non proposées, ou ont un lecteur natif explicite. Aucun comportement propre au cloud OpenAI n’est attribué au serveur.

### 4.1 Identité : fournisseur, modèle exact, génération de connexion

Adopter `(provider, model_id)` pour le catalogue et les capacités. Pour les faits acquis auprès d’un endpoint, ajouter la génération de connexion à la clé de cache/qualification. Les fournisseurs locaux sont exclus de toute résolution tarifaire : leur coût est toujours zéro, même si leur identifiant ressemble à celui d’un modèle cloud payant.

- Le `model_id` transmis au serveur reste **exact** : conserver slash, tag, alias, quantification et suffixe de date. Aucun préfixe interne n’est envoyé sur le fil.
- Remplacer l’unicité globale SQL par `UNIQUE(provider, model_name)`, conserver les UUID et toutes les FK de prix existantes.
- Augmenter les limites de longueur SQL/Pydantic du catalogue et des overrides à une borne commune proposée de 512 caractères ; rejeter au contrat si dépassée, sans troncature. Cette borne est une décision proposée, pas un fait sur les modèles actuels.
- Toutes les lectures nouvelles et les lecteurs runtime concernés nomment le fournisseur. Les lectures historiques par nom seul restent possibles seulement lorsqu’une identité unique existe ; une ambiguïté ne choisit jamais arbitrairement.
- Les routes de capacités nomment le fournisseur ; les routes tarifaires concernent les fournisseurs payants existants. Conserver leurs anciennes requêtes non ambiguës et les empêcher de sélectionner une ligne locale homonyme. Aucun formulaire de prix n’est créé pour ces serveurs.
- Traiter les noms contenant `/` sur les routes d’administration : proposer aussi une variante adressée par UUID pour les opérations CRUD. Le front utilise cet identifiant, pas une interpolation naïve dans un segment URL.
- La normalisation des noms datés et les alias de tarification restent propres aux fournisseurs qui en ont le contrat ; ne pas retirer une date d’un modèle local.
- Adapter le failover : une entrée historique sans fournisseur reste utilisable si unique ; format qualifié additif proposé `provider::model_id`, séparé de la syntaxe des tags du modèle. Aucun homonyme local ne doit détourner une cible historique.

Lecteurs identifiés : `core/llm_config_helper.py`, `core/bootstrap.py`, `model_profiles.py`, `capability_gate.py`, `structured_output.py`, `reasoning/translate.py`, `providers/adapter.py`, `providers/deepseek_limits.py`, `failover.py`, `middleware_config.py`, `domains/llm_config/service.py`, `decision_validation.py`, `domains/meetings/synthesis.py`, repository/service/router du catalogue, catalogue/preflight et leurs tests. La vérification structurelle recherche de nouveau tous les appels avant clôture du lot ; la liste ne remplace pas le scan.

### 4.2 Connexion : faire évoluer le contrat existant

Faire évoluer `ProviderApiKey` et son service/cache, plutôt que créer une deuxième autorité de credentials dans un domaine nouveau.

Champs proposés : `base_url` nullable pour compatibilité, `encrypted_key` nullable pour absence de secret, `connection_revision` monotone. `updated_by` et l’audit existants restent les propriétaires de l’écriture. Aucun champ de mode de facturation n’est ajouté.

Résolution d’une connexion locale :

1. Si une ligne DB moderne possède `base_url`, **toute la connexion vient de cette ligne**. Un secret absent reste absent ; ne jamais emprunter le secret d’une autre URL via l’environnement.
2. Pour une ligne Ollama historique sans `base_url`, interpréter sa valeur chiffrée comme l’URL, avec absence de secret. Aucune décryption de données n’est requise pendant la migration Alembic.
3. Sans connexion DB, construire une connexion complète à partir des variables d’environnement de cette famille.
4. Sans URL, état « non configuré ». Aucun repli vers `api.openai.com`.

Proposer `OMLX_BASE_URL`, `OMLX_API_KEY`, `LLAMACPP_BASE_URL`, `LLAMACPP_API_KEY`, `LMSTUDIO_BASE_URL`, `LMSTUDIO_API_KEY`, et `OLLAMA_API_KEY` pour l’authentification optionnelle du client natif. Conserver `OLLAMA_BASE_URL`. Les valeurs de ports usuels sont des aides de formulaire, pas des connexions actives présumées.

Une nouvelle route administrative `GET/PUT/DELETE /api/v1/admin/llm-config/providers/{provider}/connection` sert les quatre familles locales. Le PUT est un remplacement explicite de la connexion avec :

```json
{
  "base_url": "http://host.docker.internal:1234/v1",
  "key_action": "keep",
  "api_key": null
}
```

`key_action` vaut `keep`, `replace` ou `clear` ; `replace` exige une valeur, les deux autres n’acceptent pas un secret contradictoire. Le retour publie URL, origine DB/env, présence du secret et révision, **jamais le secret**. Le coût local zéro découle de la famille, pas d’un choix de formulaire. La suppression revient à l’environnement si celui-ci configure encore la famille : l’UI doit l’annoncer.

Compatibilité : conserver les routes de clés existantes pour tous les fournisseurs. Le PUT historique Ollama reste un changement d’URL ; le résolveur/cache offrent la vue historique attendue aux lecteurs encore migrés. À la première écriture moderne, promouvoir la ligne historique : l’ancienne URL chiffrée ne doit jamais devenir le bearer token. Un secret moderne préexistant n’est pas effacé par une modification d’URL via un vieux bundle.

URL : un seul normaliseur pour découverte et client ; HTTP(S) exclusivement, hostname requis, pas d’userinfo, query ou fragment. Conserver les préfixes de reverse proxy ; ajouter/retirer uniquement le suffixe exact attendu, de façon idempotente. Ollama utilise la racine native, les autres la base `/v1`. Distinguer racine native et base compatible sans utiliser un remplacement global de chaîne.

Les IP privées sont nécessaires à ce besoin. Leur autorisation reste limitée aux endpoints configurés par un administrateur authentifié ; elle ne modifie pas la protection des URLs d’outils, des liens ou du sandbox. Refuser les redirections implicites transportant un bearer, vérifier TLS, et ne pas offrir `verify=false` comme solution normale. Conserver le secret chiffré et hors navigateur/stockage web.

### 4.3 Client partagé, sans héritage accidentel d’OpenAI

Créer un client dédié mince, construit par le dispatch existant pour les trois nouveaux fournisseurs. Utiliser les primitives du SDK installé, avec overrides ciblés à la frontière du payload/résultat ; aucun monkey-patch global.

Contrat :

- Chat Completions imposé initialement, `use_responses_api=False`, aucun `previous_response_id`, aucun cache OpenAI ajouté automatiquement.
- `max_tokens` envoyé sous le nom accepté par le profil qualifié ; ne pas envoyer simultanément deux limites contradictoires. Le chemin universel initial utilise `max_tokens`.
- Neutraliser les changements de rôle ou les décisions fondées sur un nom OpenAI. La gestion d’un template qui refuse `system` est un comportement déclaré et testé ; ne pas aplatir tous les prompts par défaut.
- Paramètres optionnels envoyés seulement selon la surface connue. `provider_config` reste l’échappatoire avancée existante, mais ne peut écraser identité, URL ou credential résolus sans contrat explicite.
- Fusionner `extra_body` avec les traductions de raisonnement ; rejeter les collisions contradictoires plutôt que supprimer silencieusement une intention.
- Pas de dépendance à un endpoint HTTP `/parse` : le parsing Pydantic est côté client. Corriger les commentaires existants qui assimilent support SDK et route serveur.
- Conserver les erreurs, `finish_reason`, usage et `invalid_tool_calls` ; ne pas convertir une sortie malformée en succès.
- Conserver `reasoning_content` dans le champ LangChain attendu et dans les chunks, tout en laissant la réponse utilisateur dans `content`. Couvrir streaming et réponse complète avec le même contrat.
- Pour les serveurs/templates qui exigent le renvoi du raisonnement précédent, préserver cette information dans la conversion sortante qualifiée ; ne pas transformer la trace en prose utilisateur ni l’appliquer à toutes les familles.
- Réutiliser `coerce_content_to_text`, `usage_metadata`, `output_truncation` et l’instrumentation existants. Ne pas faire un second parser d’outils ou un second comptable.

Le cache d’instances tient compte de la génération de connexion et de capacités. Une rotation de clé, une nouvelle URL, une qualification modifiée ou un changement de modèle invalident les instances dans tous les workers. Une opération en cours conserve son snapshot ; les opérations suivantes adoptent la nouvelle génération.

Les clients async ont un propriétaire et une fermeture explicites à l’éviction/arrêt sur leur boucle. Une suppression de référence du cache ne prouve pas la fermeture d’un transport : ce comportement fait partie du test de cycle de vie. Ne pas exposer des clients partiellement reconstruits.

### 4.4 Découverte et vérité des capacités

Un listing identifie des modèles ; il ne remplit pas automatiquement tous les booléens de `ModelProfile`.

Proposer un descripteur découvert avec identifiant exact, kind connu ou inconnu, états de chargement, maxima théoriques, contexte actif, champs de capacité connus et provenance **par champ**. Réutiliser `ModelProfile` pour le runtime, avec une représentation explicite des capacités inconnues et de leurs sources ; ses lecteurs ne doivent pas interpréter un placeholder `False` comme un refus établi.

Les mêmes fonctions composent le profil proposé à l’UI et celui que le runtime lit. Priorités : contrainte de transport/serveur observée ; déclaration opérateur compatible ; catalogue pertinent pour le couple fournisseur/modèle ; valeur de repli affichée comme telle. Une découverte ne remplace que les faits qu’elle a effectivement lus. Une colonne par défaut ne devient pas vérifiée par contagion de la provenance de sa ligne.

Le contrat d’évidence nomme au minimum tools, vision, streaming usage, méthode structurée, strict JSON Schema, contrôles de sampling et raisonnement. Chaque valeur a une source `server/operator/qualified/unknown`, une date et, pour les faits endpoint-dépendants, une génération. `unknown_fields` porte les absences ; les booléens de compatibilité ne suffisent jamais à représenter cet état. Le mapping `supports_tools` API → `supports_tool_calling` runtime réutilise la couture déclarée, avec un test de vocabulaire. Les qualifications liées à un build, template ou modèle deviennent périmées si cette identité change ; un nom réutilisé sans métadonnée de version ne permet pas de détecter automatiquement un changement de poids.

La vérité fonctionnelle est l’intersection de trois contrats : **modèle**, **template/serveur**, **client**. Exemple : « modèle entraîné aux outils » et « template parse les outils » sont deux preuves différentes.

Le catalogue vendored reste distinct de cette découverte. Son import ne doit pas assimiler un nom local à une entrée cloud, remplacer une ligne vérifiée, importer les prix/raisonnement/kind ni déduire un retrait de modèle local d’une dépréciation cloud. Les préflights utilisent les références réelles de la cible ; aucune collecte réseau de registre ou téléchargement de tokenizer n’est ajoutée sur le chemin d’exécution.

La nouvelle route `/api/v1/admin/llm-config/providers/{provider}/models` compose les lecteurs des quatre familles ; la route Ollama actuelle demeure compatible. Retour proposé : `models`, `source`, `status`, `unknown_fields`, `observed_at`, `connection_revision`, `error_code`. Vocabulaires proposés : source `live/cache/catalogue/manual`, statut `ready/empty/unavailable/unauthorized/partial`. Chaque valeur a un producteur, un lecteur et une traduction/test.

- `/v1/models` est le socle compatible. Enrichissement natif ciblé, lecture uniquement, avec repli si route absente ou permissions insuffisantes.
- LM Studio : joindre les instances chargées à leur clé sans choisir arbitrairement la première si plusieurs contextes existent. L’identifiant sélectionné doit désigner la cible effective.
- llama.cpp : distinguer serveur direct et router ; `n_ctx`/capacité de template doivent venir du modèle ciblé, pas d’un autre modèle du router.
- oMLX : utiliser l’alias annoncé et le maximum présent ; ne pas déduire tools/vision du nom ou du propriétaire. Les champs non exposés restent manuels ou qualifiés.
- Aucun téléchargement, warm-up, benchmark ni appel de génération au chargement de la page.
- TTL incluant les résultats vides, cache d’échec court, appels simultanés coalescés ; durée totale bornée et concurrence limitée pour les enrichissements.
- Clé : fournisseur + génération de connexion. Ne jamais servir le cache d’une URL antérieure après un changement.
- Panne : garder le dernier résultat de la même génération avec âge/statut stale explicites ; un listing réussi vide retire les modèles découverts. Une panne ne signifie pas « liste vide ».
- Publication atomique de la nouvelle génération ; une réponse tardive de l’ancienne URL ne peut la remplacer. Démarrage et mutation DB ne gardent aucune transaction pendant ces appels réseau.
- Les profils endpoint-dépendants atteignent tous les workers, ou chaque worker découvre sa propre génération avant usage. La notification des seuls credentials ne suffit pas à diffuser un refresh de capacités déclenché par l’UI.

### 4.5 Raisonnement et sorties structurées

Conserver `ReasoningIntent`, la ladder et `kwargs_for(provider, model, stored)` comme seule couture. Ajouter une surface de raisonnement dérivée de preuves du serveur/template, avec des renderers propres aux nouvelles familles. `core` reçoit un descripteur typé ; il n’importe pas un service DB ou un client d’infrastructure.

- `provider_default` ne produit aucun contrôle.
- `none` n’est proposé que si la désactivation est exprimable sur **la route choisie**.
- Les niveaux, budgets et exclusion sont proposés uniquement s’ils sont validés par le même résolveur utilisé à l’écriture et à l’exécution.
- Une surface inconnue ne déclenche aucun kwarg et porte un état non vérifié. Une configuration héritée inexprimable est signalée ; aucune activation silencieuse de raisonnement n’est présentée comme une désactivation effective.
- Ne pas appliquer le renderer Ollama à llama.cpp/oMLX/LM Studio parce que le modèle a le même nom.
- Les demandes de budget et les champs `chat_template_kwargs` passent par `extra_body` quand le SDK ne les possède pas, sous un mapping déclaré et testé.

Sorties structurées : remplacer la seule décision globale par fournisseur par une sélection de méthode à partir de la surface qualifiée : JSON Schema, JSON object, fonction forcée, ou prompt + validation. Préférer le schéma natif lorsqu’il est réellement contraint. `strict=True` reste une demande distincte, jamais une preuve de conformité.

Les schémas imbriqués, unions, champs optionnels, `$ref`, enums, contraintes et caractères multilingues sont qualifiés. Toute réponse est validée en Pydantic. Une réponse tronquée est refusée avant les réparations ; une boucle de retry identique ne peut compléter un budget insuffisant. La capture de raisonnement ne doit pas provoquer deux inférences ordinaires ; les reprises permises restent comptées.

## 5. Tokens, coûts, quotas et capacité matérielle

### 5.1 Deux comptages différents

Le préflight de contexte estime ou mesure ce qui va entrer ; le ledger enregistre ce que le serveur annonce avoir consommé. Un tokenizer OpenAI appliqué à un modèle local ne devient pas exact parce que son transport ressemble à OpenAI.

Avant appel : utiliser le compteur existant selon sa précision connue ; ne pas lancer de requête réseau synchrone dans `TokenCounter.count`. Une éventuelle tokenisation native est async, bornée, annoncée comme telle et réserve une marge pour le template. L’estimation doit être éprouvée sur français, anglais, chinois, code, JSON d’outils, contenus encodés et entrées multimodales. La marge est paramétrable, documentée et calibrée ; aucune affirmation d’exactitude sur une estimation.

Après appel : reprendre le normaliseur central d’usage. Demander l’usage final lorsque le serveur qualifié le supporte, **uniquement** sur un flux. Gérer le chunk avec `choices=[]`, usage manquant, zéro réel, interruption avant usage et incohérence de cache. Séparer un chiffre mesuré d’une estimation ; ne pas fabriquer des tokens exacts à partir de caractères. Un mode sans usage fiable n’est pas déclaré pleinement qualifié pour une plateforme à quotas tokens.

### 5.2 Fenêtre réellement utilisable

Conserver la résolution par poste. Pour les nouveaux serveurs, distinguer : maximum théorique du modèle `M`, allocation effective du serveur `R`, limite voulue pour le poste `S`.

La fenêtre utilisable ne dépasse aucun plafond connu : `W = min(S, R, M)` sur les valeurs présentes, avec `R` établi ou une allocation explicitement déclarée par l’opérateur. Sans allocation connue ni déclaration, demander la fenêtre dans la configuration du nouveau poste ; ne pas substituer le défaut générique comme preuve d’une grande allocation.

Le budget vérifie l’historique, les prompts système, les schémas/outils, les données externes, le coût multimodal, la sortie et la réserve du template/raisonnement. Respecter `entrée + sortie réservée + marge <= W`. Les bornes et erreurs sont exposées au formulaire qui produit les valeurs. Un choix au-dessus du maximum connu est refusé à l’écriture pour la nouvelle surface ; ne pas transmettre `context_window` comme kwarg OpenAI.

Ollama conserve sa traduction `num_ctx` et ses règles actuelles. Pour les autres serveurs, LIA peut limiter sa propre fenêtre ; cela ne recharge ni ne reconfigure l’allocation serveur. L’UI dit « fenêtre utilisée par LIA » et affiche séparément l’allocation observée.

Réutiliser la compaction et les budgets ReAct, sans supprimer des outils, de l’historique ou des contextes métier pour afficher une économie. Quand les contextes nécessaires ne tiennent pas, proposer/indiquer la configuration adaptée et une erreur explicite plutôt qu’une troncature silencieuse.

### 5.3 Coût fournisseur et mode plateforme

Le modèle de credentials actuel est celui de l’instance. Ces nouveaux endpoints suivent donc la route de dépense `llm` existante, avec propriétaire du tour ou ledger d’instance hors compte. Il n’y a pas de BYOK utilisateur à inventer.

Pour Ollama, oMLX, llama.cpp et LM Studio, le coût est **toujours zéro par décision produit**. Il n’y a ni tarif à saisir, ni recherche de prix, ni refus pour tarif manquant, ni variante `metered`. Cette règle ne chiffre pas l’électricité, le GPU ou le stockage.

Déclarer la famille locale au point commun de comptabilité, avant toute recherche par nom : un alias local identique à un modèle cloud ne doit jamais recevoir son tarif. Le provisionnement réutilise la même déclaration de fournisseurs non facturés. Les providers cloud existants conservent leur dispositif de prix.

La signature actuelle du calculateur reçoit seulement le modèle. Propager explicitement le fournisseur depuis l’identité de l’appel jusqu’à `priced_call`, au calculateur de tokens et aux lecteurs directs : préflight/instance spend, callbacks, proactive, briefing et notifications. Le registre partagé définit les familles locales ; chaque chemin utilise ce verdict, sans inférence depuis un nom de modèle ou la classe ChatOpenAI. Les lecteurs cloud/audio existants conservent leurs contrats et leur snapshot tarifaire. Un garde de call sites vérifie que les coûts LLM chat ont une identité ; il complète les ratchets de cache-write sans les affaiblir.

Les callbacks conservent l’identité configurée, les tokens et les tentatives ; l’alias annoncé reste une observation. Tokens de cache et de raisonnement ne se comptent pas deux fois. Un fallback vers un fournisseur cloud configuré retrouve uniquement les règles de coût de ce fournisseur.

Conserver les plafonds utilisateur et instance et leur comportement existant. Un coût nul ne désactive pas les limites tokens, les bornes de tour ou les contrôles de transport. Un éventuel fallback vers le cloud a un coût et une destination différents : seul un fallback déjà configuré et validé est utilisé, jamais ajouté implicitement.

### 5.4 Saturation, reprises et latence

Le contrôle de débit `wait_for_slot` compose déjà `RedisRateLimiter`, attend de manière bornée et échoue ouvert. Il peut être réutilisé pour lisser les appels au même endpoint, avec une clé globale de fournisseur/génération ; **ce n’est pas un sémaphore d’inférences concurrentes**.

Le serveur reste propriétaire de sa file et de sa concurrence GPU. La qualification fixe un plafond d’inférences serveur, une taille de file et un délai compatibles avec le nombre de workers API et les consommateurs simultanés (chat, tâches de fond, radio, réunions). Un semaphore Python local ne prouve pas une limite globale. Ne pas ajouter un gestionnaire de leases distribué sans besoin distinct démontré.

Conserver des délais séparés pour connexion, lecture inactive, découverte et opération complète. Le chargement à froid peut allonger le TTFT sans signifier une panne ; un keepalive SSE utilisateur ne doit pas cacher indéfiniment une inférence bloquée.

Les tentatives sont bornées par un budget total et un seul propriétaire de retry. Éviter SDK × middleware × structured retry. Pas de retry sur auth, modèle absent, schéma refusé ou contexte dépassé ; reprise structurelle limitée sur saturation transitoire ou erreur réseau avant publication. Honorer `Retry-After` quand applicable. Après contenu publié ou effet d’outil, ne pas rejouer aveuglément le tour. Tester la fermeture du flux sur annulation ; la fermeture client ne garantit pas, à elle seule, l’arrêt du calcul GPU côté serveur.

## 6. Mémoire, état et registres

L’extension du provider ne crée pas de domaine agent ni de nouvel état LangGraph. Elle conserve les prompts versionnés, les blocs de connaissance, les données externes marquées non fiables, les outils et la validation du système actuel.

Effets indirects à couvrir :

- Extraction/consolidation mémoire et carnets, intérêts et références personnelles : sorties structurées, langues, tokens et timeouts ; pas de mutation sur réponse invalide.
- Compaction : un contexte plus petit change son déclenchement ; vérifier conservation des faits utiles et de la séquence d’outils.
- Pipeline : route/analyse, planning DSL, validation, HITL, orchestration et réponse. Le fournisseur n’ajoute aucun contournement d’approbation.
- ReAct : tool calls fragmentés, arguments invalides, budget, sortie vide/tronquée, recovery et fermeture explicite des appels abandonnés. Puis reprendre un second tour sur le checkpoint réel.
- HITL : sérialiser/reconstruire tout champ ajouté au profil/contexte d’exécution ; aucune instance SDK, dataclass arbitraire ou secret dans `MessagesState`.
- Registres d’effets, consultations et décisions : chaque outil réellement exécuté est enregistré une seule fois ; une génération qui annonce un acte ne prouve pas l’acte.
- Ledger et debug : conserver fournisseur effectif, poste, modèle demandé/annoncé, méthode structurée, origine/fenêtre de contexte, génération de connexion, tentatives et usage. Les mots du modèle/raisonnement et les secrets n’atteignent pas les logs INFO.
- RAG/embeddings : pas de changement de dimension, d’index vectoriel ou de réindexation. Les embeddings restent sur leur couture dédiée ; un modèle embedding découvert n’est pas offert dans un poste chat.
- JEV : garder le kind `decision` et le runtime natif séparés, même si llama.cpp expose aujourd’hui une route de décisions.

Les nouveaux registres keyed par fournisseur ou vocabulaire ont un assert de complétude au démarrage ; la branche qui appelle cet assert doit propager l’échec. Tout blob Redis ajouté est versionné, a un TTL et une famille déclarée. Chaque paire de sérialisation a un test round-trip de tous les champs.

## 7. Administration, UX et mobile

Utiliser la section Administration LLM existante. Remplacer le test `isOllama` par la métadonnée du type de connexion, fournie par l’API. Les fournisseurs cloud conservent leur formulaire de clé ; les familles locales affichent URL et secret optionnel séparément.

Parcours cible : choisir la famille → enregistrer la connexion → consulter le listing → choisir/configurer le modèle pour un poste → enregistrer ses overrides complets. Le bouton « vérifier la connexion » lit le listing et affiche ce qu’il a vérifié ; une qualification d’inférence est une action distincte et explicite.

Le formulaire :

- Affiche l’origine effective DB/env et explique la suppression qui révèle encore une configuration env.
- Conserve les champs et le focus pendant une actualisation ; la première lecture, le refresh et l’enregistrement sont des états distincts.
- Distingue non configuré, connexion refusée, auth refusée, serveur indisponible, liste vide, modèle non chargé, résultat en cache et capacités partielles.
- Affiche les contraintes du poste et les capacités inconnues avec un libellé traduit. La saisie manuelle reste possible ; aucun modèle n’est inventé à partir d’un catalogue d’une autre famille.
- Le modèle déjà configuré reste visible même s’il a disparu du listing ou ne satisfait plus le filtre ; montrer un avis, sans effacer silencieusement sa valeur.
- Un changement de fournisseur remet à zéro les propriétés liées au précédent serveur (modèle, options, raisonnement, fenêtre proposée). Ne pas transmettre une réponse de découverte tardive à la nouvelle sélection.
- Les nouveaux providers ne sont proposés que pour les kinds supportés ; TTS, Live, image, embedding et decision conservent leurs offres.
- Affiche le contexte LIA, le contexte actif observé et le maximum théorique comme trois notions. Ne pas appliquer le plafond local Ollama aux autres serveurs.
- Le JSON avancé ne contient aucun secret, reste replié par défaut et ouvert si des valeurs non standard sont présentes.

Conventions : hooks typés `useApiQuery/useApiMutation`, `api-client`, `FormSection`, `Input`/`FieldFrame`, composants de sélection/dialogue et notifications existants ; pas de fetch direct, de nouvelle route de page ni de composant cosmétique copié.

Mobile : empiler les champs dans la carte de connexion à 320/360/390 CSS px ; URL et identifiant longs se replient sans élargir la page ; actions accessibles sans hover. La largeur est portée par le wrapper `FieldFrame`. Dialogues avec hauteur bornée, contenu défilant et commandes accessibles au clavier/avec clavier virtuel. Vérifier reflow/zoom 200 % et clair/sombre/OLED.

Accessibilité : noms traduits et stables par rôle, erreurs reliées au champ, annonce du chargement et du résultat, tabulation et retour du focus, contrôle de révélation du secret nommé. Pas de disparition d’un contrôle occupé ou de mise en disabled qui déplace le focus sans intention.

Locales : en, fr, de, es, it, zh pour tous les libellés, hints, erreurs, placeholders et noms accessibles ; paramètres serveur et noms de modèles restent littéraux. Les routes/settings restent celles de LIA, y compris dans les WebViews. Le navigateur ne contacte jamais directement le serveur LLM : pas d’extension CSP/CORS nécessaire à ce transport.

## 8. Cartographie des impacts et risques

### 8.1 Surfaces directes et indirectes

| Domaine | Surfaces actuelles à adapter | Nature de l’impact |
|---|---|---|
| Configuration | `core/llm_agent_config.py`, `core/config/llm.py` et autres Literals de provider, `llm_config/constants.py`, schemas/models/service/cache/router | Identités, connexion complète, statut effectif, remplacement d’overrides, complétude |
| Client/runtime | `providers/adapter.py`, nouveau client partagé, lecteurs de découverte, URL/résolution communes, `factory.py` | Payload, flux, timeouts, raisonnement, cycle de vie, cache |
| Capacités/contexte | `model_capabilities_cache.py`, `model_profiles.py`, `capability_gate.py`, `llm_config_helper.py`, résolution de raisonnement | Identité composée, preuves par champ, allocation réelle |
| Sorties structurées | `structured_output.py`, settings du support structuré, tests Pydantic et troncature | Choix de méthode, refus/repair/retry, coût des reprises |
| DB/catalogue/prix | `domains/llm/models.py`, schemas/repository/service/router, migration Alembic, lecteurs de prix existants et seeds | Unicité composée, compatibilité des routes payantes ; aucun prix local |
| Comptabilité | callbacks, `tracking_records.py`, portes de dépenses, snapshots et quotas | Provider déclaré indépendant de la classe SDK, coût local zéro avant tout lookup |
| État/consommateurs | Compaction, ReAct, HITL, mémoire, carnets, briefing, routines, radio, réunions, téléphonie déléguée | Couverture de flux ; aucun nouveau champ de state exigé par l’extension |
| Front | `AdminLLMConfigSection.tsx`, helpers et hook dédié, types, vues de prix existantes, six locales | Connexion/discovery génériques, offre par kind, états et mobile ; pas de prix local à éditer |
| Infrastructure | `.env.example`, exemples prod/minimal/demo, Compose, documentation d’installation | Adresses joignables depuis l’API, auth réseau, variables ; pas d’installation automatique de serveurs |
| Provisionnement | `provisioning/demo_llm.py`, manifeste/questions de l’installateur et guards liés | Ne pas ajouter arbitrairement les trois providers aux clés obligatoires ; ne pas assimiler chaque endpoint compatible à un fournisseur gratuit |
| Public/observabilité | Statistiques landing/JSON-LD et textes de providers, métriques, Grafana/alertes, documentation | Décomptes cohérents et affichage des nouveaux providers ; aucune qualification universelle annoncée |

### 8.2 Matrice des risques

| Risque | Gravité | Déclencheur | Mitigation vérifiable |
|---|---|---|---|
| Régression Ollama natif | Critique | Généralisation du dispatch/structured/reasoning | Tests actuels + fixture wire native ; conserver client natif et anciennes URL |
| Mauvais profil ou coût cloud attribué à un local | Critique | Même identifiant sur deux familles | Capacités composées ; coût zéro avant tout lookup tarifaire ; tests de concurrence |
| Secret envoyé au mauvais hôte | Critique | Résolution hybride, redirect, ancien cache | Connexion atomique, refus userinfo/redirect, génération, rotation deux workers |
| Contexte perdu silencieusement | Critique | Maximum théorique lu comme allocation | Modèle/runtime/poste séparés ; préflight complet et preuve près de la limite |
| Outils inventés ou exécutés sans consentement | Critique | Résultat ambigu, MCP serveur activé | Outils LIA seulement, HITL existant, round-trip et ledger d’effets |
| Dépense cloud invisible | Haute | Fallback autorisé vers un provider payant | Fallback explicite, comptabilité cloud existante et tentatives comptées |
| Strict JSON déclaré mais non garanti | Haute | Grammaire indisponible/schema non supporté | Qualification des schémas, validation Pydantic, état de méthode réel |
| Raisonnement disparu ou activé malgré `none` | Haute | Champ non conservé, renderer erroné | Convertisseurs entrée/sortie testés, off expressible seulement, no double call |
| Burst GPU/OOM et TTFT excessif | Haute | Workers API + jobs simultanés | Limites serveur mesurées, file bornée, shaper optionnel, tests saturés/cold start |
| Multiplication des tentatives | Haute | SDK × middleware × structured retry | Propriétaire unique, compteurs d’appels wire, deadline totale |
| Ancienne découverte publiée après rotation | Haute | Réponse tardive/TTL/cross-worker | Compare génération, swap atomique, résultat stale explicite, test deux acteurs |
| Transactions DB longues | Haute | Discovery dans reload ou mutation | Commit/fin de session avant réseau ; contrôle `pg_stat_activity` |
| Config écrasée par vieux bundle | Haute | PUT complet/ancien endpoint clé | Adaptateur de compatibilité ; keep/replace/clear ; scénarios ancien client |
| Erreur malformée interprétée comme succès | Haute | HTML 200, SSE coupé, tool JSON invalide | Validation transport/typed output et erreur structurée, aucun effet validé par prose |
| Régression mobile/a11y | Moyenne | URL longue, rangée fixe, refresh | Oracles focus/valeur/reflow et scénarios browser hermétiques |
| Cache multiworker divergent | Haute | Refresh UI sur un worker uniquement | Publication/invalidation après commit, générations observées sur deux workers |
| Upgrade/downgrade destructeur | Haute | Enums nouveaux et homonymes introduits | Migration PostgreSQL réelle ; downgrade refuse les données incompatibles sans suppression |

La probabilité n’est pas chiffrée sans mesures. Les sondes ont également établi les différences de `tool_choice` et de JSON mode, les refus Pydantic de plans et la perte du raisonnement dans le SDK. Les scénarios non exercés restent des risques à provoquer, pas des incidents actuels affirmés.

## 9. Plan de test directeur

### 9.1 Matrice de couverture

| Contrat | TU | Intégration back/front | E2E/flux | Oracle de succès |
|---|---|---|---|---|
| Identité composée | Homonymes, aliases, dates, ambiguïté legacy | PostgreSQL unicité/repository ; prix payants préservés ; import/export | Deux providers configurés avec même nom | Deux profils/fenêtres indépendants ; coût local zéro ; wire exact |
| Credentials | Normalisation, tri-state, DB/env, migration legacy | Auth admin, Fernet, audit, rollback et cache | Créer/modifier/supprimer/rotation | Aucun secret retourné ; nouveau serveur reçoit la bonne clé |
| Client | Payload complet, modèles aux noms OpenAI, merge extra_body | SDK réel contre fake HTTP local ; sync/async et SSE | Texte + outils + JSON + annulé | Route/headers/cap/rôles exacts ; nombre d’appels attendu |
| Discovery | Parsers partiels, champs inconnus et bornes | Fake endpoints natifs/compatibles, TTL/générations/2 workers | Liste vide, panne puis récupération, changement rapide | Valeur sélectionnée/focus conservés ; pas de cache croisé |
| Raisonnement | Tout niveau × toute famille ; round-trip | Non-stream et SSE, off/on/budget supportés/refusés | Trace séparée de l’answer | Off reçu quand offert ; aucun objet intent sur le fil |
| Structured | Méthode selon preuves ; variantes de schémas | SDK + Pydantic, raw/tronqué/refus/parsing | Planning, extraction mémoire, synthèse | Objet complet valide ou erreur honnête ; pas de faux succès |
| Contexte | M/R/S, inconnus, réserves, deux slots | Prompt final réel + outils/historique | ReAct et compaction près de limite | Aucun contenu important retiré/tronqué en silence |
| Usage/coût | Mesuré vs estimé, cached/reasoning, local toujours zéro | Callbacks/TrackingContext/DB/instance | Local zéro même homonyme cloud, retry/fallback | Tokens attribués une seule fois ; aucun prix local recherché |
| Quotas/charge | Gate compte/instance, shaper, retry classifier | Redis panne/charge, deadline, file serveur | Plusieurs comptes/jobs ; 429/503 | Attente bornée, erreur actionnable, pas de boucle de retry |
| State/registres | Vocabulaire + serialization round-trip | Checkpoint PostgreSQL, HITL/recovery | Tour 1 tools/budget → tour 2 | Historique fournisseur valide ; effets non dupliqués |
| UX/kinds/i18n | RTL par rôle/nom et helpers | Hook/API réel simulé ; six locales | Mobile/keyboard/zoom/themes | Aucun overflow, perte de champ ou de focus |
| Cycle de vie | Eviction, rotation, async close | Arrêt/redémarrage/annulation/deux workers | Serveur inaccessible puis restauré | Aucun transport/tâche non clos ou génération obsolète |

### 9.2 Simulations obligatoires

Fake HTTP hermétique avec inspection des requêtes ; SDK installé réel au-dessus du fake. Prévoir :

1. DNS introuvable, refus TCP, erreur TLS, mauvais port/prefix `/v1`, timeout connexion, lecture lente et deadline totale.
2. 301/302 vers un autre hôte, 401/403, 404 modèle/route, 408, 429 avec/sans `Retry-After`, 500/502/503, 507 mémoire ; parsing d’erreurs OpenAI, FastAPI ou HTML non JSON.
3. JSON tronqué, mauvais Content-Type, tableau/object incohérent, entrées null/non dict, `id` absent, doublons, valeurs booléennes pour une taille, tailles négatives/énormes, identifiant Unicode/slash/tag/date/512+ caractères.
4. Modèle téléchargé mais non chargé, auto-load désactivé, alias modifié, deux instances à contextes différents, modèle supprimé/remplacé sous même nom, absence de métadonnées pendant chargement.
5. Flux avec texte, reasoning seul, tool calls seuls et `content=null`, noms/arguments fragmentés sur plusieurs indexes, JSON d’arguments invalide, appels sans ID, chunks vides, final usage `choices=[]`, `[DONE]` absent et déconnexion.
6. Reasoning off ignoré/refusé, budget de pensée qui consomme toute la sortie, prose dans la trace, trace nécessaire au tour suivant, wrapper structured qui ne termine pas ; compteur de tentatives explicite.
7. Schémas imbriqués/union/nullable/ref/enum/arrays et taille importante ; schéma refusé, JSON valide hors schéma, fin `length`, refusal/content_filter et réponse vide.
8. Usage absent, zéro réel, cache supérieur à input, chiffres invalides, usage reçu deux fois, annulation avant métriques finales et erreur portant usage partiel.
9. Deux connexions changeant pendant une discovery ; deux workers avec caches séparés ; suppression DB dévoilant l’env ; rotation de clé avec appel actif ; Redis indisponible ; réponse ancienne terminant après la nouvelle.
10. Compte bloqué tokens/coût/appels, budget instance atteint avec limites utilisateur désactivées, traitement sans owner, local à coût zéro même sans ligne de prix ou avec homonyme cloud, tentative locale puis fallback payé autorisé.
11. Ancien bundle utilisant les anciennes routes et PUT complet ; kind incompatible ; capacité inconnue ; modèle courant hors filtre ; traduction manquante ; clavier/zoom/mobile et navigation native.
12. Cancel à chaque étape et arrêt de worker : aucun effet dupliqué, aucun état persistant incohérent ni warning de coroutine/transport.

### 9.3 Qualification réelle limitée et reproductible

Le fake valide LIA ; il ne prouve pas qu’un modèle réel sait appeler ses outils. Pour chaque famille réellement disponible, enregistrer binaire/build, modèle, quantification, template, matériel, mémoire allouée et endpoint depuis le conteneur API.

Une séquence courte et plafonnée : listing → texte streaming avec usage → sortie Pydantic représentative → appel d’outil de lecture puis retour outil → tour suivant après checkpoint → prompt près du contexte → annulation/cold start/saturation. Ne pas utiliser de mutation réelle de compte ni de fournisseur payant pour les sondes ordinaires. Pas de retry automatique ni benchmark massif ; une destination payante relève d’un budget explicitement autorisé.

Les résultats qualifient **la combinaison testée**. Une fonction non éprouvée reste signalée comme telle. Les trois nouveaux serveurs ne sont pas installés/qualifiés dans cette analyse ; les sources officielles consultées ne sont pas une preuve de leur présence sur le réseau de ce déploiement.

## 10. Plan d’actions consolidé et séquencé

### 10.1 Implantation précise des nouveaux tests

Chemins ci-dessous **à créer** ; ils complètent les tests existants cités dans les lots. Racine backend : `apps/api/` ; racine frontend : `apps/web/`.

| Lots | Modules de tests proposés | Frontière conservée réelle |
|---|---|---|
| 0 et 4 | `tests/unit/infrastructure/llm/providers/test_openai_compatible_chat.py`, `tests/fixtures/llm_servers/` | SDK installé ; fake HTTP capturant payload et SSE |
| 1 | `tests/unit/infrastructure/llm/test_model_identity.py`, `tests/integration/domains/llm/test_provider_model_identity.py` | Cache réel ; PostgreSQL pour contrainte et CRUD |
| 2 | `tests/unit/infrastructure/llm/providers/test_server_connections.py`, `tests/unit/domains/llm_config/test_server_connection_api.py`, `tests/integration/domains/llm_config/test_server_connection_persistence.py` | Résolveur/cache, API/auth et Fernet ; DB/Redis pour commit/invalidation |
| 3 | `tests/unit/infrastructure/llm/providers/test_server_discovery.py`, `tests/integration/infrastructure/llm/test_server_discovery_generations.py` | Parsers ; deux consommateurs et Redis pour publication |
| 5 | `tests/unit/infrastructure/llm/reasoning/test_server_reasoning_surface.py`, `tests/unit/core/test_server_context_budget.py` | Résolveurs/translator et prompt final, sans modèle payant |
| 6 | `tests/unit/infrastructure/llm/test_local_server_accounting.py`, `tests/integration/domains/llm/test_provider_pricing_isolation.py` | Callback/ledger réels ; PostgreSQL pour prix/attribution |
| 7 — à créer | `src/hooks/__tests__/useLocalModelServer.test.ts`, tests Administration existants, `e2e/smoke/admin-local-model-servers.spec.ts` | Transport simulé via API/SSE ; vrais composants et navigateur |
| 8 | `tests/integration/domains/agents/test_local_server_checkpoint_flow.py` | Checkpoint PostgreSQL et séquence d’outils réelle avec inférence simulée |

Tout module nouveau reçoit les markers appropriés et reste découvert dans au moins un job CI. Le transport fake fournit des réponses contrôlées ; il ne remplace pas la fonction ou le SDK qui constitue l’objet du test.

Chaque lot suit : test caractérisant le contrat → échec observé → implémentation minimale → tests ciblés → revue inline à froid → gates pertinents. Aucun commit automatique n’est demandé par cette analyse. Les snippets ci-dessous sont des oracles TDD proposés, pas du code produit ajouté au dépôt.

### Lot 0 — Figer les contrats et fixtures

**Fichiers :** tests existants `tests/unit/infrastructure/llm/providers/`, `tests/unit/domains/llm_config/`, `tests/unit/core/test_slot_context_window.py` ; [preuves réelles déjà collectées](../qualification/2026-10-06/README.md), à transformer en fixtures wire dans la même famille de tests.

**Consomme :** spécification présente, SDK locké, versions/builds disponibles. **Produit :** fixtures datées de listings, payloads et SSE ; matrice de fonctions supportées/non qualifiées.

- [ ] Rejouer les 50 tests ci-dessus et ajouter les tests de caractérisation SDK : limite/rôle, reasoning perdu, alias, structured et usage.
- [ ] Capturer le défaut d’homonyme sans changer le comportement du cache.
- [ ] Figer la provenance et la version amont de chaque fixture ; valider les parsers sur la fixture, pas sur un mock inventé.
- [x] Exécuter la sonde réelle bornée sur les API stables accessibles ; conserver les échecs et la limite matérielle oMLX. Aucun appel payant.

**Sortie :** aucune hypothèse de wire format dépendante de la mémoire de l’ingénieur ; les limites des fixtures sont écrites.

### Lot 1 — Identité fournisseur/modèle dans catalogue et runtime

**Fichiers :** `domains/llm/models.py`, repository/service/router/schemas ; Alembic ; `model_capabilities_cache.py`, `model_profiles.py`, `llm_config_helper.py`, `capability_gate.py`, lecteurs énumérés section 4.1 ; tests catalogue/cache/contexte. Les types et vues de prix payants sont adaptés uniquement si leur lecture par nom devient ambiguë ; aucune édition de tarif local.

**Consomme :** fixture homonyme. **Produit :** lookup `get(model_id, *, provider)` et identité typée commune ; contrainte `(provider, model_name)` ; routes de prix non ambiguës, sans activation des nouveaux providers.

- [ ] Écrire le test d’isolation suivant et les cas retrait d’une famille/ambiguïté legacy.
- [ ] Migrer la contrainte en conservant UUID/FK/prix/historique ; aligner les longueurs SQL/API.
- [ ] Propager le provider aux lecteurs ; les chemins explicites ne consultent plus un nom nu.
- [ ] Tester sur PostgreSQL les collisions autorisées entre fournisseurs, interdites au sein d’un fournisseur, et l’ancien CRUD non ambigu.
- [ ] Fixer la syntaxe qualifiée du failover et l’adressage de noms avec slash.

```python
# Interface proposée pour le lot 1 : C.get(model_id, provider=provider)
assert C.get("shared-model", provider="ollama").max_input_tokens == 8192
assert C.get("shared-model", provider="lmstudio").max_input_tokens == 32768
assert C.get("shared-model") is None  # une lecture historique ambiguë ne devine pas
```

**Sortie :** coexistence prouvée et régression des providers actuels absente ; migration replay-check vert.

### Lot 2 — Connexions et providers complets

**Fichiers :** `domains/llm_config/models.py`, schemas/service/cache/router ; résolveur proposé `providers/server_connections.py`, URL helper proposé `providers/server_urls.py` ; `core/llm_agent_config.py`, `core/config/llm.py`, `llm_config/constants.py`, catalogue enum/schemas et assertions de boot ; Alembic et exemples env.

**Consomme :** identité du lot 1. **Produit :** `ResolvedServerConnection` typé (provider, URL native/compatible, secret optionnel, source, génération) ; `resolve_server_connection(provider)` pure depuis snapshot ; routes connection et compatibility Ollama.

- [ ] Tests DB/env atomiques et anciens credentials Ollama, promotion et key_action contradictoire.
- [ ] Ajouter les trois providers dans toutes les déclarations réellement consommatrices ; guard de parité entre registre/types/usage/mappings.
- [ ] Migration additive de connexion ; changement atomique de révision ; aucun réseau dans la transaction.
- [ ] Les nouveaux enum PostgreSQL sont ajoutés dans une migration compatible avant toute ligne qui les utilise ; tester la chaîne réelle.
- [ ] API admin/auth/audit/erreurs, invalidation tous workers après commit ; source env et suppression visibles.

```python
# Interface proposée : resolve_server_connection(provider)
assert resolve_server_connection("lmstudio").api_key is None
# Même si l'env a une clé, une connexion DB explicitement keyless ne l'emprunte pas.
assert resolve_server_connection("lmstudio").source == "db"
```

**Sortie :** pas de configuration hybride, fuite ni réseau pendant une transaction ; ancien Ollama fonctionne.

### Lot 3 — Découverte et profils partiels cohérents

**Fichiers :** découverte Ollama existante, lecteurs proposés `omlx_discovery.py`, `llamacpp_discovery.py`, `lmstudio_discovery.py`, cœur proposé `server_discovery.py` ; cache/profiles et service metadata ; schémas de réponse ; tests des parsers/caches et concurrent refresh.

**Consomme :** `ResolvedServerConnection`. **Produit :** descripteurs découverts typés et profil composé unique ; `discover_server_models(connection)` async ; réponse metadata/discovery utilisable par le runtime et le front.

- [ ] Tests listing compatible, enrichissement natif, unknown distinct de false, unloaded/router et partiel.
- [ ] TTL résultats vides/pannes, coalescence, deadline totale, bornes de payload/enrichissement.
- [ ] Compare de génération avant publication ; deux URL/deux workers ; aucune réutilisation du cache précédent.
- [ ] Diffuser la génération de capacités et invalider les instances seulement après un résultat cohérent.
- [ ] Rendre le fallback de la même génération visible et garder l’ancienne route Ollama.

```python
# Contrat proposé : publish_if_current(result, connection_revision) -> bool
assert publish_if_current(old_result, old_revision) is False
assert current_models.source in {"live", "cache", "catalogue", "manual"}
```

**Sortie :** un champ absent ne devient jamais une incapacité certaine ; cache/front/runtime convergent.

### Lot 4 — Client commun et méthodes structurées

**Fichiers :** client proposé `providers/openai_compatible_chat.py`, dispatch `adapter.py`, `factory.py`, `structured_output.py`, `output_truncation.py` si nouveaux shapes réels, configuration du support structuré ; tests SDK contre fake HTTP.

**Consomme :** connexion et profil du lot 3. **Produit :** client LangChain partagé et tracé ; payload exact, méthode structurée sélectionnée et réponses/chunks normalisés.

- [ ] Test capturant endpoint, headers, `max_tokens`, rôle système et absence de Responses/OpenAI cache pour les trois familles.
- [ ] Tester non-stream, SSE, tools fragmentés, invalid_tool_calls, usage terminal et fermeture.
- [ ] Méthodes JSON Schema/object/function/prompt validées selon preuves, plus refus et troncature avant repair.
- [ ] Fixtures LM Studio : refus objet `tool_choice` et `json_object`, traduction vers outil unique + `required`, aucun retry identique ; contrôles des identifiants inexistants servis implicitement par llama.cpp/LM Studio.
- [ ] Fixtures de `ExecutionPlan` JSON valide mais métier invalide : conserver la validation Pydantic et son erreur ; aucun outil n’est exécuté à partir du plan rejeté.
- [ ] Réutiliser les convertisseurs/compteurs centraux ; aucun monkey-patch global.
- [ ] Cycle de vie clients/éviction/rotation/arrêt et absence de warning async.

```python
# Oracle du fake HTTP recevant un appel d'un nouveau provider :
assert request.path.endswith("/v1/chat/completions")
assert request.json["max_tokens"] == configured_output_cap
assert "max_completion_tokens" not in request.json
assert request.json["messages"][0]["role"] == "system"
assert request_count == 1
```

**Sortie :** texte, tool loop et objet Pydantic fonctionnent via le vrai SDK sans spécialiser tous les appelants.

### Lot 5 — Raisonnement, contexte et usages

**Fichiers :** `core/reasoning_profiles.py`, `reasoning/translate.py`, `llm_config/reasoning_validation.py`, metadata/profiles, `core/llm_config_helper.py`, `providers/token_counter.py`, `usage_metadata.py`, callbacks et `tracking_records.py` ; tests golden/seam et flux de contexte.

**Consomme :** surface serveur/template et client du lot 4. **Produit :** profils de raisonnement et fenêtre par poste qui correspondent aux valeurs effectivement envoyées/observées, usage mesuré et attribué.

- [ ] Toutes les familles × tous les niveaux ; inconnus, `provider_default`, off non exprimable, budgets et conflits extra_body.
- [ ] Tests reasoning complet/chunks, conservation quand nécessaire au tour suivant, et absence de double inférence.
- [ ] Tests M/R/S, contexte inconnu déclarable, budget entrée/sortie/template et deux postes distincts.
- [ ] Multilingue/code/JSON/multimodal ; origine/précision du comptage explicites.
- [ ] Streaming usage reçu/manquant/partiel ; total/cache/reasoning non dupliqués.

```python
# Oracle de normalisation d'une réponse ou d'un chunk :
assert message.content == "réponse"
assert message.additional_kwargs["reasoning_content"] == "trace"
# L'intention persistée ne voyage jamais comme objet SDK.
assert all(not isinstance(v, ReasoningIntent) for v in payload.values())
```

**Sortie :** aucune commande de raisonnement offerte sans traduction validée ; contexte et usage honnêtes.

### Lot 6 — Prix, plafonds et comportement dégradé

**Fichiers :** `pricing_cache.py`, `pricing_service.py`, import/export prix, callbacks/tracking, `usage_guard.py` seulement si contrat nouveau l’exige ; `provisioning/demo_llm.py`, failover/middleware ; métriques/panels/règles réellement nécessaires.

**Consomme :** identité/générations et usage. **Produit :** coût local toujours zéro, usage conservé, traitement correct des reprises/fallbacks et saturation ; aucun nouveau dispositif tarifaire local.

- [ ] PricingCacheData versionné et round-trip ; anciens blobs non ambigus ; démarrage depuis DB et invalidation après commit.
- [ ] Tests local sans prix, local homonyme cloud et alias annoncé : coût zéro et aucun lookup de prix ; chaque tentative et double callback observés. Les tests cloud existants conservent les snapshots avant rotation tarifaire.
- [ ] Reprendre la preuve de collision tarifaire : transmettre le fournisseur à chaque calculateur chat, court-circuiter les quatre familles avant le lookup, conserver tokens et FX. Couvrir les chemins directs hors callback et ajouter le garde des call sites sans hausse de baseline.
- [ ] Quotas avec owner/sans owner, limites désactivées/budget instance actif ; local zéro toujours observé.
- [ ] Wire request_count pour retry imbriqué, 429/503 et délai total ; aucune reprise des erreurs permanentes.
- [ ] Dimensionner avec limite/file du serveur, workers et jobs ; lissage via limiter existant si nécessaire, sans fausse promesse de concurrence globale.
- [ ] Métriques nouvelles immédiatement visibles dans un panel/règle/alerte, log sans contenu/secret.

```python
# Contrat proposé : la famille locale court-circuite le lookup tarifaire.
assert account_call("lmstudio", "shared-model", usage).cost_eur == 0
pricing_lookup.assert_not_called()
assert ledger.total_calls == actual_wire_attempts
```

**Sortie :** usage des appels locaux observé à coût zéro, aucun prix cloud emprunté à un homonyme, aucune nouvelle destination de fallback implicite.

### Lot 7 — Formulaires et catalogue front

**Fichiers :** `AdminLLMConfigSection.tsx`, helpers, nouveau hook proposé `hooks/useLocalModelServer.ts`, types LLM/prix ; sous-composants de connexion/découverte extraits si le hotspot l’exige ; six locale JSON ; tests RTL/hooks et e2e proposé `smoke/admin-local-model-servers.spec.ts`.

**Consomme :** contrats connection/discovery/profiles/prix définitifs. **Produit :** parcours complet dans la section existante, mobile et accessible.

- [ ] Tests par rôle/nom pour clé optionnelle, origine DB/env, erreur auth, cache stale, unknown capabilities, modèles avec slash et kind.
- [ ] Saisie/valeur/focus conservés pendant refresh ; late response ignorée et annulation du hook.
- [ ] Réutiliser FormSection/FieldFrame/actions ; priorité de profil identique au runtime.
- [ ] Six langues et noms accessibles EN/FR, table de sources/status complète.
- [ ] E2E succès, auth incorrecte/correction, URL modifiée, même model_id chez deux fournisseurs ; clavier mobile/reflow/themes.

```text
Oracle browser : modifier une URL → rafraîchir le catalogue →
la saisie et le focus restent ; une ancienne réponse n'altère pas la nouvelle famille.
À 320 CSS px, largeur du document <= largeur du viewport.
```

**Sortie :** nouveaux providers configurables sans JSON caché nécessaire et sans régression des fournisseurs cloud/Ollama.

### Lot 8 — Flux bout en bout et qualification

**Fichiers :** tests d’agents/pipeline/ReAct/HITL/compaction/mémoire, tests d’intégration PostgreSQL/Redis, fixtures SDK ; documentation technique/guide/ADR, exemples env et surfaces publiques réellement touchées.

**Consomme :** lots 0 à 7. **Produit :** preuves des flux et qualification datée de chaque combinaison réellement testée.

- [ ] Pipeline conversation puis plan/outils/HITL/réponse avec chaque transport simulé.
- [ ] ReAct budget/cancel/recovery, tools abandonnés puis nouveau tour ; replay de checkpoint réel.
- [ ] Extraction mémoire/carnets et synthèse structurée d’un consommateur hors chat ; prix/owner/quotas attribués.
- [ ] Sonde réelle courte par serveur disponible ; cas froid/contexte/saturation/annulation, limites écrites.
- [ ] Documentation de connexion Docker/LAN, TLS/secrets et coût ; rien n’annonce que « tous les modèles » possèdent outils/vision/raisonnement.
- [ ] Revue adversariale inline des fichiers modifiés et analyse des branches non couvertes.

**Sortie :** l’extension est qualifiée selon la matrice annoncée ; les fonctions et versions non éprouvées restent explicitement non qualifiées.

## 11. Gates, migrations et livraison future

Les ratchets restent shrink-only : aucune hausse de baseline, aucune baisse de seuil, aucun ignore/Any/cast ajouté pour absorber une régression. Le gros composant d’administration et l’adapter ne doivent pas grossir en monolithes ; extraire les responsabilités nécessaires, sans déplacer la complexité.

Commandes du dépôt, choisies selon le lot :

```text
task lint
task test:backend:unit:fast
task test:backend:unit:coverage
task test:frontend
task test:frontend:coverage
task test:markers
task db:migrate:replay-check
task test:backend:integration
task test:backend:agents
task test:e2e
task lint:docs:preview
task ci:fast
```

Les tests runtime restent dans Docker ; les checks statiques suivent le Taskfile. Le frontend garde le contrôle TypeScript propre non incrémental. La commande frontend neutralise `NEXT_PUBLIC_API_URL` via le task. Les tests hermétiques ne dépendent d’aucune clé fournisseur et ne se désactivent pas sur son absence. Pas de suite exhaustive par défaut.

En production future : migration expand avant les nouvelles configurations ; aucun seed qui devine les modèles installés ; aucune modification des providers effectivement configurés par l’administrateur. Faire le preflight de catalogue sur la cible réelle avant une évolution du catalogue. Vérifier tous les workers après rotation, pas un seul healthcheck.

Downgrade : si des homonymes ou lignes de nouveaux providers existent, refuser un retour incompatible avec diagnostic explicite. Ne pas supprimer automatiquement des tarifs/configurations pour recréer une unicité globale. Les anciennes vues restent maintenues pendant la transition ; les blobs sont versionnés et les écritures de cache invalidées après commit.

Publication ultérieure : ADR, guide technique, index/maps, six langues et statistiques de providers suivent leurs sources ; `AGENTS.md` reste généré. Les exemples d’environnement prod/minimal/demo sont alignés quand une variable est ajoutée. Commit/push/déploiement sont hors de l’autorisation de cette analyse.

## 12. Auto-évaluation formelle et décisions restantes

| Critère demandé | Verdict | Justification/limite |
|---|---|---|
| Conviction à 100 % demandée | **Périmètre techniquement engageable ; pas de garantie universelle de support** | Les API stables accessibles ont été éprouvées, avec écarts reproductibles et adaptations définies. L’inférence oMLX reste non qualifiée sans Mac ; les modèles de production et flux intégrés doivent passer leurs critères après développement. Ces limites sont explicites, sans arbitrage métier caché. |
| Analyse complète pour engager le développement | **Oui, pour le périmètre fixé** | Architecture, contrats de connexion/identité, migrations, profils, comptabilité, UX, risques, lots et critères de sortie explicités. |
| Hypothèses sur l’existant confrontées au code | **Oui pour les conclusions retenues** | Chaque prémisse de la matrice a des lecteurs/producteurs inspectés ; les points majeurs sont contre-vérifiés par tests, sonde isolée ou SDK installé. Les interfaces nouvelles sont étiquetées proposées. |
| Tokens/coûts/quotas cadrés | **Oui ; calibration matérielle de production reste une qualification** | Préflight vs usage, allocation vs maximum, owner/instance, coût local toujours zéro, retries/fallbacks et burst distingués. Contexte, deux requêtes concurrentes, usage et timeout éprouvés ; aucune capacité GPU inventée. |
| Registres/mémoire/persistance cadrés | **Oui** | Identity scoped, commits avant réseau, générations, round-trips, checkpoint/HITL/ReAct, effets et ledgers traités. Aucun nouvel état métier spéculatif. |
| Responsive/a11y et six langues cadrés | **Oui sur les critères d’acceptation** | Parcours et composants existants, états, focus, largeurs, reflow et matrice browser définis. Validation visuelle effective appartient au lot 7. |
| Plan assez précis pour démarrer immédiatement | **Oui dès le lot 0** | Interfaces, fichiers propriétaires, séquence TDD et oracles fournis ; aucune décision métier n’empêche les travaux de caractérisation et de socle. |

**Arbitrages métier bloquants : aucun dans le périmètre proposé.** Le support de plusieurs endpoints d’une même famille, BYOK par utilisateur, extensions embeddings/Live ou gestion automatique du serveur ne sont pas implicitement inclus.

**Conditions avant de déclarer le support complet :** adapter les différences de contrat observées et qualifier les flux intégrés après développement ; valider les modèles choisis pour chaque poste et la concurrence matérielle de production ; disposer d’un endpoint Apple Silicon pour l’inférence oMLX. Les sondes API stables déjà exécutées sont acquises dans leurs limites exactes. Aucun arbitrage métier supplémentaire n’empêche de commencer le développement.
