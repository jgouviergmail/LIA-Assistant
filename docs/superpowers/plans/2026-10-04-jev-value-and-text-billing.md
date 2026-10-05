# JEV : valeur applicative et comptabilité des tarifs texte

Ce bilan prolonge la qualification des [lots précédents](2026-09-29-jev-lots-4-8.md)
et le [guide d'intégration](../../technical/JEV_INTEGRATION.md). Les corrections
sont locales ; les expériences ne constituent ni un déploiement ni une activation
des réglages de production. Les préférences des usages déjà intégrés sont conservées.

## Méthode et critères

Le skill TypeSafe fourni par le titulaire et les contrats officiels
[State](https://docs.typesafe.ai/concepts/state),
[Choice](https://docs.typesafe.ai/primitives/choice) et
[confidence routing](https://docs.typesafe.ai/patterns/confidence-routing)
guident les décisions : état complet pour l'objet évalué, question étroite,
choix fermés, abstention et repli. La concentration n'est pas un taux de justesse.
Les permissions, identités, calculs, dates et actions restent en code.

Les tests payants utilisent exclusivement des états synthétiques, les clés gardées
en mémoire dans l'API dev et sa configuration effective lue sans modification.
Les comparaisons génératives emploient la factory, le prompt, les rôles et le schéma
du parcours produit ; elles prennent en compte les tokens communiqués, les
lectures/écritures du cache et le tarif configuré. Aucun e-mail, événement ou
enregistrement utilisateur n'est exécuté ou modifié par ces expériences.

Les corpus de calibration et de validation indépendante sont distingués. Un appel
natif accepté évite seulement le travail explicitement placé après sa garde.
Une erreur payée et son repli sont deux dépenses. Les sommes de durées isolées
modélisent une cascade séquentielle ; elles ne mesurent pas une discussion complète,
ses recherches parallèles, la persistance, les quotas ou le navigateur.

## Deux intégrations ajoutées, désactivées par défaut

Le [registre](../../../apps/api/src/domains/llm_config/jev_registry.py) conserve le
mécanisme existant : une configuration et un interrupteur par usage, avec le circuit
général. Les nouvelles préférences restent OFF même si le circuit général et les
usages existants sont déjà ON. Une désactivation retrouve le parcours génératif
sans appel fournisseur ni quota JEV.

### Présence de références personnelles

La garde [memory presence](../../../apps/api/src/domains/agents/services/analysis/jev_memory_presence.py)
précède l'extracteur de références du
[MemoryResolver](../../../apps/api/src/domains/agents/services/analysis/memory_resolver.py).
Elle ne sélectionne ni une personne ni un souvenir : seul un verdict d'absence
accepté peut éviter cet extracteur. La recherche large des faits reste exécutée.
Relations personnelles, pronoms, lieux implicites, ambiguïté et décision incertaine
conservent l'extraction et la résolution existantes. L'identité et la facturation
proviennent du tracker actif ; les appels non liés à ce contexte restent inchangés.

La première question binaire a été rejetée : faible couverture et surcoût de
cascade. La version retenue explicite que le titulaire est connu et distingue ses
propres ressources des références personnelles à résoudre. Sur une calibration de
36 cas, elle reconnaît les 18 absences sans supprimer de résolution nécessaire.
Une version plus compacte a été rejetée sur cette calibration : seulement neuf
absences admises, malgré un appel natif moins cher.

Le corpus indépendant contient 48 nouveaux cas dans six langues, dont 24 absences
et 24 situations à préserver. Les 48 appels natifs réussissent ; 18 extractions
sont évitées, sans faux évitement sur ce corpus. Le générateur extrait une référence
incorrecte dans 13 cas ; la garde bloque sept de ces cas. Elle ne corrige pas les
autres erreurs du générateur lorsque son repli est nécessaire.

| Observation sur les mêmes 48 cas | Générateur seul | Cascade reconstruite |
| --- | ---: | ---: |
| Première passe, coût USD | 0,004065732 | 0,003584022 |
| Nouvelle passe avec cache chaud, coût USD | 0,002257596 | 0,002450262 |
| Cache chaud, médiane isolée ou somme séquentielle | 819 ms | 888 ms |
| Cache chaud, percentile 95 descriptif | 1 008 ms | 1 262 ms |

La première passe suggère une économie de 11,8 %, mais la passe chaude montre un
surcoût de 8,5 %. Le gain retenu est la fiabilité observée et le délai des cas
acceptés : médiane native de 228 ms contre 825 ms pour leur extraction générative.
Ce n'est pas une économie générale ni un gain de latence globale. Le switch OFF
permet de qualifier ce compromis sur le trafic réel avant toute activation.
La passe chaude conserve un registre par tentative ; tous ses appels ont été
observés avec une seule tentative. Les mesures antérieures ne permettent pas
d'affirmer le nombre d'éventuelles reprises internes non capturées.
Le recalcul des distributions conservées avec le transport actuel garde les
18 évitements sur 48. Il ne constitue pas une nouvelle cascade réellement appelée.

### Refus complet d'une confirmation

La garde [HITL rejection](../../../apps/api/src/domains/agents/services/hitl/jev_rejection.py)
peut reconnaître exclusivement le retrait explicite de toutes les actions en
attente. APPROVE, EDIT, REPLAN, refus partiel, condition, correction, ambiguïté et
injection reviennent au classificateur actuel. L'état proposé est photographié
avant l'appel et comparé après ; une mutation impose le repli. Le tracker actif
attribue le coût au titulaire et au run. Aucun résultat ne vaut approbation ou
exécution, et aucun paramètre d'action n'est généré.

Le corpus fixé avant les appels contient 24 cas de calibration et 24 cas
indépendants, dans six langues. Les premières admissions ont précédé le plafond
de confiance calculé à partir des probabilités. Une cascade historique admettait
cinq refus ; le transport actuel en conserve quatre sur ces mêmes distributions.
Une nouvelle cascade réellement appelée avec la politique actuelle en admet trois,
sans faux refus admis. Les trois autres refus totaux attendus passent au
classificateur existant, qui les classe correctement.

| Nouvelle passe de 24 cas, politique actuelle | Générateur seul | Cascade réellement appelée |
| --- | ---: | ---: |
| Coût USD | 0,004782876 | 0,004783662 |
| Appels génératifs évités | 0 | 3 |
| Faux refus complets observés | 0 | 0 |
| Médiane | 1 179 ms | 1 380 ms |
| Percentile 95 descriptif | 1 486 ms | 1 780 ms |

Le coût augmente de 0,0164 % : aucune économie globale n'est démontrée par cette
reprise. Les trois branches acceptées prennent une médiane native de 266 ms,
contre 1 055 ms pour les mêmes cas génératifs ; la médiane du corpus entier
augmente. Référence et cascade ne font aucune erreur sur le gold binaire :
aucun gain de précision sur la référence n'est établi. Les volumes de cache et
de sortie varient entre les passes. Cette reprise représente 69 tentatives
payées connues, pour 0,009566538 USD, en additionnant référence et cascade.

L'ancienne réduction de 13,2 % est une mesure historique, qui ne caractérise
pas la politique actuelle. Le premier registre expérimental contient
116 requêtes, pour 0,010920660 USD de coûts connus. Ce total comprend un premier
appel génératif payé dont les compteurs ont été perdus par une erreur du harness après la réponse.
Le coût de cet appel demeure inconnu ; il n'est ni inventé ni exclu silencieusement
d'un total prétendument exhaustif. Le harness a été corrigé avant les autres appels.

## Initiative : mesures et fidélité du contexte

Le relevé agrégé de production décrit dans le guide n'avait montré aucun appel
génératif d'initiative évité. Une étude supplémentaire utilise le contexte complet,
le catalogue d'outils et la politique produit sur 30 nouveaux états synthétiques
dans six langues. Le générateur effectif produit 17 initiatives et 13 réponses
vides, pour 0,014653848 USD. Aucun verdict d'absence accepté n'a supprimé une
initiative non vide dans ces expériences.

Trois questions atomiques partagées dans un batch atteignent les 12 absences
attendues, mais augmentent le coût natif de 17,4 %. Une projection JSON sans perte
réduit ce coût de 1,57 %, sans gain fonctionnel ou de latence établi. En incluant
les replis et le cache du générateur, les cascades restent plus chères que le
générateur seul : environ +6,36 % pour la baseline, +8,41 % pour les questions
atomiques et +4,83 % pour la projection JSON. Ces variantes expérimentales de
question ne sont pas retenues comme optimisation. L'interrupteur et le repli
génératif sont conservés.

Cette étude comprend 150 appels payants : 120 natifs (119 succès, une somme de
probabilités invalide comptabilisée) et 30 génératifs, pour 0,026145510 USD connus.
Les différences de format sur un seul échantillon ne démontrent pas une amélioration
de fiabilité universelle. Les observateurs et previews conservent leur rôle de
diagnostic ; ils ne deviennent pas des économies par le seul succès d'un appel.

L'incident DEV a ensuite montré une requête locale trop grande et des résumés
génératifs pouvant omettre des preuves. Le contexte natif doit transmettre les
résultats autorisés réellement récupérés, leurs relations, les erreurs du tour,
les faits de mémoire et intérêts chargés et la politique exacte. Les métadonnées
réservées aux cartes restent exclues ; elles ne sont pas rendues accessibles au
modèle. Un état non sérialisable ou réellement incomplet impose le repli, et un
état trop grand reste refusé par le plafond du transport. Le prompt du générateur
habituel conserve son format existant.

Le retrait de `meta.display` exige une enveloppe de registre identifiable ; un
sous-objet métier externe portant les mêmes clés conserve ses champs. Le dernier
delta de projection a passé 109 tests ciblés et une revue indépendante, après les
passes globales ; il ne change ni orchestration asynchrone ni facturation.

Un pilote indépendant de quatre états synthétiques, chacun avec deux à quatre
objets, a comparé cet état JSON au vrai générateur DEV. Les huit appels payés
représentent 0,003221874 USD connus. Aucun faux verdict d'absence n'est admis,
mais aucune génération n'est évitée : aucune économie ni amélioration globale
de latence n'est revendiquée. Les latences natives vont de 238 à 306 ms et celles
du générateur de 1,83 à 12,05 s, avec des conditions de cache différentes.

## Consultations existantes : travail génératif évité

Huit consultations synthétiques ont aussi été comparées avec le vrai builder du
planner, son catalogue et son schéma. Les contextes de compte, dégradation et
skills étaient explicitement vides pour éviter toute donnée réelle. La cascade
utilise l'usage existant ; aucun nouveau switch ni nouvelle optimisation n'est
ajouté pour ce parcours. Les gardes, validations et permissions restent intactes.

Les trois chemins natifs admis évitent le planner sans admission incorrecte
observée. Sur cette passe, le coût passe de 0,003282024 à 0,002374092 USD, soit
une baisse de 27,7 %. La médiane globale augmente de 1 225 à 1 309 ms ; celle des
trois décisions admises est d'environ 250 ms. Les cinq replis ont les mêmes
compteurs et coûts génératifs dans les deux passes. Un premier préfixe moins
chaud et le petit corpus interdisent une généralisation. Les 21 appels réellement
exécutés de cette étude ont un coût connu total de 0,005656116 USD.
Les plans ont été observés avant validation et sans exécution d'outil ; une
différence de requête produite n'est pas déclarée comme une erreur exécutée.
Le recalcul hors ligne des huit distributions complètes avec le transport actuel
conserve ces trois admissions. Il ne rejoue pas les factures génératives :
l'économie reste celle de la campagne historique, sans promesse de coût actuel.

## Tarifs texte : défauts corrigés et invariants

L'audit suit les tarifs horaires et jours de
[pricing_time_slots](../../../apps/api/src/domains/llm/pricing_time_slots.py),
le [calculateur DB](../../../apps/api/src/domains/llm/pricing_service.py),
le [cache](../../../apps/api/src/infrastructure/cache/pricing_cache.py) et les
consommateurs de comptabilité. Les heures configurées sont en UTC ; le fuseau
d'affichage du titulaire ne déplace pas le tarif fournisseur. Les créneaux sont
semi-ouverts : début inclus, fin exclue. Pour une plage traversant minuit, le jour
est celui où elle commence. Hors plage ou jour applicable, le prix de base reprend.

Défauts reproduits : valorisation à la fin au lieu du début d'appel, modèle exact
normalisé avant sa recherche de tarif, dépenses multi-appels repricées au dernier
modèle, génération de prix/FX relue après un rafraîchissement, et consommations
entièrement cachées omises par une garde. Les corrections conservent le modèle,
l'instant UTC de début, les compteurs et le prix/FX de chaque tentative avant de
les agréger. Un prix de cache absent reprend le prix d'entrée ; un zéro explicite
reste gratuit. La même règle s'applique aux overrides de créneau.

Les données internes de
[LLMBillingRecord](../../../apps/api/src/core/llm_usage.py) ne sont pas exposées par
les DTO de présentation. Le ledger garde chaque consommation avec son instant
réel d'appel, sans repricer une synthèse différée ou une reprise au tarif courant.
Les réponses payées connues restent à comptabiliser si une validation structurée
échoue ou si l'opération est annulée ; les erreurs sans compteurs ne créent pas
de coût imaginaire. Un callback d'erreur de streaming qui porte un usage fournisseur
explicite conserve cette tentative au statut d'erreur ; les notifications répétées
et la fin tardive du même appel ne la refacturent pas. Les chemins JEV conservent
leur propre attribution.

La comparaison en lecture seule du cache et du calculateur DB sur les trois
tarifs dev à créneaux couvre chaque minute d'une semaine UTC : 30 240 comparaisons,
aucun écart. Les régressions couvrent en plus bornes exactes, passage de minuit,
week-end, changement d'heure, modèles versionnés, cache seul, rafraîchissement
prix/FX et plusieurs tentatives. Les résultats des tests finaux sont ajoutés au
rapport de livraison après gel des sources ; cette lecture des tarifs dev ne
modifie aucun tarif de production et n'établit pas une facture fournisseur.

## Analyse des essais DEV : décision, preuve et couverture

Une lecture des diagnostics DEV a rapproché quatre tours et 24 tentatives natives,
dont 23 réponses valides et un refus local de taille. Pour la question d'identité
du frère, la décision `preserve` conserve le résolveur habituel. Le tableau vide
de l'observateur mémoire est la proposition du générateur de **nouvelles écritures**,
pas le résultat de recherche des souvenirs existants. Cette observation ne suffit
pas à prouver la qualité de la réponse finale d'identité.

Pour la recherche médicale, le preview n'évaluait que 14 des 75 candidats et aucun
des titres évalués ne portait le lexique médical du cas signalé. Les 14 décisions
étaient appliquées comme `unknown` ; les autres objets restaient aussi conservés.
Le LLM final a retenu quatre objets. Ce cas démontre une couverture partielle,
sans démontrer un mauvais classement natif des quatre rendez-vous non évalués.
Un compteur de sélection finale du LLM ne décrit pas la sélection JEV.

La projection historique était partagée avec des règles de résumé vocal : elle
supprimait notamment `labelIds` / `label_ids`, où les connecteurs normalisent les
statuts de courrier. Deux courriers différant seulement par leur statut pouvaient
alors devenir des preuves identiques. Les preuves de filtrage doivent conserver
les booléens, valeurs nulles, listes et relations JSON, sans identifiants de
transport ou permission déduite d'un contenu externe.

Les comparaisons temporelles du calendrier appartiennent au
[helper déterministe](../../../apps/api/src/domains/agents/display/jev_collection_time.py).
Une opération capture son instant de référence et son fuseau. Une date de journée
entière est comparée en date civile, avec cette granularité explicitement publiée ;
une heure sans offset exige son fuseau source. Les heures ambiguës ou inexistantes
au changement d'heure restent inconnues. Ces faits ne prouvent pas une borne de
recherche qui n'a pas été transmise, et ne remplacent pas une contrainte plus précise.

Le client plafonne désormais toutes les confiances Choice selon la distribution
reçue, sans arrondir une valeur inférieure à un seuil pour la faire accepter.
Les campagnes antérieures ci-dessus ont précédé ce durcissement : leurs admissions
et économies ne constituent pas automatiquement des mesures de la politique
actuelle. Un succès de transport et une concentration élevée ne démontrent ni la
couverture du contexte ni la justesse d'une composition.

La qualification conserve maintenant des preuves JSON typées et un instantané
profond pris avant l'appel. Une modification concurrente ne peut plus juxtaposer
un ancien verdict et un nouveau contenu. Les questions indépendantes parcourent
les candidats par lots bornés, avec le même instantané de configuration et un
compteur global de couverture ; les inconnus évalués et les objets non soumis
sont distingués. Les résultats canoniques et le contexte du LLM final restent
intacts. Ce travail diagnostique supplémentaire est payant.

La campagne collections représente 114 appels natifs, dont 112 réponses valides,
pour 0,014905968 USD, erreurs payées incluses. Un complément indépendant de
47 objets améliore les choix bruts de 39 à 43 avec la question ciblée, sans
fausse admission ; aucune de ses douze correspondances médicales positives ne
franchit toutefois le seuil inchangé. Le prototype Noul à deux propositions
n'admet aucun verdict et n'est pas intégré.
Son seuil de probabilité 0,975 correspond à une concentration Choice binaire
de 0,95 ; il n'est pas équivalent au Choice produit à trois options, et utilise
deux questions par objet. Cette différence limite la comparaison directe.

La dernière reproduction avec la question adoptée soumet les 75 candidats en
six lots : 856,66 ms et 0,001884624 USD. Trois des quatre rendez-vous médicaux
sont admis ; le quatrième reste inconnu. Les trois contre-exemples sociaux ou
commerciaux sont correctement exclus. Par rapport au même JSON avec l'ancienne
question, cette seule mesure baisse le coût natif de 8,0 % et sa durée de 21,4 %.
Elle n'établit ni une économie de synthèse ni une amélioration générale de rappel,
et ne remplace pas une distribution de mesures répétées.

Le panneau debug distingue désormais la décision native de la proposition du
générateur d'extraction, puis de l'action appliquée. Un tableau mémoire vide
signifie absence de nouvelles écritures proposées ; les anciennes traces sans
couverture affichent cette donnée comme indisponible, sans extrapolation depuis
l'aperçu de contexte limité en taille.

## Critère d'activation

Les nouvelles intégrations restent OFF. Une activation future doit mesurer sur dev
le nombre de décisions acceptées, les replis, leur qualité, chaque coût payé et
la durée du parcours complet, avec les mêmes modèles et conditions de cache.
Un avantage sur un sous-ensemble n'est pas présenté comme un gain général. Les
comptes, sources et préférences de production ne sont pas modifiés par cet audit.
