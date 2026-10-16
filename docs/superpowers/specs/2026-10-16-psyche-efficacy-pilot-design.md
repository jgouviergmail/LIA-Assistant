# Auto-efficacité de LIA : analyse et architecture proposée

**Statut : pilote autorisé le 16 octobre 2026.** Périmètre de cette implémentation : sept domaines, preuves privées, feedback séparé, et trois influences bornées (vérification pertinente, clarification, limites explicites) sur les échanges pipeline/ReAct. Les autres canaux restent explicitement hors collecte tant que leur identité/preuve n’est pas qualifiée. Aucun gain réel n’est considéré acquis avant comparaison OFF/ON. Étude du 16 octobre 2026, sur le worktree codex/ui-accueil. Elle porte sur les sept domaines d’auto-efficacité et leur influence pendant les échanges ; elle ne redéfinit ni les traits OCEAN ni le moteur émotionnel.

## 1. Recommandation

Rendre opérationnelle une boucle **objectif demandé → preuves finales → expérience privée par domaine → stratégie de travail adaptée → résultat observable**. Le score doit aider LIA à choisir une vérification pertinente, à préciser une hypothèse ou à éviter une demande de clarification inutile. Modifier seulement ses adjectifs de confiance ne suffirait pas.

La meilleure base est déjà présente dans LIA : analyse structurée de la demande, couverture des résultats demandés, registres d’exécution, retours utilisateur, identité du tour et contraintes de budgets. Il faut relier ces contrats, sans créer un nouvel agent juge exécuté à chaque échange.

Deux dimensions doivent rester distinctes : **ce qui a été vérifié/accompli** et **ce que l’utilisateur a trouvé utile**. Un pouce positif n’établit pas la vérité d’une réponse ; un pouce négatif sur un refus légitime n’établit pas une incompétence. Je déconseille une moyenne de ces deux dimensions présentée comme un taux de compétence.

« Pleinement opérationnel » signifie que les sept domaines savent recevoir un signal approprié, conserver sa provenance et produire un effet utile lorsque le contexte le justifie. Cela ne signifie pas que les sept domaines disposeront de preuves dès l’installation. Le soutien émotionnel, le social et la créativité comportent notamment une appréciation subjective qui doit être nommée.

## 2. Constat initial vérifié avant le pilote

| Constat | Conséquence | Source |
|---|---|---|
| Sept domaines initialisés, mais mise à jour uniquement d’emotional_support à partir de l’auto-évaluation générale | Une réussite technique peut alimenter le mauvais domaine | [constants.py](../../../apps/api/src/domains/psyche/constants.py), [service.py](../../../apps/api/src/domains/psyche/service.py) |
| Le prompt de qualité limite Q lorsque la valence utilisateur est négative, même si la réponse est techniquement correcte | Le signal mélange expérience émotionnelle et réussite technique | [psyche_self_report_instruction.txt](../../../apps/api/src/domains/agents/prompts/v1/psyche_self_report_instruction.txt) |
| Avec l’initialisation actuelle, une première réussite donne 66,67 %, un premier échec 33,33 % | Un seul échange franchit les seuils force/faiblesse | [calcul](../../../apps/api/src/domains/psyche/engine.py), simulation de caractérisation (66,67 % / 33,33 %) |
| Le poids plafonné reste à 10 dans la simulation après 8 comme après 100 réussites | Ce poids n’est ni le nombre de preuves ni une incertitude calibrée | Même simulation, paramètre prior_weight=5 pour le probe |
| La classification force/faiblesse ne consulte que le score | Une preuve et cent preuves peuvent être traitées de la même façon | [engine.py](../../../apps/api/src/domains/psyche/engine.py) |
| Le format principal n’injecte que les faiblesses et les omet dans son chemin PAD presque neutre | La prudence dépend accidentellement de l’humeur ; les forces n’y ont pas d’effet direct | [engine.py](../../../apps/api/src/domains/psyche/engine.py), [confidence](../../../apps/api/src/domains/psyche/engine.py) |
| L’injection se trouve dans la préparation de la réponse finale | Le planificateur et les décisions de la boucle ReAct ne sont pas guidés par ces scores | [response_context.py](../../../apps/api/src/domains/agents/services/response_context.py) |
| Le run_id de la tâche de fond n’est pas une clé de déduplication de l’écriture ; lecture puis remplacement JSONB | Risques de replay et de mises à jour concurrentes perdues à qualifier sur PostgreSQL | [background](../../../apps/api/src/domains/psyche/service.py), [repository](../../../apps/api/src/domains/psyche/repository.py) |
| L’historique Psyché n’enregistre pas ces contributions | Une migration ne peut pas reconstruire honnêtement les anciennes preuves | [snapshot](../../../apps/api/src/domains/psyche/service.py) |

Les risques de concurrence sont établis par l’inspection des garanties disponibles ; cette étude ne prétend pas avoir reproduit une perte de mise à jour en base réelle.

## 3. Trois options comparées

| Option | Avantage | Limite | Avis |
|---|---|---|---|
| Distribuer l’auto-évaluation actuelle aux sept domaines et enrichir les prompts | Modification courte | Auto-récompense, mauvais domaine, absence de preuve et influence essentiellement verbale | Écarter |
| Preuves existantes + feedback propriétaire + profil privé + politique bornée | Traçable, exploite les contrats présents, aucun nouveau juge systématique | Nécessite une persistance fiable et une attribution mieux définie | **Recommandée** |
| Évaluateur LLM et optimisation automatique généralisée | Peut explorer des stratégies plus riches | Coûts, latence, biais du juge, contrôle et qualification plus lourds | Réserver à une expérimentation séparée |

Les travaux sur l’auto-évaluation montrent qu’elle peut fournir un signal utile, mais que sa calibration dépend des tâches et du protocole. Ils ne valident pas les pourcentages actuels de LIA. Notre choix de preuves indépendantes est une décision de conception, non une garantie tirée de ces publications : [Kadavath et al.](https://arxiv.org/abs/2207.05221), [Lin et al.](https://arxiv.org/abs/2205.14334).

## 4. Attribution et utilité des sept domaines

| Domaine | Signal pertinent | Influence utile proposée |
|---|---|---|
| Planification | Contraintes explicites et objectifs effectivement couverts ; retour sur l’utilité du plan | Décomposer si nécessaire, vérifier les dépendances et les contraintes oubliées |
| Information | Sources exploitables, date demandée, correspondance entre résultat et demande ; correction explicite | Contre-vérifier une affirmation incertaine ou signaler précisément ce qui manque |
| Soutien émotionnel | Retour explicite sur l’aide ressentie ; auto-évaluation relationnelle conservée séparément | Reformuler avec tact, poser une question utile si la demande est ambiguë, éviter les inférences abusives sur la personne |
| Créativité | Livraison du contenu demandé ; préférence ou appréciation explicite du propriétaire | Clarifier un critère créatif si nécessaire ; proposer des variantes seulement si cela sert la demande |
| Technique | Tests/calculs réellement exécutés avec outils autorisés, contraintes vérifiées, corrections | Tester l’hypothèse importante lorsque le mode et les outils le permettent ; nommer les limites non testées |
| Social | Retour sur le ton et la pertinence du brouillon ; destinataire vérifié séparément | Clarifier l’intention sensible, proposer un brouillon adapté ; un envoi réussi ne prouve pas la qualité sociale |
| Organisation | Dates/fuseaux, doublons, éléments créés ou modifiés et confirmations d’exécution | Vérifier les paramètres qui ont posé problème ; distinguer préparation et action accomplie |

Les domaines cognitifs ne sont pas ceux des connecteurs : lire un calendrier peut relever de l’information ; construire un programme de la planification ; créer les événements de l’organisation. Lire une fiche contact ne prouve pas une compétence sociale.

Réutiliser user_goal, immediate_intent, les domaines et les GoalRequirement. Les intentions actuelles ne distinguent pas assez la créativité et le soutien émotionnel. Si nécessaire, ajouter un petit champ de capacités concernées à l’analyse structurée déjà exécutée, avec vocabulaire fermé, cardinalité bornée et ancrage dans la demande. Aucun classificateur supplémentaire par défaut, aucun classement par mots-clés multilingues. Une attribution inconnue reste valide.

Limiter l’attribution d’un objectif à un domaine principal et éventuellement un second domaine réellement justifié. Ne pas diffuser un succès à tous les domaines du tour. Un pouce global sur un épisode multidomaine reste un retour global : il ne permet pas à lui seul de condamner chaque compétence séparément.

Sources : [QueryIntelligence](../../../apps/api/src/domains/agents/analysis/query_intelligence.py), [objectifs ancrés](../../../apps/api/src/domains/agents/analysis/requested_outcomes.py), [registre des domaines](../../../apps/api/src/domains/agents/registry/domain_taxonomy.py).

## 5. Contrat de preuve et calcul

### Nature des observations

Un résultat observé et un feedback restent deux canaux de preuve, jamais deux interfaces web/voix dans la clé de déduplication.

- **Résultat vérifié** : exigences effectivement satisfaites, échecs attribuables, parties vérifiées et limites. Ne jamais lire un HTTP 200 ou un booléen générique d’outil comme une exactitude métier.
- **Utilité exprimée** : 👍/👎 authentifié, lié au message du propriétaire. Une correction renseignée apporte du contexte ; le silence n’est pas un avis positif. Pour l’efficacité, le feedback doit viser le résultat terminal canonique de l’épisode. Une question HITL, une clarification, une carte de session, une notification ou une réponse provisoire n’évalue pas automatiquement la tâche finale ; son utilité éventuelle reste distincte. Plusieurs messages assistant du même run ne créent pas plusieurs jugements de compétence.
- **Auto-évaluation** : utile au moteur relationnel, mais non utilisée seule pour augmenter une compétence ni pour valider la vérité d’une réponse.

Conserver les verdicts success/failure/partial/unknown/excluded avec raison typée. Réutiliser la couverture finale après récupération : un premier échec puis une récupération correcte forment une expérience logique, pas deux apprentissages opposés. Un résultat partiel ne vaut pas automatiquement 0,5 : exploiter seulement ses sous-objectifs quantifiables, sinon conserver le statut partiel sans inventer une précision numérique.

Attente de confirmation, refus humain, expiration HITL, quota, connecteur absent, indisponibilité fournisseur et résultat opaque ne sont pas des échecs cognitifs. Un paramètre inventé par LIA peut constituer un échec attribuable ; une donnée que l’utilisateur n’a pas fournie appelle éventuellement une clarification. Une recherche vide peut être un résultat correct. Une limite annoncée honnêtement ne doit pas être pénalisée comme une fausse réussite.

La couverture d’une contrainte prouve cette contrainte, pas toute la vérité du texte généré. Pour les questions sans outil ni oracle, le résultat factuel peut rester inconnu tandis que l’utilité reçoit un vrai retour humain.

### Projection par domaine

Conserver séparément les agrégats de résultats vérifiés et de retours utiles, avec nombre d’épisodes distincts, quantité de preuves, date de dernière observation, contexte de configuration et statut non évalué/en apprentissage/étayé. Éviter une nouvelle fonction de style différente à chaque pourcentage.

Le score actuel lissé peut être remplacé par des statistiques explicables sur une fenêtre bornée, avec lissage initial explicite ; ne pas transformer une fréquence observée en probabilité universelle d’avoir raison. Le choix du lissage, du minimum de preuves et de l’hystérésis doit être qualifié sur le corpus. Condition de livraison ferme : un seul échange ne suffit plus à attribuer durablement une force/faiblesse. Aucun seuil expérimental n’est présenté ici comme validé.

Les faits du tour courant dominent toujours l’historique : même une longue série de réussites ne rend pas valide un résultat absent ou contradictoire.

Sources : [couverture](../../../apps/api/src/domains/agents/services/outcome_evidence.py), [compaction sans charge privée](../../../apps/api/src/domains/agents/services/outcome_evidence.py), [convention technique insuffisante](../../../apps/api/src/core/tool_outcome.py), [feedback propriétaire](../../../apps/api/src/domains/conversations/response_feedback.py).

## 6. Architecture et points d’intégration

~~~mermaid
flowchart TD
    A[Demande et analyse existante] --> B[Capacités pertinentes et profil privé]
    B --> C[Politique de travail bornée]
    C --> D[Planificateur ou boucle ReAct]
    D --> E[Résultat final et preuves de couverture]
    E --> F[Réponse et archivage]
    F --> G[Contribution dédupliquée]
    H[Retour explicite du propriétaire] --> G
    G --> I[Deux axes conservés séparément]
    I --> B
    J[Permissions, HITL et budgets existants] --> C
    J --> D
~~~

1. **Après l’analyse, avant le travail** : lire les domaines pertinents dans un accès indexé ; figer une projection compacte dans query_intelligence. Étendre sa déclaration, sérialisation et reconstruction. Éviter une nouvelle clé d’état écrite occasionnellement qui serait héritée d’un ancien tour. Le checkpoint conserve uniquement la politique dérivée minimale, les domaines, la génération et une borne de validité ; il ne duplique pas les scores privés ni les preuves brutes. À la reprise HITL/différée, contrôler génération et validité avant réemploi. Reset, purge ou expiration rendent l’ancienne influence inactive : recalculer depuis une source actuelle admissible ou revenir à une politique neutre, sans recréer un état.
2. **Politique commune** : une fonction pure décide quoi vérifier ou préciser, à partir des preuves actuelles, de leur couverture, de l’expérience pertinente et du budget. Le planificateur, chaque appel ReAct et la synthèse finale lisent la même politique. L’humeur/PAD ne masque pas cette politique.
3. **Influence attestable** : un contrôle nécessaire doit être démontré par une observation existante. Une phrase du modèle affirmant avoir vérifié ne suffit pas. Réutiliser les mécanismes de couverture/récupération ; ne pas ajouter une seconde boucle de rattrapage.
4. **Après le résultat terminal** : capturer les données fraîches du streaming et de l’archivage, pas le checkpoint local potentiellement ancien. Les signaux d’apprentissage sont dérivés de ce résultat unique.
5. **Feedback** : ajouter un consommateur par port injecté au démarrage, comme le couplage aux journaux. Aucun cycle entre conversations et Psyché. Ne pas lier ce mécanisme à l’activation optionnelle des analytics produit.

Points de code : [routeur](../../../apps/api/src/domains/agents/nodes/router_node_v3.py), [sérialisation](../../../apps/api/src/domains/agents/analysis/query_intelligence.py), [reconstruction](../../../apps/api/src/domains/agents/analysis/query_intelligence_helpers.py), [planificateur](../../../apps/api/src/domains/agents/services/smart_planner_service.py), [setup ReAct](../../../apps/api/src/domains/agents/nodes/react_context.py), [terminal](../../../apps/api/src/domains/agents/api/service.py).

### Effet utile, sans surcoût systématique

Une expérience faible ou absente ne déclenche pas automatiquement un appel supplémentaire. Une vérification est proposée seulement s’il existe une lacune identifiable, une source pertinente et un budget disponible. Pour une demande émotionnelle ou créative, une vérification factuelle sans rapport serait contre-productive.

Une expérience étayée peut rendre la réponse plus directe lorsque les faits sont établis. Les agrégats par domaine ne suffisent pas à identifier une stratégie ou une présentation précise appréciée : cette V1 ne prétend donc pas apprendre ces préférences sans preuve attribuable. Elle ne supprime aucune vérification obligatoire. Une expérience de faible utilité peut inciter à clarifier le besoin ou la présentation, sans modifier arbitrairement les conclusions factuelles.

Aucun changement automatique de modèle, aucune extension d’outils ou de permissions, aucun contournement HITL, aucune augmentation automatique de quota. Ne pas relier le score à un gain de fierté ou d’attachement : ce couplage a déjà été retiré du moteur.

## 7. Persistance, confidentialité et reprise

Une petite table PostgreSQL de contributions actives privées et une projection par propriétaire suffisent ; pas de nouvel entrepôt ni de Redis nécessaire en V1. La table est justifiée par la déduplication, les corrections de feedback et l’explication du profil ; le JSONB actuel seul ne les apporte pas.

- Définir un épisode comme le travail logique d’un tour, indépendant des segments SSE et reprises HITL. Réutiliser son run_id ; pour une voix directe dont le run_id couvre toute une session, exiger une identité stable de tour/segment archivé avant de compter séparément les échanges.
- Unicité sur propriétaire, génération d’apprentissage, épisode, domaine et nature de preuve. Les versions de politique/configuration sont des métadonnées, pas des clés permettant de compter de nouveau le même épisode.
- Conserver un état actif par contribution : 👍→👎→👍 remplace la contribution, sans empiler trois récompenses. Une preuve finale remplace le provisoire. Le verrou propriétaire est acquis avant lecture ; insertion/remplacement et projection sont dans la même transaction.
- La génération est capturée au départ et contrôlée après verrouillage. Reset complet : nouvelle génération ; doux : expérience conservée ; purge : les tâches anciennes sont refusées et ne recréent pas l’état. Une nouvelle interaction explicite peut créer un nouvel état.
- Fenêtre temporelle et quantité physique bornées. Hypothèses de départ à mesurer : 90 jours, au plus 500 épisodes actifs par propriétaire et au plus deux domaines consolidés par épisode en V1. Les autres objectifs restent dans la couverture métier, sans diffusion automatique de leur issue à tous les scores. Avec deux natures de preuve, plafonner ainsi les contributions actives à 2 000, sans empiler les versions, et borner également les index/métadonnées. L’expiration cesse d’influencer la lecture même si le ménage différé n’est pas encore passé.
- L’âge et l’ordre d’éviction sont fondés sur la date terminale canonique et immuable de l’épisode, jamais sur sa réingestion. Un retour ou une preuve tardive peut enrichir un épisode encore admissible, sans renouveler son ancienneté. Un retour sur un ancien message reste enregistré sur ce message, mais ne recrée pas une contribution expirée.
- Après une éviction par quantité, garder dans les métadonnées de génération une borne d’éligibilité monotone fondée sur le couple date terminale/identifiant canonique du dernier épisode évincé. Un finaliseur rejoué sous cette borne ne réinsère pas sa contribution, même si sa date est encore dans les 90 jours. Les contributions antérieures encore inconnues sont alors explicitement hors fenêtre quantitative. Cela évite des tombstones par épisode sans limite de rétention. Si une contribution est évincée, son influence quitte aussi les agrégats.
- La suppression de l’historique de conversation conserve l’apprentissage selon la doctrine USER_LEARNING ; « tout oublier », purge Psyché et suppression de compte ont leurs périmètres explicites. Ne pas introduire un FK de message qui effacerait silencieusement le profil à chaque reset conversation. Ne conserver aucun texte brut, adresse, destinataire, payload d’outil ou commentaire privé dans les agrégats.
- Propriétaire privé de bout en bout. Les retours d’un pair ne notent jamais directement le profil du destinataire. Les labels de métriques sont fermés, sans identifiant utilisateur ni texte libre.

Migration : les anciens score/weight peuvent rester identifiés comme hérités pour compatibilité, mais ne deviennent pas des preuves V2. Le profil commence sans évaluation crédible, pas avec des observations reconstruites artificiellement. Le changement de personnalité ne réinitialise pas l’expérience. Les changements matériels de modèle/contrat conservent la provenance et rendent explicite l’applicabilité des anciennes observations ; ils ne sont pas assimilés silencieusement à la même calibration.

## 8. Cohérence des canaux et de l’auto-amélioration existante

| Surface | Proposition |
|---|---|
| Chat web et messageries via le graphe | Première surface qualifiée : pipeline et ReAct reçoivent la même politique |
| Voix déléguée au graphe | Réutiliser l’épisode du graphe, sans compter sa restitution orale une seconde fois |
| Voix directe | Adaptateur nécessaire pour des tours stables et leurs preuves ; ne pas prendre la fin normale d’un appel pour une réussite |
| Routines | Les résultats techniques prouvés peuvent contribuer après qualification ; aucune augmentation de relation/satisfaction produite par les propres automatismes de LIA |
| Messages peer et notifications | Pas de note de compétence issue des appréciations d’un tiers ; génération et livraison seules ne prouvent pas l’aide apportée |
| Point de LIA et récit d’identité | Exposer la projection validée pour expliquer les domaines réellement étayés, sans inventer de niveau ni en faire une instruction de décision |

L’étude d’auto-amélioration du 14 octobre réserve sa V1 aux patterns pipeline read-only qualifiés. Elle n’est pas implémentée comme ledger commun dans ce snapshot. Partager le futur contrat de résultat terminal et la définition des verdicts, mais conserver **la calibration personnelle** séparée **des suggestions globales de plans**. L’extension à ReAct, mutations ou canaux autonomes doit être une décision de périmètre explicite, avec ses propres preuves ; cette étude ne l’active pas.

Ne pas réutiliser directement PlanPatternLearner : ses clés et signaux ne portent pas la même identité ni le même sens. Ne pas brancher EvaluationPipeline sur chaque échange : son simple nom ne garantit ni appel de production, ni calibration, ni coût approprié. Ne pas copier les compteurs journal « premier verdict seulement » pour une expérience qui doit accepter les corrections.

Référence d’étude existante : spécification du 14 octobre, document d’étude hors dépôt consulté pendant cette analyse.

## 9. Affichage et coûts

Garder les sept rubriques, mais remplacer la fausse précision par « non évalué », « en apprentissage » ou un niveau étayé accompagné de son nombre de preuves et de sa date. Dans le détail, distinguer résultats observés et retours utiles. Afficher la méthode du chiffre éventuel : un pourcentage de retours favorables n’est pas un pourcentage d’exactitude. Aucun graphe historique inventé depuis les scores absents des anciens snapshots.

Projection lecture seule fournie par l’API Psyché, accrochée au hook existant et à ses protections de compte. Pas d’enregistrement manuel ni de requête par domaine ; rendu repliable et lisible sur mobile, six langues et clavier conservés.

Pas de nouveau juge LLM par défaut. Réutiliser l’analyse structurée et les signaux disponibles. Cible de conception à mesurer : une lecture indexée du profil par tour pertinent, une écriture/consolidation bornée après réponse, contexte utile plafonné autour de 120 tokens pour les seuls domaines concernés. Ce plafond n’est pas un coût déjà mesuré. Toute vérification ajoutée consomme les limites réelles du tour ; en cas de quota insuffisant, dire ce qui reste non vérifié sans sanctionner la compétence.

Conserver les métadonnées de configuration effective et l’attribution des dépenses existantes. Le profil ne choisit pas un LLM plus cher ni un outil non autorisé. Un éventuel juge hors ligne reste dans une campagne d’évaluation distincte, budgétée et non présentée comme gratuite.

## 10. Tests et preuves de bénéfice avant activation

| Famille | Vérifications indispensables |
|---|---|
| Attribution | Sept domaines, cas ambigus et inconnus, six langues, objectifs multiples, calendrier lu vs programme construit vs événements créés |
| Qualité des preuves | Succès outil sans résultat utilisable, résultat vide valide, sortie opaque, contrainte temporelle incorrecte, livraison sans qualité créative prouvée |
| Influence | Même expérience en humeur neutre/positive/négative ; même politique pipeline/ReAct ; compte neuf neutre ; lacune actuelle prioritaire sur historique flatteur |
| Limites | Pas de contrôle inutile, pas de seconde boucle de récupération, aucun dépassement de budget, outil absent du mode, permissions et HITL inchangés |
| Mise à jour | Premier résultat puis récupération, partiel quantifié/non quantifié, quota/panne/refus neutres, aucune auto-récompense par le texte du modèle |
| Feedback | 👍→👎→👍, doublon, feedback avant consolidation, commentaire visant le ton, refus légitime noté négativement, feedback ancien, message étranger, plusieurs messages assistant/HITL/provisoires dans le même épisode |
| PostgreSQL réel | Deux contributeurs simultanés, replay, rollback, crash entre contribution et projection, compte supprimé, JSONB relu, expiration/éviction puis finaliseur rejoué sans résurrection |
| Gestion | Reset doux/complet/purge, tâche ancienne terminant après reset, projection périmée reprise après HITL, désactivation collecte/influence, données legacy sans preuves fabriquées |
| Canaux | Reprises HITL/SSE, délégation voix sans doublon, tours de voix directe, routine automatique, pair non autorisé |
| UX | Champs inconnus/anciens, absence de preuves, preuves contradictoires, compte changé, six langues, clavier et mobile |

Comparer OFF/ON sur un corpus figé avec même configuration et mêmes oracles, puis sur un ensemble tenu à part. Mesurer erreurs factuelles, exigences réellement satisfaites, tours de clarification inutiles, couverture des vérifications pertinentes, coût/tokens, latence et appréciation humaine séparée. Lorsque les modèles sont stochastiques, répéter et alterner l’ordre ; un exemple spectaculaire ne prouve pas une amélioration.

Inclure des scénarios adversariaux : faux succès annoncé, utilisateur qui pousse à l’assurance, 👍 sur une hallucination, 👎 sur une sécurité justifiée, instructions malveillantes dans un résultat externe, rafale de feedback et configurations de modèle différentes.

Activation proposée : collecte et influence désactivables séparément ; qualification en observation, puis influence limitée. Le repli fonctionnel par interrupteur, dans le code V2, produit une politique neutre sans réactiver l’ancien proxy émotionnel. Un retour binaire à une image antérieure reste une opération distincte : il faut alors empêcher explicitement la réactivation de son ancien writer, et ne pas présumer la compatibilité de ses lectures. Aucune publication automatique de prompts, aucun déploiement production dans ce mandat.

## 11. Découpage et effort indicatif

| Lot proposé | Contenu | Ordre de grandeur |
|---|---|---|
| 1 — Preuves et persistance | Contrat terminal, observations privées, correction de feedback, atomicité/génération et migration | 6–10 h |
| 2 — Attribution et influence | Sept domaines, politique commune pipeline/ReAct/synthèse, budgets et faits du tour | 4–7 h |
| 3 — Lecture et interface | API/hook, présentation honnête, détails et six langues | 3–5 h |
| 4 — Qualification | Corpus, intégration PostgreSQL, comparaison OFF/ON, responsive et revue à froid | 5–8 h |

**Total indicatif : 18–30 h pour une V1 complète sur les échanges passant par le graphe**, incluant tests et corrections. Qualifier toutes les surfaces voix directe/routines/peer ajoute environ 6–12 h selon leurs preuves et identités disponibles. Ce sont des estimations d’ingénierie, pas des temps mesurés ni un engagement de livraison. Les délais de validation humaine et d’observation en usage réel sont séparés ; aucun calendrier ne garantit à lui seul que chaque domaine aura reçu assez de retours pertinents.

Ce travail constitue un lot backend distinct du rafraîchissement UI. Avant implémentation, valider notamment : les deux axes séparés, la place strictement secondaire de l’auto-évaluation, l’absence d’autonomie supplémentaire par le score, et le périmètre initial des canaux. Les constantes de fenêtre/minimum de preuves sont à qualifier, pas à copier dans le code sans essai.

## 12. Vérifications réellement réalisées pour cette étude

- Inspection du code actuel et de l’étude antérieure ; revues spécialisées en lecture seule sur les preuves, les consommateurs et la persistance, puis revue adversariale de la proposition.
- Huit tests unitaires existants ciblés : SelfEfficacy, InitializeSelfEfficacy et ConfidenceBlock ; huit réussis, aucun ignoré.
- Cinq assertions de caractérisation sur la fonction pure exacte extraite par AST : premier succès/échec, absence de mutation de l’entrée, poids plafonné, répétition sans déduplication extérieure. Rapport JSON de caractérisation conservé avec les pièces de l’analyse ; aucune nouvelle fonction de production créée.
- Aucun changement de code produit, migration, donnée, configuration ou environnement ; aucun appel modèle ni déploiement. Les futurs bénéfices et les garanties de concurrence V2 restent à démontrer par les tests proposés, ils ne sont pas acquis par cette analyse.
Plan d’implémentation : [pilote auto-efficacité](../plans/2026-10-16-psyche-efficacy-pilot.md).


## Décisions précisées pendant l’implémentation

- Les indices et leur statut nécessitent des observations de leur propre axe ; aucun poids historique n’est converti en effectif. Une couverture partielle ne reçoit aucun score arbitraire. Une répétition suffisante de couvertures partielles, dominante face aux réussites complètes, peut néanmoins justifier une vérification ciblée si une lacune actuelle existe. Les seuils du pilote sont déclarés dans les constantes Psyché.
- La génération est capturée avant l’analyse asynchrone ; la politique est revalidée à chaque appel ReAct, après reprise et avant la synthèse, sous verrou propriétaire. Le contexte de politique expire ; un feedback tardif reste possible si la réponse était admissible à son horodatage canonique et demeure dans la fenêtre du registre.
- Le vérificateur doit exister dans le catalogue et le mode courants, appartenir aux domaines de connecteurs sélectionnés et lire de vraies données. L’introspection ne constitue pas une vérification. Une clarification déjà résolue ou un objectif entièrement satisfait neutralise l’ancienne ambiguïté.
- L’empreinte immuable décrit les paramètres LLM réellement journalisés. L’expérience demeure celle de l’assistant du propriétaire à travers ses configurations ; les indices ne prétendent pas calibrer le modèle actuellement sélectionné.
- Les tours graphes ordinaires sont couverts. Aucune collecte n’est ajoutée aux routines, réponses peer ou sessions Live directes. Les métriques factuelles d’exécution ne permettent toujours pas de juger seules une création ou une relation sociale : ces domaines utilisent le retour explicite d’utilité.
- Les enrichissements sont bornés en temps et échouent de manière neutre. L’activation en développement partagé est une étape distincte des essais isolés ; aucun gain général sur les échanges réels n’est revendiqué avant comparaison sur corpus tenu à part.
