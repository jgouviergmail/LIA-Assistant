# Qualification des API stables des serveurs locaux

Campagne du 6 octobre 2026, exécutée inline, avant toute implémentation métier de l’extension. Les requêtes réelles partent du conteneur API LIA. Elles utilisent uniquement des prompts synthétiques, un petit modèle local et des outils fictifs sans effets externes.

**Décision produit : coût fournisseur toujours zéro pour Ollama, oMLX, llama.cpp et LM Studio.** Les tokens, limites et tentatives restent comptabilisés. Cette campagne ne modifie pas la comptabilité de l’application : la règle est inscrite dans le [plan d’implémentation](../../plans/2026-10-06-openai-compatible-servers.md).

## 1. Versions et identité de la campagne

Les versions stables ont été vérifiées sur les sources officielles et confrontées aux binaires ou sources réellement utilisés. Les URLs de téléchargement, hashes, paramètres et la révision du modèle sont dans le [manifeste](manifest.json).

| Famille | Référence stable vérifiée | Artefact effectivement éprouvé | Portée |
|---|---|---|---|
| Ollama | [v0.35.1](https://github.com/ollama/ollama/releases/tag/v0.35.1) | Binaire Windows portable officiel, API `/api/version` = `0.35.1` | API compatible et transport natif LIA |
| llama.cpp | [v0.6.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0) | Build CPU Windows b11429, commit `d81235049384534c167caea52b85a694f6103d14` | API compatible réelle |
| LM Studio | [daemon stable fourni par l’installeur officiel](https://lmstudio.ai/install.sh) | llmster `0.0.25+1`, CLI `69d945a`, moteur CPU `llama.cpp-linux-x86_64-avx2-2.41.0` | API du daemon headless réel, conteneur isolé |
| oMLX | [v0.7.0](https://github.com/jundot/omlx/releases/tag/v0.7.0) | Sources de cette release, tests officiels de schémas et conversion | Contrats uniquement, sans inférence MLX |

Le build llama.cpp annonce `0.6.0-dev` dans son exécutable. Son commit a été comparé au commit du tag stable annoté v0.6.0 ; ils sont identiques. Le build b11429 est celui référencé par cette release : aucune nightly ultérieure n’a été substituée.

La version desktop LM Studio [0.4.25](https://lmstudio.ai/changelog/lmstudio/lmstudio-v0.4.25) est la référence stable affichée sur le site au moment du contrôle. Le logiciel exécuté est **llmster 0.0.25+1**, pas l’application graphique 0.4.25. Le projet présente llmster comme son [moteur autonome pour les déploiements headless](https://lmstudio.ai/docs/developer/core/headless). Les résultats portent précisément sur ce daemon et son moteur.

Le propriétaire ne dispose pas de Mac. Aucun endpoint Apple Silicon n’était disponible : **l’inférence oMLX demeure non qualifiée**. Les tests de ses schémas ne sont pas comptés comme une preuve d’inférence.

Modèle commun : GGUF Qwen3-0.6B, quantification Q8_0, dépôt officiel [Qwen/Qwen3-0.6B-GGUF](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF), révision `23749fefcc72300e3a2ad315e1317431b06b590a`. Son SHA-256 est consigné dans le manifeste. Ce choix borne le coût matériel du test ; il n’est pas une recommandation de modèle de production ou un changement des modèles par défaut de LIA.

Les instances sont chargées avec un contexte de 2 048 tokens et un seul slot. Les métadonnées annoncent un maximum théorique supérieur ; les tests utilisent le contexte **alloué**, pas ce maximum. Les templates et overrides sont identifiés par le modèle, les versions et le manifeste. Les versions des clients effectivement utilisées figurent dans chaque preuve JSON.

## 2. Résultats, sans masquer les écarts

| Serveur | Socle réel | Cas complémentaires | Total | Écarts conservés |
|---|---|---|---|---|
| Ollama | 18/18 | 8/10 | **26/28** | Plan métier invalide avec ce replay ; raisonnement perdu dans le client ChatOpenAI compatible |
| llama.cpp | 17/18 | 9/10 | **26/28** | Modèle inexistant servi implicitement ; raisonnement perdu dans ChatOpenAI |
| LM Studio / llmster | 13/17 | 7/10 | **20/27** | Objet `tool_choice` refusé sur trois parcours ; modèle inexistant servi ; `json_object` refusé ; plan métier invalide ; raisonnement perdu dans ChatOpenAI |

**72 cas réussis sur 83 sondes réelles ; 11 écarts restent visibles dans les résultats.** Le harnais termine la collecte même lorsqu’un cas échoue : son exit 0 signifie que la campagne a terminé, pas que chaque contrat est accepté. Les verdicts sont dans `cases[].passed`, avec les réponses brutes et les causes.

Pour oMLX : **81 tests officiels de schémas réussis**, puis **491 tests de conversion et parsing réussis**. Les 59 autres tentatives (44 échecs, 15 erreurs de setup) exigent `mlx_lm`, absent de ce runtime Linux. Toutes leurs causes capturées sont `ModuleNotFoundError`; elles ne sont ni reclassées en succès, ni présentées comme des régressions d’inférence. Le [résumé machine](omlx-contract-summary.json) conserve ces verdicts. Les commandes ont désactivé le `conftest` amont et n’ont pas simulé un moteur MLX.

Le socle LIA existant a également été caractérisé avant cette campagne : 50 tests unitaires Ollama/URL/profils/contexte réussis, détaillés dans le plan lié. Ils ne sont pas ajoutés au total des sondes réelles.

## 3. Couverture réellement exercée

| Contrat | Ollama | llama.cpp | LM Studio / llmster |
|---|---|---|---|
| Listing et métadonnées natives | Réussi, identifiant canonique avec `:latest` | Réussi, contexte alloué et template dans `/props` | Réussi, modèle disponible distinct de l’instance chargée |
| Texte et usage complet | Réussi | Réussi | Réussi |
| JSON Schema simple strict | Réussi | Réussi | Réussi |
| `$ref`, objets imbriqués, nullable, liste, enum | Réussi | Réussi | Réussi |
| Schéma réel LIA `ParameterItem` et validation Pydantic | Réussi | Réussi | Réussi |
| Schéma complet LIA `ExecutionPlan` | JSON accepté ; validation métier échoue | Réussi sur ce replay | JSON accepté ; validation métier échoue |
| Outil automatique et résultat réinjecté dans l’historique | Réussi | Réussi | Réussi |
| Outil imposé par objet nommé | Réussi | Réussi | HTTP 400, également avec le SDK |
| Outil unique imposé par `required` | Réussi : complet, streaming, SDK | Réussi : complet, streaming, SDK | **Réussi : complet, streaming, SDK** |
| Streaming d’outils en mode `auto` | Réussi | Réussi | Réussi |
| Streaming texte, `[DONE]`, usage final | Réussi | Réussi, chunk à `choices=[]` traité | Réussi |
| Limite de sortie et `finish_reason=length` | Réussi | Réussi | Réussi |
| Identifiant de modèle inexistant | HTTP 404 | HTTP 200, autre modèle annoncé | HTTP 200, autre modèle annoncé |
| Message malformé | Refus | Refus | Refus |
| Clé invalide | Serveur local sans authentification, non exercé | HTTP 401/403 attendu et constaté | Instance sans authentification, non exercé |
| Dépassement du contexte alloué | Refus | Refus | Refus |
| Deux requêtes simultanées avec un slot | Réussi | Réussi | Réussi |
| Fermeture SSE, puis requête suivante | Réussi | Réussi | Réussi |
| Read timeout réel, puis requête suivante | Réussi | Réussi | Réussi |
| Texte, usage et JSON Schema via ChatOpenAI installé | Réussi | Réussi | Réussi |
| Raisonnement sur le flux brut | Observé | Observé | Observé |
| Conservation dans les chunks ChatOpenAI | **Échec** | **Échec** | **Échec** |
| Mode `response_format=json_object` | Réussi | Réussi | **HTTP 400** |
| API native et client `ChatOllamaTraced` existant | Réussi | Sans objet | Sans objet |

Le test de concurrence établit que deux requêtes ont abouti ; il n’est pas un benchmark de capacité GPU, de rate limits ou de saturation multi-utilisateurs. Fermer un flux ou subir un timeout ne prouve pas l’arrêt immédiat du calcul côté serveur. Aucune lecture d’énergie ou de coût matériel n’a été effectuée.

## 4. Décisions techniques tirées des échecs

1. **LM Studio exige un profil de transport précis.** La réponse brute refuse les objets nommés pour `tool_choice`, et annonce accepter `none`, `auto`, `required`. Le client doit traduire un choix explicite en proposant uniquement cet outil avec `required`, préserver l’historique et laisser les autorisations à LIA. Les quatre sondes complémentaires outils passent avec cette forme. Le JSON mode `json_object` ne doit pas être choisi comme fallback automatique pour ce daemon ; JSON Schema et prompt validé restent des méthodes distinctes.
2. **L’identifiant demandé doit être contrôlé par LIA.** llama.cpp et llmster, avec une seule instance dans cette campagne, servent leur modèle chargé pour un nom absent et annoncent le modèle réellement choisi. Le lecteur de découverte doit identifier le modèle ou son alias reconnu avant l’appel. Un désaccord au retour est un diagnostic d’intégrité, pas un droit à mélanger capacités et contexte. Les configurations multi-modèles restent à éprouver séparément.
3. **Le client compatible doit préserver le raisonnement.** Les flux bruts montrent `reasoning_content`; les chunks du client installé le perdent. La perte est reproduite par une inférence réelle, en plus de la lecture du code du SDK. Le client natif Ollama n’est pas remplacé : les échecs ChatOpenAI sur Ollama caractérisent son pont compatible, pas une régression du client natif LIA.
4. **Le schéma JSON n’exécute pas les règles métier.** Sur le replay de clarification, Ollama omet `metadata.needs_clarification`; LM Studio produit `needs_clarity`. Les validateurs `ExecutionPlan` refusent correctement les plans sans étape. Les mêmes poids passent sur llama.cpp avec son template et son moteur. Le modèle ne peut donc pas être déclaré qualifié pour tous les postes sur la seule réussite de JSON Schema ou des outils. Les validations et reprises bornées sont nécessaires ; aucun plan rejeté ne doit exécuter un outil ou modifier la mémoire.
5. **Le renommage SDK de la limite de sortie est une différence à maîtriser, pas une panne constatée ici.** Les requêtes ChatOpenAI, dont le payload contient `max_completion_tokens`, passent sur ces trois combinaisons. La neutralisation des heuristiques OpenAI reste justifiée pour une identité et un contrat local explicites ; on ne prétend pas que ces serveurs stables ont refusé ce champ.

Une [contre-vérification tarifaire isolée](local-cost-collision.json), distincte des 83 sondes API, a exécuté le calculateur réel avec un snapshot synthétique. Il reçoit le nom seul et applique un tarif payant à un appel déclaré local homonyme. Aucun cache du processus servant les utilisateurs n’a été modifié. Le lot comptabilité transmettra le fournisseur et retournera zéro pour les quatre familles avant tout lookup ; les chemins directs hors callback sont inclus.

Ces décisions sont reportées dans les lots découverte/client/structured du plan. Les preuves constituent le socle des tests de caractérisation à écrire avant l’implémentation.

## 5. Preuves et reproduction

- [Harnais Python](probe_local_apis.py), deux suites : `core` et `edge`.
- [Ollama : socle](ollama.json), [cas complémentaires](ollama-edge.json).
- [llama.cpp : socle](llamacpp.json), [cas complémentaires](llamacpp-edge.json).
- [LM Studio : socle](lmstudio.json), [cas complémentaires](lmstudio-edge.json).
- [oMLX : résumé des tests officiels](omlx-contract-summary.json).
- [Manifeste de téléchargement et d’exécution](manifest.json).
- [Collision tarifaire : calculateur réel et snapshot isolé](local-cost-collision.json).
- [Première collecte llama.cpp](llamacpp-initial.json) et [première collecte Ollama](ollama-initial.json), conservées pour expliquer les corrections du harnais.

La première collecte llama.cpp comportait un `PYTHONPATH` manquant pour importer le schéma LIA et une consigne textuelle que le petit modèle interprétait mal. La consigne a été explicitée sans affaiblir l’assertion sur `probe`, et l’environnement d’import corrigé. La première collecte Ollama a utilisé le nom sans tag alors que le listing annonce `:latest`; la campagne finale utilise l’identifiant découvert. Les échecs de contrat et de validation métier de la campagne finale n’ont pas été corrigés dans les serveurs ou masqués.

Après avoir démarré les serveurs isolés selon le manifeste, copier le harnais dans le conteneur API, puis exécuter, pour chaque serveur :

```text
docker cp docs/superpowers/qualification/2026-10-06/probe_local_apis.py lia-api-dev:/tmp/lia-probe-local-apis.py
docker exec -w /app -e PYTHONPATH=/app lia-api-dev python /tmp/lia-probe-local-apis.py --kind llamacpp --base http://host.docker.internal:12911 --output /tmp/lia-qualification-llamacpp.json
docker exec -w /app -e PYTHONPATH=/app lia-api-dev python /tmp/lia-probe-local-apis.py --kind llamacpp --base http://host.docker.internal:12911 --suite edge --output /tmp/lia-qualification-llamacpp-edge.json
```

Pour Ollama, remplacer `--kind`, utiliser le port 12912 et `--model lia-qa-qwen3:latest`. Pour llmster, utiliser `--kind lmstudio` et `http://lia-qa-lmstudio-20261006:12913` depuis le même réseau Docker privé.

Mise en place exacte des serveurs :

- llama.cpp : `llama-server -m <GGUF> --host 127.0.0.1 --port 12911 --alias lia-qa-qwen3 -c 2048 --parallel 1 --threads 4 --threads-batch 4 --api-key lia-qualification-key`, avec `LLAMA_ARG_CHAT_TEMPLATE_KWARGS={"enable_thinking":false}` dans l’environnement du processus. Le secret est fictif et ne protège aucun compte utilisateur.
- Ollama portable : `serve` avec `OLLAMA_HOST=127.0.0.1:12912`, un `OLLAMA_MODELS` temporaire, `OLLAMA_NUM_PARALLEL=1`. Importer par `ollama create lia-qa-qwen3 -f <Modelfile>` sur cette adresse ; le Modelfile contient `FROM <GGUF>`, `PARAMETER num_ctx 2048`, `PARAMETER num_predict 160`, `PARAMETER temperature 0`. Aucun template personnalisé n’est ajouté.
- llmster : bundle Linux officiel bootstrapé dans un conteneur dédié, modèle monté en lecture seule et référencé dans son répertoire de modèles. `lms load qwen3-0.6b --gpu off --context-length 2048 --parallel 1 --identifier lia-qa-qwen3 --yes`, puis `lms server start --port 12913 --bind 0.0.0.0`. Aucun port n’est publié sur l’hôte et CORS reste désactivé. Le daemon Windows temporaire a refusé de coexister avec l’installation existante ; celle-ci n’a pas été arrêtée pour les tests.

Les commandes de tests officiels oMLX, après copie des sources du tag dans `/tmp/lia-qa-omlx` :

```text
docker exec -w /app -e PYTHONPATH=/tmp/lia-qa-omlx:/app lia-api-dev python -m pytest -c /dev/null --noconftest /tmp/lia-qa-omlx/tests/test_openai_models.py -q
docker exec -w /app -e PYTHONPATH=/tmp/lia-qa-omlx:/app lia-api-dev python -m pytest -c /dev/null --noconftest /tmp/lia-qa-omlx/tests/test_openai_adapter.py /tmp/lia-qa-omlx/tests/test_tool_calling.py -q --junitxml=/tmp/omlx-contract-results.xml
```

Les avertissements observés portent sur les dépréciations Pydantic des sources oMLX et sur Node lors du bootstrap llmster. L’échec de téléchargement d’une couche Docker Ollama a été contourné par le binaire portable officiel vérifié ; aucun daemon Docker partagé n’a été redémarré ou nettoyé.

## 6. Limites avant de déclarer la fonctionnalité intégrée

Les nouveaux fournisseurs ne sont pas implémentés. Les parcours front, migrations, cache composé, quotas, mémoire, registres, pipeline/ReAct et outils à effets externes seront éprouvés lors des lots TDD du plan. Ces tests API ne peuvent pas remplacer les tests d’intégration d’un code encore absent.

La vision, les modèles multiples, les vrais modèles affectés aux postes, l’authentification LM Studio/oMLX, les proxies/TLS et la capacité matérielle de production restent à qualifier dans les environnements concernés. oMLX exige toujours une sonde réelle Apple Silicon pour obtenir le même niveau de preuve d’inférence.

Les processus créés pour cette campagne sont arrêtés ; le modèle Ollama temporaire est déchargé et le conteneur llmster dédié est supprimé. L’état final des téléchargements est indiqué dans le manifeste. Les installations et services utilisateur sont préservés. Le harnais passe Black et Ruff selon la configuration backend de LIA ; le contrôle documentaire de la campagne passe également.
