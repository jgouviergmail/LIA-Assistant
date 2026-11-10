# JEV — intégration native et bascule administrative

Les usages email/agenda ajoutent des [qualifications consultatives typées](EMAIL_EVENT_CLASSIFICATION.md)
aux données affichées et au contexte de réponse. Ils sont désactivés par défaut ;
leur état réel dépend des réglages administrateur. Le
[correctif de validation numérique](../superpowers/qualification/jev-probability-sum-2026-10-19/README.md)
résout les interruptions `probability_sum`. La
[qualification sémantique suivante](../superpowers/qualification/jev-classification-2026-10-19/README.md)
clarifie les questions et passe les corpus de calibration, validation et
nouveaux cas adversariaux, sans diminuer les seuils. Le transport commun des
usages du registre est vérifié sur les formes simple, lot et mixte Choice/Noul.
Les rapports comptabilisés sont conservés ; ni l'absence de badge ni une forte
concentration ne prouvent la sûreté.

Décision d'architecture : [ADR-325 — décisions bornées, bascules à chaud et replis comptabilisés](../architecture/ADR-325-JEV-Bounded-Decisions-With-Hot-Switches-And-Accounted-Fallbacks.md).

Le lot 1 ajoute TypeSafe/Jev pour le choix automatique du modèle de compte rendu
de réunion. L'activation est facultative et désactivée par défaut. La rédaction du
compte rendu reste assurée par le modèle configuré dans `meeting_synthesis`.
Le lot 2 ajoute une alternative au vérificateur radio. Le lot 3 ajoute les
consultations simples. Les lots suivants ajoutent mesure, consultations bornées,
observation des extractions et exclusions HITL. Chaque usage possède son propre
interrupteur OFF par défaut. Le
[registre des usages](../../apps/api/src/domains/llm_config/jev_registry.py) définit
les interrupteurs indépendants ; une bascule générale conserve leurs préférences.

Les huit aperçus de collections (`filter_email`, `filter_event`, `filter_task`,
`filter_file`, `filter_reminder`, `filter_ticket`, `filter_mcp`, `filter_document`)
sont retirés depuis le 8 novembre 2026
([ADR-374](../architecture/ADR-374-JEV-Retirements-Declared-Thresholds-And-Durable-Statistics.md)) :
leur seule surface, la fenêtre **Premiers résultats**, était masquée depuis le
4 octobre et rien d'autre ne lisait leurs verdicts. Leurs interrupteurs, postes de
configuration et l'événement de flux `result_preview` sont partis avec eux ; une
migration efface leurs lignes avant que le code qui ne les connaît plus démarre.

Deux usages supplémentaires utilisent ce même mécanisme, sans changer les
préférences existantes : **Présence de références personnelles** et **Refus complet
d'une confirmation**. Ils sont désactivés par défaut. Le premier peut éviter
l'extraction des références lorsqu'il conclut à leur absence, tout en conservant
la recherche large des souvenirs. Le second peut seulement annuler toutes les
actions explicitement refusées ; il n'approuve jamais une exécution. Une décision
incertaine retrouve le parcours génératif. Les sources, expériences avec cache,
gains observés et limites sont détaillés dans le
[bilan de valeur et de comptabilité](../superpowers/plans/2026-10-04-jev-value-and-text-billing.md).
Ce bilan distingue la latence des décisions admises de celle de la cascade
complète ; une économie observée sur un corpus n'est pas une promesse générale.

## Bonnes pratiques communes aux usages existants et futurs

Le guide TypeSafe joint et la documentation officielle — [State](https://docs.typesafe.ai/concepts/state),
[Choice](https://docs.typesafe.ai/primitives/choice), [Noul](https://docs.typesafe.ai/primitives/noul),
[Confidence](https://docs.typesafe.ai/confidence) et les recettes — guident la conception ; les
permissions, les invariants métier et les contrôles de LIA restent exécutés en code.

- Une condition (oui ou non) est un Noul : une seule probabilité, sans option
  « incertain » — le doute est une probabilité proche de 0,5. Un Choice qui garde
  une issue de repli la propose EN PREMIER, car Choice favorise sa première option.
- Instructions et critères sont structurés (`question` et `rules` ; `what`,
  `not_for`, `examples`), les chemins d'état entre accents graves, et l'état ne
  porte que les champs que la question lit.
- Une question ne change qu'après mesure sur les corpus de calibration et de
  validation de son usage : pas plus de raccourcis faux, au moins la même
  couverture. Méthode et résultats du 11 octobre 2026 :
  [JEV_SEMANTIC_QUALIFICATION.md](JEV_SEMANTIC_QUALIFICATION.md).

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
Les plafonds de requête suivent les contextes documentés par le fournisseur
(64k jetons par requête, 32k pour l'état et une question, estimés par le tokenizer
local avec une marge mesurée) ; un dépassement provoque le repli, sans troncature.
Les usages qui regroupent plusieurs éléments dans un même état gardent la taille de
lot avec laquelle ils ont été mesurés. Depuis le 25 octobre 2026, les décisions
partagent un client à connexions persistantes, ouvert et fermé par le cycle de vie
de l'application ([relevé](../superpowers/qualification/jev-audit-2026-10-25/README.md)).
Un refus de quota est propagé, jamais contourné par le repli.

## Seuils déclarés et réglables

Depuis le 8 novembre 2026
([ADR-374](../architecture/ADR-374-JEV-Retirements-Declared-Thresholds-And-Durable-Statistics.md)),
chaque seuil est déclaré une seule fois dans le
[registre des portes](../../apps/api/src/domains/llm_config/jev_gates.py) : sa valeur
par défaut (celle qualifiée sur jev-1.14.0), ses bornes, ce qu'il compare (la
confiance d'un choix, la concentration bornée d'une classification ou la marge d'un
Noul) et s'il juge chaque réponse seule ou toutes les réponses d'un même appel. Les
consommateurs décident tous par `gate_passes`, avec les seuils figés dans
l'instantané de l'opération (`DecisionAttempt.thresholds`) : un seuil changé
s'applique à l'opération suivante, jamais à un appel déjà parti. Un garde de
caractérisation rejoue les réponses enregistrées des corpus qualifiés et exige les
mêmes prédictions aux seuils par défaut.

L'écran « Intégrations JEV » publie chaque porte avec ses bornes ; l'administrateur
la déplace au centième (`PATCH /admin/llm-config/jev/thresholds`, sérialisé avec les
interrupteurs et audité). Seules les valeurs différentes du défaut sont stockées,
dans `JEV_<USAGE>_THRESHOLDS` : une valeur illisible ou hors bornes est ignorée au
profit du défaut et journalisée (`jev_threshold_ignored`). Dès qu'un seuil quitte son
défaut, l'usage est marqué « hors relevé qualifié » : la valeur n'est plus couverte
par la qualification, et un nouveau défaut demande une requalification payante.
L'empreinte de politique des classifications inclut les seuils déplacés, si bien
qu'un jugement rendu sous un autre seuil n'est jamais servi par le cache. Les quatre
observateurs ne décident rien et n'ont aucun seuil.

## Statistiques durables

Trois compteurs journaliers (UTC) gardent ce que Prometheus ne garde qu'une semaine :
`jev_judgement_daily` (chaque réponse jugée par une porte, rangée dans son compartiment au
centième), `jev_outcome_daily` (l'issue de chaque opération) et
`jev_observer_agreement_daily` (le verdict d'un observateur à côté de ce que son extracteur
a proposé). Ils ne contiennent que des codes du registre et des comptes, aucune colonne
utilisateur. Trois portes seulement y écrivent, dans
[`jev_statistics_sink.py`](../../apps/api/src/domains/llm_config/jev_statistics_sink.py) :
`count_jev_outcome` (le seul écrivain de `jev_decisions_total`, garde AST), appelée par
chaque consommateur ; `record_judgements`, appelée par le moteur après chaque tentative
payée réussie ; `record_observer_agreement`, appelée par l'observateur. Une issue
`disabled` n'alimente que le compteur Prometheus.

Une confiance est rangée à `floor(score × 100)`, lu sur sa valeur décimale ; le jugement
d'une marge l'est à sa distance à une réponse certaine, `ceil(min(p, 1 − p) × 100)`. Avec
ces compartiments, « conclut à ce seuil » se lit exactement : à partir du compartiment
`t × 100` pour une confiance, jusqu'au compartiment `m × 100` pour une marge.

Chaque worker agrège en mémoire et son propre vidangeur écrit, toutes les
`JEV_STATISTICS_FLUSH_INTERVAL` secondes (30) puis une dernière fois à l'arrêt dans la
borne `JEV_STATISTICS_FINAL_FLUSH_TIMEOUT`, un UPSERT trié et découpé : un worker tué perd
au plus une période de comptes, jamais une ligne partielle, et huit écrivains concurrents
ne s'interbloquent pas. Un vidage dont les instructions échouent garde son lot pour le
suivant ; un vidage dont le commit échoue l'abandonne, son issue étant inconnue, plutôt que
de le compter deux fois. `jev_statistics_rows_total` et
`jev_statistics_flush_failures_total` sont tracés sur le tableau de bord des réunions, à
côté des autres panneaux JEV.

`GET /admin/llm-config/jev/statistics?days=30` (1 à 90 jours UTC, aujourd'hui compris)
renvoie, pour chaque usage, les appels facturés, le coût et la latence médiane (un seul
agrégat sur `token_usage_logs` par poste), les issues, les compartiments de chaque porte
avec son seuil courant et, pour un observateur, son accord. L'écran « Intégrations JEV »
affiche sous chaque curseur la part que sa position conclurait, recalculée à chaque
mouvement, et la répartition en dix tranches. L'accord d'un observateur compare son verdict
à ce que l'extracteur a lui-même proposé, tel que sa propre analyse l'a déclaré : une sortie
illisible compte comme une proposition, un extracteur arrêté avant d'analyser ne laisse
aucune ligne. Sauter un extracteur reste interdit tant qu'un amendement n'a pas lu, pour
cet extracteur, aucun « vide » confiant contredit par une proposition sur au moins
200 observations en quatre semaines (ADR-374, décision 7).

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

Un corps HTTP complet est examiné avant de fermer le flux : ses compteurs valides
restent attribués même si cette fermeture échoue ou reçoit une annulation. Le
runtime clôt cette charge une fois avant de propager l'annulation. Un corps
partiel ou des compteurs invalides ne permettent pas d'inventer une consommation.

L’événement opérationnel `jev_decision_completed` expose l’usage, les modèles,
l’issue native, la durée et les compteurs/coûts disponibles, sans contexte privé.
Un `invalid_response` possède une raison de validation bornée (schéma, ensemble
de réponses ou d’options, somme des probabilités ou choix incohérent).
Ce même code fermé est conservé dans la trace et affiché dans les détails
techniques du panneau debug. Les traces historiques sans motif restent lisibles
avec une valeur absente, sans reconstruire une réponse brute.
Les anciens journaux opérationnels ne permettent pas de reconstruire cette
raison lorsqu’elle n’a pas été journalisée. Les diagnostics privés existants
restent bornés et distincts de cet événement. Une réponse native valide ne prouve
pas son acceptation par l’usage ; seuils, repli et action restent distincts.

La somme des probabilités Choice est approximative dans le contrat HTTP. Le
transport et les annotations email/agenda partagent une validation compatible
avec la quantification observée, tout en refusant les masses impossibles. Les
probabilités brutes restent visibles ; la concentration ne remplit pas une masse
manquante et abaisse le gagnant en cas d'excès. Voir le
[diagnostic et la recette](../superpowers/qualification/jev-probability-sum-2026-10-19/README.md).

Chaque réponse Choice conserve sa distribution et sa facturation, y compris
les maxima ex æquo. La confiance appliquée est le minimum entre celle reçue et
la concentration calculée avec la formule officielle
[Choice](https://docs.typesafe.ai/primitives/choice). Ce plafond ne transforme pas
la concentration en exactitude et ne relève jamais une confiance fournisseur
plus faible. Le consommateur applique ensuite ses seuils inchangés ; les calculs
aux frontières ne sont pas arrondis pour faire franchir un seuil.
`ambiguous_choice` reste un code compatible avec les diagnostics historiques,
sans être émis pour les égalités valides.

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

Les observateurs montrent séparément leur décision native et la proposition du
générateur d'extraction, avant validation métier. Un tableau vide de l'observateur
mémoire ne décrit pas une recherche de souvenirs : il indique l'absence de
nouvelles écritures proposées. Une trace écrite par une version antérieure et
devenue illisible (champ retiré, clé changée) est ignorée à la lecture ; elle ne
fait jamais échouer le reste du flux.

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
La conservation de ces informations peut augmenter la taille du prompt du filtre
existant. Il s'agit d'une correction de fidélité, sans gain de latence revendiqué.

## Lot 2 : vérification radio

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

## Lot 3 : consultations

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

L'usage `initiative_utility` qui accompagnait la consultation au lot 3 est retiré
depuis le 8 novembre 2026
([ADR-374](../architecture/ADR-374-JEV-Retirements-Declared-Thresholds-And-Durable-Statistics.md)) :
sa question ne distinguait aucun état (0,67 à 0,77 là où l'évaluateur agit, 0,41 à
0,81 ailleurs) et la production ne l'a jamais vue conclure « rien d'utile ».
L'évaluateur génératif voit de nouveau chaque tour outillé éligible ; la porte
« e-mail seulement » ajoutée le même jour a été retirée à la relecture, car le même
appel produit l'enrichissement, la suggestion et les puces de relance de tous les
autres tours.

Le seuil de la consultation provient de son propre corpus. Les mesures synthétiques
ne garantissent pas l'absence d'erreur sémantique future. Un repli ajoute le temps
JEV au traitement existant. La consultation évite des appels de planification,
mais aucun gain de latence de bout en bout n'est affirmé.

Recette dev : comparer une consultation simple à une demande avec filtre, date ou
nombre précis ; vérifier le plan, les paramètres et la réponse finale en OFF/ON.
L'usage dispose du même diagnostic, des mêmes registres de dépenses et du même
contrôle de quotas que les autres décisions natives.

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
codes restent dans « Détails techniques ».

L'événement structuré `chat_delivery_completed` mesure, côté serveur et avec une
horloge monotone, le délai avant le premier texte non vide et l'émission du `done`
final. Il inclut donc l'attente des tâches arrière-plan et la comptabilisation
finale, contrairement à la seule durée du graphe. Il ne mesure pas le transport
réseau ni le premier rendu navigateur. Un statut ne compte pas comme premier
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

Le cache d'extraction des intérêts dépend du prompt effectif complet : conversation,
intérêts existants, langue, politique et repère temporel. Réutiliser seulement le
dernier message ignorerait les changements de cet état. Les messages synthétiques
de confirmation et les notifications proactives sont exclus de la conversation
de l'extracteur de boucles ouvertes. L'initiative retrouve la requête humaine
originale en appliquant la même exclusion. Le modèle natif et son évaluateur
génératif reçoivent ainsi la même preuve pertinente.

`hitl_exclusion` traite uniquement une exclusion explicitement demandée pendant
la confirmation d'une liste. Une question indépendante `reference_scope` juge
si la demande identifie sans ambiguïté les objets visés. Elle partage le même
état et la même requête native que les questions d'exclusion par objet ; ces
questions ne lisent pas les réponses les unes des autres. Une référence singulière
à un nom porté par deux messages peut produire deux exclusions très concentrées
sans identifier le message voulu : le verdict par objet ne résout pas cette portée.

Une portée claire doit satisfaire son seuil propre, et toutes les réponses par objet
doivent être valides et satisfaire le seuil inchangé du
[consommateur](../../apps/api/src/domains/agents/services/hitl/jev_item_filter.py),
sinon la liste entière revient au filtre existant. Les indices restent ceux des
objets proposés, y compris après plusieurs modifications et reprise du checkpoint.
La correspondance entre chaque aperçu et sa position dans la source est conservée
séparément, car un objet sans champs affichables peut ne pas avoir d'aperçu. Le
[contrôle d'identité](../../apps/api/src/domains/agents/nodes/for_each_preview_identity.py)
revalide cette correspondance avant la confirmation et sa consommation. Une
sélection approuvée remplace la liste à son chemin exact, y compris dans un objet
ou une liste imbriqués ; une identité non prouvée ne peut pas devenir une sélection
exécutable. Un ancien checkpoint ne peut reconstruire ses positions que depuis
une projection exacte et non ambiguë.
Une sélection par aperçus exige que les étapes concernées partagent la même source.
Des sources différentes ne peuvent pas partager un seul ensemble d'indices :
cette sélection reste refusée, y compris à la reprise d'un ancien état approuvé.
La question de portée réserve un emplacement dans le budget commun du transport ;
la capacité restante pour les objets est dérivée dans ce même consommateur.
Le panneau debug nomme cette question et conserve sa distribution avec celles des
objets, y compris lorsque la composition utilise le repli complet.
Une liste vide annule l'opération ; sinon une nouvelle confirmation humaine reste
obligatoire. La sélection JEV ne vaut jamais autorisation d'exécution. Le filtre génératif
exige lui aussi un tableau JSON : ses explications libres et booléens ne peuvent
pas devenir des indices d'exclusion. Une réponse hors contrat conserve la liste.

## Valeurs de paramètres protégés

L'usage `parameter_kind` (« Valeurs de paramètres protégés », désactivé par
défaut) complète le garde-fou sémantique des paramètres d'adresse, de lieu et
d'email ([ADR-120](../architecture/ADR-120-Semantic-Evidence-Expansion-And-Param-Guard.md),
amendement du 11 octobre 2026). La règle déterministe décide d'abord : elle ne
refuse qu'un nom de personne résolu pendant le tour. Si elle laisse passer
l'appel, JEV reçoit, pour chaque valeur distincte, la demande du tour
(`original_query`), le paramètre tel qu'il est publié (outil, nom, type
sémantique, description) et la valeur, puis répond ce qu'est la valeur. Le code
décide seul si le paramètre accepte cette nature
([`ACCEPTED_VALUE_KINDS`](../../apps/api/src/domains/agents/semantic/jev_value_kind.py)).
Une adresse physique ou une localité ne refuse qu'une valeur reconnue comme autre
chose : un nom de personne, un numéro de téléphone, une date, une adresse email, ou
un lien pour une localité. Le lieu d'un événement est un texte libre (« Visio », une
salle) : une valeur que JEV ne range dans aucune nature connue n'est pas refusée.
Un paramètre email n'accepte qu'une adresse email.

JEV peut seulement ajouter un refus. Interrupteur coupé, aucun suivi de dépense actif, demande
absente, jugement sous le seuil `parameter_kind.kind` ([jev_gates.py](../../apps/api/src/domains/llm_config/jev_gates.py)), délai, quota ou erreur :
aucun refus, l'appel se poursuit comme avant. Une valeur prouvée par un champ
canonique sélectionné n'est pas soumise, et au plus
`JEV_PARAMETER_KIND_MAX_VALUES` valeurs d'un même appel le sont. Un refus est
compté par `semantic_param_guard_blocks_total` comme ceux de la règle
déterministe, et journalisé avec la nature jugée, jamais avec la valeur.
Chaque décision rejoint le suivi du tour : son coût figure dans le compteur de la
réponse. Mesuré sur dev le 12 octobre 2026 (compte de preuve, quatre tours en
pipeline et en ReAct) : 16 décisions, 209 à 258 ms chacune, environ 0,00004 € par
décision ; un appel d'outil protégé attend donc sa décision, les valeurs d'un même
appel étant jugées en parallèle. La mesure (décision d5) et ses limites sont dans
le [bilan de qualification](JEV_SEMANTIC_QUALIFICATION.md).

## Qualification avant activation

Le [bilan des lots 4 à 8](../superpowers/plans/2026-09-29-jev-lots-4-8.md)
distingue tests, appels synthétiques réels et observations dev. Les scripts de
mesure utilisent les prompts et projections livrés. Les corpus indépendants ne
prouvent pas une absence universelle d'erreur ; les concentrations ne sont pas
des taux d'exactitude. Les écarts entre extraction JEV et extraction existante
interdisent à ce stade de supprimer les extractions automatiquement.

Avant chaque MEP, activer un seul usage sur dev, comparer des lectures OFF/ON à
contexte égal, vérifier qualité et repli dans le debug, puis valider coûts et délais
avec le rapport de parcours. L'observation des extractions ne constitue pas une
optimisation de latence.

### Relevé synthétique du 4 octobre 2026

Les appels réels autorisés sur le corpus synthétique des usages enregistrés ont
comparé les builders produit à des questions plus courtes. La variante courte
n'a pas été retenue : certaines décisions fortement concentrées régressaient sur
les comparaisons numériques réservées au code et sur une initiative dont l'état
ambigu exigeait l'évaluateur complet. Raccourcir une question ne suffit pas à
améliorer sa composition ni à établir une économie applicative.

Le contrôle de portée HITL a été calibré sur 12 cas, puis vérifié sur 24 nouveaux
cas dans six langues. Les neuf sélections utiles admises par la baseline restent
admises ; les quatre admissions incorrectes sont bloquées et aucune demande
ambiguë du holdout n'est admise. Ce résultat vient de la composition des jugements,
sans réduction du seuil par objet. Le coût natif HITL augmente de 15,3 % ; les
médianes observées sont d'environ 229 ms pour la baseline et 231 ms pour le candidat.
Une observation par état et variante, sur des données entièrement synthétiques,
ne prouve ni la précision en production ni un gain de latence de bout en bout.

Les 200 appels réussis de cette campagne ont coûté au total 0,012177060 USD,
en incluant les reprises de langue et les expériences séparées. Les gardes étaient
rejouées hors exécution : aucun e-mail ni enregistrement réel n'a été modifié.
Les previews restaient alors des qualifications diagnostiques des données canoniques ;
les observateurs continuent à laisser fonctionner leur extracteur génératif.

Le relevé agrégé de production du même jour, arrêté à 10:30:30 UTC, contient 29
appels natifs : 28 succès et une réponse invalide comptabilisée. Les trois essais
`initiative_utility` (usage retiré depuis, ADR-374) ont tous été suivis de
l'évaluateur génératif ; aucune économie d'appel génératif d'initiative n'est donc
observée dans ce relevé. Ce constat
ne transforme ni un succès natif en décision acceptée, ni un diagnostic en travail évité.
