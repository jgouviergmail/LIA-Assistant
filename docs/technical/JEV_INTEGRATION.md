# JEV — intégration native et bascule administrative

Décision d'architecture : [ADR-325 — décisions bornées, bascules à chaud et replis comptabilisés](../architecture/ADR-325-JEV-Bounded-Decisions-With-Hot-Switches-And-Accounted-Fallbacks.md).

Le lot 1 ajoute TypeSafe/Jev pour le choix automatique du modèle de compte rendu
de réunion. L'activation est facultative et désactivée par défaut. La rédaction du
compte rendu reste assurée par le modèle configuré dans `meeting_synthesis`.
Le lot 2 ajoute des aperçus de pertinence pour les recherches et une alternative
au vérificateur radio. Chaque usage possède son propre interrupteur OFF par défaut.
Le lot 3 ajoute les consultations simples et la détection d'absence d'utilité de
l'initiative. Les lots suivants ajoutent mesure, consultations bornées, observation
des extractions, exclusions HITL et autres collections. Le
[registre des usages](../../apps/api/src/domains/llm_config/jev_registry.py) définit
les interrupteurs indépendants ; une bascule générale conserve leurs préférences.

## Bonnes pratiques communes aux usages existants et futurs

Le guide TypeSafe joint et les contrats officiels [State](https://docs.typesafe.ai/concepts/state)
et [Choice](https://docs.typesafe.ai/primitives/choice) guident la conception ; les
permissions, les invariants métier et les contrôles de LIA restent exécutés en code.

- Fournir l'état utile et ses relations, avec une question qui désigne explicitement
  l'objet évalué. Une clé de question ne remplace pas cette désignation. Les champs
  arbitraires d'un résultat MCP ne sont pas supprimés sur leur seul nom.
- Nommer la portée des preuves : un extrait documentaire ou de transcription ne
  décrit pas le document entier. Un dépassement du budget natif déclenche le repli,
  sans tronquer silencieusement la requête pour obtenir une décision.
- Grouper les questions indépendantes sur le même état dans une requête bornée.
  Laisser au code les dates, fuseaux, calculs, limites et contrôles d'identité.
- Prévoir l'abstention et valider la réponse entière avant de l'appliquer. La
  concentration des probabilités n'est pas une garantie de justesse ; chaque
  usage exige un corpus propre, un corpus indépendant et une mesure des replis.
- Garder les contenus externes comme données non fiables. Une décision de
  pertinence n'accorde jamais un droit, n'approuve pas une action et ne prouve pas
  qu'une écriture a abouti. Le panneau distingue proposition, action et observation.
- Mesurer les appels et les parcours complets séparément, en incluant erreurs,
  replis et coûts. Un observateur conserve l'extraction existante et ajoute du
  travail ; il n'est pas présenté comme une économie déjà acquise.

Les corpus, relectures adversariales et limites mesurées sont consignés dans les
plans des [lots 1](../superpowers/plans/2026-09-28-jev-lot-1.md),
[2–3](../superpowers/plans/2026-09-29-jev-remaining-lots.md) et
[4–8](../superpowers/plans/2026-09-29-jev-lots-4-8.md).

## Configuration et recette sur dev

1. Appliquer les migrations, puis vérifier que l'API et le catalogue ont démarré.
2. Dans **Administration → Configuration LLM**, enregistrer la clé du fournisseur
   **TypeSafe (Jev)**. Elle suit le stockage chiffré et l'audit existants.
3. Chaque usage expose son modèle et son délai, dont
   **Meeting template selection (Jev)** pour les réunions.
   Son modèle par défaut est épinglé dans
   [LLM_DEFAULTS](../../apps/api/src/domains/llm_config/constants.py).
   Il est de catégorie `decision` : les paramètres de génération et les emplacements
   de chat lui sont interdits. Les capacités et le tarif sont ajoutés par la
   [migration dédiée](../../apps/api/alembic/versions/2026_09_28_2101-b138c047a5d2_seed_jev.py)
   et visibles dans **Tarification LLM texte**. Un tarif administré est conservé.
4. Dans **Administration → Intégrations JEV**, activer l'usage « Choix automatique
   du modèle de compte rendu », puis l'interrupteur général. La clé, le modèle
   actif et son tarif doivent être disponibles pour activer un interrupteur.
5. Enregistrer une réunion synthétique sans modèle explicitement choisi ni
   préférence utilisateur prioritaire ; vérifier le modèle sélectionné, le compte
   rendu et son coût. L'option existante de sélection automatique doit être active.
6. Désactiver l'interrupteur général et reproduire le parcours : le sélecteur
   existant reprend la main. Les préférences des usages restent enregistrées.

L'interface n'annonce un changement qu'après la réponse du serveur. En cas de
réponse perdue, « Actualiser » relit la préférence durable. Chaque écriture est
auditée et ne modifie qu'un interrupteur. Les routes GET/PATCH
`/api/v1/admin/llm-config/jev` exigent une session administrateur.

## Contrat de bascule et de repli

Le [registre des usages](../../apps/api/src/domains/llm_config/jev_registry.py)
relie chaque emplacement livré à son réglage et à sa configuration. Le registre
refuse les usages incomplets et les interrupteurs partagés involontairement.
Une opération lit les drapeaux dans une seule requête PostgreSQL ; sa configuration
est ensuite figée jusqu'à sa fin. Les workers relisent la base à chaque opération,
sans dépendre d'une invalidation Redis. Une modification validée s'applique à la
lecture suivante ; elle n'annule pas un appel déjà parti.

Le modèle explicitement choisi pour la réunion, puis la préférence du titulaire,
gardent leur priorité. Seuls les candidats autorisés pour ce titulaire sont
présentés à JEV. La régénération réutilise le modèle de la réunion.

Le [sélecteur](../../apps/api/src/domains/meetings/jev_selection.py) accepte une
réponse valide, membre des candidats, dont la concentration atteint son seuil.
Ce seuil est une règle empirique d'acceptation, pas une probabilité de correction.
Une hésitation, une abstention, un modèle indisponible ou une réponse invalide
déclenche le sélecteur génératif existant dans son intégralité.

Le [transport natif](../../apps/api/src/infrastructure/llm/typesafe_client.py)
effectue une tentative vers l'API TypeSafe officielle, sans redirection ni reprise
automatique. Le délai couvre l'appel HTTP entier. La lecture de configuration est
aussi bornée ; le temps de persistance des registres s'ajoute à ces délais.
Les plafonds de requête/réponse sont locaux et conservateurs : un dépassement
provoque le repli. Un refus de quota est propagé, jamais contourné par le repli.

## Données, coûts et observation

Lorsque l'usage est actif, TypeSafe reçoit l'extrait borné de transcription, le
titre de calendrier et les noms/descriptions des candidats. Les références privées
des modèles sont remplacées par des clés opaques. Les instructions traitent le
contenu comme des données ; aucun contenu ni clé ne figure dans les métriques.
La transcription suit son chemin de réunion propre, sans présumer qu'elle traverse
le pivot anglais des requêtes conversationnelles.

Le [point d'entrée natif](../../apps/api/src/infrastructure/llm/jev_runtime.py)
vérifie les plafonds du compte et de l'instance avant l'appel. Les compteurs réels
restent attribués à JEV et au tarif lu avant l'appel. Une réponse inutilisable avec
des compteurs valides reste facturée avant le repli. Si le fournisseur ne retourne
aucun compteur exploitable, le coût n'est pas inventé ; le motif d'échec est visible
dans les métriques. Les compteurs JEV ne sont jamais ajoutés à la capture qui sera
tarifée comme une synthèse générative.

Le registre de plateforme reçoit une ligne par modèle sous le même `run_id`.
La réunion conserve aussi les charges natives par tentative, avec ajout atomique
et idempotent. Son coût cumulé inclut les tentatives précédentes ; une notification
ne reprend que la charge native de son propre traitement. Les montants du registre
conservent la précision monétaire commune de LIA. La sélection et la synthèse sont
affichées séparément. Une tentative payante dont la synthèse échoue ou est annulée
clôt aussi son registre de décision, sans doubler une clôture déjà enregistrée.

Le tableau Grafana **Meetings** expose les décisions par issue et la latence p95 du
chemin JEV. Cette latence n'est pas la durée totale d'une réunion et un repli ajoute
le temps du sélecteur existant. Les métriques sont
`jev_decisions_total` et `jev_decision_duration_seconds`.

## Panneau de diagnostic JEV

Dans le panneau debug du chat, ouvrir **Appels JEV**. Le flux est indépendant
des tours de conversation : la sélection exécutée en arrière-plan pour une réunion
est visible même sans nouveau message de chat. La section affiche l'appelant,
le `run_id`, le modèle demandé/retourné, la durée du chemin natif, les compteurs
disponibles et le coût calculé au tarif configuré.

Le contexte présente l'état et la question réellement transmis, avec un aperçu
borné et le nombre de caractères omis. La réponse valide montre le candidat et son
libellé, la concentration et les probabilités principales. Une réponse inexploitable
affiche son code d'échec et, lorsqu'il est disponible, le statut HTTP ; son corps
brut n'est pas conservé. Les limites sont définies dans
[jev_debug_models.py](../../apps/api/src/infrastructure/llm/jev_debug_models.py).

La réponse et l'action sont distinctes : décision appliquée, traitement existant
sollicité, traitement interrompu ou annulé. Une action encore non confirmée reste
explicitement en attente. « Traitement existant sollicité » décrit le repli demandé,
pas la réussite ultérieure de la synthèse. Une même tentative garde le même
identifiant lorsque le traitement appelant renseigne son action.

La collecte exige l'accès debug effectif du titulaire : drapeau administrateur,
ou autorisation opérateur et préférence personnelle pour les autres comptes.
`GET /api/v1/debug/jev` réévalue cette permission et ne renvoie que les appels
du compte authentifié. Une erreur ou un refus retire les données affichées.
La section se rafraîchit uniquement lorsqu'elle est ouverte et l'onglet visible ;
la fermer annule sa requête et efface son état local. Aucune trace n'est écrite
dans le stockage du navigateur. La réponse HTTP est `no-store`.

Le contenu est chiffré dans Redis, limité en nombre et en âge par appel ; une
mise à jour ne prolonge pas l'âge autorisé de la tentative. La famille `debug:jev`
emploie aussi l'[expiration absolue par champ Redis](https://redis.io/docs/latest/commands/hpexpireat/)
pour supprimer le corps chiffré à son échéance, même si des appels suivants
maintiennent le cache du compte actif. Elle
est déclarée comme cache utilisateur dans le registre de purge commun. La collecte
et les écritures sont facultatives et bornées par les délais du
[stockage de diagnostic](../../apps/api/src/infrastructure/llm/jev_debug_store.py).
Leur indisponibilité ne relance pas l'inférence et ne remplace pas sa réponse.
Ces opérations ajoutent un coût de diagnostic ; aucun gain de latence n'est
revendiqué pour le panneau lui-même. Les métriques et registres de dépenses
restent indépendants de cette collecte, qui n'ajoute aucun appel payant.

## Retour arrière

Le retour opérationnel est l'interrupteur OFF. Il conserve tarifs, préférences et
historique. Le downgrade de la migration de données ne retire que ses propres
lignes intactes, avant utilisation. Il refuse de supprimer des réglages administrés,
des modèles préexistants ou un historique de dépenses. Les étiquettes d'enum restent
présentes dans PostgreSQL ; leur retrait n'est pas nécessaire pour la bascule OFF.

## Projection des résultats recherchés

Le même lot corrige la projection des objets utilisée pour le filtrage sémantique
par le LLM existant : textes courts, booléens faux, dates imbriquées et tous les
participants restent présents avec leurs relations. Les champs techniques sont
exclus et la provenance externe est conservée. Les limites de longueur/profondeur
sont signalées explicitement. Le sérialiseur vocal reste indépendant.
Cette correction est indépendante des aperçus JEV du lot 2.
La conservation de ces informations peut augmenter la taille du prompt du filtre
existant. Il s'agit d'une correction de fidélité, sans gain de latence revendiqué.

## Lot 2 : premiers résultats et vérification radio

Les usages `filter_email`, `filter_event`, `filter_task` et `filter_file` qualifient
les objets déjà récupérés, après autorisation et analyse de la requête en anglais.
Ils publient un aperçu provisoire pendant la synthèse. Chaque objet est pertinent,
hors sujet ou incertain ; les exclusions restent consultables au clavier. Le nombre
affiché concerne les objets récupérés, jamais le total chez le fournisseur.
Les documents incluent les fichiers générés représentés par le type FILE.

Le registre d'origine, le contexte du modèle final et son filtrage restent intacts.
Une projection tronquée n'est pas évaluée ; les questions hors budget restent
incertaines. Les opérations exactes (dates, nombres, agrégats, identités) restent
du ressort de l'existant. Aucun objet distant n'est modifié. L'aperçu ne s'exécute
que pour une recherche en navigateur, hors mutation, automatisation et voix.
Sa tâche est annulée et rejointe avant la clôture de la réponse, son état disparaît
à la fin du flux et ne rejoint aucun checkpoint ni historique local.

Ce choix vise le délai avant un premier résultat lisible. Il ajoute une décision
payante et ne réduit ni le coût ni la latence de la synthèse finale. Une réponse
déjà terminée annule l'aperçu devenu inutile. Les limites de lot et de transport
sont déclarées dans le client natif ; celles de présentation dans
[jev_qualification.py](../../apps/api/src/domains/agents/display/jev_qualification.py).

L'usage `radio_verification` reçoit le script complet et tous ses faits cités.
Chaque ligne sourcée possède son verdict ; les transitions restent dans le contexte.
Une seule incertitude, référence absente, taille excessive ou erreur fait reprendre
le script original entier par le vérificateur existant. Les préférences de formats
vérifiés, l'éditeur déterministe, le retrait des lignes et les règles de refus
continuent à s'appliquer. La concentration minimale vit dans
[jev_checker.py](../../apps/api/src/domains/radio/jev_checker.py), sans garantie
statistique de vérité. Les faits et scripts radio gardent leur langue réelle.

Une requête native groupée partage un seul coût, même si elle rend plusieurs
réponses. En conversation et en radio, elle rejoint le registre du traitement
courant uniquement lorsque compte et `run_id` concordent. Une annulation conserve
la charge connue avant de laisser le registre propriétaire se clôturer.
Le panneau JEV présente toutes les réponses du lot, leur concentration et l'action
sollicitée ; contexte borné, permissions et expiration restent communs au lot 1.

Le [bilan des lots suivants](../superpowers/plans/2026-09-29-jev-remaining-lots.md)
documente les mesures et leur portée. La recette dev doit comparer OFF/ON pour
chaque usage, y compris une requête sans résultat, un document incomplet, une panne
du fournisseur et l'arrêt d'une radio. Aucune activation ni MEP n'est automatique.

## Lot 3 : consultations et initiative

`consultation_path` intervient après l'analyse de requête et le filtrage normal du
catalogue autorisé, uniquement en pipeline. Il choisit parmi les chemins fixes
déclarés dans [jev_consultation.py](../../apps/api/src/domains/agents/services/planner/jev_consultation.py) :
emails récents, non lus ou boîte de réception ; contacts ; fichiers ou dossiers ;
tâches en attente ou terminées ; rappels en attente. Les paramètres sont constants.
Le plan rejoint les validateurs et l'exécuteur habituels. JEV ne peut ni créer un
outil, ni réintroduire un outil exclu, ni inventer un paramètre.

La requête originale et son pivot anglais, l'analyse complète et le contexte du
journal sont conservés. Les références, dates, parcours multiples, compétences,
risques de cardinalité, analyses peu sûres et replans gardent le planificateur
existant. Une contrainte supplémentaire, même un nombre demandé, exige le repli.
Les séquences historiques dites « golden patterns » ne sont pas exécutées : elles
ne contiennent pas un contrat de paramètres suffisamment précis pour ce raccourci.

`initiative_utility` reçoit exactement le prompt rendu de l'évaluateur existant,
avec ses règles, résultats, outils, souvenirs et intérêts. Il ne peut que proposer
une décision entièrement vide, ou conserver l'évaluateur complet. L'utilité inclut
les actions, les suggestions et les propositions de suivi. « Aucune action » ne
suffit donc pas à éviter cet appel. Un contexte trop grand reste avec l'existant ;
aucune réduction supplémentaire du contexte n'est appliquée pour gagner du temps.

Les seuils propres à ces deux usages vivent dans leurs modules et proviennent de
corpus distincts. Les mesures synthétiques ne garantissent pas l'absence d'erreur
sémantique future. Les replis ajoutent le temps JEV au traitement existant ; le gain
sur l'initiative est faible dans le corpus de contrôle. La consultation évite des
appels de planification, mais aucun gain de latence de bout en bout n'est affirmé.

Recette dev : comparer une consultation simple à une demande avec filtre, date ou
nombre précis ; vérifier le plan, les paramètres et la réponse finale en OFF/ON.
Pour l'initiative, comparer un résultat clos et un cas nécessitant une suggestion
ou un suivi, puis enchaîner un nouveau tour pour vérifier la remise à zéro de
l'état. Les deux usages disposent du même diagnostic, des mêmes registres de
dépenses et du même contrôle de quotas que les autres décisions natives.

## Provenance du modèle

Le modèle natif épinglé n'est pas répertorié dans les deux catalogues publics
livrés avec LIA. Le contrôle du catalogue utilise donc des capacités issues de
la documentation TypeSafe, datées et limitées à cette version dans
[field_mapping.py](../../apps/api/src/infrastructure/llm/catalogue/field_mapping.py).
Les prix et paramètres de génération restent administrés en base ; aucune lecture
réseau du catalogue n'est ajoutée à l'exécution. Les alias et versions futures
n'héritent pas automatiquement de ces preuves.

## Validation reproductible

Le [plan des lots 4 à 8](../superpowers/plans/2026-09-29-jev-lots-4-8.md)
décrit les extensions en cours et leurs critères de validation.

### Parcours complets et comparaison OFF/ON

Le panneau présente d'abord l'usage et son effet dans LIA. Les identifiants et
codes restent dans « Détails techniques ». Un aperçu de collection distingue la
proposition du fournisseur du verdict réellement retenu après le seuil : un objet
proposé hors sujet à faible confiance reste « À vérifier ». Son titre identifie
la question. « Aperçu préparé » ne signifie pas que le modèle final a exclu un objet.

L'événement structuré `chat_delivery_completed` mesure, côté serveur et avec une
horloge monotone, le délai avant le premier texte non vide, le premier aperçu
contenant un objet visible et l'émission du `done` final. Il inclut donc l'attente
des tâches arrière-plan et la comptabilisation finale, contrairement à la seule
durée du graphe. Il ne mesure pas le transport réseau ni le premier rendu navigateur.
Un statut, un aperçu vide ou entièrement hors sujet ne compte pas comme premier
résultat. L'absence d'une mesure reste `null`. Un parcours interrompu avant `done`
ne produit pas cet événement de succès.

Depuis `apps/api`, le [rapport hors ligne](../../apps/api/scripts/measure_jev_journeys.py)
extrait uniquement les compteurs autorisés de ces événements :

```powershell
$env:PYTHONPATH='.'
.venv/Scripts/python scripts/measure_jev_journeys.py --logs ../../.tmp-codex/dev.jsonl --environment "commit-config-data" > ../../.tmp-codex/journeys.json
.venv/Scripts/python scripts/measure_jev_journeys.py --samples ../../.tmp-codex/journeys.json
```

L'export n'invente ni l'état des interrupteurs ni la qualité. Pour comparer,
renseigner `mode` (`off`/`on`), un `pair_id` par paire/répétition et `quality`
(`pass`/`fail`) après contrôle des résultats. Le champ `environment` doit identifier
le même code, les mêmes modèles, données, permissions et contexte conversationnel.
Alterner l'ordre OFF/ON et séparer les premières compilations/charges de cache des
essais chauds. Ne rejouer que des lectures sur des comptes/corpus de recette.

Le rapport calcule les distributions descriptives et les différences appariées
séparément. Il refuse les runs dupliqués, paires ambiguës et mesures incohérentes.
Les économies ne portent que sur des paires complètes, au même environnement,
dont les deux résultats ont été validés. Le p95 est le rang supérieur observé ;
un petit échantillon ne démontre pas la stabilité d'une queue de distribution.
Les durées de plusieurs appels LLM ne sont jamais additionnées pour reconstituer
une latence utilisateur. La trace native JEV garde sa propre portée.

Le [plan et bilan du lot](../superpowers/plans/2026-09-28-jev-lot-1.md) rassemble
les vérifications. Le [rejeu opt-in](../../scripts/analysis/jev_lot1_replay.py)
utilise le sélecteur et le prompt livrés avec un
[corpus synthétique annoté](../../apps/api/tests/fixtures/jev_meeting_cases.json).
La clé vient de `TYPESAFE_API_KEY`, jamais du corpus. Depuis `apps/api` :

```powershell
.venv/Scripts/python ../../scripts/analysis/jev_lot1_replay.py --live --cases tests/fixtures/jev_meeting_cases.json --output ../../.tmp-codex/jev-live-replay.json
```

L'option `--live` autorise des appels payants bornés. Les tests unitaires,
d'intégration PostgreSQL et les parcours navigateur n'appellent aucun fournisseur.
Le rejeu fournisseur mesure la décision, pas la transcription ni la génération du
compte rendu. La recette complète reste une validation humaine sur dev avant MEP.


## Consultations bornées, observation et exclusions

`consultation_bounded` propose des journées locales aujourd'hui/demain et des
quantités numériques explicites, résolues par le code sous les limites des outils.
Les périodes non couvertes, nombres ambigus, filtres d'échéance non exposés par
l'outil de tâches et quantités de rappels reviennent au planificateur. Les fuseaux,
permissions, validateurs et la synthèse restent actifs. La politique et son seuil
sont définis dans les
[consultations bornées](../../apps/api/src/domains/agents/services/planner/jev_bounded_consultation.py)
et leur [point d'entrée](../../apps/api/src/domains/agents/services/planner/jev_consultation.py).

Les usages `observe_memory`, `observe_interests`, `observe_journal` et
`observe_open_loops` observent le prompt complet de leur extracteur. Ils ne
suppriment aucune extraction, écriture ni opération annexe. Le diagnostic affiche
la proposition du modèle existant avant validation, sans la présenter comme une
écriture réussie. L'observation ajoute un coût et peut prolonger la clôture du tour.
Sa comptabilité est autonome, attribuée au run parent ; son attente vient après
les écritures et la comptabilisation existantes. Le
[cycle de vie commun](../../apps/api/src/domains/agents/services/jev_extraction_observer.py)
annule et rejoint chaque appel en cas d'interruption.

`hitl_exclusion` traite uniquement une exclusion explicitement demandée pendant
la confirmation d'une liste. Toutes les réponses doivent être valides et dépasser
le seuil du [consommateur](../../apps/api/src/domains/agents/services/hitl/jev_item_filter.py),
sinon la liste entière revient au filtre existant. Les indices restent ceux des
objets proposés, y compris après plusieurs modifications et reprise du checkpoint.
Une liste vide annule l'opération ; sinon une nouvelle confirmation humaine reste
obligatoire. La sélection JEV ne vaut jamais autorisation d'exécution. Le filtre génératif
exige lui aussi un tableau JSON : ses explications libres et booléens ne peuvent
pas devenir des indices d'exclusion. Une réponse hors contrat conserve la liste.

## Autres collections et périmètre des preuves

Les usages `filter_reminder` et `filter_ticket` reprennent les objets déjà récupérés
sous leurs permissions existantes. `filter_mcp` accepte les résultats structurés
par élément des serveurs MCP utilisateur, après leur retour. Il ne relance aucun
outil et n'accorde aucune permission ; les annotations déclarées par le serveur
ne peuvent pas retirer une confirmation. Les champs libres, y compris `metadata`
et les champs préfixés `raw`, restent des preuves externes non fiables. Les
wrappers scalaires, widgets interactifs et résultats MCP administrateur non
structurés ne sont pas éligibles à cet aperçu.

`filter_document` qualifie les extraits de la recherche RAG utilisateur déjà
réalisée pour le contexte de réponse, sans seconde recherche. Les mêmes extraits
et leurs espaces alimentent l'aperçu ; le contexte complet de synthèse est conservé.
Un extrait ne permet pas de conclure qu'un fait est absent d'un document entier.
La [projection documentaire](../../apps/api/src/domains/agents/display/document_preview.py)
reste dans le bundle éphémère de réponse, sans nouveau type checkpointé. Les notes
génériques et la documentation système ne sont pas éligibles. Les recherches
documentaires actives dérivées qui ne produisent qu'un extrait tronqué dans
`structured_data` ne deviennent pas artificiellement des preuves complètes.

Tous ces aperçus conservent les objets hors sujet consultables et les objets
incertains visibles. Une preuve trop longue ou incompatible n'est pas classée.
Les données de source, leurs statuts et la réponse finale ne sont jamais modifiés.
Chaque usage est désactivé par défaut et utilise le diagnostic JEV commun.

## Qualification avant activation

Le [bilan des lots 4 à 8](../superpowers/plans/2026-09-29-jev-lots-4-8.md)
distingue tests, appels synthétiques réels et observations dev. Les scripts de
mesure utilisent les prompts et projections livrés. Les corpus indépendants ne
prouvent pas une absence universelle d'erreur ; les concentrations ne sont pas
des taux d'exactitude. Les écarts entre extraction JEV et extraction existante
interdisent à ce stade de supprimer les extractions automatiquement.

Avant chaque MEP, activer un seul usage sur dev, comparer des lectures OFF/ON à
contexte égal, vérifier qualité et repli dans le debug, puis valider coûts et délais
avec le rapport de parcours. Les aperçus visent le premier résultat visible ;
l'observation des extractions ne constitue pas une optimisation de latence.
