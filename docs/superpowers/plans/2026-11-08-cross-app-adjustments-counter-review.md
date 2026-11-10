# Ajustements transverses — contre-revue des trois points sensibles

Date : 2026-11-08. Analyse uniquement, exécutée inline, sans sous-agent ni modification du code métier. Ce document précise les arbitrages de l'[analyse](2026-11-08-cross-app-adjustments-analysis.md) et du [plan TDD](2026-11-08-cross-app-adjustments-plan.md). Il distingue la preuve du comportement actuel, l'expérience de faisabilité et les critères d'acceptation de l'implémentation future.

## 1. Peer : modification minimale et défaut de livraison distinct

### Autorité et idempotence

Sources relues : [vocabulaire](../../../apps/api/src/domains/agents/registry/catalogue.py), [décision du gate](../../../apps/api/src/domains/agents/effects/gate.py), [runtime](../../../apps/api/src/domains/agents/effects/runtime.py), [scope](../../../apps/api/src/domains/agents/effects/scope.py), [outil peer](../../../apps/api/src/domains/agents/tools/peers_tools.py), [verrou de paire](../../../apps/api/src/domains/peers/pair_fence.py).

La politique `direct` reste nécessaire : envoyer à un tiers n'est ni une lecture, ni une production de brouillon, ni une mutation qu'un appel peut annuler. L'alternative `confirm` avec une approbation fabriquée détournerait le sens du registre. En revanche, **une deuxième clé d'idempotence dans PeerMessage n'est pas nécessaire** pour retirer le HITL.

Le registre possède déjà le claim, la clé stable de l'appel, la restitution du résultat et la clôture après cancellation. `_serve_lost_claim` refuse de rejouer un acte abandonné ou un acte dont le résultat est inconnu. La correction minimale consiste à exiger ces garanties sur la nouvelle politique ; elle ne consiste pas à construire une deuxième autorité de reprise.

| Cas | Contrat de `direct` à implémenter | Preuve/raison |
|---|---|---|
| Demande attendue, scope valide, claim gagné | Exécuter une seule insertion ; aucune carte d'envoi | Chemin LEDGER existant et résultat structuré d'enqueue. |
| Même identité, résultat enregistré | Restituer le résultat sans réinsérer | `_serve_lost_claim` et tests du gate existants. |
| Même identité, claim encore actif ou résultat perdu | Dire l'état connu/inconnu, ne pas réexécuter | Déjà couvert par le gate ; aucun mécanisme de retry de message ajouté. |
| Scope ou identité utilisateur absent | Refus explicite avant enqueue | Le fallback actuel serait permissif ; branche nouvelle obligatoire. |
| Registre indisponible / pas de claim | Refus explicite, aucun enqueue | `_unrecorded_or_refused` ne refuse actuellement que `confirm`. Étendre à `direct`, sans changer les autres politiques. |
| Routine sans interlocuteur ni autorité déjà approuvée | Refus d'autorité, sans carte | Conserver le prédicat `nobody_can_answer` actuel et son contexte de porteur ; ne pas ouvrir l'autonomie implicitement. |
| Initiative d'enrichissement | Outil non admissible | Aujourd'hui exclu par `create` ; rendre `initiative_eligible=False` explicite. |
| Autre effet du même plan / FOR_EACH | Ses propres règles continuent | Le retrait du brouillon peer ne supprime pas l'autorité d'un autre acte. |

La sonde de règle pure appelle le gate actuel avec la chaîne future : attended, scheduled et sans scope arrivent **tous** à LEDGER. C'est un contre-exemple à « ajouter l'enum suffit », pas une implémentation de `direct`.

La commande commune d'enqueue revalide connexion, appartenance et blocages ; redérive le destinataire depuis la paire ; vérifie les quotas puis insère. Elle réutilise `lock_peer_pair` avant le verrou de connexion. Cette porte verrouille les deux comptes en ordre canonique : deux envois du même émetteur à des destinataires différents se sérialisent déjà sur ce compte. Les tests PostgreSQL existants prouvent la compatibilité de ces verrous avec les FK et l'ordre des writers de partage/blocage. Ajouter un verrou d'émetteur indépendant serait une complication dangereuse.

Un crash après insertion mais avant clôture du registre peut laisser un résultat inconnu : la sécurité est de ne pas réinsérer automatiquement, pas de promettre qu'un résultat sera toujours récupérable. La ligne peer reste livrable. Les anciens brouillons continuent à attendre leur décision explicite et empruntent la commande commune ; aucune carte ancienne n'est auto-approuvée.

### Livraison : preuve et séparation du lot

Sources : [repository](../../../apps/api/src/domains/peers/repository.py), [livreur](../../../apps/api/src/infrastructure/scheduler/peer_message_delivery.py).

Un test de caractérisation sur PostgreSQL jetable a exécuté les méthodes réelles dans cet ordre : enqueue ; claim A + commit ; vieillissement de la seule ligne fictive ; récupération ; claim B + commit ; clôture par A ; clôture par B. Résultat : **A obtient True, B False**. Le statut `delivering` seul ne porte donc pas l'autorité de la tentative. Aucun dispatcher ni destinataire réel n'a été appelé.

Ce défaut existe avant le retrait du HITL. Le correctif propriétaire/token/génération et la reprise de notification durable constituent le sous-lot 5C, revu séparément. Ils ne justifient pas une migration d'idempotence d'enqueue dans 5B. Ils restent nécessaires avant de certifier la fiabilité complète du livreur, avec les essais crash, reprise, cancellation et résultat de settle prévus au plan. Un test ayant reproduit une clôture illégitime n'est pas une preuve de doublon en production.

Le dispatcher utilise déjà `require_durable=True` : l'accuser de valider un simple SSE serait un faux positif. Le livreur ignore en revanche le booléen de `mark_message_delivered`. Son retry englobe toute erreur de génération ; il faut séparer un échec rejouable d'une génération à résultat inconnu selon la politique centrale, et distinguer génération acquittée, livraison durable et notification de l'émetteur.

## 2. Alertes : contrat de recherche et lecteurs propriétaires

### Sémantique arrêtée

La recherche porte sur les **valeurs métier présentées dans la liste**, avec un fragment littéral normalisé par le helper commun ; une correspondance dans un des champs suffit. `%` et `_` sont des caractères, pas des jokers SQL. Pas de recherche dans les métadonnées cachées, les justifications internes, le coût, les URL de source non affichées, ni dans le contenu d'une autre rubrique. Les dates et libellés d'interface traduits restent des contrôles/catégories, pas un moteur de parsing de date ou de traduction. Les noms et le texte ne sont pas envoyés au LLM.

Ce choix de fragment est déduit du comportement réel de [RelationCardList](../../../apps/web/src/components/relations/RelationCardList.tsx) : `normalizeSearchText(...).includes(needle)`. **Ne pas confondre recherche et identité** : [normalizeSearchText](../../../apps/web/src/lib/utils.ts) applique lowercase/NFD, enlève les marques U+0300–036F et replie apostrophes/espaces typographiques ; `fold_name` fait NFKD/casefold et conserve les apostrophes. Ils ne sont pas équivalents pour `Straße`, `d’authentification` et les caractères de compatibilité. Créer une porte backend de recherche d'affichage, jumelle du contrat frontend et tenue par un corpus partagé ; ne pas modifier `fold_name`, les identities ni les highlighters existants. La même porte sert les filtres d'espaces, d'alertes et les fragments SMS ; `fold_name` reste réservé au classement/matching des noms où son contrat est voulu.

Pour « Nom », la clé est le nom/titre réellement disponible ; faute de titre, le texte métier normalisé. Pas de titre inventé par IA. Une égalité se départage par la date puis l'id. Les catégories sont les sections/kinds actuels autorisés, pas un nouveau classement sémantique. Les offres/décisions conservent leur place et leur fonctionnement distincts.

Les dates À suivre restent celles affichées : échéance/prochaine occurrence, sans repli silencieux sur une date de création non montrée. Les dates absentes sont en dernier dans les deux sens. Le libellé d'aide précise ce sens ; l'ordre initial peut préserver « prochaine d'abord » avant choix explicite du tri. Chronologie : récent par défaut. Aucune permutation des rubriques.

### Contrats source par source vérifiés

Tous les chemins ci-dessous sont relatifs à `apps/api/src/domains/`. Les extensions de critères sont additives ; sans nouveau critère, les consommateurs historiques gardent leur contrat.

| Rubrique | Porte et propriétaire actuel | Champs recherchés / Nom | Pagination à préserver/étendre |
|---|---|---|---|
| Peers | `GET /peers/messages`, `peers/router.py`, `PeersRepository._delivered_with_peer` / `list_delivered_message_activity` | `peer_display_name`, texte directionnel ; nom du peer | limit/offset ; delivered_at + id ; mêmes ACL et compteurs. L'émetteur voit sa directive, le destinataire sa restitution. |
| Proactivité | `GET /heartbeat/history`, `heartbeat/router.py`, `HeartbeatNotificationRepository.get_history` | `content` ; contenu | limit/offset ; created_at ; ajouter id au départage. |
| Intérêts | `GET /interests/notifications/history`, `interests/notifications_router.py`, `InterestNotificationRepository.get_history` | `topic` du centre d'intérêt accessible et `content` ; topic sinon contenu | limit/offset ; created_at + id ; conserver le chargement eager et l'ACL de la relation. Pas de champ `title` supposé. |
| Discussions | `GET /proactive-discussions/openings`, `proactive_discussions/router.py`, `openings.py` / `native_discussion_page` | `ConversationMessage.content` visible ; contenu | curseur after_id actuellement dépendant de recorded_at/id ; nouveau curseur versionné lié aux critères pour les autres ordres. Ne pas modifier le helper partagé pour tous ses consommateurs par accident. |
| SMS | `POST /sms/search`, `sms/router.py`, `SmsFacade` / `SmsReadService` | corps et display_name ; display_name | curseur signé/chiffré propriétaire + révision + as_of ; extension spécifique ci-dessous. |
| Rappels | `GET /reminders`, `reminders/router.py`, `ReminderRepository` / `pending_reminders` | content ; content | limit/offset ; trigger_at + id ; pending uniquement. |
| Routines | `GET /scheduled-actions`, `scheduled_actions/router.py`, service/repository | title et schedule_display ; title | collection entière puis page client actuelle ; trier/filtrer toute la collection, pas une page. Condition routines : prochaine date éventuellement absente. |
| Workboard | `GET /workboard/needs-me`, `workboard/service.py`, `repository.py` / `board_queries.needs_me_stmt` | title uniquement ; title | limit/offset ; due_at NULLS LAST + id ; garder les droits owner/holder et le prédicat métier. La description n'est pas rendue par NeedsMeList. |

Les clauses communes ACL + critères alimentent page et compte exact, avec un même instant `as_of` lorsque l'éligibilité dépend du temps. Pour les projections normalisées calculées en Python, compter et classer le jeu filtré dans la même lecture avant pagination, sans filtre SQL plus restrictif que le contrat de recherche d'affichage. Les lectures ne doivent charger que les colonnes utiles, sans embeddings ni objets ORM lourds. Une borne de ressources dépassée donne une indisponibilité explicite, jamais un total partiel annoncé exact. Les mesures au plafond de données et les EXPLAIN des variantes SQL sont des gates de développement, pas des performances déjà mesurées par cette étude.

La chronologie conserve ses six sources et sept kinds. Filtrer et choisir le sens **avant** le plafond de chaque source ; la projection des événements créés/clos d'une boucle précède ce plafond. Le total filtré ne se déduit pas du pool plafonné. `failed_kinds`, `truncated` et `has_more` ont des fonctions différentes. L'expérience initiale de sept événements démontre les deux erreurs de filtre/tri après coupe.

Les compteurs de sections fermées ne déclenchent pas une résolution de contacts ou le déchiffrement des SMS pour une recherche jamais ouverte. Hors recherche, conserver les comptes généraux. Sous recherche, un compte filtré inconnu affiche `—` jusqu'à la lecture de sa section ; aucun zéro simulé. `_safe_count` doit aussi distinguer panne et vide. Une réponse est associée à `{owner, source, q, kinds, sort, as_of}` ; tout changement remet à zéro la pagination et rend les anciennes réponses inapplicables.

### SMS : deux erreurs du premier plan corrigées

Sources : [recherche](../../../apps/api/src/domains/sms/search.py), [lectures](../../../apps/api/src/domains/sms/reads.py), [façade](../../../apps/api/src/domains/sms/facade.py), [identités](../../../apps/api/src/domains/sms/identity_resolution.py), [index](../../../apps/api/src/domains/sms/search_index.py), [ingestion](../../../apps/api/src/domains/sms/ingestion.py).

1. **Ne pas substituer une recherche lexicale à la recherche d'affichage.** La lecture réelle sur PostgreSQL trouve un SMS pour `facture` et zéro pour `fact`, alors que son corps affiche « facture ». Conserver le mode lexical des outils, ajouter un mode d'affichage explicite dans la même porte autorisée. Le nom d'expéditeur n'est pas une recherche dans le corps et `sender_id` est l'id d'un SMS, pas celui d'un contact.
2. **Ne pas limiter un tri par nom au nombre de corps vérifiables.** Une archive de 501 messages avec deux expéditeurs demande deux résolutions de nom, pas 501 déchiffrements de corps. La sonde vérifie cet ordre sur données fictives ; le test SQL du futur reader doit prouver la même propriété avant validation.

Architecture de recherche d'affichage arrêtée :

- Ajouter une projection de fragments HMAC séparée de l'index lexical, dans son stockage propriétaire. Le prototype de faisabilité utilise les trigrammes de la chaîne normalisée. Une requête de moins de trois caractères passe par la vérification bornée sans filtre de trigrammes ; elle peut être refusée comme trop large, jamais déclarée sans résultat à tort.
- Le corps est candidat si ses fragments contiennent ceux du fragment demandé **ou si sa projection est absente, ancienne ou incomplète**. Vérifier ensuite la présence littérale dans le corps déchiffré. La sonde couvre 85 572 sous-chaînes sans faux négatif et prouve un faux positif de trigrammes : `abc---bcd` possède les grammes de `abcd` sans contenir `abcd`. La vérification exacte est obligatoire.
- Réutiliser `blind_digest` avec une finalité distincte, la clé par compte, le cycle d'effacement et les budgets. Aucune nouvelle copie durable en clair. Prévoir des colonnes de projection/complet/version propres au mode fragment : ne pas dégrader la complétude de l'index lexical pour loger les fragments.
- Les writers sont `sms/ingestion.py` et `sms/search_index.py`. Le calcul de `logical_bytes`, le quota d'archive, la migration additive, le rebuild atomique à côté de l'index actif et les lectures de versions doivent évoluer ensemble. La migration ne purge pas le bon index et n'appelle pas de fournisseur. Une génération refusée conserve l'ancienne ; le mode nouveau indique son indisponibilité ou vérifie les candidats manquants sous budget.
- Le coût est matériel : l'échantillon français de 83 caractères ajoute 78 empreintes, soit 2 496 octets bruts avant structures PostgreSQL ; ce n'est pas une estimation universelle ni une mesure physique de GIN. Une archive proche de son quota peut refuser le rebuild. Mesurer stockage physique et latence sur le corpus de charge avant de retenir les paramètres ; ne jamais relever un ratchet pour absorber ce coût.
- Résoudre les expéditeurs distincts sous `as_of`, hors transaction pendant I/O, avec `resolve_senders`. Pour une recherche, leurs hashes exacts correspondant au nom affiché forment l'autre branche du prédicat (nom **OU** corps), avec déduplication des ids. Pour un tri par nom, joindre un mapping éphémère hash→rang validé, puis ORDER BY rang/date/id en SQL. Aucune colonne de nom en clair persistée.
- Valider le scope de résolution avant publication. Le curseur lie critères, compte, as_of, révision de données, génération d'identités et empreinte du mapping. Alias/contact changé, retrait de capacité ou reset : refus de curseur et reprise explicite. La mémoire temporaire de noms a un budget de distincts indépendant du budget de corps ; un dépassement demande une restriction de période via les bornes déjà acceptées par SmsQuery.
- Un compte exact de correspondances par nom se calcule sans déchiffrer tous leurs corps. Les correspondances corps restantes sont vérifiées sous budget puis unionnées sans compter deux fois. Les corps ne correspondant que par nom ne sont déchiffrés que pour la page présentée.

L'index de fragments est donc un sous-lot réel, pas une capacité attribuée à l'existant. C'est le prix de conserver le comportement demandé sans stocker les SMS en clair. Aucune installation de dépendance, migration ou index n'a été exécuté dans cette étude.

## 3. Menus : preuves avec les vrais composants React

La fixture importe les composants de production Input, Textarea, RichBody et Dialog, ainsi que `useAssistCall`, `handOff`/`takeHandoff`, `useHandoff` et `normalizeSearchText`. Les traductions et le transport HTTP sont remplacés ; ce dernier ignore volontairement l'abort pour éprouver les réponses tardives. Les fonctions de navigation/Workbench non invoquées échoueraient si appelées. Le style du containing block transformé est reproduit explicitement ; la feuille CSS complète de l'application n'est pas chargée. Aucun rendu de l'application complète ni appel fournisseur n'est prétendu.

| Expérience | Résultat identique sur Chromium / Firefox / WebKit | Arbitrage |
|---|---|---|
| Insertion dans Input/Textarea contrôlés | Valeur et state changent ; undo restaure | Adaptateur de commande native, pas affectation DOM muette. |
| Insertion dans le vrai RichBody | Texte changé ; undo restaure `<p>Bonjour <b>monde</b> !</p>` | Réutiliser sa porte d'édition et respecter la plage/HTML hors sélection. |
| Portail brut dans body, parent modal | Focus demandé dans la bulle refusé | Un z-index ne suffit pas. |
| Portail DOM dans le Dialog transformé | `(20,20)` devient environ `(250,325–329)` | Ne pas appliquer des coordonnées viewport à ce contenant. |
| Dialog non modal imbriqué dans l'arbre React du parent, portail DOM body | Focus accessible, coordonnées `(20,20)`, parent conservé | Host React local et état central. |
| Même Dialog rendu en frère à la racine globale | Clic dans la bulle ferme le parent | Le provider global ne doit pas rendre toutes les bulles hors de leur arbre modal. |
| Formulaire de question dans un portail React sous un formulaire parent | Une soumission de bulle, zéro du parent avec preventDefault + stopPropagation | Protection explicite contre envoi accidentel de mail/chat. |
| Escape puis Escape | Ferme la bulle, restaure son déclencheur, puis ferme le parent | Laisser Radix gérer la couche ; restauration asynchrone attendue dans le test. |
| Réponse HTTP tardive après changement de scope | Résultat ignoré | Conserver ce mécanisme. |
| Retry après changement de scope | L'ancien body est renvoyé | Corriger le scope du dernier appel et effacer sa rétention. |
| Handoff sans identité de compte | Payload consommable sans contrôle d'owner | Store lié au compte, purge, TTL et prise atomique. |
| Handoff publié quand le consommateur est déjà prêt | Non reçu tant que ready ne change pas | Store observable et abonnement, pas un effet dépendant seulement de kind/ready. |

Le système générique a donc trois responsabilités séparées : provider d'état/snapshot/cancellation ; adaptateur de sélection/édition propriétaire de la cible ; host de couche interactif dans la surface React. Il garde un seul menu actif et un seul appel. Les hosts des modales s'enregistrent/se retirent ; une bulle ne s'enregistre pas récursivement comme nouveau host. Une surface native opaque ou un contrôle non textuel reste exclu explicitement.

L'adaptateur capture owner, cible, révision, valeur, sélection et bornes du champ. Avant application, il revalide l'ensemble, les limites et l'absence d'IME ; une cible obsolète n'est pas écrasée. Le résultat d'une commande native est contrôlé ; si elle n'est pas disponible, proposer Copier ou l'adaptateur explicite du composant, pas une mutation DOM dissimulée. Le choix est testé sur les trois moteurs actuels ; les tests futurs doivent garder cette couverture, car cette porte native est historique.

Le handoff reste éphémère, sans URL contenant du texte : dix minutes via constante UX, compte + proposition + destination discriminée, abonnement stable, consommation seulement quand le formulaire est prêt/libre. Retour arrière et remount ne réouvrent pas une proposition consommée ; formulaire modifié et proposition suivante ne s'écrasent pas. Une erreur d'indisponibilité de calendrier/liste conserve la proposition jusqu'à résolution ou expiration. La mémoire rejoint les réglages existants ; aucune création/embedding avant le Save manuel.

Les cas restant à qualifier sur l'implémentation sont nommés, pas présumés acquis : IME, sélection tactile et clavier logiciel sur appareils réels, host World, zoom, lecteur d'écran, permissions micro et coexistence audio, véritables routes de destination et révocation de connecteur. Ils sont les critères de sortie des lots 7–9.

## 4. Preuves, incidents de harness et reproductibilité

| Exécution de cette contre-revue | Résultat | Portée |
|---|---|---|
| Backend unitaire ciblé | **313 passed, 5,01 s, exit 0** | Gate, outils/livraison peer, SMS, notifications. |
| Backend intégration ciblé | **54 passed, 29,37 s, exit 0** | Lecteurs/index/identités SMS, comptes du hub, repository/verrous peer sur PostgreSQL neuf et Redis jetable. |
| Deux contre-exemples réels ajoutés dans output | **2 passed, 5,68 s, exit 0** | Confirment les défauts actuels : clôture peer par ancien owner, fragment SMS absent. Des tests verts ici attestent un défaut reproduit, pas sa correction. |
| Frontend composants/hooks | Première passe **74 passed / 5 failed**, exit 1 ; sept fichiers hors hub verts | Les cinq échecs appartenaient aux fixtures d'offres obsolètes du chantier concurrent. Aucun fichier métier/test de ce chantier modifié par cette étude. |
| Hub après modification concurrente constatée | **23 passed, 6,00 s, exit 0** | Le fichier a changé pendant la contre-revue ; les nouvelles fixtures ciblent habits/proposals. Ce succès ne remplace pas l'historique de la première passe. |
| Relance finale frontend complète ciblée | **83 passed, 8 fichiers, 11,76 s, exit 0** | Même sélection des huit fichiers, sur le snapshot intégrant les changements concurrents. |
| React réel, trois moteurs | **15 contrôles de caractérisation par moteur**, attendus vrais | Résultats positifs, contrat de normalisation et défauts reproduits, décrits ci-dessus. Pas des E2E de fonctionnalité future. |
| Simulation de candidats de recherche | **85 572 sous-chaînes**, aucun faux négatif dans ce corpus ; exit 0 | Condition nécessaire des trigrammes seulement ; aucune promesse de performance/absence de collisions HMAC en production. |

Les fichiers de sonde et résultats JSON sont sous `output/playwright/analysis-20261108/`. Ils sont des artefacts d'étude, pas une nouvelle suite produit livrée. Les premiers essais ont aussi rencontré des erreurs de harness : chemin de test inexistant (aucun test exécuté), configuration asyncio non chargée pour le test extérieur au répertoire habituel (setup refusé), dépendances de bundle non exercées non isolées, puis lecture de state avant la fin de l'effet React. Ces erreurs ont été corrigées dans le harness ; aucun test n'a été ignoré ni assertion produit affaiblie. Les verdicts ci-dessus proviennent des relances terminées.

Aucun warning de ressource ou de coroutine non attendue n'apparaît dans les résumés réussis. Les logs WARNING de scénarios de panne simulée ne sont pas des warnings de teardown. Les conteneurs PostgreSQL de test sont possédés et arrêtés par Testcontainers ; le Redis créé pour cette analyse a été arrêté par son id après vérification du nom. Aucun conteneur de chantier concurrent n'a été arrêté.

Commandes backend, depuis `apps/api` :

```powershell
.venv/Scripts/python -m pytest tests/unit/domains/agents/effects/test_gate_decision.py tests/unit/domains/agents/effects/test_gate_runtime.py tests/unit/domains/agents/effects/test_effect_metrics.py tests/unit/domains/agents/tools/test_peers_tools.py tests/unit/domains/peers/test_delivery.py tests/unit/domains/peers/test_repository_logic.py tests/unit/domains/sms tests/unit/domains/notifications -q --no-cov -o addopts='' -o faulthandler_timeout=45

# TEST_REDIS_URL doit désigner un Redis jetable dédié, sur /15.
# Sans TEST_DATABASE_URL, les fixtures démarrent leur propre PostgreSQL Testcontainers.
.venv/Scripts/python -m pytest tests/integration/test_sms_reads.py tests/integration/test_sms_search_index.py tests/integration/test_sms_identity_registry.py tests/integration/domains/notifications/test_hub_counts_db.py tests/integration/domains/peers/test_repository_db.py tests/integration/domains/peers/test_pair_fence_lock_order_db.py -q --no-cov -o addopts='' -o faulthandler_timeout=60

.venv/Scripts/python -m pytest -c pyproject.toml ../../output/playwright/analysis-20261108/test_current_boundaries.py -p tests.conftest -p tests.integration.conftest -q --no-cov -o addopts='' -o log_cli=false -o faulthandler_timeout=60

$env:PYTHONPATH = (Get-Location).Path
.venv/Scripts/python ../../output/playwright/analysis-20261108/review-probe.py
```

Commandes frontend/probe, depuis la racine :

```powershell
task test:frontend -- src/components/ui/__tests__/dialog.test.tsx src/components/ui/__tests__/dialog-retained.test.tsx src/components/ui/__tests__/dialog-focus-return.test.tsx src/components/workbench/mail/__tests__/RichBody.test.tsx src/components/workbench/assist/__tests__/useAssistCall.test.ts src/lib/workbench/__tests__/handoff.test.ts src/hooks/__tests__/usePagedSection.test.ts src/components/notifications/__tests__/NotificationsHub.test.tsx
task test:frontend -- src/components/notifications/__tests__/NotificationsHub.test.tsx
node output/playwright/analysis-20261108/react-probe.cjs
```

## 5. Verdict de conception et conditions de passage

Les trois arbitrages ne reposent plus sur une équivalence supposée : idempotence du registre explicitement réutilisée, défaut du livreur reproduit et séparé, écarts SMS pris en charge dans un sous-lot identifié, topologie React et édition testées avec les composants réels, deux lacunes de lifecycle reproduites. Aucun arbitrage métier supplémentaire n'est nécessaire pour démarrer les lots décrits.

La conviction porte sur cette conception et sur le caractère exécutable du plan. Elle ne vaut pas certification des fonctions non écrites, de la charge du futur index, des futurs contrats SQL ni du mobile physique. Les seuils et tests de sortie du plan demeurent obligatoires. Une assurance « 100 % sans aucun aléa » confondrait ces niveaux de preuve ; elle n'est pas revendiquée.
