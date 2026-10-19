# JEV — qualification sémantique et audit du transport partagé

Cette suite complète le [diagnostic numérique](../jev-probability-sum-2026-10-19/README.md).
Elle ne modifie aucun seuil de confiance, modèle, credential, interrupteur ni quota.
Les observations sont fictives ; aucune boîte email ni aucun agenda réel n'est lu.

## Cause et périmètre

Les 23 usages du [registre](../../../../apps/api/src/domains/llm_config/jev_registry.py)
utilisent le même runtime et le même transport natif. La recherche des appels et
des lecteurs de probabilités n'a trouvé aucun second contrôle de somme divergent.
Les usages Choice héritent du correctif numérique ; Noul renvoie une probabilité
unique et n'a pas de somme de distribution à valider. Aucun consommateur ne
reconstruit une confiance plus permissive.

La faiblesse sémantique était distincte. Les questions mélangeaient le sujet du
message et la preuve de sa véracité : une panne d'authentification évoquait le
phishing sans demande de secret ; une publicité pour une activité douteuse
évoquait une arnaque ; un incident majeur rapporté restait incertain faute de
corroboration extérieure. La définition de l'incident doit aussi couvrir les
opérations internes, pas seulement les services destinés aux clients.

Les deux questions email désignent maintenant explicitement leur preuve et
séparent ces frontières. Une qualification décrit le message reçu ; elle ne
certifie ni son expéditeur ni la réalité de l'incident. La sollicitation
trompeuse doit être présente pour le phishing ; l'urgence publicitaire seule
ne crée pas d'obligation. Les exercices, incidents résolus et extraits
insuffisants conservent leur traitement distinct. Les questions agenda, les
seuils d'alerte, le score et les réponses attendues restent identiques.

## Résultats natifs conservés

Le premier candidat passe sa [calibration](candidate-1-calibration.json), mais
échoue sur spam et critique en [validation](candidate-1-holdout.json). Il n'est
pas livré. Après clarification des ambiguïtés identifiées, le candidat final est
figé puis testé, sans nouvelle retouche :

| Corpus | Cas | Couverture positive | Faux labels acceptés | Verdict |
|---|---:|---:|---:|---|
| [Calibration](../../../../apps/api/tests/fixtures/jev_classification_qualified_calibration.json) | 64 | 86,5 % | 0 | Réussi |
| [Validation distincte](../../../../apps/api/tests/fixtures/jev_classification_qualified_holdout.json) | 70 | 90,6 % | 0 | Réussi |
| [Nouveaux cas adversariaux](../../../../apps/api/tests/fixtures/jev_classification_qualified_adversarial.json) | 36 | 88,9 % | 0 | Réussi |

La validation publie les six priorités critiques, les six spams et les huit
phishings attendus. Les cas adversariaux, rédigés après le gel du candidat final,
publient six critiques, six spams et six phishings attendus. Ils éprouvent aussi
les exercices sans incident réel, les avis de sécurité sans demande et les
extraits insuffisants. Toutes les classes dépassent les objectifs figés de leur
corpus. Certaines abstentions restent normales : un test réussi ne signifie pas
que chaque observation produira un badge.

Ces corpus de régression sont de taille limitée et du même auteur. Ils ne
mesurent pas la précision en population, ni une garantie de détection de fraude.
Les résultats de calibration et de validation ne sont pas présentés comme une
étude indépendante en aveugle. Les nouveaux cas n'ont pas servi à ajuster les
prompts. Une modification ultérieure impose une nouvelle qualification.

## Vérification de bout en bout et revue à froid

La [preuve du service et du cache](service-cache.json) utilise les prompts
réellement intégrés, sans substitution. Cinq observations, deux lectures
identiques, une seule écriture native ; les badges critique, spam et phishing
sont vérifiés. Le contexte assistant et l'interface gardent les mêmes types et
la même politique d'acceptation. L'empreinte des prompts invalide les anciennes
annotations en cache, sans nouveau champ d'état LangGraph ni migration.

Les [tests du contrat commun](../../../../apps/api/tests/unit/infrastructure/llm/test_jev_shared_probability_contract.py)
exécutent les 23 usages avec les formes sélection simple, lot et lot mixte
Choice/Noul, en réponse arrondie valide et réellement malformée : 138 cas,
réussis sous Windows et dans le runtime Linux DEV. Ils vérifient le transport
HTTP réel simulé, l'atomicité, le quota, l'absence de reprise et une facture
exactement, succès comme erreur. Les distributions brutes ne sont pas modifiées.

La garde du [dossier natif](../../../../apps/api/tests/unit/domains/agents/services/test_classification_native_record.py)
échoue d'abord sur les anciens prompts, puis exige l'identité de la politique
livrée, les empreintes des corpus et le recalcul des scores. Le corpus
adversarial possède aussi une empreinte figée. Les tests de publication,
annulation, coalescence, cache et précision numérique complètent cette preuve.

Le corpus adversarial conserve exactement les octets qualifiés, y compris ses
fins de ligne CRLF. Une règle Git propre à ce fichier interdit leur conversion
automatique ; aucune empreinte de rapport n'est réécrite pour s'adapter au clone.

Revue adversariale : pas de changement des permissions, de la portée des
sources, des secrets, des seuils, des préférences ou des défaillances de repli.
Les budgets de requête, tokens, lots, concurrence et délai restent appliqués
par les mêmes constructeurs, en comptant le texte exact des nouveaux prompts.
Un dépassement conserve le résultat source sans annotation inventée. Aucun
appel LLM supplémentaire par observation ni fallback génératif n'est ajouté.

## Comptabilité

La [relecture comptable de la base](accounting.json) regroupe les huit essais historiques, les cinq nouveaux
corpus et la vérification du service : **104 écritures natives, 14 synthèses,
0,025937 EUR** cumulés, sous le plafond autorisé de 0,05 EUR. Les appels sont
attribués au compte autorisé ; les interrupteurs DEV préexistants restent actifs.
Les anciens rapports restent intacts. Le runner déduit de son plafond les
factures historiques absentes de sa chaîne de reports et garde une réserve
d'arrondi ; il ne remplace jamais un ancien compteur.

Le [script de rejeu](../../../../scripts/analysis/jev_classification_replay.py)
accepte aussi `--split adversarial`. Il reste sec par défaut, réservé au DEV,
sans reprise payante automatique, avec propriétaire explicite et budget cumulé.
