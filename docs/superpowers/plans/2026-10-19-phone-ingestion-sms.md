# Ingestion téléphone et Mes SMS — plan d’implémentation TDD

> Pour l’exécution : utiliser superpowers:executing-plans. Travail strictement
> INLINE, sans sous-agent, selon la demande explicite de la personne.
> Implémentation autorisée par la demande explicite de reprise. Lots logiciels 1 à 8 réalisés et relus INLINE ; les validations physiques iPhone restent à effectuer et ne sont pas certifiées.

**Goal :** recevoir les messages du téléphone dans une archive SMS native,
sur un socle d’ingestion réutilisable, et intégrer les parcours LIA existants.

**Architecture :** domaine ingestion pour les contrats techniques et la file
durable, domaine sms pour les données et politiques. Adaptateur santé compatible.
Lectures directes pour les pages ; outils natifs pour la discussion.

**Tech Stack :** FastAPI, SQLAlchemy/PostgreSQL, Redis, ordonnanceur et
chiffrement LIA existants ; Next.js, React, TypeScript et primitives UI existants.
Pas de bus externe ni de dépendance frontend lourde ajoutés par principe.

**Spec :** [analyse et spécification](../specs/2026-10-19-phone-ingestion-sms-design.md).
La section 13 de la spécification, issue de la relecture contradictoire du
19 octobre, complète les obligations de purge, d’export, de registres et de
consommateurs indirects. Elle s’applique à tous les lots ci-dessous.

## Contraintes globales

- Proposition validée par la demande explicite d’implémentation et de reprise.
- Aucun sous-agent, y compris pour la revue ; relecture contradictoire INLINE.
- Ne pas toucher aux changements concurrents ; inventorier Git à chaque lot.
- Secrets d’accès identifiables et expéditeurs bloqués exclus avant persistance.
- Push immédiate à toute heure, désactivable ; indépendante des horaires heartbeat.
- Conservation jusqu’à suppression manuelle, sans suppression automatique sur quota.
- Accès Assistant désactivé par défaut ; lecture personnelle indépendante.
- Aucun appel LLM ou embedding sur ingestion, filtrage ou notification immédiate.
- Santé : routes, jetons hm_, identifiants et données conservés ; pas de migration
  physique des jetons dans ce chantier.
- Toutes les mutations applicatives réutilisent commandes, autorité fraîche et
  confirmation serveur existantes, y compris celles déclenchées depuis les réglages.
- Aucun secret de jeton dans le modèle, le checkpoint ou le stockage navigateur.
- Chaque champ nouveau d’un registre a producteur, lecteurs et garde de complétude.
- Six locales, fuseau utilisateur, accessibilité et comportement mobile testés.
- Fichiers cohésifs sous les ratchets ; aucun plafond, seuil ou règle affaibli.
- Source d’instructions : CLAUDE.md ; AGENTS.md uniquement régénéré si nécessaire.
- Aucun déploiement ni envoi de données réelles vers la production dans ce plan.

## Points de revue obligatoires

1. Une réponse perdue après commit n’engendre ni nouveau SMS ni nouvelle occurrence.
2. Un message sensible n’existe dans aucune table de contenu, index, file ou log.
3. Un appareil push réussi n’est pas renotifié à cause de l’échec d’un autre.
4. Consentement, blocage, révocation et suppression gagnent les courses définies
   avant toute nouvelle publication de contenu ou effet externe.
5. Les compteurs et la recherche restent honnêtes sous pagination, ambiguïté
   d’identité, index tronqué/indisponible et saturation des budgets.

Chaque point a un test dans son lot propriétaire. Les qualifications iPhone
et performance ne sont pas remplacées par des simulations.

## Carte des fichiers

Les fichiers nouveaux ci-dessous sont prospectifs. Les chemins existants ont
été repérés pendant l’analyse ; compléter les points d’enregistrement en
suivant les gardes de complétude, sans fabriquer des tables de correspondance.
Un fichier n’a pas vocation à porter toutes les responsabilités d’un lot.

| Unité nouvelle proposée | Responsabilité |
|---|---|
| apps/api/src/domains/ingestion/principal.py | Principal typé, portées et source |
| apps/api/src/domains/ingestion/parser.py | Enveloppes et indices sans perte silencieuse |
| apps/api/src/domains/ingestion/schemas.py | Reçus et verdicts publics |
| apps/api/src/domains/ingestion/token_auth.py | Extraction, hachage et résolution des adaptateurs de jetons |
| apps/api/src/domains/ingestion/token_commands.py | Création/révocation sûres des nouveaux jetons |
| apps/api/src/domains/ingestion/authority.py | Vérification fraîche et ordre de locks |
| apps/api/src/domains/ingestion/limits.py | Débit et budgets techniques |
| apps/api/src/domains/ingestion/models.py | Sources, jetons, reçus et travaux |
| apps/api/src/domains/ingestion/repository.py | SQL atomique des reçus et sources |
| apps/api/src/domains/ingestion/delivery_repository.py | Claim/lease/fence et résultats par destination |
| apps/api/src/domains/ingestion/registry.py | Contrats des adaptateurs et complétude |
| apps/api/src/domains/ingestion/router.py | Gestion par session, hors dépôt externe |
| apps/api/src/domains/sms/models.py | Archive chiffrée et index dérivé |
| apps/api/src/domains/sms/schemas.py | Messages, pages, filtres, préférences |
| apps/api/src/domains/sms/ingest_router.py | POST externe demandé |
| apps/api/src/domains/sms/ingestion.py | Validation, filtrage, transaction métier |
| apps/api/src/domains/sms/sensitive_filter.py | Règles déterministes versionnées |
| apps/api/src/domains/sms/sender_policy.py | Blocages et normalisation d’identifiant |
| apps/api/src/domains/sms/identity.py | Projection contacts/relations et provenance |
| apps/api/src/domains/sms/repository.py | Requêtes owner-scopées, agrégats et pagination |
| apps/api/src/domains/sms/search.py | Tokenizer unique, HMAC et budget de recherche |
| apps/api/src/domains/sms/reads.py | Autorisation de lecture et projection LLM |
| apps/api/src/domains/sms/management_commands.py | Effacement confirmé, tombstones et dérivés |
| apps/api/src/domains/sms/preferences.py | Préférences strictes, lecture tolérante versionnée |
| apps/api/src/domains/sms/notifications.py | Politique et contenu déterministe sans PII |
| apps/api/src/infrastructure/scheduler/ingestion_delivery.py | Reprise des travaux, I/O sans transaction longue |
| apps/api/src/infrastructure/startup/scheduler_ingestion.py | Installation du job avec jitter et propriétaire |
| apps/api/src/core/config/ingestion.py | Paramètres des nouvelles ressources |
| apps/api/src/domains/shared/ingestion_delivery_sink.py | Couture typée de transport/registre si requise pour éviter un cycle |
| apps/api/src/domains/agents/sms/catalogue_manifests.py | Contrats de lecture SMS et contexte |
| apps/api/src/domains/agents/tools/sms_tools.py | Trois outils de lecture |
| apps/api/src/domains/agents/graphs/sms_agent_builder.py | Agent natif et slot runtime |
| apps/api/src/domains/agents/prompts/v1/sms_agent_prompt.txt | Prompt versionné |
| apps/api/src/domains/agents/display/components/sms_card.py | Carte native échappée |
| apps/web/src/hooks/useSms.ts | Lectures et filtres typés |
| apps/web/src/hooks/useSmsSettings.ts | Préférences et commandes par la voie applicative |
| apps/web/src/hooks/useIngestionTokens.ts | Interface de gestion des jetons avec adaptateur de ressource |
| apps/web/src/components/settings/SmsSettings.tsx | Section Mes SMS |
| apps/web/src/components/settings/ingestion/IngestionApiPanel.tsx | Présentation commune URL/jetons, sans secrets persistants |
| apps/web/src/app/[lng]/dashboard/sms/page.tsx | Page de lecture localisée |
| apps/web/src/app/[lng]/dashboard/sms/[id]/page.tsx | Destination stable pour carte/alerte |
| apps/web/src/components/sms/SmsTimeline.tsx | Projection par jour/expéditeur |
| apps/web/src/components/sms/SmsMessageRow.tsx | Texte littéral et détails lisibles |
| apps/web/src/components/notifications/SmsMessagesList.tsx | Section du hub |
| apps/web/src/components/relations/RelationSmsSection.tsx | Messages de la relation |
| apps/web/src/components/dashboard/cards/SmsCard.tsx | Carte déterministe d’accueil |

Extensions des fichiers existants, regroupées par contrat :

- Santé : ingest_router.py, parser.py, service.py et fichiers de jetons du
  domaine health_metrics, via délégation au socle et adaptateur compatible.
- Routes/config : apps/api/src/api/v1/routes.py, core/config, core/constants.py,
  infrastructure/startup/registries.py, startup/schedulers.py, main.py seulement
  si le point de cycle de vie l’exige.
- Préférences : users/models.py, user_column_map.py, schémas/projections utilisateur,
  preference_cas, agents/application/preference_fields.py, preference_catalogue.py
  et registre des opérations applicatives.
- Capacités : feature_switches/registry.py et clé de réglage associée, capacités
  publiées de l’API, useAppConfig, section/outil/worker sous le même verdict.
- Confidentialité : users/user_data_map.py, account_deletion_service.py,
  account_export/builder.py et ses chemins executor/downloads, users/extraction_consent.py,
  infrastructure/database/export_stream.py et infrastructure/cache/key_families.py.
  La liste chiffrée sms_sender_blocks est séparée de users.sms_preferences,
  classée SCRUBBED_PREFERENCE pour le JSON de réglages.
- Notifications : notifications/service.py pour une API publique par appareil
  si nécessaire, schémas et hub_counts.py ; frontend useNotifications.ts,
  routage des notifications et service worker réellement utilisé.
- Heartbeat : source_policy.py, source_availability.py, source_placement.py,
  context_aggregator.py par extraction si nécessaire, schemas.py et context_sources.py.
- Relations : service.py, schemas.py, overview_scope.py, overview/blocks.py,
  overview/evidence.py, debrief/service.py ; useRelations.ts, RelationDetailPanel.tsx,
  RelationScopeSection.tsx et contrats TypeScript associés.
- Accueil : briefing/schemas.py, constants.py, service.py, cache_keys.py,
  consultations.py, llm.py et résumeur de cartes ; types/briefing.ts,
  useBriefing, TodayBriefing.tsx, icônes, personnalisation et setup.
- Outils : domain_taxonomy.py, catalogue_loader.py, tool_registry.py,
  context/registry.py, semantic/semantic_type.py et type_registry.py lorsque
  le nouveau type de référence le nécessite ; base_agent_builder.py et registre
  de configuration LLM pour le slot natif (llm_config/constants.py), export du
  builder dans graphs et installation dans infrastructure/startup/agents.py.
- Rendu : data_registry/models.py et trust.py, tools/output.py,
  display/component_registry.py, sérialiseurs et références front des cartes.
- Registres : shared/consultation_surfaces.py et enregistreurs des trois surfaces,
  effets de notification et déclarations spend_roads/decision_filers concernées.
- Consommateurs indirects à protéger : shared/phone_domains.py, agents/telephony/live_tools.py,
  radio/personal.py, radio/day_source.py, scheduler/condition_evaluators.py et
  enums de partage entre pairs. Vérifier leur refus/absence SMS en V1 ;
  ne pas élargir leurs autorisations par effet de bord du nouveau domaine.
- Réglages UI : lib/settings-sections.ts, settings-section-registry.tsx,
  settings-section-icons.ts et recherche de sections.
- Traductions : les six locales front et catalogues/mécanismes backend existants.
- Documentation/exploitation : ADR à numéro déterminé au développement, guide
  Raccourcis, cartes de domaines et modules, living maps et instrumentation visible.

## Lot 0 — Lever les incertitudes techniques sans code métier

Livrable : contrat Raccourcis et rapport de qualification des options nouvelles.
Ce lot est la première étape après validation ; il ne nécessite pas de créer
toutes les surfaces fonctionnelles.

- [x] Préparer des SMS fictifs nominaux, OTP, expéditeur alphanumérique,
  accents/emoji/CJK, rafale et reprise identique.
- [ ] Relever un payload anonymisé réellement disponible dans Raccourcis :
  expéditeur, corps, date et origine ; distinguer date de réception et
  date d’exécution, et noter transport/id seulement s’ils existent.
- [ ] Éprouver un UUID stable pour les reprises. Si absent, documenter la
  garantie limitée du fingerprint et le scénario de collision réelle.
- [ ] Tester l’URL et le certificat de développement depuis l’iPhone ; ne pas
  désactiver la vérification TLS globalement.
- [ ] Vérifier reprise après timeout, réseau coupé, téléphone verrouillé et
  rafale. Si aucune reprise fiable n’est possible, consigner la limite avant
  de présenter une garantie de bout en bout.
- [x] Écrire le corpus positif/négatif du filtre et la taxonomie des verdicts ;
  publier les limites de détection au lieu de promettre le filtrage universel.
- [x] Qualifier en expérimentation jetable l’index lexical aveugle, CJK, termes
  courts, requêtes très fréquentes, temps/RAM/empreinte à volume représentatif.
- [ ] Vérifier le parcours iOS du réveil générique jusqu’aux Alertes ; ne pas
  modifier ni republier la coque mobile dans le cadre de cette qualification.
- [x] Mettre à jour les seules décisions techniques que les mesures justifient.

Les cases physiques non cochées ci-dessus sont reprises dans les limites de
[qualification](../../technical/SMS_QUALIFICATION.md). Le contrat serveur et le guide
couvrent la reprise avec UUID stable, mais ne certifient aucun appareil réel.

Acceptation : les champs effectivement produits sont connus ; chaque limite
résiduelle est explicitement rattachée à sa garantie. La suite peut démarrer
avec les fixtures validées ; les preuves dépendant de l’appareil restent un
critère d’acceptation finale si l’appareil n’est pas disponible immédiatement.

## Lot 1 — Socle commun et compatibilité santé

Fichiers : ingestion/principal, parser, token_auth, authority, registry,
schemas ; adaptateurs dans health_metrics. Tests proposés sous
tests/unit/domains/ingestion et dans les suites santé existantes.

- [x] Écrire les caractérisations santé : formes de payload, compteurs,
  authentification, dernière utilisation, rejet, révocation concurrente,
  création de jeton à commit incertain.
- [x] Exécuter ces caractérisations avant extraction ; distinguer les
  anomalies héritées des comportements contractualisés.
- [x] Écrire les tests rouges du principal, des portées fermées, de l’adaptateur
  santé et du parser strict conservant indices et valeurs non objets.
- [x] Implémenter les primitives minimales et le registre vérifié au boot.
- [x] Faire déléguer les routes santé sans changer leurs chemins, jetons,
  clés métier ou règle de compatibilité historique.
- [x] Vérifier explicitement qu’un jeton santé ne dépose jamais un SMS et
  qu’un futur type n’hérite jamais d’une portée par défaut.
- [x] Passer les suites unitaires et frontières de commandes santé concernées.
- [x] Revue INLINE du lot et diff isolé, sans embarquer l’index concurrent.
  Aucun commit réalisé : la publication Git reste hors périmètre.

Acceptation : deux adaptateurs exercés par contrats, santé inchangée et
absence de duplication d’authentification/politique dans la nouvelle route.

## Lot 2 — Modèle durable, jetons SMS et ingestion filtrée

Fichiers : migrations Alembic additives, ingestion/models/repository/limits/
token_commands ; sms/models/schemas/ingestion/ingest_router/sensitive_filter/
sender_policy ; config et cartes de données.

- [x] Écrire les tests rouges parser/limites/dates et les fixtures du lot 0.
- [x] Écrire les tests rouges du filtre : chaque catégorie de secret,
  faux positifs, blocage par identifiant, entrée ambiguë et six langues.
- [x] Écrire les tests de schéma SQL : unicité, FK, propriétaire, crypto,
  token/source séparés et absence du secret brut.
- [x] Écrire le test de confidentialité transversal : message ignoré absent
  des contenus, index, file, réponses et logs.
- [x] Écrire les courses PostgreSQL : deux dépôts, révocation, désactivation
  du compte, édition de blocage, saturation de stockage.
- [x] Implémenter les migrations et commandes ; reçu + SMS + travaux dans
  une transaction avec ordre de verrouillage documenté.
- [x] Implémenter les codes HTTP, acquittement par élément et invariant
  arithmétique des compteurs ; validation sans réémission des valeurs.
- [x] Ajouter limitation source/compte partagée et panne Redis en 503,
  sans modifier la politique historique santé.
- [x] Tester rollback avant commit, perte d’acquittement après commit et
  renvoi avec même event_id ; conflit si contenu différent.
- [x] Déclarer tables et préférences dans les cartes de données avant que
  leurs gardes ne soient ajustées ; aucun secret exportable.
- [x] Écrire le test de purge avec la ligne users CONSERVÉE, comme le produit :
  suppressions explicites des nouvelles racines, enfants supprimés par leur
  parent réel, compte B intact. Une FK CASCADE depuis users ne suffit pas.
- [x] Stocker et tester la liste de blocage chiffrée dans sms_sender_blocks,
  avec HMAC de comparaison ; aucun numéro en clair dans les préférences,
  aucun résidu de celles-ci après suppression du compte.
- [x] Rejouer les migrations et tests PostgreSQL sur base jetable.
- [x] Revue INLINE et diff cohésif conservé dans le worktree isolé ; aucun commit.

Acceptation : le POST demandé stocke ou ignore de façon traçable, sans LLM,
sans appel contacts/push dans la transaction et sans faux acquittement.

## Lot 3 — Lecture, recherche, identité et effacement

Fichiers : sms/repository/search/identity/reads/preferences/management_commands ;
réutilisation contact_directory, phone_numbers et IdentityResolver ; export,
effacement du compte et cache.

- [x] Écrire les tests rouges des lectures : owner, tri double, instantané,
  curseur opaque lié aux filtres, page/totaux et réception tardive.
- [x] Écrire les tests d’identité uniques/ambigus : trois fournisseurs,
  numéros courts/internationaux, homonymes, alias, source tronquée et indisponible.
- [x] Écrire les tests du tokenizer et HMAC : accents, CJK, littéraux,
  termes courts, ET, faux candidats et reconstruction/version de clé.
- [x] Implémenter recherche déterministe et requêtes indexées selon la
  qualification, avec refus explicite des requêtes trop larges.
- [x] Tester la reconstruction de l’index interrompue et le rattrapage des
  écritures concurrentes ; bascule de génération seulement après validation.
- [x] Tester la pagination des expéditeurs indépendamment de celle des
  messages : un expéditeur ancien ne disparaît pas à cause d’une page récente.
- [x] Écrire puis implémenter le contrôle d’accès aux lectures Assistant ;
  revalidation avant publication et refus des caches périmés.
- [x] Écrire les tests de suppression confirmée : portée revue, état périmé,
  tombstone, reprise tardive, annulation d’envois et invalidation de débrief.
- [x] Implémenter les commandes par la voie applicative existante, avec
  reçu de commit et pas de mutation directe depuis le navigateur.
- [x] Tester export déchiffré, exclusions de secrets/index/file, effacement
  du compte et reset de discussion qui conserve les SMS.
- [x] Étendre la liste de colonnes déchiffrées et les redactions d’export pour
  les SMS, sources et blocages ; contrôler la classe de chaque nouvelle table.
- [x] Écrire un test d’export volumineux qui échoue sur l’accumulation en RAM
  et le tri non déterministe ; implémenter lecture et écriture incrémentales
  à tampon borné, réutilisant export_stream lorsque son contrat convient.
- [x] Tester export_too_large avec le plafond existant, nettoyage des fichiers
  partiels et annulation ; aucun succès tronqué ni hausse de plafond.
- [x] Tester suppression SMS/compte pendant construction et avant publication :
  aucun nouveau fichier téléchargeable contenant la source effacée.
- [x] Invalider les exports déjà hébergés susceptibles de contenir un SMS
  supprimé ; nettoyage de fichier récupérable et téléchargement ensuite refusé.
- [x] Tester la barrière extraction_revision sur retrait/effacement SMS :
  un extracteur ancien ne republie pas sous une autorisation périmée.
- [x] Vérifier la portée honnête de l’effacement : une mémoire issue d’une
  discussion n’est pas présentée comme supprimée par la seule suppression du SMS.
- [x] Mesurer plans SQL, temps, mémoire et taille d’index ; vérifier budget
  d’archive avec insertions simultanées.
- [x] Revue INLINE et diff cohésif conservé dans le worktree isolé ; aucun commit.

Acceptation : archive consultable et recherchable sans LLM, identité honnête
en dégradé, et suppression qui résiste aux reprises.

## Lot 4 — Notifications durables par appareil et Alertes backend

Fichiers : ingestion/delivery_repository, scheduler/ingestion_delivery,
startup/scheduler_ingestion, sms/notifications ; adaptateur de transport
notifications/service, couture neutre et hub_counts/schemas.

- [x] Écrire la FSM de livraison et ses transitions dans un test de table :
  pending, claimed, accepted, skipped, failed, unknown ; chaque statut
  a producteur et lecteur. Reprise conditionnée au lease owner/fence.
- [x] Écrire les tests crash avant envoi, après envoi avant acquittement,
  worker périmé, deux workers, compte supprimé, jeton d’appareil invalidé.
- [x] Écrire le test de livraison partielle : un appareil accepté, un échoué ;
  la reprise vise seulement l’appareil en échec.
- [x] Tester qu’un appareil inscrit après la réception n’entre pas dans les
  destinataires d’une occurrence en attente ou en reprise.
- [x] Exposer si nécessaire un envoi public par appareil sur le service existant,
  au lieu d’appeler une méthode privée ou de réenvoyer à tous les appareils.
- [x] Implémenter snapshots courts puis I/O hors transaction, résultats explicites,
  backoff borné et état d’échec consultable.
- [x] Vérifier SMS ignoré/doublon/supprimé : aucune push ; notifications désactivées :
  aucune nouvelle émission ; appareil nouvellement inscrit : aucun backfill.
- [x] Vérifier aucune archive du corps dans le chat et aucune diffusion
  Telegram/Slack/pairs/e-mail par défaut.
- [x] Ajouter compteur exact et lecture paginée SMS au hub.
- [x] Enregistrer l’effet de notification par occurrence et résultat réel,
  en distinguant SSE, transport accepté et personne ayant lu.
- [x] Tester source scheduled pour l’avis à réception et proactive pour
  le commentaire autonome du heartbeat. Ajouter la façade publique adaptée ;
  ne pas réutiliser tel quel le helper qui impose proactive.
- [x] Tester la chaîne des tentatives et la terminalité des lignes du registre :
  occurrence stable, tentative distincte reliée, résultat unknown réconcilié
  avant tout renvoi, labels traduits et export du registre lisible.
- [x] Ajouter métriques et panneaux/alertes dans le même lot ; wiring startup
  déclaré avec jitter, arrêt et reprise propres.
- [x] Revue INLINE et diff cohésif conservé dans le worktree isolé ; aucun commit.

Acceptation : un SMS retenu arme une notification à toute heure ; aucun
échec de transport ne détruit l’archive et aucun succès SSE ne devient un
faux succès de push.

## Lot 5 — Paramètres, page de lecture et Alertes frontend

Fichiers : nouveaux hooks et composants SMS/ingestion, routes localisées,
réglages/registry/icônes/recherche, NotificationsHub/useHubCounts/
useNotifications/routage et locales.

- [x] Écrire les tests rouges de position de Mes SMS après Réunions,
  recherche de section, liens profonds, URL calculée et visibilité de capacité.
- [x] Écrire les tests de gestion des jetons : révélation unique, pas de
  stockage navigateur, commit incertain, révocation/retry et changement de compte.
- [x] Extraire le panneau ingestion présentatif commun et adapter la santé
  sans changer sa logique de données ni ses secrets.
- [x] Écrire les tests page/liste/détail : jours et expéditeurs, recherche,
  fuseau utilisateur, pagination, focus, états vides/erreurs et rafraîchissement.
- [x] Implémenter avec les primitives identifiées et hooks useApiQuery/
  useApiMutation ; aucun fetch libre dans un composant.
- [x] Ajouter blocages, accès Assistant, push et gestion ; une préférence
  serveur commune pour l’interrupteur répété dans la zone notifications.
- [x] Ajouter section Alertes et synchronisation : déduplication occurrence
  SSE/FCM, rattrapage après reconnect et navigation localisée.
- [x] Écrire les tests négatifs de texte HTML/script/URL hostile, longues
  chaînes, gros caractères et résultat tardif d’un autre compte.
- [x] Couvrir les noms accessibles EN/FR, la parité des six locales et les
  parcours clavier/retour de focus, y compris commandes occupées.
- [x] E2E hermétique setup → page → alerte → détail, puis plus haut risque
  erreur/reprise ; API/SSE/FCM contrôlés.
- [x] Revue INLINE et diff cohésif conservé dans le worktree isolé ; aucun commit.

Acceptation : parcours personnel complet, lecture cohérente mobile/desktop,
sans requête pour une section de détail repliée ni fuite au changement de compte.

## Lot 6 — Outils, agent et carte HTML

Fichiers : agents/sms/catalogue_manifests, tools/sms_tools,
graphs/sms_agent_builder, prompt ; taxonomie, contextes/sémantique,
catalogue et enregistrements ; rendu et sorties.

- [x] Écrire les tests rouges list/search/get et erreurs déclarées, schémas
  @tool comparés aux manifestes pour bornes et paramètres temporels.
- [x] Écrire les tests catalogue : capacité off, consentement off, appel direct,
  reprise de checkpoint et source supprimée.
- [x] Ajouter le domaine singulier sms et le result_key explicite ; agent,
  slot de configuration, manifests, imports et smoke tests dans le même lot.
- [x] Implémenter la projection de données structurées et sa pagination de corps.
  Ne pas mettre les faits uniquement dans le champ message.
- [x] Déclarer type SMS, EXTERNAL, clé de résultat, contexte et présentation ;
  boot échoue sur toute entrée absente.
- [x] Écrire les tests carte pour texte littéral, dates, expéditeur brut/résolu,
  lien interne, contenu long, six langues et sanitation.
- [x] Implémenter SmsCard via BaseComponent et helpers existants, sans
  action d’envoi et sans HTML non échappé provenant du SMS.
- [x] Écrire les tests de round-trip complets : id, origine, provenance,
  curseurs et références « le deuxième », après checkpoint.
- [x] Exécuter les flux pipeline et ReAct avec réponses de modèles simulées,
  vrais outils et vraie forme de sortie.
- [x] Mesurer budget tokens sur corps maximal/emoji/CJK et petite fenêtre ;
  vérifier portes de dépense, quota compte et quota instance.
- [x] E2E cartes et HTML + cartes ; aucune duplication de corps ou de carte.
- [x] Revue INLINE et diff cohésif conservé dans le worktree isolé ; aucun commit.

Acceptation : les deux modes lisent les mêmes SMS autorisés, mêmes résultats
et erreurs, et le rendu respecte le budget et la préférence d’affichage.

## Lot 7 — Relations, débrief, accueil et proactivité

Ce lot suit les lectures/outils stables ; il ne réimplémente pas leurs requêtes.
Il a été subdivisé en trois sous-lots cohérents, chacun avec son cycle TDD ; aucun commit n’a été effectué.

### 7A. Relations

- [x] Tests rouges agrégats : relation uniquement SMS, alias/merge/unmerge,
  ordre d’activité, totaux exacts au-delà de la page et source indisponible.
- [x] Ajouter section SMS typée et son composant, sans copier tout le détail
  du message dans les modèles de relation.
- [x] Étendre périmètre 360°, preuves, consultations et digest de débrief.
  Tester les anciennes préférences : vide reste vide, sélection exprimée
  ne gagne pas SMS implicitement.
- [x] Tester arrivée/suppression/retrait du consentement pendant génération ;
  débrief obsolète annoncé, aucune regénération par SMS.
- [x] Tests front et E2E périmètre → point → carte de message.

### 7B. Accueil et textes

- [x] Tests rouges de complétude des sections : payload/unions, noms, ordre,
  personnalisations, cache, setup, rafraîchissement et rendu.
- [x] Ajouter fetcher SMS séparé et indexé ; comptes exacts et fenêtre publiée.
- [x] Ajouter carte, hook/types, icône, préférences et lien localisé.
- [x] Ajouter résumé compact pour greeting et projection bornée pour synthèse,
  derrière le consentement et les protections de contenu externe.
- [x] Tester carte masquée = aucune lecture, consentement off même cache
  présent = aucun SMS au modèle, quota épuisé = cartes toujours disponibles.
- [x] Tester invalidation multilingue, course read/write du cache et absence
  de boucle de génération à l’arrivée de plusieurs SMS.
- [x] Tester l’ancien schéma de cache CardsBundle : aucune erreur 500 pendant
  la transition. Radio, voix/live, conditions et pairs ne gagnent pas de lecture
  SMS par l’ajout du champ ; scénarios négatifs explicites.

### 7C. Heartbeat et registres

- [x] Tests rouges source disponible/indisponible et autorisée/refusée ;
  pas de récupération SMS avant le contrôle des permissions.
- [x] Ajouter source, ordre, placement, contexte typé et fenêtre
  anti-répétition ; avis immédiat et commentaire ultérieur distingués.
- [x] Étendre consultation_surfaces et enregistreurs des surfaces réellement
  lectrices ; ne pas compter les caches comme appels fournisseur.
- [x] Tester budget, quota et absence de notification répétant seulement
  l’avis de réception ; aucun envoi si aucun fait nouveau pertinent.
- [x] Exécuter les tests d’effets/consultations, de dépenses et de complétude.
- [x] Revue INLINE par sous-lot et diffs cohésifs conservés ; aucun commit.

Acceptation : chaque écran et chaque texte lit le même contrat d’autorisation,
de compteur, d’identité et de fraîcheur ; les coûts restent attribués.

## Lot 8 — Qualification transverse et livraison révisable

- [x] Rejouer l’ensemble ingestion → file → push simulée → page → discussion →
  relations → accueil en Docker dev, avec données fictives.
- [ ] Tester sur iPhone réel le raccourci et la push, en documentant version iOS,
  permissions, type de message et états réseau réellement éprouvés.
- [x] Mesurer latence d’acquittement, requêtes, index, mémoire et délai de file ;
  publier les résultats, pas un objectif transformé en performance mesurée.
- [x] Mesurer aussi l’export personnel (RAM, volume complet, ordre, fichiers
  temporaires), le dump de sauvegarde et la reconstruction de l’index.
- [x] Passer les vérifications de migration et suppression du compte sur base
  jetable ; jamais une migration expérimentale sur dev partagé ou production.
- [x] Rédiger ADR, guide Raccourcis reproductible, erreurs/reprise/rotation et
  description exacte des limites de détection/livraison.
- [x] Compléter le runbook de restauration : environnement isolé, livraison
  désactivée, réconciliation des suppressions/révocations et des notifications
  antérieures ; ne pas rejouer automatiquement l’outbox d’un ancien dump.
- [x] Mettre à jour cartes des domaines/modules, traductions et documentation
  depuis leurs sources ; CLAUDE.md puis sync-agents si de nouvelles règles
  permanentes sont effectivement ajoutées.
- [x] Revue contradictoire INLINE de la matrice des risques et preuves.
- [x] Préparer le diff et la synthèse de validation ; laisser toute action de
  publication/déploiement hors périmètre sans instruction nouvelle.

Clôture logicielle : voir la [qualification et ses limites](../../technical/SMS_QUALIFICATION.md). Les cases physiques du lot 0 et du présent lot restent ouvertes ; aucun résultat simulé ne les remplace. Aucun commit, intégration au checkout principal, publication ni déploiement effectué.

## Commandes et portes de validation

À chaque cycle : tests ciblés réellement rouges avant implémentation, puis
verts sur le contrat touché. Depuis apps/api, exemple prospectif :

    .venv/Scripts/python.exe -m pytest tests/unit/domains/sms -q
    .venv/Scripts/python.exe -m pytest tests/unit/domains/ingestion -q

Les tests PostgreSQL/Redis sont marqués pour une exécution CI réelle, avec
services jetables. Ne pas les remplacer par SQLite, ni les désactiver selon
la présence d’une clé fournisseur.

Avant clôture des changements frontend et backend :

    task lint
    task test:markers
    task test:frontend:coverage
    task test:backend:unit:coverage
    task test:e2e

Pour le frontend, le contrôle hôte sans cache fait aussi partie de la preuve :

    cd apps/web
    pnpm exec tsc --noEmit --incremental false

Les tâches frontend sont préférées aux appels directs de couverture pour
neutraliser NEXT_PUBLIC_API_URL comme le prévoit le dépôt.

Pour les tables et files :

    task test:backend:integration
    task db:migrate:replay-check
    task test:alerts

Ne lancer ces tâches qu’avec leurs cibles jetables correctement configurées.
Adapter l’exécution ciblée aux marqueurs et fixtures réellement créés.

Avant push éventuellement autorisé : task ci:fast, hook pre-commit normal
et hook pre-push de scan de secrets. Aucun --no-verify. Le commit doit isoler
les fichiers du lot dans l’index déjà modifié par ailleurs.

Pour la documentation, task lint:docs:preview distingue les fichiers nouveaux
non stagés de ce que voit l’index. Ne pas corriger un faux lien qui disparaît
dans le preview. Les ratchets de couplage, taille, complexité, hooks, a11y,
métriques, logs et couverture ne peuvent que rester stables ou diminuer.

Un résultat global rouge hérité est rapporté séparément avec sa preuve.
Les tests réels sur appareil, les tests simulés et les validations statiques
sont trois preuves distinctes, jamais présentées comme équivalentes.

## Définition de terminé

- Tous les besoins V1 ont leur parcours et leurs tests.
- Les décisions métier de la personne sont appliquées côté serveur.
- Chaque nouvelle donnée a une classification explicite, un export ou motif
  d’exclusion, une purge effective avec users conservé, et son test de propriété.
- Aucun SMS exclu n’a de contenu conservé dans LIA.
- Aucun succès d’ingestion sans commit acquitté.
- Une reprise ne recrée ni message ni occurrence de notification.
- Les échecs partiels, délais et ambiguïtés sont visibles et récupérables.
- Recherche, effacement/export, consentement, registres et coûts sont cohérents.
- Santé, téléphonie et contacts restent couverts par leur non-régression.
- Docker dev et iPhone apportent les preuves attendues, ou les limites
  restantes sont déclarées et empêchent la certification correspondante.
- Contrôles requis réussis, changements concurrents préservés, documentation à jour.
