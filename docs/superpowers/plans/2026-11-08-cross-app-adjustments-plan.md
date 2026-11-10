# Ajustements transverses LIA — plan d'exécution TDD

Date du cadrage : 2026-11-08. Implémentation autorisée le 2026-11-09.
Ce document conserve le découpage approuvé et sa liste initiale de vérifications.
L'état effectivement exécuté, les corrections de revue, les commandes et leurs limites
sont tenus dans le [registre de livraison](2026-11-09-cross-app-adjustments-progress.md).

Référence fonctionnelle et preuves : [analyse préalable](2026-11-08-cross-app-adjustments-analysis.md). Ce plan intègre les réponses utilisateur : horaires personnalisables ; actions de sélection pilotées par IA ; création dans l'écran natif prérempli ; conservation des rubriques d'alertes.

Consolidation : la [contre-revue](2026-11-08-cross-app-adjustments-counter-review.md) fixe les contrats des trois sujets approfondis et consigne les nouvelles preuves. Les lots 4, 5, 7 et 8 ci-dessous remplacent leurs arbitrages initiaux : index de fragments SMS explicite, tri sur expéditeurs distincts, claim d'effet réutilisé, host dans l'arbre React de la modale, retry et handoff liés au compte.

Exécution strictement inline, sans sous-agent. Aucun commit, branche, staging, push ou déploiement automatique. Ne pas appliquer les recommandations génériques de skills qui contrediraient ces contraintes. Toutes les tâches non cochées ci-dessous sont futures.

## Ordonnancement et conditions de passage

Ordre recommandé : 0 → 1 → 2 → 3 → 4 → 5A/5B → 6 → 7 → 8 → 9. Le correctif de livraison préexistant 5C est indépendant des autres fonctionnalités ; le traiter avant de valider la fiabilité complète du parcours peer. Dans le lot 4, stabiliser 4C avant d'exposer la recherche SMS et 4D avant d'exposer son tri par nom. Les domaines sont découpés pour rendre chaque changement révisable et testable ; cet ordonnancement n'exige pas plusieurs workers.

Chaque sous-lot suit le même cycle : écrire le test comportemental qui échoue pour la bonne raison ; apporter la plus petite modification cohérente ; vérifier ; refactorer sans modifier le contrat ; rejouer le test et les guards touchés. Une erreur d'import ou de fixture n'est pas un RED métier. Les fichiers proposés sont des responsabilités à créer uniquement si la source actuelle ne les fournit pas déjà.

| Lot | Résultat observable | Condition de sortie |
|---|---|---|
| 0 | Contrats et preuves de départ stabilisés | Recensement des surfaces, scénario de concurrence/undo/focus reproductible, aucune hypothèse silencieuse. |
| 1 | Mode automatique complet | Profil, stockage, bootstrap et runtime concordent ; plages personnalisables validées. |
| 2 | Espaces filtrables et triables | Recherche complète sur métadonnées, compteurs exacts, quatre tris. |
| 3 | Chronologie filtrable et triable | Filtre avant coupe, ordre déterministe, borne et données partielles honnêtes. |
| 4 | Reçues / À suivre filtrables et triables | Chaque rubrique exacte, paresseuse et isolée ; SMS conserve ses protections. |
| 5 | Envoi peer direct et tracé | Pas de carte d'envoi ; claim central obligatoire ; quotas atomiques. Livraison 5C qualifiée séparément. |
| 6 | Porte IA de sélection indépendante des Outils | Un appel, une attribution, un contrat de proposition ; capacités et timeouts cohérents. |
| 7 | Deux menus génériques opérationnels | Sélection lecture/édition, réponses locales, application sûre, modalité/mobile. |
| 8 | Créations préremplies et migration des usages | Tâche/agenda/mémoire natifs ; aucune création avant validation ; anciens menus remplacés. |
| 9 | Qualification et documentation | Gates applicables fraîches, parcours inter-domaines et limites déclarées. |

## Lot 0 — Fixer les frontières avant de modifier les consommateurs

- [ ] Relever les modifications concurrentes des fichiers concernés par lecture seule ; relire les CLAUDE.md applicables et l'analyse. Ne pas réinitialiser, déplacer ou formatter en masse les fichiers d'un autre chantier.
- [ ] Capturer une base des tests ciblés et des ratchets de taille/complexité ; identifier les hotspots actuels (router assists, managers, hub, peers repository). Les valeurs du baseline ne sont pas des budgets à augmenter.
- [ ] Recenser les composants `<input>`, `<textarea>`, contenteditable, lecteurs readOnly, overlays et surfaces World. Classer chacun : couvert par primitive, adaptateur spécifique, exclusion justifiée (secret, opaque, canvas). Rendre le recensement vérifiable par un test de garde sur les primitives et cas explicites, pas une promesse « tous les champs » non testée.
- [ ] Promouvoir les scénarios de la sonde React de contre-revue vers une fixture E2E maintenue : Input/Textarea contrôlés, RichBody, Dialog imbriqué, racine globale invalide. La faisabilité édition/undo/focus est maintenant prouvée avec les vrais composants ; les scénarios de menu futur, IME et tactile restent à ajouter. Ne pas inventer un composant Sheet absent des primitives recensées : couvrir les overlays réellement présents.
- [ ] Définir les enums de requêtes, la sémantique de date par rubrique et les états (`idle`, `running`, `answer`, `refused`, `stale`, `cancelled`) sans faire un booléen pour chaque combinaison.
- [ ] Écrire le corpus partagé de normalisation de recherche d'affichage et sa porte backend jumelle de `normalizeSearchText` : accents, apostrophes typographiques, espaces insécables, CJK, ß, ligatures/caractères de compatibilité, `%`/`_`. Ne pas détourner `fold_name` ni changer l'identité des personnes ; un test de parité tient les deux couches.
- [ ] Définir le contrat de handoff commun : `ownerId`, `proposalId`, `createdAt/expiresAt`, destination discriminée et proposition. Aucun contenu dans l'URL. Durée UX retenue : dix minutes, dans une constante commune ; ce choix n'est pas une durée de rétention serveur. Lecture par abonnement stable et consommation conditionnelle owner/id, pas un singleton lu seulement au montage.

Tests nouveaux proposés : `components/selection-assist/__tests__/SelectionTarget.test.tsx` et un scénario `e2e/smoke/selection-assist.spec.ts`, plus un petit corpus Unicode/horaires partagé par les tests de règles. Ne pas créer un package ni une dépendance supplémentaire pour ces seuls contrats.

## Lot 1 — Préférences et thème automatique

### 1A. Contrat et persistance

- [ ] RED : validation de `auto`, horaires stricts, PATCH partiel produisant deux horaires égaux, null explicite, booléen, hors borne, valeurs anciennes inchangées.
- [ ] Étendre `domains/users/display_preferences_columns.py`, `users/schemas.py`, `domains/shared/schemas.py` et `core/constants.py` ; deux colonnes minute avec contraintes et defaults centralisés. Appliquer la validation croisée après fusion avec le profil courant dans le service de mise à jour.
- [ ] Ajouter une migration additive à partir de la tête réellement courante ; ne pas supposer le numéro de révision aujourd'hui. Tester upgrade/downgrade sur base jetable, données existantes et contraintes par écriture SQL directe.
- [ ] Étendre UserProfile/UserBase, le type `lib/auth.ts`, la projection `agents/application/schema_projection.py` et les tests de la porte de préférences. Les opérations de mise à jour de thème par l'assistant doivent accepter les mêmes valeurs que l'UI.

Tests existants à localiser/étendre : tests users/display preferences et validations partagées. Nouveau fichier cohésif proposé : `tests/unit/domains/users/test_theme_schedule.py`, miroir d'un helper de validation si cette logique justifie son extraction.

### 1B. Résolution et interface

- [ ] RED : règle pure de plage semi-ouverte, minuit, horaires égaux refusés, fuseau du compte, passage DST printemps/automne, zones à décalage non entier, horloge avancée/reculée.
- [ ] Ajouter `lib/theme-schedule.ts` pour la règle pure ; faire évoluer `theme-mode.ts` en distinguant intention et rendu. Définir un provider de préférence unique consommé par `useThemeMode`, pas un timer par hook.
- [ ] Adapter `theme-init-script.tsx` et le provider pour la même résolution avant/après hydratation. Valider le cache local ; ne pas écrire un nouveau mode inconnu dans next-themes.
- [ ] Ajouter la radio auto et les deux champs horaires dans DisplayModeSelector. Indiquer le fuseau, la plage claire et l'enregistrement échoué, via les six locales.
- [ ] Tester le bouton cyclique : un clic quitte auto pour un mode manuel ; un tick d'horloge n'écrit ni le profil ni l'historique de navigation.
- [ ] Tester double montage, deux consommateurs, plusieurs onglets, refreshUser en retard, logout/relogin, offline/localStorage refusé, reprise après veille, suppression du timer.

Fichiers de tests existants : `lib/__tests__/theme-mode.test.ts`, `components/__tests__/theme-init-script.test.tsx`, `hooks/__tests__/useThemeMode.test.tsx`. Ajouter les scénarios de formulaire et navigateur au même domaine.

## Lot 2 — Liste des espaces et métadonnées de recherche

- [ ] RED : nom avec accents/casse, filename sur document non prêt, plusieurs fichiers correspondants mais une seule carte, aucun match, espace système exclu, espace géré conservé, autre compte invisible.
- [ ] Introduire les critères typés dans `rag_spaces/schemas.py` et `router.py`, puis une méthode de lecture de listing dans repository/service. Filtrage serveur sur métadonnées complètes, normalisation unique ; pas d'usage détourné du catalogue ready-only d'attachements.
- [ ] Remplacer les lectures de statistiques par espace sur ce chemin par une agrégation groupée. Totaux/documents prêts distincts, absence de gonflement par jointure. Départager chaque ordre par id.
- [ ] Mesurer nombre de requêtes et temps de lecture au plafond configuré, puis sur le cas historique dépassant ce plafond. Si une coupe est nécessaire, elle doit être exposée ; une mesure ne justifie jamais de masquer des fichiers.
- [ ] Introduire un hook de listing séparé ou une requête dédiée dans `useSpaces` qui n'altère pas les stats globales. Clé = compte + critères ; en cas de réponse tardive, garder l'identité de requête.
- [ ] Ajouter la toolbar partagée dans SpacesManager : champ, mode name/filename, quatre tris, reset, compteur de résultats filtrés, état no-match distinct de no-space. Le tri par défaut du manager est nom.
- [ ] Invalider après création/suppression/renommage/déplacement/synchronisation de document et toggle espace. Préserver le focus sur une action même si l'ordre de la carte change.

Fichiers : `apps/api/src/domains/rag_spaces/{router,schemas,repository,service}.py` ; `apps/web/src/hooks/useSpaces.ts`, `components/spaces/SpacesManager.tsx`. Tests : étendre `tests/unit/domains/rag_spaces/test_service.py`, les tests repository, `hooks/__tests__/useSpaces.test.ts`, et ajouter une intégration PostgreSQL du listing et un test de manager page/réglages.

## Lot 3 — Chronologie : contrats de lecture avant présentation

- [ ] RED : événement correspondant hors pool récent, ordre oldest avec plus de lignes que le cap, deux événements d'une boucle à des dates différentes, égalités de date, catégorie inconnue, filtre ne trouvant rien.
- [ ] Ajouter des critères immuables (`q`, `kinds`, `sort`, `as_of`) dans activity/schemas. Le router valide tailles et enums ; les fetchers reçoivent exactement ces critères.
- [ ] Dans `activity/repository.py`, construire les prédicats une fois par source ; mêmes WHERE pour lignes/count ; ordre demandé avant limite ; id final. Séparer les streams de création/clôture des loops avant leur plafond.
- [ ] Étendre `timeline.merge_timeline` pour les deux sens, sans réimplémenter des filtres sur le pool fusionné. Service : ne lancer que les sources nécessaires ; une session propre par fetcher, erreur partielle conservée.
- [ ] Stabiliser la borne temporelle sur les pages suivantes ; définir précisément cap, total exact et has_more. Tester insertions entre pages et suppressions : pas de faux snapshot historique annoncé.
- [ ] Étendre `useActivityTimeline` avec identité compte+query+borne, remise à zéro et invalidation des réponses obsolètes. Garder le scroll/focus lors d'un simple refresh, remettre le listing au début lors d'un nouveau critère.
- [ ] Ajouter les contrôles dans ActivityTimeline et le groupement au fuseau du compte ; aucun tri par nom qui déstructurerait les jours.

Fichiers : tout le petit domaine `apps/api/src/domains/activity/`, `apps/web/src/hooks/useActivityTimeline.ts`, `components/activity/ActivityTimeline.tsx`. Tests existants dans `tests/unit/domains/activity/` et hooks/components frontend. Ajouter une intégration PostgreSQL qui prouve COUNT et sélection sur des données au-delà du cap ; compilation SQL seule insuffisante.

## Lot 4 — Rubriques d'alertes : adaptation par propriétaire

### 4A. Critères et pagination partagés

- [ ] RED : changement de filtre depuis page 4, réponse page 4 retardée, erreur avec anciennes données, changement de compte, fermeture/réouverture, refresh de ressource.
- [ ] Étendre `usePagedSection` d'une `queryKey` explicite et distinguer données retenues/critères chargés/critères demandés. Propager la même identité dans les sections spécialisées SMS et discussions.
- [ ] Extraire une toolbar légère réutilisable avec les primitives existantes : composition de slots/contrôles, sans abstraire des modèles de données incompatibles. Si l'extraction du toolbar Relations est faite, préserver strictement son ranking/favoris et ses tests.
- [ ] Ajouter les critères au hub tout en gardant Reçues / À suivre, offres, états ouverts et lazy reads. La catégorie masque/exclut les sections non choisies ; elle ne fusionne pas leurs pages.

### 4B. Readers et compteurs

- [ ] Pour peers, heartbeat, interests, reminders, workboard et discussions, étendre router/schema/repository propriétaire avec recherche et ordre facultatifs. Localiser les readers exacts depuis les chemins déjà utilisés dans NotificationsHub ; ne pas inventer un nouveau stockage de notifications.
- [ ] Vérifier les champs visibles et ACL pour chaque section selon la table de l'analyse. Le peer sort/recherche le texte propre à son lecteur ; les discussions ne révèlent pas des messages masqués ; le Workboard garde owner/holder.
- [ ] Dans `notifications/hub_counts.py`, remplacer « échec → 0 » par absence/indisponibilité. Conserver les comptes généraux hors recherche ; sous recherche, une rubrique non évaluée montre `—`, puis le compte exact de sa propre lecture. Aucun déchiffrement/résolution de contacts pour calculer les badges filtrés d'une rubrique fermée. Les types frontend et tous les consommateurs évoluent ensemble.
- [ ] Garder le chemin client des routines uniquement si le reader fournit réellement toute la collection ; appliquer tri/filtre avant sa pagination locale.
- [ ] Appliquer le tableau de readers de la contre-revue : intérêts = topic, Workboard = title seulement, routine = title/schedule_display ; aucun champ ou fallback de date inventé. Séparer le nouveau curseur des discussions du helper partagé des autres lecteurs ; valeurs de défaut historiques conservées.
- [ ] Tests intégration par reader : count + page + limites + panne + autre compte + retrait. Mesurer la charge des compteurs et ne pas transformer l'ouverture de la page en chargement de tous les contenus fermés.

Tests front à étendre : NotificationsHub, usePagedSection, SmsHubSection, DiscussionsHubSection. Parcours E2E : taper une recherche, choisir une catégorie, trier, paginer, recevoir un refresh, perdre une source, recommencer ; contrôler que les rubriques restent présentes et les dates ont le sens publié.

### 4C. Recherche d'affichage SMS, distincte du contrat lexical

- [ ] RED sur le reader réel : `fact` trouve `facture` en mode affichage, le mode lexical historique reste inchangé ; nom affiché OU corps, déduplication, accents/CJK/punctuation, `%`/`_` littéraux ; compte exact au-delà de la première page.
- [ ] Ajouter le mode typé dans `sms/read_schemas.py` et son identité dans `cursors.py`. Ne pas étendre implicitement le sens de `query` pour les outils existants.
- [ ] Ajouter une projection de trigrammes HMAC dans `sms/models.py` distincte de la complétude/version lexicale ; migration additive. Centraliser normalisation et finalité HMAC, réutiliser la clé du compte. Paramètres de budget dérivés des mesures, publiés dans la configuration ; aucune valeur de coût devinée.
- [ ] Faire évoluer ENSEMBLE `sms/ingestion.py`, `sms/search_index.py`, le calcul de logical_bytes et le quota. Conserver l'index actif jusqu'au swap validé ; projection absente/ancienne/incomplète reste candidate. Prouver rollback, dépassement du quota, ingestion concurrente et effacement sur PostgreSQL.
- [ ] Dans `sms/repository.py`/`reads.py`, ne prendre les trigrammes que pour une présélection permissive ; vérifier le fragment exact après déchiffrement. Sous trois caractères, vérification bornée sans présélection restrictive. Refus QUERY_TOO_BROAD explicite et restriction de période, jamais résultat incomplet assimilé à exact.
- [ ] Tests de corpus : faux positif `abc---bcd` pour `abcd` éliminé ; fragment à cheval sur deux tokens, caractères combinés, espaces conservés, anciennes lignes sans projection, projection tronquée ; tests de concurrence de reconstruction.
- [ ] Mesurer EXPLAIN, latence et mémoire, taille physique des index et logical_bytes sur corpus court/long/CJK/forte répétition, au plafond d'archive et avec projection incomplète. L'expérience de trigrammes de l'analyse ne remplace pas cette gate de charge.

### 4D. Identités SMS et tri sans lecture de tous les corps

- [ ] RED : plus de sms_search_max_candidates messages mais deux expéditeurs doivent rester triables ; nom résolu absent du corps ; homonymes ; identité indisponible/ambiguë ; alias changé entre deux pages ; même nom/dates égales.
- [ ] Sous les mêmes ACL/as_of, lire les expéditeurs DISTINCTS et leurs hashes ; libérer la transaction, appeler `resolve_senders`, puis `validate_resolutions` avant publication. Utiliser le cache d'identités existant, sans nouvel index de noms en clair.
- [ ] Créer le mapping éphémère hash→rang et le joindre à la requête propriétaire, trier par rang/date/id, ne déchiffrer les corps que pour la page ou les candidats texte. Budget spécifique sur les distincts, sans réutiliser abusivement le plafond de corps vérifiés.
- [ ] Pour une recherche nom OU corps, compter la branche nom par agrégat et vérifier les candidats corps non déjà couverts ; union sans doublon. Aucune résolution externe sous verrou.
- [ ] Le curseur versionné porte ordre, critères, owner, révision/as_of, génération et empreinte du mapping. Invalidation sur changement d'identité ou d'autorité ; reset client explicite. Tests de page suivante et précédente, suppression de la ligne pivot et changement de compte.

Tests à étendre : `tests/integration/test_sms_reads.py`, `test_sms_search_index.py`, `test_sms_index_rebuild.py`, `test_sms_identity_registry.py`, avec nouveaux tests ciblés de recherche d'affichage et tri par expéditeur. Le passage SQL des noms de personnes reste masqué par l'infrastructure de logs ; aucune valeur de nom dans une clé Redis.

## Lot 5 — Peer direct : autorité, commande et reprise

### 5A. Autorité explicite

- [ ] RED : matrice des politiques native/MCP en Pipeline/ReAct, attended/unattended, scope absent/approuvé/non approuvé ; `direct` est journalisé sans carte et ne change rien aux autres politiques.
- [ ] Ajouter `direct` à MutationPolicy et tous ses sets/lecteurs. Justification obligatoire, registre exhaustif. Exiger scope/identité/claim ; étendre `_unrecorded_or_refused` pour refuser direct sans claim, sans changer les politiques historiques. Conserver le prédicat unattended avec refus d'autorité sans carte et sans approbation fabriquée.
- [ ] Mettre à jour les lecteurs d'expressivité, confirmation, résultats et guards de complétude. L'initiative reste explicitement interdite pour l'envoi peer.
- [ ] Tester les plans mixtes et FOR_EACH : aucun brouillon d'envoi pour le peer unique, maintien des confirmations effectivement dues aux autres actes ou au lot. La politique du peer ne supprime pas un HITL sans rapport avec lui.

### 5B. Enqueue commun sous le claim existant

- [ ] RED au gate réel : répétition d'une clé d'effet restitue le résultat sans second enqueue ; même texte/deux effets crée deux lignes ; claim absent refuse ; crash après enqueue avant settle ne réinsère pas ; quota concurrent ; connexion bloquée entre résolution et insertion ; destinataire historique incohérent refusé.
- [ ] Extraire une commande typée sous `domains/peers/` appelée par le tool et l'ancien exécuteur de brouillon. Un seul propriétaire des règles connexion/quota/enqueue.
- [ ] Réutiliser la clé et le claim du registre d'effets ; **aucune migration d'idempotence de PeerMessage pour 5B**. Le résultat d'enqueue explicite est celui clos/rejoué par le gate.
- [ ] Compter et insérer sous `lock_peer_pair` puis verrou de connexion, dans l'ordre propriétaire déjà utilisé. Tester deux destinataires partageant le même émetteur, ainsi que block/remove concurrents ; aucun verrou pendant réseau.
- [ ] Changer `send_peer_message_tool` pour retourner le résultat explicite d'enqueue ; conserver les décorateurs métriques/rate limit. Mettre à jour manifeste, descripteurs et prompt publié : pas de promesse de carte ni de livraison instantanée.
- [ ] Garder l'exécuteur PEER_MESSAGE pour les brouillons historiques ; tests de reprise et de refus d'un brouillon périmé. Aucun auto-approve rétroactif.

### 5C. Frontière de livraison

Correctif préexistant séparé : le contre-exemple PostgreSQL reproduit une clôture gagnée par l'ancien livreur après reprise du claim. Ce sous-lot n'est pas nécessaire pour câbler `direct`, mais il est nécessaire pour qualifier une livraison robuste de bout en bout. Il ne bloque pas l'implémentation des autres demandes.

- [ ] RED PostgreSQL deux acteurs : claim A, expiration, claim B, tentative de clôture/échec/renew par A, aucun effet accepté après perte d'autorité.
- [ ] Ajouter owner token/génération et transitions conditionnelles aux claims du repository et au livreur/sweep. Respecter l'atomicité claim→commit avant le travail externe.
- [ ] Établir la clé de notification durable liée au message, tester le crash après notification avant commit. Lire le résultat de settle ; ne notifier le sender d'une réussite qu'une fois l'état gagné.
- [ ] Classer les échecs de génération selon la politique centrale : résultat inconnu non regénéré automatiquement ; refus quota différé selon le contrat existant ; échec de livraison distinct d'échec du modèle.
- [ ] Prouver qu'un SSE seul ne ferme pas la livraison et que l'absence de canal durable donne une issue explicite.

Tests à étendre : `tests/unit/domains/agents/tools/test_peers_tools.py`, `tests/unit/domains/agents/peer/test_catalogue_manifests.py`, `tests/unit/domains/peers/test_delivery.py`, `test_repository_logic.py`, guards effects. Ajouter des tests dans `tests/integration/domains/peers/` sur une base jetable. Ce lot ne passe pas sur la seule suite mockée existante.

## Lot 6 — Assistance IA commune et propositions

### 6A. Une capacité, une porte et des bornes publiées

- [ ] RED : assistance texte accessible hors Workbench quand TOOL_ASSISTS est actif ; source Workbench inaccessible quand WORKBENCH est désactivé ; destination sans capacité/connexion non proposée ; API refuse le bypass du frontend.
- [ ] Réorganiser les route dependencies dans `tool_assists/router.py` avec groupes cohérents. Garder les routes existantes et leur limite utilisateur. Extraire un module de routes texte si nécessaire pour réduire le hotspot, sans fichier artificiel par branche.
- [ ] Publier une lecture légère des capacités/bornes/durée transport de l'assistance. Aucun téléchargement ni lecture mail pour rendre un menu.
- [ ] Vérifier le timeout du slot, la limite transport réellement configurée et le client ; supprimer l'hypothèse fixe de `useAssistCall` lorsque le contrat publié la remplace. Si le transport impose une borne inférieure au slot, résoudre cette incompatibilité avant d'offrir le parcours ; ne pas relancer une requête dont l'issue est inconnue.
- [ ] Brancher le budget complet de tokens (prompt + données + schéma + sortie) sur la porte existante. Erreur typée avant paiement si trop long ; aucune coupe invisible des créations.

### 6B. Réponses et créations proposées

- [ ] RED : passage d'origine chat/page/document/mail traité comme donnée non fiable ; question incluse une fois ; instruction hostile n'appelle aucun outil ; texte vide/tronqué/malformé refusé.
- [ ] Étendre le contrat PassageAssist et ses origines sans fabriquer d'identité serveur à partir du DOM. Les prompts restent sous `agents/prompts/v1/`, placeholders produits et bornes issues des settings.
- [ ] Réutiliser actions/text/passage et leurs projections pour les task/event de sélection. Le contexte minimal inclut l'horloge du compte ; les ressources optionnelles nécessaires, comme les listes, sont fournies par leur porte autorisée et déclarées comme lues.
- [ ] Ajouter une proposition mémoire dans `tool_assists` : schéma de proposition compatible avec les champs MemoryCreate, bornes partagées, origine explicitement attribuée, aucun appel d'embedding. La validation ne convertit pas une assertion tierce en autobiographie.
- [ ] Ajouter les actions à ToolAssist/ASSISTS, la complétude, les labels observables et les déclarations de spend/consultation pertinentes. Réutiliser run_assist pour succès, refus, quota, erreur et cancellation.
- [ ] Tester que le coût capturé reste attribué après fermeture de la bulle et qu'un retry manuel a une nouvelle identité de run. Aucun retry invisible, aucun coût client inventé.

### 6C. Fermeture du trou de comptabilité mémoire

- [ ] RED : création manuelle depuis le formulaire avec embeddings simulés observe une garde compte+instance, un contexte owner/run correct et sa restauration, y compris erreur/cancellation.
- [ ] Extraire la préparation d'embeddings actuellement dans `agents/application/memory_creation_embeddings.py` vers un module propriétaire adapté du domaine mémoire ; les callers application et CRUD la réutilisent. Aucune dépendance inverse vers agents.
- [ ] Conserver les embeddings avant l'ouverture de la transaction d'écriture ; revalidation d'autorité autour des appels ; tests `pg_stat_activity` ou instrumentation de session sur cible jetable.
- [ ] Conserver les règles existantes de pin/category et le comportement de stockage quand l'embedding n'est pas disponible, en disant honnêtement son résultat. Ne pas facturer la même préparation une seconde fois dans le service.

## Lot 7 — Moteur de sélection et deux présentations

- [ ] RED : règle d'éligibilité lecture/édition, champ readOnly, champ secret exclu, sélection inter-surfaces refusée, texte CJK d'un caractère accepté, contenu streaming dont la révision change.
- [ ] Créer le noyau typé sous `lib/selection-assist/` : registre fermé, snapshot de cible, règles d'application, résultats discriminés et états. Aucun singleton avec compte/texte conservé sans owner.
- [ ] Ajouter un provider dans la racine authentifiée qui couvre aussi les routes World pertinentes ; un seul listener partagé et une seule assistance active. Réutiliser le positionnement/scrollports existant.
- [ ] Ajouter les adaptateurs Input/Textarea et RichBody ; conserver state contrôlé, onChange, ref, sélection, IME, limites du champ et undo. Recenser/adapter les contrôles natifs qui ne passent pas par ces primitives.
- [ ] Extraire les parties réutilisables de SelectionAssist/WritingAssist/InstructionForm/WaitOrRefusal/tellCost/DictationAct ; les modules génériques ne doivent pas importer WorkbenchShell.
- [ ] Construire les deux listes exactes demandées dans le registre. L'action « écrire à partir de rien » spécialisée existante peut rester dans les formulaires, mais n'ajoute pas un huitième choix au menu de lecture.
- [ ] RED : une réponse tardive ne s'applique pas après frappe, sélection déplacée, navigation, unmount, logout ou changement de compte. Proposer Copier si la cible est devenue obsolète.
- [ ] Ajouter les hosts de rendu dans l'arbre React de la surface/modale concernée ; un Dialog non modal imbriqué porte la bulle et son portail DOM vers body. Éviter le portail dans le containing block transformé et le Dialog frère à la racine globale, tous deux invalidés par la sonde. Enregistrement/désenregistrement du host sans récursion de la bulle ; tester Escape/focus et clic extérieur.
- [ ] Corriger `useAssistCall` : dernière requête liée au scope, retry refusé si l'identité a changé, payload effacé à stop/logout, contrôle de l'identité avant de retourner une proposition. Reproduire le défaut actuel puis l'inverser ; tester réponse tardive, ancien retry et même texte sous deux comptes. Prouver que soumettre la question n'envoie ni e-mail ni message chat.
- [ ] Dicter : montage au clic seulement, arbitrage du micro avec les usages existants, cleanup intégral, aperçu avant application de transcription, aucune connexion audio à l'affichage du menu.
- [ ] Responsive : menu repliable sans recouvrir les poignées, bulle dans visualViewport, clavier logiciel, réduction de mouvement, zoom et six traductions. Aucun style clair/noir absolu hardcodé contredisant les tokens du thème.

Fichiers nouveaux proposés : `SelectionAssistProvider.tsx`, `SelectionToolbar.tsx`, `SelectionBubble.tsx`, `useSelectionAssistTarget.ts` et modules cohésifs de types/actions/adapters. Ne pas créer ces noms à l'identique si un composant existant peut être déplacé proprement ; la responsabilité et la dépendance sont le contrat, pas le nombre de fichiers.

## Lot 8 — Brancher les destinations et remplacer les anciens menus

- [ ] RED : proposition reçue une seule fois, liée au compte, durée expirée, double mount, navigation sur route déjà active, formulaire déjà modifié, listes/calendriers indisponibles.
- [ ] Faire évoluer le handoff existant en store observable avec branche mémoire, snapshot stable et `useSyncExternalStore`. Adapter `useToolBridges/useHandoff` ; aucun deuxième slot global. RED reproduisant l'arrivée sur route déjà prête, puis réception unique sans toggle artificiel de ready ; prise conditionnelle owner/id et TTL, purge logout, protection du formulaire modifié.
- [ ] Tâche : conserver HandedTaskReview/NewTaskDialog et le choix des listes ; ajustement possible avant POST existant, aucune création au simple clic de sélection.
- [ ] Événement : utiliser le formulaire agenda et les projections existantes ; ne pas transformer une date inconnue en date extraite. Distinguer clairement les valeurs proposées des defaults du formulaire.
- [ ] Mémoire : utiliser `settingsSectionHref(lng, 'memories')` puis ouvrir le formulaire de création avec la proposition. Rien du contenu dans la query string. Ajouter un mécanisme de réception au composant paresseusement monté.
- [ ] Afficher le coût de la proposition une seule fois, y compris après navigation. Save utilise la porte manuelle native ; failure/retry garde les champs. Double Save protégé comme les formulaires existants.
- [ ] Retirer l'ancien montage SelectionActions du ChatWorkspace et les montages locaux concurrents de SelectionAssist. Migrer leurs tests vers le comportement commun ; ne pas laisser deux menus répondre à une même sélection.
- [ ] Garder les actions spécialisées e-mail, les boutons d'écriture de champ et le texte sélectionnable dans les lecteurs, tous branchés sur la même infrastructure pour les actions communes.
- [ ] Matrice finale de couverture des surfaces recensées au lot 0 : native couverte, adaptateur couvert ou exclusion justifiée visible. Aucun « partout » déclaré sur une iframe opaque non instrumentée.

## Lot 9 — Qualification intégrée, documentation et revue inline

- [ ] Revoir les diffs et les invariants inline : conformité du périmètre, compatibilité des anciennes cartes/profils/requêtes, aucune mutation implicite, aucune fuite PII, aucun cast double/Any ajouté.
- [ ] Exécuter `task lint` sur le snapshot final. Les ratchets doivent passer sans hausse de baseline ; le lint frontend doit lancer son tsc non incrémental. Corriger la source d'une violation touchée plutôt que l'exclure.
- [ ] Exécuter `task test:backend:unit:fast`, `task test:frontend` et `task test:frontend:coverage` ; pour les changements d'exécution en arrière-plan, ajouter la gate séquentielle de couverture pertinente et vérifier les ressources après le résumé.
- [ ] Exécuter les intégrations PostgreSQL/Redis sur cibles jetables et `task db:migrate:replay-check` pour les migrations. Ne jamais viser les comptes ni les canaux de la personne.
- [ ] Exécuter les E2E hermétiques et axe sur les trois moteurs. En environnement de développement, respecter le runtime Docker prescrit ; ne pas lancer un build/dev local concurrent dans le checkout partagé. Employer le harness isolé du projet pour la production E2E.
- [ ] Qualifier les parcours critiques sur Android et iOS réels : sélection tactile, clavier, permissions micro, reprise, noir absolu, modales. Si l'appareil est absent, inscrire cette limite et ne pas déclarer une qualification native acquise.
- [ ] Mettre à jour les documents propriétaires : TOOL_ASSISTS, WORKBENCH, HITL/AI_ACT_TRACEABILITY, NOTIFICATIONS_FLOW, guide RAG, configuration/profil et guides utilisateur concernés. Amender les ADR existants ou créer une ADR lorsque la politique direct et l'assistance transversale l'exigent ; choisir le numéro seulement au moment de l'écriture.
- [ ] Revoir README/FAQ/guide public dans six langues pour les comportements réellement livrés. Mettre à jour INDEX/ADR_INDEX et cartes vivantes si une ADR/structure est ajoutée ; lancer les tâches de génération prévues. Ne pas recopier des versions, plafonds ou nombres que le code possède.
- [ ] `CLAUDE.md` ne change que si un invariant de travail nouveau mérite une règle courte ; dans ce cas régénérer AGENTS.md et mesurer le budget. Ne pas y raconter le chantier.
- [ ] Produire un relevé final des commandes, exit codes, comptes de tests, avertissements, intégrations exécutées et limites matérielles. Aucun succès ciblé ne remplace une gate requise. `ci:fast` sera nécessaire avant tout push futur demandé par l'utilisateur ; aucun push n'est inclus ici.

## Commandes et preuves

### Base frontend exécutée pour l'analyse

Depuis la racine, exit 0, 14 fichiers / 192 tests :

```powershell
task test:frontend -- src/lib/__tests__/theme-mode.test.ts src/components/__tests__/theme-init-script.test.tsx src/hooks/__tests__/useThemeMode.test.tsx src/hooks/__tests__/useTextSelection.test.ts src/lib/__tests__/selection-position.test.ts src/components/chat/__tests__/SelectionActions.test.tsx src/components/workbench/assist/__tests__/SelectionAssist.test.tsx src/components/workbench/assist/__tests__/WritingAssist.test.tsx src/components/workbench/assist/__tests__/FieldAssist.test.tsx src/components/workbench/assist/__tests__/useAssistCall.test.ts src/components/notifications/__tests__/NotificationsHub.test.tsx src/components/activity/__tests__/ActivityTimeline.test.tsx src/hooks/__tests__/useActivityTimeline.test.ts src/hooks/__tests__/useSpaces.test.ts
```

### Base backend exécutée pour l'analyse

Depuis `apps/api`, exit 0, 374 tests :

```powershell
.venv/Scripts/python -m pytest tests/unit/domains/tool_assists tests/unit/domains/activity tests/unit/domains/agents/tools/test_peers_tools.py tests/unit/domains/agents/peer/test_catalogue_manifests.py tests/unit/domains/peers/test_delivery.py tests/unit/domains/peers/test_repository_logic.py tests/unit/domains/rag_spaces/test_service.py -q --no-cov -o addopts='' -o faulthandler_timeout=45
```

Le `--no-cov` rend cette base ciblée plus légère ; elle n'est pas une preuve de seuil de couverture ni le remplacement de la suite fast/coverage finale. La première tentative d'initialisation interrompue n'est pas incluse dans les 374 tests.

### Probes de faisabilité exécutées

Les fichiers sont des probes d'analyse sous `output/`, pas du code applicatif ni une suite CI livrée. Ils utilisent uniquement des données fictives. Aucun fournisseur payant ni compte réel n'est appelé.

```powershell
# Depuis la racine : 6 contrôles x 3 moteurs, tous vrais.
node output/playwright/analysis-20261108/selection-probe.cjs

# Depuis apps/api : contre-exemples sur le merge réel + tokenizer local.
$env:PYTHONPATH=(Get-Location).Path
.venv/Scripts/python ../../output/playwright/analysis-20261108/data-probe.py
```

La probe navigateur vérifie explicitement : Range de lecture, offsets textarea, sélection non applicable sur input number, focus extérieur refusé par une modale, iframe opaque inaccessible, insertion contenteditable suivie d'undo. Elle ne prouve pas la géométrie d'un menu LIA futur ni le comportement d'un appareil iOS physique.

### Gates à exécuter pendant le développement

Pour les livrables de cette analyse, `task lint:docs:preview` a terminé avec exit 0 : liens/chemins vivants et orphelins sans défaut, faits sans dérive, cartes et langue conformes. Les avertissements historiques affichés par le dépôt n'ont pas été modifiés. Ce contrôle ne certifie pas les gates applicatives futures ci-dessous.

```powershell
task lint
task test:backend:unit:fast
task test:frontend
task test:frontend:coverage
task db:migrate:replay-check
```

Ajouter les fichiers d'intégration des lots à leur runner sur base/Redis jetables, puis les parcours E2E via le harness du projet. Les commandes d'infrastructure doivent être préparées d'après l'environnement courant ; ne pas réutiliser un conteneur de test appartenant à un chantier parallèle. `task test:backend:exhaustive` reste exclu.

## Relecture du plan avant livraison

- [x] Les cinq demandes sont mappées à des lots, avec les deux types de menus et les trois créations préremplies.
- [x] Les réponses utilisateur sont intégrées ; les anciennes propositions contradictoires (création dans la bulle, horaires fixes) sont abandonnées.
- [x] Les mécanismes déjà présents sont réutilisés avec leurs limites explicites : draft peer, next-themes/OLED, lecteurs paginés, tool_assists, handoff, formulaires natifs.
- [x] Les risques de coûts, registres, mémoire, permissions et mobilité ont des tests de sortie désignés.
- [x] Les niveaux de preuve sont distingués : intégrations PostgreSQL et contre-exemples actuels exécutés, composants React sondés, mais pas d'E2E des fonctions futures ni de qualification physique. Les défauts observés ne sont pas présentés comme corrigés.
- [x] Aucun relèvement de ratchet, nouvelle dépendance non justifiée, git mutation ou déploiement n'est prévu par défaut.
- [x] L'exécution peut commencer par le lot 0 sans décision produit supplémentaire ; les preuves techniques manquantes bloquent la sortie de leur lot, pas l'analyse des autres.
