# Ingestion téléphone et Mes SMS — analyse fonctionnelle et technique

Date : 19 octobre 2026. Statut : proposition à valider avant développement.

Analyse effectuée strictement INLINE, sans sous-agent et sans code métier.
Relecture contradictoire du 19 octobre : les corrections et contrats
complémentaires de la section 13 précisent les dépendances induites.
Référence de travail : HEAD 4b8016fba, branche main, avec des changements
concurrents déjà présents dans l’index et le répertoire de travail. Le code
consulté comprend ces changements ; ce document ne décrit donc pas seulement
le commit HEAD. Aucun de ces changements n’a été modifié pour cette étude.

Plan associé : [plan TDD](../plans/2026-10-19-phone-ingestion-sms.md).

## 1. Alignement et décisions de la personne

La valeur recherchée est de rendre consultables dans LIA les messages reçus sur
le téléphone, puis de les rendre utiles dans les parcours existants :
discussion, relations, accueil et alertes. Le transport sera un appel HTTPS
effectué par l’application Raccourcis, comme pour les données santé.

Le besoin comporte deux livrables indissociables :

1. Un socle d’ingestion réutilisable pour de futures remontées du téléphone :
   authentification, limites, validation, acquittement, dédoublonnage,
   traitements durables, diagnostics et cycle de vie.
2. Un premier domaine de messages reçus, exposé à la personne sous « Mes SMS »,
   avec son modèle strict et ses intégrations.

Arbitrages explicitement confirmés pendant cette analyse :

| Sujet | Décision |
|---|---|
| Émetteur technique | Application Raccourcis, appel d’une URL LIA |
| Secrets d’accès | Exclusion dès l’ingestion des OTP, codes de récupération, mots de passe et liens de connexion identifiables |
| Blocage personnel | Liste d’expéditeurs à exclure, en complément des règles de détection |
| Autres messages | Conservation des autres SMS ; pas d’exclusion générale du domaine bancaire ou médical |
| Push | Immédiate à toute heure, avec un interrupteur SMS dédié |
| Conservation | Jusqu’à suppression manuelle |
| Méthode | Analyse puis validation avant tout code métier, strictement INLINE |

Les nombres et comportements nouveaux proposés ci-dessous sont des choix de
conception, pas des faits du produit actuel ni des arbitrages déjà approuvés.

### Périmètre V1 proposé

- Messages textuels reçus et effectivement transmis par Raccourcis.
- Ingestion simple par POST /api/v1/ingest/message.
- Paramètres « Mes SMS », immédiatement après « Réunions ».
- Page de lecture : vues « Par expéditeur » et « Par jour », recherche et filtres.
- Notification immédiate déterministe et historique SMS dans les Alertes.
- Section SMS des Relations et prise en compte autorisée dans le point 360° et
  le débrief existants.
- Carte d’accueil ; informations pertinentes dans « Le point de LIA » et le
  greeting, sous contrôle de la personne.
- Outils de liste, recherche et consultation dans les deux modes d’exécution.
- Carte HTML native dans les modes cartes et HTML + cartes.
- Gestion des jetons, blocages, suppression et export personnel.

La V1 ne promet pas l’accès à la boîte Messages de l’iPhone : elle conserve
ce que Raccourcis envoie. Elle ne déduit pas l’état lu du téléphone, ne lit pas
les messages sortants et n’envoie pas de SMS. MMS, pièces jointes, RCS,
iMessage, conversations de groupe et historique antérieur ne sont pas
présumés disponibles. Un message reçu par Raccourcis peut être conservé avec
un transport « unknown » si l’iPhone ne permet pas de le distinguer.

## 2. Ce qui existe réellement et ce qui manque

Les chemins de cette section ont été consultés dans le répertoire de travail.
Les conclusions portent sur le code, sans certification du runtime.

| Contrat vérifié | Source actuelle | Conséquence |
|---|---|---|
| Ingestion santé séparée de l’authentification par session | [ingest_router.py](../../../apps/api/src/domains/health_metrics/ingest_router.py) | Réutiliser le principe Bearer, jamais la session du navigateur sur le téléphone |
| Jetons santé hachés, révélation unique, révocation et propriétaire actif | [models.py](../../../apps/api/src/domains/health_metrics/models.py), [service.py](../../../apps/api/src/domains/health_metrics/service.py) | Bonne base de sécurité ; le modèle reste spécifique à la santé |
| Révocation et écriture sérialisées sur le propriétaire | [management_lock.py](../../../apps/api/src/domains/health_metrics/management_lock.py), [ingestion_authority.py](../../../apps/api/src/domains/health_metrics/ingestion_authority.py) | Conserver une vérification d’autorité fraîche dans la transaction d’ingestion |
| Création de jeton avec acquittement de commit et secret hors modèle | [token_creation_commands.py](../../../apps/api/src/domains/health_metrics/token_creation_commands.py), [health_token_creation_spec.py](../../../apps/api/src/domains/agents/application/health_token_creation_spec.py) | L’industrialisation doit préserver ces garanties, pas seulement copier le formulaire |
| Parsing santé flexible mais lié aux mesures | [parser.py](../../../apps/api/src/domains/health_metrics/parser.py) | Le singleton est reconnu par date_start/date_end ; certains éléments non dictionnaires sont ignorés avant comptage. Ne pas recopier cela dans les SMS |
| Idempotence santé par période, avec mise à jour | [repository.py](../../../apps/api/src/domains/health_metrics/repository.py) | Une mesure remplaçable et un SMS immuable n’ont pas la même clé métier |
| Limite HTTP générale et garde de taille ASGI | [middleware.py](../../../apps/api/src/core/middleware.py) | Ajouter des limites métier plus petites ; aucune exemption générale pour les nouvelles routes |
| Registre des réglages et des entrées UI | [settings-sections.ts](../../../apps/web/src/lib/settings-sections.ts), [settings-section-registry.tsx](../../../apps/web/src/components/settings/settings-section-registry.tsx) | Ajouter la section, son icône, sa recherche et ses liens profonds dans les sources existantes |
| Page Réunions et primitives de frise réutilisables | [page.tsx](../../../apps/web/src/app/[lng]/dashboard/meetings/page.tsx), [timeline-group.tsx](../../../apps/web/src/components/ui/timeline-group.tsx) | Réutiliser les composants visuels ; ne pas importer les commandes propres aux réunions |
| Relations = agrégation, favoris et alias manuels | [service.py](../../../apps/api/src/domains/relations/service.py), [identity.py](../../../apps/api/src/domains/relations/identity.py), [models.py](../../../apps/api/src/domains/relations/models.py) | Pas de relation persistée universelle identifiée par un numéro ; ne pas supposer un carnet local complet |
| Contacts normalisés et cache de répertoire versionné | [contact_directory.py](../../../apps/api/src/domains/connectors/clients/contact_directory.py), [contacts.py](../../../apps/api/src/domains/relations/providers/contacts.py) | Réutiliser les trois fournisseurs et leurs indicateurs de cache et de troncature |
| Normalisation des numéros déjà partagée | [phone_numbers.py](../../../apps/api/src/domains/telephony/phone_numbers.py) | Réutiliser le socle ; qualifier ses limites : code pays de déploiement, correspondance nationale/internationale et numéros courts |
| Point 360° avec périmètre serveur et débrief persistant | [overview_scope.py](../../../apps/api/src/domains/relations/overview_scope.py), [evidence.py](../../../apps/api/src/domains/relations/overview/evidence.py), [debrief/service.py](../../../apps/api/src/domains/relations/debrief/service.py) | Ajouter SMS au périmètre, aux preuves, au digest et à la fraîcheur du débrief |
| Accueil séparant cartes et génération de texte | [service.py](../../../apps/api/src/domains/briefing/service.py), [llm.py](../../../apps/api/src/domains/briefing/llm.py) | Ne pas transformer l’ingestion en exécution LangGraph ni regénérer les textes à chaque SMS |
| Carte typée dans plusieurs unions et registres | [schemas.py](../../../apps/api/src/domains/briefing/schemas.py), [TodayBriefing.tsx](../../../apps/web/src/components/dashboard/TodayBriefing.tsx) | Ajouter le payload, les préférences d’ordre/masquage, le renderer et les parcours d’erreur ensemble |
| Push par appareil et résultat explicite | [notifications/service.py](../../../apps/api/src/domains/notifications/service.py) | Réutiliser le transport, distinguer absence d’appareil, erreur transitoire et jeton invalide |
| Diffusion proactive vers plusieurs canaux et archive du chat | [notification.py](../../../apps/api/src/infrastructure/proactive/notification.py) | Le booléen global peut être vrai grâce à l’archive ou au SSE. Il ne prouve pas une push ; ne pas diffuser les SMS vers Telegram par effet de bord |
| Outbox métier déjà présente en téléphonie | [models.py](../../../apps/api/src/domains/telephony/models.py), [reapers.py](../../../apps/api/src/domains/telephony/reapers.py) | Reprendre les invariants durables ; ce n’est pas un service générique prêt à recevoir tous les SMS |
| Notifications proactives avec sources autorisées | [source_policy.py](../../../apps/api/src/domains/heartbeat/source_policy.py), [source_availability.py](../../../apps/api/src/domains/heartbeat/source_availability.py) | Séparer « prévenir à réception » et « laisser LIA commenter un SMS » |
| Hub Alertes paginé, avec agrégats de compteurs | [hub_counts.py](../../../apps/api/src/domains/notifications/hub_counts.py), [NotificationsHub.tsx](../../../apps/web/src/components/notifications/NotificationsHub.tsx) | Ajouter une source SMS et son compte exact, sans requête de détail pour chaque section repliée |
| Catalogue de tour commun aux modes | [turn_catalogue.py](../../../apps/api/src/domains/agents/services/turn_catalogue.py) | Toute exclusion de capacité/consentement doit être commune au pipeline et à ReAct |
| Résultats riches, types et classement de confiance exhaustifs | [models.py](../../../apps/api/src/domains/agents/data_registry/models.py), [trust.py](../../../apps/api/src/domains/agents/data_registry/trust.py), [component_registry.py](../../../apps/api/src/domains/agents/display/component_registry.py) | Ajouter un type SMS explicitement EXTERNAL, avec toutes ses lectures et sa sérialisation |
| Chiffrement applicatif disponible | [utils.py](../../../apps/api/src/core/security/utils.py) | Réutiliser Fernet pour les contenus ; une recherche SQL en clair serait un autre choix de sécurité |
| Export et effacement déclaratifs | [user_data_map.py](../../../apps/api/src/domains/users/user_data_map.py), [builder.py](../../../apps/api/src/domains/account_export/builder.py), [account_deletion_service.py](../../../apps/api/src/domains/users/account_deletion_service.py) | Déclarer chaque nouvelle table, déchiffrer les données exportables, exclure les secrets |

La recherche ciblée dans les routes, la taxonomie et la téléphonie ne révèle
pas de domaine natif d’archivage SMS à étendre. Des mentions « SMS » existent
dans des descriptions et tests génériques ; elles ne constituent pas un outil
de réception ou d’envoi déjà disponible.

### Limites externes à qualifier

Apple documente un déclencheur de communication sur réception d’un message,
avec critères d’expéditeur et de contenu :
[documentation Apple](https://support.apple.com/en-euro/guide/shortcuts/apdd711f9dff/ios).
Cela confirme la voie choisie, pas la disponibilité d’un identifiant stable,
de l’horodatage exact de réception, de tous les transports ni d’une file de
reprise garantie. Ces points exigent un essai sur la version iOS utilisée.

L’URL de développement doit être accessible depuis l’iPhone et son certificat
accepté ; le compose de développement démarre bien l’API en HTTPS. L’étude
n’a effectué aucun appel d’ingestion ni test réseau vers les URLs fournies.

## 3. Architecture proposée et arbitrages

### Choix : socle partagé natif, adaptateurs métier typés

Créer un domaine ingestion pour les contrats techniques, et un domaine sms
pour l’archive et sa politique de lecture. La couche ingestion ne dépend ni
des agents, ni des relations, ni d’un fournisseur LLM.

Les adaptateurs santé et SMS utilisent des services communs pour :
principal d’ingestion, extraction de jeton, hachage, contrôle de portée,
garde de taille, transport des erreurs, limitation, diagnostic et autorité
du propriétaire. Chaque ressource garde son schéma, sa règle d’idempotence
et son écriture métier. Un registre fermé d’adaptateurs est installé au
démarrage et vérifié dans les deux sens.

Les routes santé, leurs jetons hm_, leurs identifiants et leur table restent
compatibles. Un adaptateur de jeton santé les transforme en principal de
portée health:write seulement. Les nouveaux jetons utilisent leur propre
préfixe et une portée explicite sms:write. Aucun jeton santé n’autorise les
SMS et aucun jeton SMS n’autorise la santé. Les futures ressources ne gagnent
aucune portée implicitement.

Ce choix mutualise la mécanique sans imposer une migration simultanée des
secrets santé et de toutes les commandes applicatives qui les manipulent.
Le maintien transitoire de deux stockages de jetons est explicite : les
politiques et primitives sont communes, leurs dépôts sont deux adaptateurs.
Une unification physique ultérieure ne fait pas partie de ce chantier.

| Option | Intérêt | Limite | Verdict |
|---|---|---|---|
| Copier le domaine santé | Première route rapide | Duplication des correctifs, mauvaise idempotence, intégrations divergentes | Écartée |
| Table universelle de payloads JSON et workflow universel | Extension apparente facile | Typage faible, recherche et cycle de vie opaques, logique métier dispersée | Écartée |
| Bus externe et nouveaux workers spécialisés | Forte isolation | Exploitation et dépendances supplémentaires sans besoin de débit démontré | Écartée en V1 |
| Socle natif + données typées + file PostgreSQL durable | Cohérent avec LIA, évolutif, testable | Contrats communs et reprise à formaliser soigneusement | Recommandée |

### Chaîne de traitement

    Raccourcis
       → HTTPS + jeton à portée limitée
       → authentification et garde de taille
       → parsing strict et validation par élément
       → filtre secrets / expéditeurs bloqués
       → transaction : autorité fraîche + dédoublonnage + SMS chiffré
                       + reçu d’ingestion + travaux durables
       → COMMIT acquitté
       → réponse au téléphone

    Travaux durables, après commit
       → invalidation et signal de changement
       → résolution d’identité si nécessaire
       → notification par appareil autorisé
       → suivi des résultats, reprise bornée, état d’échec visible

La réception n’attend ni carnet de contacts, ni notification, ni LLM.
Une erreur d’enrichissement laisse le SMS disponible sous son expéditeur brut.
Un échec de push ne demande pas au téléphone de renvoyer un SMS déjà stocké.

### Contrat HTTP proposé

Conserver exactement les destinations exprimées :

- Développement : https://192.168.0.29.nip.io:8000/api/v1/ingest/message
- Production : https://lia.jeyswork.com/api/v1/ingest/message

L’interface calcule l’URL à partir de l’origine API avec apiEndpointUrl,
comme la santé ; les deux adresses ne deviennent pas des constantes front.

Exemple canonique, proposé pour Raccourcis :

    {
      "sender": "+33612345678",
      "date": "2026-10-19T14:42:08+02:00",
      "body": "Je serai là à 18 heures.",
      "o": "iphone",
      "schema_version": 1,
      "event_id": "8668c470-6cd5-4ced-893b-a6a08e749291"
    }

- Les quatre premiers champs expriment le besoin initial.
- schema_version vaut 1 lorsqu’il est omis en V1.
- event_id est recommandé, mais sa stabilité doit être prouvée dans Raccourcis.
- Le téléphone ne fournit jamais user_id : le propriétaire vient du jeton.
- o est une étiquette, jamais une preuve d’appareil ou un droit d’accès.
- Le jeton est lié à une source LIA stable, distincte du jeton pour survivre à
  une rotation. Un éventuel identifiant source envoyé doit lui correspondre.
- Le corps est du texte littéral UTF-8, conservé sans réécriture sémantique.
  Un expéditeur vide ou un corps vide/tout blanc est refusé. Les types sont
  stricts : pas de conversion silencieuse d’un nombre, booléen ou objet en
  texte. Les champs inconnus sont signalés ; une nouvelle version ajoute
  explicitement ses champs au contrat.
- date est ISO 8601 avec fuseau ; conversion UTC. Une date naïve ou ambiguë
  est refusée avec le format attendu. Ne jamais la remplacer par « maintenant ».
- Si Raccourcis ne donne que l’heure d’exécution, l’horodatage doit être marqué
  comme tel ; ne pas le présenter comme l’heure de réception prouvée.
  Le champ optionnel date_kind porte received, captured ou unknown ; son
  absence donne unknown, sans inventer la provenance. La base distingue
  l’instant transmis et ingested_at, horloge serveur.
- Transport et identifiant natif du message restent optionnels et inconnus
  lorsqu’ils ne sont pas réellement exposés.

Le parser commun peut reconnaître objet, liste et enveloppe data ; un
adaptateur de transport couvre les formes historiques santé. Le mode SMS est
strict : aucune entrée n’est ignorée silencieusement et les indices originaux
sont conservés. NDJSON peut être supporté par le même parser si son test
canonique est vert ; il n’est pas nécessaire au raccourci de référence.
La compatibilité de l’ancien singleton santé et de son enveloppe iOS reste
testée explicitement ; pas de modification silencieuse de sa réponse.

Réponse d’un objet : 201 si créé, 200 si déjà reçu ou ignoré par la politique.
Un rejet sensible est acquitté comme ignored_sensitive et non comme erreur
à rejouer. L’expéditeur bloqué produit ignored_sender. Les réponses ne
répètent ni texte ni secret ; message_id est présent uniquement pour un SMS
stocké. Un lot valide syntaxiquement reçoit une réponse 200 avec verdict par
indice et compteurs dont la somme égale le nombre d’éléments reçus.

400 : enveloppe illisible ; 401 : jeton absent/invalide/révoqué ; 403 : mauvaise
portée ou ressource désactivée ; 409 : même event_id avec contenu différent ;
413 : taille dépassée ; 422 : schéma d’un objet invalide ; 429 : limitation
avec Retry-After ; 503 : dépendance nécessaire indisponible ou commit non
acquitté. Les erreurs de validation ne doivent pas réémettre les valeurs
Pydantic input ni le corps brut. Aucun secret dans une URL.

Bornes initiales proposées, configurables et publiées par une même déclaration
aux producteurs, schémas et outils :

| Borne nouvelle | Proposition |
|---|---|
| Taille HTTP métier | 256 Kio, en complément du plafond ASGI existant |
| Éléments par lot | 50 |
| Expéditeur | 256 caractères |
| Corps | 16 000 caractères, jamais coupé silencieusement à l’ingestion |
| Origine | 32 caractères |
| Décalage futur accepté | 5 minutes ; au-delà, erreur explicite |
| Requêtes SMS par source | 60/minute, compteur partagé |
| Requêtes SMS par compte | 120/minute, pour empêcher le contournement par multiplication de jetons |
| Page de lecture | 20 par défaut, 50 au maximum |

Ces valeurs sont à mesurer au lot de qualification ; elles ne changent pas
les limites santé existantes. Déclarer les paramètres dans config, exemples
d’environnement et métadonnées. Les plafonds de stockage doivent être séparés
des quotas LLM : la conservation manuelle n’est pas une allocation disque
infinie. Premier réglage proposé : budget d’archive SMS de 1 Gio par compte,
incluant l’index applicatif, seuils visibles et refus explicite à saturation,
sans suppression automatique de messages. L’empreinte réelle doit être
mesurée avant de confirmer cette valeur d’exploitation.

### Idempotence et garanties exactes

Avec event_id stable, contrainte unique par propriétaire, source, ressource et
identifiant ; le digest canonique décide entre reprise identique et conflit.
Le digest est un HMAC avec séparation de domaine, pas un hash en clair
facilement testable sur un code court. La portée ne dépend pas du token_id.

Sans identifiant stable, une empreinte de l’expéditeur, de la date normalisée,
du corps exact et de l’origine fournit un dédoublonnage de secours. Deux vrais
messages identiques au même instant peuvent alors être confondus : c’est une
limite du signal reçu, pas une garantie qu’une contrainte SQL peut inventer.
Le même SMS capté par deux appareils ne peut être reconnu avec certitude que
si une identité commune du message est fournie.

La garantie serveur est « après une réponse de succès acquittée, le verdict
et, s’il est accepté, le SMS et les traitements associés sont durables ».
Perte de réponse après commit : renvoi avec le même identifiant, même résultat.
Perte d’acquittement SQL : pas de faux succès, puis réconciliation par la même
clé lors d’une nouvelle tentative.

La push est au moins une tentative durable, avec reprises bornées. Une
acceptation FCM/APNs n’est pas une lecture par la personne. Un crash après
envoi mais avant enregistrement peut occasionner un doublon externe si le
transport ne déduplique pas ; tag et identifiant stables réduisent ce risque,
sans promesse de livraison exactement une fois.

Redis indisponible : nouvelle ingestion SMS refusée en 503 avec indication de
reprise, plutôt qu’un débit non borné. Le comportement historique santé reste
inchangé. Ce choix rend indispensable la qualification des reprises côté
Raccourcis ; si le téléphone ne peut pas conserver et rejouer un événement,
la garantie de bout en bout reste explicitement best effort avant acquittement.

## 4. Confidentialité et autorisations

### Filtre préalable au stockage

La liste de blocage et le détecteur déterministe s’appliquent avant l’écriture
du corps, de l’expéditeur, de l’index, d’un travail d’enrichissement ou d’une
notification. Aucun LLM n’est appelé pour classer le SMS à réception.
La politique est relue sous le verrou du propriétaire : si sa version a changé
depuis le parsing, refaire le filtrage avant toute écriture. Un changement
concurrent de blocage ne peut donc pas être ignoré par un ancien snapshot.

- Identifiants bruts de blocage typés : numéro, adresse éventuelle, nom
  alphanumérique littéral. Les numéros utilisent la normalisation partagée
  lorsque le pays est connu ; ne pas déduire un pays d’un nom de langue.
- Les blocages par libellé sont des correspondances explicites normalisées,
  pas une recherche approximative ni une fusion de relations.
- Règles multilingues de secrets : formulations de connexion/validation,
  OTP, récupération, mots de passe et liens d’authentification reconnus.
  Un nombre dans une date, un montant ou un numéro de colis n’est pas
  automatiquement un OTP.
- Verdicts et version de politique sont testables. Une règle fournit une
  catégorie bornée, sans conserver son extrait déclencheur.
- Pour un message ignoré, seul un reçu technique minimal peut subsister :
  compte/source, identifiant ou empreinte HMAC, date de traitement et code de
  verdict. Ni expéditeur, ni corps, ni valeur de code dans ce reçu.

Un détecteur déterministe ne garantit pas la reconnaissance de tout secret
dans du texte libre. Le produit doit présenter exactement ce qu’il filtre.
Les expéditeurs connus peuvent être bloqués pour renforcer la protection.
Le filtre serveur ne peut pas supprimer ce qui existait déjà dans l’app
Messages du téléphone ; il empêche sa conservation dans LIA.

Une modification de blocage concerne les prochaines réceptions. Proposer
séparément « supprimer aussi les messages déjà reçus de cet expéditeur »,
avec périmètre et confirmation serveur ; ne jamais effacer rétroactivement
une archive par simple édition de la règle.

### Trois consentements différents

1. Le jeton autorise uniquement le dépôt.
2. Le réglage Assistant autorise les consultations par LIA, désactivé par
   défaut comme la santé.
3. Le réglage de notification autorise la push immédiate, indépendamment de
   l’Assistant et du heartbeat. L’enregistrement d’un appareil et ses
   permissions système restent nécessaires.

Les pages personnelles et la carte d’accueil déterministe peuvent afficher
l’archive avec Assistant désactivé. En revanche, aucune donnée SMS ne doit
alors atteindre greeting, synthèse, débrief, outils ou contexte heartbeat,
y compris à partir d’un cache.

Le contrôle est effectué au point de lecture métier, puis revérifié avant
publication d’un travail long. Le catalogue de tour retire les outils non
autorisés ; l’exécution reste l’autorité contre les appels directs et les
reprises HITL. Une préférence chargée avant sa révocation n’est pas suffisante.

Le retrait du consentement interdit les nouvelles consultations et invalide
les projections en cache ; il n’efface pas des phrases déjà écrites dans
l’historique de discussion. L’UI doit le dire. Les instantanés SMS encore
réinjectables sont filtrés/réhydratés sous la politique actuelle ; les copies
déjà présentes dans une réponse historique relèvent de la suppression de
cette conversation.

### Autres protections nécessaires au besoin

- Corps et identifiants sensibles chiffrés par le mécanisme applicatif existant.
- Aucun contenu dans les logs INFO/WARNING/ERROR, métriques, labels ou traces
  d’erreur. Logs de diagnostic de contenu désactivés par défaut pour cette
  route ; pas de dump du corps même en exception de validation.
- Textes SMS classés EXTERNAL dans les deux chemins LLM, y compris les
  assemblages directs du dashboard, du débrief et du heartbeat.
- Pas d’exécution d’instruction contenue dans un SMS ; aucune URL ouverte
  automatiquement, aucune suggestion « répondre » qui enverrait un message.
- Aperçu de push masqué par défaut : « Nouveau SMS dans LIA », sans expéditeur
  ni corps. Option d’aperçu explicite ultérieure possible ; non nécessaire V1.
- Aucun transfert implicite des SMS vers Telegram, Slack, pairs ou e-mail.
- Les commandes d’administration ne donnent pas accès aux contenus des SMS.

## 5. Stockage, recherche et cycle de vie

### Modèle proposé

| Table nouvelle | Responsabilité |
|---|---|
| ingestion_sources | Source déclarée, propriétaire, libellé chiffré si personnel, identifiant stable indépendant des jetons |
| ingestion_tokens | Hash, préfixe public, source, portées, dates d’usage et de révocation ; jamais le secret |
| ingestion_receipts | Clé d’idempotence, HMAC canonique, verdict, version et acquittement rejouable sans contenu sensible |
| ingestion_deliveries | Travail durable par reçu/type/destination, tentative, prochain essai, propriétaire de lease et fence, résultat explicite |
| sms_messages | Reçu accepté, compte, identifiant, expéditeur brut chiffré, identité de regroupement opaque, horodatages, corps chiffré, origine et provenance |
| sms_search_terms | Index lexical aveugle dérivé ; aucun mot du SMS en clair |
| sms_sender_blocks | Identifiants bloqués chiffrés et clés HMAC de comparaison ; aucune liste de numéros en clair dans les préférences |

Les tables métier se rattachent au reçu par une vraie FK ; la file référence
le reçu. La suppression du compte PURGE explicitement les nouvelles racines :
la ligne users est conservée par LIA, donc une FK CASCADE depuis users ne se
déclenche pas. Les cascades entre enfants et parents réellement supprimés sont
déclarées dans la carte de données et testées. Révoquer
un jeton ne supprime ni source, ni messages. Le registre des adaptateurs porte
la lecture typée d’une ressource pour un travail ; la file générique ne
contient pas de copie de son corps.
Le retrait d’une source est logique : son identifiant demeure utilisable pour
reconnaître les reprises. L’effacement de son archive est une commande distincte.

Le choix d’identité de regroupement doit rester réversible : conserver la
source brute, la preuve de résolution, sa version et son niveau de confiance.
Une clé opaque ne devient jamais un nouveau référentiel de noms autonome.

Index minimaux : propriétaire/date de réception/id, propriétaire/clé
d’expéditeur/date/id, unicité d’idempotence, et file par état/échéance.
Le tri est toujours date décroissante puis id décroissant, avec instantané de
pagination as_of et curseur opaque validé pour le compte et les filtres.
Les totaux sont exacts sur le même prédicat que la page ; le nombre d’éléments
retournés n’est jamais un total.

### Recherche : décision explicite, pas de faux plein texte chiffré

Fernet ne permet pas ILIKE ou un index PostgreSQL de plein texte sur le corps.
Déchiffrer toute l’archive à chaque recherche serait coûteux et non borné.
Copier le corps dans un tsvector en clair annulerait une partie de la protection.

Choix proposé V1 : index aveugle de termes normalisés avec HMAC tenant-scopé,
et vérification des candidats après déchiffrement. Recherche lexicale par
mots entiers combinés en ET, insensible à la casse et aux accents ; pas de
recherche sémantique, de préfixe implicite ou de résumé LLM.

Un seul tokenizer sert l’écriture et la requête. Il conserve les mots Unicode,
les numéros et les tokens courts ; pour les écritures sans espaces, ajouter
des segments CJK déterministes couverts par le corpus chinois. Les exemples
acceptés et refusés figurent dans l’aide et les schémas. Une recherche par
expéditeur et période reste disponible sans texte.

Les termes et éventuelles positions sont dérivés ; leur fréquence et égalité
peuvent encore être observées dans une fuite de base. Le HMAC empêche une
vérification triviale sans clé, pas toute analyse de fréquence. Utiliser une
clé dérivée avec séparation de domaine à partir du secret applicatif,
avec version de clé et chemin de reconstruction. Ne jamais utiliser le
jeton d’ingestion comme clé de recherche.

Un budget de candidats et de temps est obligatoire. Une requête trop large
retourne QUERY_TOO_BROAD et demande un filtre ; elle ne publie ni total partiel
comme exact, ni faux « aucun résultat ». Qualification PostgreSQL sur une
archive représentative avant validation de la stratégie. La recherche par
fragments arbitraires serait une extension distincte, avec son coût d’index
et son contrat explicitement approuvés.
Une reconstruction de l’index maintient la génération active jusqu’à validation
de sa remplaçante et bascule atomiquement ; échec ou crash garde le dernier
index valide. Les nouvelles écritures sont rattrapées avant la bascule.

### Effacement et dérivés

Dans les paramètres, proposer suppression par expéditeur, plage et totalité,
avec confirmation serveur et relecture du périmètre avant commit. La page de
présentation reste une page de lecture.

Effacer corps, index, projections et débriefs devenus obsolètes ; annuler les
travaux non envoyés. Conserver un tombstone technique minimal d’idempotence
pour qu’une reprise tardive ne réintroduise pas ce que la personne a supprimé.
Le tombstone ne conserve ni numéro ni corps ; il disparaît avec le compte.
La durée et l’empreinte de ces reçus techniques sont visibles dans le budget
de stockage ; ce ne sont pas des SMS archivés.

L’export inclut les SMS retenus, lisibles et dans leur ordre temporel ; il
exclut jetons, clés, index aveugles et états internes de livraison. Son
implémentation doit aussi traiter la mémoire, la taille maximale et les
archives déjà produites, selon le contrat détaillé en section 13. Les tables
et préférences entrent dans user_data_map et user_column_map, ainsi que dans
les gardes de complétude et l’effacement du compte. Un reset de conversation
ne touche pas l’archive SMS ni les reçus, conformément aux familles de données.

Une nouvelle règle d’exclusion ne peut pas effacer rétroactivement une réponse
déjà produite. La suppression des sources, la reconstruction des débriefs et
la suppression éventuelle des conversations sont des périmètres distincts.

## 6. Résolution de l’expéditeur

Ordre demandé conservé : contacts de la personne, puis relations, puis valeur brute.

1. Déterminer si l’identifiant est un numéro, une adresse ou un nom alphanumérique.
   Un numéro court ou un nom d’entreprise n’est pas rejeté comme « téléphone invalide ».
2. Sur les contacts normalisés du fournisseur actif, chercher une correspondance
   exacte et unique après normalisation vérifiée. Des contacts portant le même
   nom ou le même numéro ne donnent pas une identité certaine.
3. En absence de correspondance certaine, appliquer les alias manuels déjà
   déclarés et l’identité des relations. Une similitude de nom n’invente pas
   une association entre numéro et personne.
4. Si indisponible, ambigu ou tronqué, conserver et afficher l’identifiant brut.
   État de résolution explicite ; pas d’échec de réception.

Le répertoire versionné évite une requête fournisseur par SMS. Résolution
après commit, single flight par version du répertoire et invalidation sur
changement du connecteur ou du carnet. Un cache tronqué ne prouve jamais
« absent de tous les contacts ». Les fusions manuelles restent réversibles et
ne redirigent aucun message vers un autre compte.

Réutiliser phone_numbers et IdentityResolver ; si un helper doit être déplacé
vers un module neutre, conserver ses réexports et ses tests téléphonie/partage
e-mail. Ne pas modifier la sémantique de same_line pour résoudre le seul cas SMS.

## 7. Intégrations fonctionnelles et UX

### Paramètres et page Mes SMS

Section après Réunions, cohérente avec SettingsSection et les accordéons :

- « API d’ingestion » : URL complète, aide Raccourcis, liste des sources et
  jetons, création/révocation, révélation unique, dernier appel acquitté,
  compteurs de reçus/ignorés/erreurs sans contenu.
- « Assistant » : opt-in explicite et portée lisible des usages.
- « Confidentialité » : expéditeurs bloqués et explication des exclusions.
- « Notifications » : lien vers le réglage SMS, même donnée que dans la
  section des notifications proactives.
- « Mes SMS » : accès à la page de lecture.
- « Gestion » : stockage, export et suppressions confirmées.

Une seule source de préférences sert les deux emplacements de l’interrupteur
de push ; deux composants ne doivent pas créer deux réglages concurrents.
Le jeton brut ne passe ni dans le LLM, ni dans les registres, ni dans
localStorage/sessionStorage ; continuation éphémère du navigateur d’origine
sur le modèle santé lorsque la commande vient du chat.

Page /[lng]/dashboard/sms, avec accès depuis les paramètres, la carte d’accueil,
les Alertes et les Relations. Pas de nouvel onglet obligatoire dans la
navigation principale déjà dense. Vue par jour par défaut, vue par expéditeur
en alternative ; le mode et les filtres sont conservés dans l’URL.
Par jour, la page de messages est triée globalement puis regroupée.
Par expéditeur, le serveur pagine les groupes par leur dernier message, puis
les messages d’un groupe ouvert disposent de leur propre curseur décroissant.
Ce regroupement ne doit pas être calculé sur une page tronquée de messages :
il ferait disparaître des expéditeurs ou diviserait leurs fils sans l’annoncer.
Les totaux distinguent explicitement nombre d’expéditeurs et nombre de SMS.

Les groupes de jours suivent le fuseau de préférence de la personne,
explicitement transmis aux primitives ; le helper Réunions prend sinon le
fuseau du navigateur. Ce défaut ne doit pas devenir la règle SMS.
Un groupe poursuivi sur la page suivante est annoncé comme tel.

Réutiliser SectionHeader, BackLink, TimelineDayGroup/TimelineGroup, SearchInput,
Pagination, EmptyState, Skeleton et LoadingAnnouncement. Préserver recherche,
position et focus au rafraîchissement. Gros texte, liens et numéros non cassables
ne provoquent pas de débordement horizontal ; mobile, zoom et lecteur d’écran
sont des critères de réception.

L’état « consulté dans LIA » est une amélioration proposée, distincte du statut
lu sur l’iPhone. V1 peut se limiter à l’historique daté sans badge « non lu »
si cette mutation n’est pas ajoutée avec son contrat serveur ; ne pas inventer
un état de lecture à partir de la présence d’une notification dans le navigateur.

### Push et Alertes

Une réception retenue crée une occurrence de notification durable, sans
passage par la décision LLM du heartbeat et sans dépendre de ses horaires.
Les SMS ignorés, reprises identiques et tombstones ne créent aucune push.

Relecture des préférences et du compte au moment de l’envoi ; l’arrêt des
notifications annule les envois encore en attente. Une panne FCM, un appareil
sans permission ou un relais absent ne bloque pas la consultation de l’archive.
Ne pas envoyer rétroactivement tous les anciens SMS quand un appareil s’inscrit.
Les destinations éligibles sont figées pour l’occurrence, et les permissions
sont revérifiées avant envoi ; une inscription ultérieure n’ajoute pas de
destination à une vieille occurrence. Une révocation ne peut retirer une
notification déjà acceptée par le transport.

Déduplication commune SSE/foreground push par identifiant d’occurrence ; un
signal de changement provoque un refetch limité. Au reconnect, reprendre
depuis la base : Redis Pub/Sub n’est pas durable.

La section SMS des Alertes liste les messages retenus avec lien localisé vers
le détail et total exact. Elle est alimentée par le domaine SMS, pas par une
copie de chaque corps dans l’historique général du chat.

Sur iOS natif, le code actuel envoie un réveil générique via le relais ; il
ne transporte pas nécessairement le titre et le lien détaillés du SMS. Réutiliser
ce fonctionnement et vérifier le parcours après ouverture. Ne pas promettre
une navigation ciblée depuis une push iOS sans preuve sur la coque publiée.

### Notifications proactives intelligentes

Présenter le réglage « SMS reçus : me prévenir immédiatement » dans la zone
existante de notifications, avec sa propre politique horaire explicite.
La source optionnelle « SMS » du heartbeat sert à signaler un élément utile
oublié ou à contextualiser une information, sous opt-in Assistant et permission
de source. Elle ne répète pas l’avis de réception déjà envoyé.

Étendre source_policy, disponibilité, placement, contexte typé et fenêtre
anti-répétition ensemble. Le jeu des sources désactivées actuel active par
défaut les futures sources : le consentement Assistant SMS reste donc une
barrière obligatoire, et l’activation de cette source est présentée
explicitement dans l’UI.

### Relations

Ajouter l’agrégat d’activité SMS à l’aperçu des relations, et une section
« SMS reçus » avec page et total exact dans le détail. Une personne dont le
seul signal est un SMS peut apparaître ; une identité inconnue reste telle.

Le point 360° et le débrief lisent SMS seulement si la source est sélectionnée
et l’accès Assistant autorisé. Ajouter la source à OverviewSection, au modèle
de détail, aux blocs, consultations, payloads et au digest de débrief.
Une préférence historique vide reste vide ; une évolution de schéma ne doit
pas activer silencieusement SMS pour une sélection déjà exprimée.

L’arrivée, la suppression, le changement de consentement ou d’identité marque
le débrief comme obsolète. Pas d’appel LLM par réception : reconstruire au
prochain déclenchement prévu ou demandé, avec les limites existantes.

### Accueil et textes de LIA

Carte déterministe : nombre exact sur une fenêtre publiée, derniers
expéditeurs/messages, fraîcheur et lien vers Mes SMS. Proposition de fenêtre :
les dernières 24 heures, avec date explicite et accès à l’archive complète.
La borne est un paramètre partagé avec le payload, jamais un nombre écrit
seulement dans le prompt.

Ajouter payload, union, CardsBundle, noms/ordre, préférences, rafraîchissement,
hook et renderer ensemble. Une carte masquée ne déclenche aucune lecture.
Invalider la carte SMS pour toutes les langues par les builders de clés
existants ; la synthèse devient obsolète mais n’est pas recalculée en boucle.

Greeting : métadonnées compactes uniquement, par exemple un nombre de
nouveaux messages récents ; pas de corps de SMS ni de détail privé gratuit.
Synthèse : petit ensemble de messages pertinents autorisés, avec provenance
et budget ; ne pas injecter toute l’archive ni résumer automatiquement chaque SMS.

### Discussion et cartes HTML

Domaine canonique singulier sms, result_key explicite sms_messages pour éviter
un pluriel dérivé absurde. Un agent SMS natif et trois lectures proposées :

- list_sms_tool : liste récente filtrée, paginée, bornes temporelles explicites.
- search_sms_tool : recherche lexicale, expéditeur et période.
- get_sms_tool : message identifié et lecture paginée du corps si nécessaire.

Manifestes, schémas @tool, contexte typé, sémantique des identifiants, filtre
de catalogue, builder d’agent, configuration LLM, prompts et registre de
présentation sont livrés ensemble. Les erreurs passent par la taxonomie
standard et les données par UnifiedToolOutput.structured_data.

Le SMS est SENSITIVE pour la confidentialité et EXTERNAL pour la confiance :
ce sont deux axes distincts. Une carte ne se fait pas passer pour un e-mail.
SmsCard réutilise BaseComponent, échappement, format de date, texte littéral
et sections repliables ; son rendu ne génère ni action d’envoi ni HTML issu du
corps. Respecter les modes d’affichage et la chaîne de sanitation existants.

La sélection/référence « le deuxième SMS », un résultat utilisé plus tard et
une reprise de checkpoint doivent conserver l’id et la provenance, sans
perdre de champ lors de la sérialisation. Une source supprimée ou désormais
interdite est signalée, jamais réanimée par un cache.

## 8. LLM, coûts, registres et performance

Zéro appel LLM, embedding ou résumé à réception, au filtrage, à la résolution
déterministe, à la lecture de page et à la notification immédiate.

Les usages autorisés passent par les voies de dépense existantes :

- Discussion : TrackingContext et catalogue du tour ; le nouveau slot SMS
  suit la configuration runtime, pas un modèle codé en dur.
- Greeting et synthèse : même appel existant, entrée enrichie sous budget,
  facturation et fallback existants.
- Débrief et heartbeat : gardes de dépense du compte et de l’instance,
  consultations déclarées, effet de notification réclamé avant l’envoi.

Budget proposé pour les nouvelles projections : au plus 1 500 tokens SMS par
bloc de lecture/synthèse et une fraction de la fenêtre effective du slot,
le minimum des deux. Réponse de liste : aperçu court et identifiants ; le
corps long se lit par fragments via curseur. Le tokenizer réel est l’autorité,
pas une estimation caractères/4. Ne pas s’appuyer sur l’exception « premier
item entier » de ReAct pour faire entrer un SMS géant dans le contexte.

Les limites de fragments, nombre d’items et temps de requête sont publiées
dans les manifestes ET les schémas que ReAct lie réellement. Tout fragment
coupé annonce son curseur suivant et son caractère partiel ; la carte peut
consulter le détail par la voie authentifiée sans gonfler le prompt.

En quota épuisé, conserver réception, archive, recherche déterministe et
push générique ; greeting de repli et synthèse/débrief non générés portent le
verdict prévu. Ne pas provoquer une relance LLM pour remplacer un refus de quota.

Les appels de contacts réels sont enregistrés dans le registre des
consultations ; un cache hit ne prétend pas avoir rouvert le carnet.
Les lectures SMS de la synthèse, du débrief et du heartbeat étendent
consultation_surfaces et leurs enregistreurs existants, sans importer
agents/effects depuis le domaine SMS. Les actes de notification utilisent une
couture typée neutre, avec résultat par canal, sans détourner le booléen
global du dispatcher.
L’avis de réception configuré par la personne relève d’une instruction
permanente, source scheduled dans le registre ; le commentaire décidé plus
tard par le heartbeat relève de proactive. Le helper existant
proactive_notification_effect impose actuellement proactive : il ne peut pas
être repris tel quel pour classer l’avis immédiat.

Pas d’extraction automatique de mémoire, d’habitude, d’intérêt ou d’open loop
à chaque SMS en V1. Une utilisation ultérieure dans une discussion reste
soumise aux contrats de mémoire existants. Leur provenance actuelle pointe
vers la conversation et son message, pas vers une ligne SMS : la V1 ne doit
pas annoncer une traçabilité native SMS → mémoire déjà disponible.
Une future extraction autonome exigerait un opt-in, une référence typée avec
FK et tombstone, une stratégie d’effacement des dérivés et un budget séparés.

Pour les postes modestes : liste serveur paginée, rendu des sections ouvertes,
pas d’archive complète en mémoire navigateur, pas de bibliothèque de recherche
ou de virtualisation ajoutée sans mesure. Serveur : requêtes indexées, sessions
courtes, pas de session partagée dans gather ni maintenue pendant un appel push.

## 9. Matrice des impacts et risques

| Risque / impact | Niveau | Mesure concrète | Preuve attendue |
|---|---|---|---|
| Régression ingestion santé | Élevé | Adaptateur compatible, mêmes routes/jetons/erreurs documentées, pas de migration des secrets | Caractérisation avant extraction, replay PostgreSQL |
| Deux appels simultanés créent deux SMS/push | Élevé | Unicité SQL, reçu et file dans la même transaction | Deux sessions/connexions réelles, une seule occurrence |
| Révocation pendant ingestion | Élevé | Fence du propriétaire et vérification du jeton sous verrou | Course déterministe PostgreSQL |
| Règle de blocage modifiée pendant un dépôt | Élevé | Préférence versionnée et même ordre de verrouillage | Aucune écriture après le point de révocation établi |
| Secret stocké dans erreur/index/outbox | Critique | Filtre précoce, erreurs sans valeurs, reçus minimaux, aucun corps dans la file | Assertions sur toutes les tables, logs et réponses |
| Faux négatif du détecteur de secrets | Élevé, résiduel | Corpus six langues, règles bornées, liste de blocage, annonce honnête | Mesure des faux positifs/négatifs ; aucune promesse de détection universelle |
| Mauvaise personne associée | Élevé | Correspondance unique, alias existants, brut en ambiguïté | Homonymes, contacts partagés, carnet tronqué, changements de fournisseur |
| Injection via contenu SMS | Élevé | EXTERNAL sur toutes les surfaces, sanitation, aucune action implicite | Payloads adverses pipeline/ReAct/briefing/débrief |
| SMS réintroduit après suppression | Élevé | Tombstone sans contenu et annulation de file | Reprise tardive, changement de jeton, reset de conversation |
| Double notification ou crash après envoi | Moyen/élevé | Occurrence stable, résultat par appareil, tag, état unknown si nécessaire | Crash à chaque frontière et reprise multi-worker |
| Dispatcher diffuse vers un canal non demandé | Élevé | Transport SMS explicite, aucune archive chat ni canal externe implicite | Test négatif Telegram/pairs/e-mail |
| « Push envoyée » alors que seul SSE a marché | Élevé | Résultats distincts accepted/skipped/failed/unknown par destination | Échec FCM total, succès SSE seul |
| Consentement révoqué mais cache servi | Élevé | Contrôle au point de lecture et de publication, invalidation versionnée | Course avec synthèse/débrief en cours |
| Archive lente ou coûteuse à rechercher | Élevé | Index aveugle, filtre de date, borne de candidats et mesure réelle | EXPLAIN, cardinalités, temps/RAM, refus explicite si trop large |
| Croissance disque sans rétention automatique | Élevé | Budget de stockage mesuré et visible, refus sans effacement | Saturation concurrente, garde avant insert, index inclus |
| Mauvais jour local / ordre instable | Moyen | UTC en base, fuseau utilisateur, tri double, instantané de pagination | DST, minuit, date identique, arrivée tardive |
| Oubli d’un registre/lecteur | Élevé | Complétude au boot + tests bidirectionnels | Type, outil, builder, présentation, confiance, données utilisateur |
| Surcoût LLM à chaque événement | Élevé | Aucun appel sur ingestion/push, invalidation sans génération | Espions des portes de dépense et compteur d’invocations |
| Perte avant réception serveur | Élevé, externe | Raccourci avec identifiant stable et reprise à qualifier | Test iPhone hors ligne, verrouillé, faible énergie |
| Mauvais certificat ou URL de développement | Moyen | Test LAN depuis iPhone, URL calculée à l’origine API | Réception réelle dans Docker dev |
| Changement de compte pendant refetch UI | Élevé | Durée de vie du compte, abort et toast contextualisé comme Réunions | Résultat tardif A jamais visible à B |

### Observabilité utile

Mesures bornées : reçus créés/doublons/ignorés/rejetés par code, latence de
commit, âge et profondeur des travaux en attente, tentatives push par
transport/résultat, dégradation du limiteur, recherches trop larges et temps
de recherche. Aucun label de compte, numéro, nom, corps ou URL libre.

Chaque métrique nouvelle a son panneau, règle ou alerte dans le même lot.
Les absences de séries sont rendues explicitement. Les diagnostics personnels
affichent dernier acquittement, statut des jetons et retards de traitement ;
l’absence récente de SMS ne prouve pas une panne du raccourci. Ne pas créer
d’alerte « téléphone déconnecté » sans signal périodique effectivement produit.

## 10. Plan de tests directeur et simulations

| Couche | Scénarios nominaux et limites | Simulation / environnement |
|---|---|---|
| TU parser/schémas | Objet, liste, enveloppe, Unicode, retours ligne, JSON/UTF-8 cassé, éléments non objets, champs inconnus, limites exactes | Bytes réels de Raccourcis anonymisés + corpus synthétique |
| TU secrets/blocages | OTP et liens six langues, mots de passe explicites, faux amis chiffres/colis/dates, expéditeur court, règles versionnées | Corpus positif/négatif avec oracle écrit, aucun fournisseur LLM |
| TU idempotence | Fuseaux équivalents, corps distinct, rotation, id réutilisé, empreinte de secours | Horloge injectée et principal typé |
| TU identité | Contacts uniques/ambigus, noms équivalents, numéros internationaux/courts, alias, absence/limite du carnet | Trois formes normalisées fournisseurs, source tronquée et panne |
| TU recherche | Normalisation écriture/lecture, accents, CJK, termes courts, ET, littéraux %, _, apostrophes, collision HMAC simulée | Même tokenizer avec assertions indépendantes sur résultats |
| Intégration PostgreSQL | Unicité, rollback, requêtes owner-scopées, compte effacé/désactivé, révocation, blocage et stockage concurrents | Plusieurs connexions, barrières explicites, base jetable |
| Intégration file | Commit puis crash, claim expiré, ancien worker après reprise, deux workers, livraison partielle | Horloge + pannes injectées à chaque frontière, PostgreSQL réel |
| Intégration Redis | Débit partagé, limites compte/source, panne/timeouts, reprise, familles reset | Redis jetable, plusieurs workers |
| Intégration confidentialité | Ignorés absents des SMS/index/file, pas de PII dans exceptions, secrets de jeton jamais exportés | Capture logs/réponses et lecture directe des tables de test |
| Intégration cycle de vie | Suppression source, tombstone, export lisible, compte, reset, débrief obsolète, réactivation de consentement | PostgreSQL + Redis ; données de plusieurs propriétaires |
| TU/intégration outils | Pipeline/ReAct, tool schema = manifeste, catalogue interdit, résultat structuré, erreur réelle, références ordinales | Modèles simulés au niveau des appels, vrais contrats outils |
| TU budget | SMS maximal, chinois/emoji, faible fenêtre modèle, pages du corps, quota compte/instance, mesure des dépenses | Tokenizer/portes réelles avec provider simulé ; aucune dépense payante |
| TU front | Réglages, révélation unique, erreur/reprise, recherche, tri, compteurs, chargement initial vs refresh, changement de compte | Vitest + requêtes contrôlées, hooks publics non intégralement court-circuités |
| E2E hermétique | Setup jeton, Mes SMS, détail via Alertes, Relations, accueil, consentement, sanitation, SSE/push dupliquées | API/SSE/push interceptés, Chromium puis matrice périodique |
| A11y/mobile | Clavier/focus/dialogues, noms EN/FR, six locales, reflow, gros textes, zoom, contraste | axe + tests clavier, Firefox/WebKit, lecteur d’écran selon campagne |
| Flux Docker dev | POST → reçu → archive → signal → carte/Alertes → outils → débrief | API/web dev Docker, données fictives, aucun appel production |
| iPhone réel | Payload exact, date, id stable, réseau perdu, certificat, téléphone verrouillé, rafale, reprise, SMS/iMessage/groupe effectivement supportés | Raccourci et appareil de la personne, uniquement données de test |
| Push appareils | Appareil absent/invalide, un sur deux échoue, permission refusée, iOS relais générique, clic | Doubles typés en CI + appareils réels pour l’acceptation finale |
| Performance | Archive représentative, plus gros corps, rafale, forte répétition de mots, quota disque, index et RAM | PostgreSQL réel, EXPLAIN ANALYZE, rapport reproductible |
| Non-régression santé | Formes historiques, stats, jetons, révocation et locks | Suites santé existantes, y compris frontières de commandes applicatives |

Les tests doivent vérifier les effets visibles et persistants. Des snapshots,
des assertions CSS ou un mock de dépôt ne prouvent ni l’unicité, ni le verrou,
ni l’absence de contenu dans les mauvaises tables.

## 11. Compléments, optimisations et points laissés ouverts

Compléments recommandés pour la V1 : diagnostic d’ingestion sans contenu,
rotation sûre des jetons, blocage d’expéditeur, suppression avec tombstone,
export, retour à la page d’origine et provenance explicite de l’identité.
Ce sont des pièces de l’exploitation normale, pas des fonctions autonomes.

Optimisations retenues : aucun LLM sur événement, répertoire partagé/versionné,
requêtes paginées, une source de préférences, file PostgreSQL existante comme
technologie, invalidations regroupées sans regénération immédiate, lectures
de sections repliées différées et index reconstruisible.

Extensions séparées : badges « consulté dans LIA », règles d’importance,
mise en sourdine par expéditeur, aperçu push opt-in, pièces jointes,
groupes, messages sortants et autres remontées téléphone. Chaque future
ressource ajoutera un adaptateur et ses tests au socle commun ; elle ne
nécessitera pas de refaire les jetons, les limites et les garanties de reprise.

Après les réponses reçues, il ne reste pas de question métier bloquante
identifiée pour cadrer la V1. L’adoption de cette proposition de périmètre et
de ses choix techniques reste à valider avant implémentation.

Restent des preuves techniques à obtenir, qui ne peuvent pas être remplacées
par une lecture du dépôt :

1. Payload Raccourcis réel : date, identifiant et capacité de reprise.
2. Corpus de secrets : mesure des faux positifs et faux négatifs.
3. Index aveugle : pertinence linguistique, empreinte et performance PostgreSQL.
4. Push iOS : comportement du relais et navigation après ouverture.

Ces preuves forment le premier lot et des critères d’acceptation. Aucune
nouvelle hypothèse à leur sujet n’est présentée ici comme un fait établi.

## 12. Grille d’auto-évaluation

| Critère demandé | Verdict honnête |
|---|---|
| Besoin et arbitrages explicites | Oui, avec les réponses de la personne intégrées |
| Analyse fondée sur les contrats actuels | Oui pour les surfaces inspectées ; références fournies, limites cachées identifiées |
| Toutes les hypothèses déjà prouvées en exécution | Non : iPhone, corpus de secrets et performance exigent les qualifications listées |
| Architecture robuste et extensible | Proposition cohérente, à éprouver par les tests de concurrence/reprise avant certification |
| Tokens, coûts et quotas | Cadrés : aucune dépense à réception, budgets de projection, voies de dépense et deux plafonds |
| Registres et mémoire | Cadrés : vocabulaire, complétude, consultations/effets, provenance, sérialisation et absence d’extraction autonome |
| Responsive et accessibilité | Cadrés dans les composants, scénarios et critères d’acceptation ; pas encore testés en runtime |
| Plan exécutable immédiatement | Oui pour commencer la qualification puis les lots TDD ; données iPhone nécessaires à la certification du flux réel |
| Conviction à 100 % d’absence de tout angle mort | Non revendiquée : une étude statique ne peut pas prouver une livraison iOS ni un détecteur de secrets universel |

L’analyse vise à rendre les incertitudes localisées et vérifiables avant
qu’elles ne deviennent des blocages en fin de développement. Le plan associé
définit l’ordre, les contrats et les preuves de sortie de chaque lot.

## Vérification documentaire initiale de cette étude

Les 45 liens locaux du dossier et du plan ont été contrôlés : aucune cible
manquante. La tâche task lint:docs:preview a terminé avec succès : aucun lien
brisé ni chemin obsolète dans les documents vivants, aucune dérive de faits et
living maps à jour. Les chemins prospectifs du plan restent identifiés comme
futurs dans la section historique de l’audit ; leur absence est attendue.

Aucun test métier, appel d’ingestion, essai iPhone, essai push ou benchmark
de recherche n’a été exécuté pendant cette phase d’analyse. Ces vérifications
documentaires ne constituent pas une validation du futur fonctionnement.

## 13. Relecture contradictoire — dépendances et corrections obligatoires

Cette seconde passe ne change pas les décisions métier de la personne.
Elle corrige une formulation inexacte sur les cascades et transforme plusieurs
mentions transverses en contrats d’implémentation vérifiables. Le premier
dossier identifiait bien export, effacement et registres ; il ne suffisait
pas encore, sur ces points, pour prétendre que toutes leurs conséquences
étaient spécifiées.

### 13.1. Inventaire des données : export, purge et secrets

Sources revérifiées :
[carte des tables](../../../apps/api/src/domains/users/user_data_map.py),
[carte des colonnes utilisateur](../../../apps/api/src/domains/users/user_column_map.py),
[purge explicite](../../../apps/api/src/domains/users/account_deletion_service.py),
[constructeur d’export](../../../apps/api/src/domains/account_export/builder.py).

La ligne users n’est pas supprimée par le parcours habituel de suppression
du compte. L’ajout de ForeignKey(users.id, ondelete=CASCADE) ne purge donc
aucune nouvelle racine à lui seul. Il faut compléter build_purge_statements
dans l’ordre des dépendances, puis faire vérifier cette liste par
test_user_data_map_guard.py.

| Donnée nouvelle | Export personnel | Suppression du compte | Protection / lecteur |
|---|---|---|---|
| ingestion_sources | FULL, métadonnées utiles et libellé lisible | USER_PURGED explicite | Libellé personnel déchiffré par la règle d’export |
| ingestion_tokens | EXCLUDED comme les jetons santé | USER_PURGED explicite | Jamais secret ni hash dans une archive |
| ingestion_receipts | EXCLUDED, état technique sans contenu | USER_PURGED explicite | Identifiants/HMAC internes, pas un second journal des SMS |
| ingestion_deliveries | EXCLUDED, file et tentatives techniques | USER_PURGED explicite avant reçus/sources | Référence d’appareil, jamais copie de son credential |
| sms_messages | FULL, corps/expéditeur/provenance de date lisibles | USER_PURGED explicite avant reçus | Colonnes chiffrées nommées dans la déclaration de déchiffrement |
| sms_search_terms | EXCLUDED, index dérivé reconstruisible | USER_CASCADE depuis un SMS réellement supprimé | FK et propriétaire cohérents, aucun mot en clair |
| sms_sender_blocks | FULL, liste de blocage personnelle lisible | USER_PURGED explicite | Identifiant chiffré, HMAC de recherche exclu de l’export |
| users.sms_preferences | Préférence exportable pendant la vie du compte | SCRUBBED_PREFERENCE à la suppression | Booléens/valeurs techniques uniquement, aucune liste de numéros |

Les noms de colonnes chiffrées et internes sont déclarés explicitement dans
_DECRYPTED_COLUMNS et _REDACTED_COLUMNS ou leurs adaptateurs communs. Une
valeur historique indéchiffrable doit être signalée comme telle, sans échec
de l’archive entière ni faux texte vide. Les identifiants de source et de SMS
utiles à la personne peuvent rester dans l’export ; lease, fence, HMAC et
clés d’index en sont exclus.

La liste de blocage est une donnée personnelle, pas un simple booléen de
configuration. La placer en clair dans users.sms_preferences puis classer
tout ce JSON comme préférence ordinaire laisserait un numéro dans la ligne
conservée. D’où son stockage séparé, son chiffrement et sa purge explicite.

Tests obligatoires : compte A et B, enfants et parents, toutes les tables,
décryptage contrôlé, secret jamais exporté, blocages lisibles dans l’archive,
préférences effacées et absence de résidus après suppression du compte.

### 13.2. L’export existant n’est pas déjà adapté à une archive volumineuse

Le constructeur actuel fait fetchall pour chaque table et conserve les
tables_payload avant d’écrire le ZIP. Il n’applique pas d’ordre explicite à
cette lecture générique. Le plafond d’archive est contrôlé après construction.
Ces faits interdisent d’assimiler « table ajoutée à FULL » à « export SMS
complet, ordonné et compatible avec un poste modeste ».

Le module [export_stream.py](../../../apps/api/src/infrastructure/database/export_stream.py)
fournit déjà lecture par curseur, ordre et tampon borné pour les registres ;
sa disponibilité ne signifie pas que le constructeur d’export personnel
l’utilise. L’adaptation SMS doit employer ces primitives ou une lecture
paginée équivalente, avec sérialisation incrémentale et tampon borné, sans
reconstituer ensuite toute l’archive dans une liste ou une chaîne.

Exigences supplémentaires :

- Ordre déterministe date/id et instantané cohérent annoncé pour l’export.
- Contrôle d’autorité à l’ouverture et avant publication du fichier final ;
  suppression du compte ou effacement concurrent invalide la publication.
- Empreinte mémoire mesurée à grand volume, pas seulement taille du ZIP.
- Réutilisation du plafond configuré account_export_max_bytes et de son
  verdict export_too_large. Aucun succès contenant une sélection tronquée
  pour tenir dans le plafond ; aucune hausse silencieuse de ce plafond.
- Quota d’archive SMS proposé à vérifier avec le volume du reste du compte,
  les doublons JSON/rendu lisible et la place temporaire sur disque.
- Annulation/panne : fichier partiel supprimé, job classé correctement,
  reprise selon le contrat existant, jamais fichier incomplet téléchargeable.

Les durées de disponibilité et téléchargements authentifiés restent celles
du domaine account_export, notamment ses
[réglages](../../../apps/api/src/core/config/account_export.py) et
[contrôles de téléchargement](../../../apps/api/src/domains/account_export/downloads.py).
Un export déjà téléchargé par la personne ne peut pas être révoqué à distance.

Une suppression de SMS ou du compte doit également empêcher de télécharger
une ancienne archive encore hébergée qui contient ces données : invalider
les jobs/fichiers concernés côté serveur, puis nettoyer le fichier par un
travail récupérable. Une archive immuable n’est pas réécrite partiellement.
Un téléchargement déjà émis ne peut pas être « retiré » ; cette frontière
doit rester explicite.

### 13.3. Registres : distinction des rôles, de l’auteur et des tentatives

Sources :
[autorité d’un acte](../../../apps/api/src/domains/agents/effects/source.py),
[effets hors tour](../../../apps/api/src/domains/agents/effects/out_of_turn_effects.py),
[lecteurs déclarés](../../../apps/api/src/domains/agents/effects/user_data_readers.py),
[consultations directes](../../../apps/api/src/domains/shared/consultation_surfaces.py).

| Événement | Traçabilité attendue | Ce qui ne doit pas être inventé |
|---|---|---|
| Dépôt du téléphone | Reçu technique, verdict et source ; métadonnées sans corps | Consultation par LIA ou décision LLM alors qu’aucune n’a eu lieu |
| Push demandée à chaque SMS | Effet sous instruction permanente scheduled, occurrence et destination stables | Initiative proactive simplement parce qu’un worker exécute l’envoi |
| Lecture SMS dans une discussion | Consultation par le tool gate, source du tour | Nouvelle consultation identique ajoutée une seconde fois par le service |
| Lecture SMS par briefing/débrief/heartbeat | Déclaration de surface et lecture réelle avec son verdict | Source utilisée alors que la carte/politique la refuse ; appel contacts supposé sur cache hit |
| Notification décidée par heartbeat | Effet proactive sous le run de cette décision | Confusion avec l’avis de réception antérieur |
| Filtrage sensible/expéditeur bloqué | Compteurs/verdicts techniques minimaux | Texte rejeté copié dans un label de registre |
| Relance d’un envoi échoué | Tentative reliée à l’occurrence et aux essais antérieurs | Nouvel événement métier ou notification considérée reçue par la personne |

Le helper proactive_notification_effect fixe actuellement la source à proactive.
Il faut une façade d’effet explicitant l’auteur, réutilisant le registre
existant et conservant le comportement des callers historiques. Le domaine SMS
ne doit ni importer les modules agents/effects, ni appeler leur fonction privée
_claim_effect. L’adaptateur d’infrastructure installe la couture neutre typée.

Les relances respectent la terminalité des lignes de registre existantes :
une tentative distincte se rattache à sa précédente, sans rouvrir arbitrairement
une ligne close. L’occurrence métier reste unique. Un résultat unknown ne
déclenche pas de renvois aveugles ; il suit la stratégie de réconciliation
documentée et expose le risque de doublon du transport.

Le nouveau domaine ajoute aussi ses libellés dans les six langues et les
lecteurs/exporteurs des registres. Le registre de données, le registre de
consultations, le registre d’actions, les déclarations de décision/dépense et
le reçu d’ingestion sont des contrats distincts ; une entrée dans l’un ne
prouve pas la couverture des autres.

### 13.4. Suppression, consentement et apprentissage différé

Le mécanisme [extraction_consent.py](../../../apps/api/src/domains/users/extraction_consent.py)
fournit déjà extraction_revision et invalidate_extractions. Lorsqu’un
effacement ou retrait de consentement SMS doit invalider un apprentissage
qui avait lu cette source, la commande doit utiliser cette barrière sous
le verrou utilisateur, avant de laisser une tâche ancienne publier.
Ne pas créer un compteur concurrent indépendant de ce mécanisme pour les
extracteurs qu’il protège déjà.

La [provenance actuelle](../../../apps/api/src/domains/shared/provenance.py)
ne contient pas de FK SMS. La conséquence exacte de la V1 est :

- Aucune extraction autonome déclenchée par l’ingestion.
- Les débriefs/cache explicitement dérivés des SMS deviennent obsolètes ou
  sont retirés à l’effacement/retrait prévu.
- Une mémoire déjà issue d’une discussion conserve sa provenance de
  conversation ; supprimer le SMS ne signifie pas que cette mémoire, cette
  discussion ou une réponse générée a été effacée.
- Les liens de provenance supprimés ne se résolvent jamais vers du contenu
  mis de côté ailleurs. Ajouter une provenance native SMS future exige une
  vraie FK avec SET NULL, ses lecteurs et ses tests de tombstone.

La formulation UI doit distinguer « effacer les SMS », « retirer l’accès
Assistant », « supprimer la discussion » et l’oubli des connaissances
apprises. Ce sont des effets différents ; aucune case ne doit promettre tous
les autres sans les exécuter.

### 13.5. Autres consommateurs indirects : décisions V1 explicites

Les contrats sont vérifiés sur :
[PHONE_DOMAINS](../../../apps/api/src/domains/shared/phone_domains.py),
[outils live](../../../apps/api/src/domains/agents/telephony/live_tools.py),
[sources radio](../../../apps/api/src/domains/radio/personal.py),
[lecture radio des cartes](../../../apps/api/src/domains/radio/day_source.py),
[conditions de routines](../../../apps/api/src/infrastructure/scheduler/condition_evaluators.py),
[partages entre pairs](../../../apps/api/src/domains/peers/models.py).

Proposition V1 : la nouvelle carte SMS n’inscrit pas automatiquement sa source
dans les listes d’autorisation de Radio, des conditions de routines, des
appels téléphoniques/live ni des partages entre pairs. Ces lecteurs ont leurs
listes propres ; les élargir serait une nouvelle fonction et une nouvelle
autorisation. Ajouter des tests négatifs afin que le simple élargissement de
CardsBundle ou du catalogue global ne provoque aucune lecture SMS indirecte.
La discussion habituelle conserve ses modes pipeline/ReAct et ses contrats.

Les composants, fixtures et consommateurs de CardsBundle doivent accepter
le nouveau champ, même lorsqu’ils n’utilisent pas cette source. Conserver
leurs sections non sélectionnées en HIDDEN et vérifier la compatibilité de
leurs anciens payloads/cache. Un changement de schéma oblige à gérer la
version de cache ou un lecteur tolérant : ne pas attendre une erreur 500
jusqu’à expiration de toutes les anciennes entrées Redis.

### 13.6. Sauvegardes, restauration et traitements externes

Le compose de production sauvegarde la base entière. Les nouvelles tables
entreront donc dans les dumps sans ajout à une liste de tables du sidecar.
La [documentation de sauvegarde](../../technical/SECURITY.md) précise toutefois
que Fernet protège des colonnes désignées, pas le dump entier.

Les conséquences d’exploitation à documenter et tester sont :

- Nouvelle taille des dumps, du stockage et de la durée de restauration.
- Disponibilité et rotation des clés nécessaires au déchiffrement et à la
  reconstruction de l’index aveugle ; restauration des métadonnées de version.
- Une suppression de la base active ne modifie pas les sauvegardes anciennes.
  Leur rétention est celle de la politique de sauvegarde existante.
- Une restauration antérieure à une suppression/révocation peut restaurer
  d’anciens messages, jetons et travaux. Les tombstones du même dump ne peuvent
  pas décrire une suppression survenue après ce dump.
- Restaurer en environnement isolé, workers de livraison désactivés. Avant
  remise en service, réconcilier suppressions/révocations et anciens envois
  selon les preuves d’exploitation disponibles ; aucun rejeu automatique
  de toutes les notifications restaurées.

Cela ne constitue pas une promesse d’effacement rétroactif de toutes les
copies ni de rappel de données déjà envoyées à un fournisseur LLM. Les coûts,
traces autorisées et destinations effectives doivent être expliqués par les
contrats existants, sans garantie supplémentaire inventée.

### 13.7. Preuve de couverture à fournir au développement

Avant clôture, une matrice exécutée doit relier chaque table, préférence,
lecture et effet à : son propriétaire, sa règle d’export, sa purge, ses
lecteurs, son contrôle de consentement, sa rétention et son test réel.
La section 13 complète les lots du plan ; elle est normative pour leur revue.
Une simple recherche des mots « export » ou « registre » dans le document
ne vaut pas cette preuve.

Vérification après relecture : 65 liens locaux contrôlés, aucune cible
manquante, absence d’espaces de fin de ligne et nouvelle exécution réussie de
task lint:docs:preview. La vérification confirme la cohérence documentaire ;
elle ne remplace aucun des tests métier et runtime prévus.
