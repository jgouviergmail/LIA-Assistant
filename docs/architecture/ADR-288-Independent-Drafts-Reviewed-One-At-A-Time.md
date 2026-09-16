# ADR-288 — Plusieurs brouillons dans un tour se relisent un par un ; un lot FOR_EACH pré-approuvé garde sa confirmation groupée

- **Statut** : Accepté
- **Date** : 2026-09-16
- **Amende** : ADR-153 (la taxonomie HITL disait ce qu'une action doit à la
  personne ; cette décision dit ce qu'un TOUR à plusieurs actions lui doit),
  ADR-276 lot 7 (un ticket rejoue « identique à ce qui a été montré →
  confirmé, sinon redemandé » — l'identité est désormais celle du brouillon à
  l'écran, jamais celle d'un lot que personne n'a vu), ADR-263 (une action est
  réclamée puis close à partir d'un résultat explicite — un brouillon annulé
  dans une suite est rapporté, jamais perdu en silence), ADR-184 (ce que le
  code impose est publié — la position dans la suite est dite), ADR-274 (une
  seule autrice de la forme : la position est une ligne du serveur, aucun
  frontal n'a à l'apprendre)
- **Périmètre** : `domains/agents/nodes/draft_sequence.py` (nouveau),
  `domains/agents/nodes/hitl_dispatch_node.py`,
  `domains/agents/nodes/for_each_hitl_prep.py` (`is_pre_approved_lot`),
  `domains/agents/nodes/task_orchestrator_node.py`,
  `domains/agents/nodes/react_nodes.py`, `domains/agents/models.py`
  (`pending_drafts_grouped`, `confirmed_drafts`),
  `domains/agents/services/draft_executor.py`,
  `domains/agents/drafts/result_renderer.py`,
  `domains/agents/services/hitl/interactions/draft_critique.py`,
  `core/i18n_hitl.py`

## Contexte

Mesuré sur Docker dev le 2026-09-16, tour `d07cc9a0` : « envoie un email à X
pour lui dire que tout va bien et un email à Y pour penser à appeler Hua
demain ». Le plan a deux étapes indépendantes, sans approbation préalable
(`requires_hitl: false`). Deux brouillons sont créés, accumulés par étape,
puis versés dans `pending_draft_critique` plus `pending_drafts_queue`
(`registry_pending_batch_drafts_added_to_state batch_size=2`). Une seule
question HITL est posée, statique, sur le premier brouillon, avec
`batch_total: 2` : la liste des deux sujets. La carte n'affiche que le
premier (le normaliseur du front ignore `batch_total` et `batch_drafts`). Le
clic « Valider » devient `hitl_dispatch_batch_draft_confirmed`, action
`confirm_batch`, et les deux e-mails partent (`success_count: 2`). Un
« Modifier » réécrit le premier seul ; le second part tel quel à la validation
suivante.

La cause est une sémantique de LOT écrite pour FOR_EACH — « When a FOR_EACH
HITL was already approved… ALL queued items are auto-confirmed too » — et
appliquée à tout tour produisant plusieurs brouillons, quel que soit leur type,
en pipeline comme en ReAct (plusieurs appels d'outil d'une même itération).
Rien ne distinguait une file venue d'un FOR_EACH que la personne avait approuvé
comme un tout d'une file venue de deux actes distincts.

Une sonde sur le générateur statique a montré le troisième défaut de la même
conception : un lot mélangé (un e-mail, un événement) est titré « Confirmation
d'envoi » et rend l'événement en « 📧 Email » sans libellé — il est invisible en
tant que tel et se crée à la validation ; le résultat final le compte ensuite
parmi les e-mails.

## Décision

1. **Le producteur déclare le mode.** L'orchestrateur et le nœud ReAct écrivent
   TOUJOURS `pending_drafts_grouped` et `confirmed_drafts` (une valeur d'un tour
   précédent ne peut pas fuir). `pending_drafts_grouped` n'est vrai que pour un
   lot pré-approuvé (`is_pre_approved_lot`) : tous les brouillons sont des
   ITEMS (`<étape>_item_<n>`) d'une étape FOR_EACH du contexte que la personne
   a approuvé dans CE tour (`plan_id`, `turn_id`), et ils partagent un type.
   Deux étapes indépendantes, un FOR_EACH que personne n'a approuvé, un intrus
   dans le lot, deux types, ou plusieurs appels ReAct : jamais un lot.

2. **Une suite se consomme un brouillon par interruption.** Sur `confirm` ou
   `cancel` avec une file non groupée, la décision rejoint `confirmed_drafts`
   (liste NEUVE, jamais mutée), le suivant devient `pending_draft_critique`,
   le compteur d'édition et la clarification repartent à zéro, et le nœud ne
   retourne PAS de `draft_action_result` : le routage existant boucle sur
   `pending_draft_critique`, chaque interruption reste dans sa propre exécution
   de nœud (doctrine replay-safe du chemin `edit`, 2026-07). Un `edit` ne touche
   que le brouillon à l'écran. Rien ne s'exécute avant la dernière réponse.

3. **La dernière réponse règle tout d'un coup** (`settle`) : un `confirm_batch`
   ordonné dont chaque entrée porte SA décision et SON type ; une annulation
   nue quand rien n'est à exécuter. Une sortie terminale (plafond d'éditions,
   erreur de modification, décision absente, verbe inconnu) annule le brouillon
   à l'écran et RAPPORTE les brouillons encore en file comme annulés, avec la
   raison — ce qui avait été confirmé avant s'exécute quand même.

4. **Le lot pré-approuvé garde son comportement** : montré entier
   (`batch_total`, `batch_drafts`), confirmé entier, annulé entier.

5. **L'exécuteur saute une entrée annulée et la compte** (`cancelled_count`,
   ligne `cancelled`, métrique `registry_drafts_executed_total{outcome=
   cancelled}`) ; `total_count` est ce qui a été TENTÉ ; un lot dont les entrées
   n'ont pas un seul type se déclare `batch`, et le rendu nomme chaque ligne par
   son propre type, l'en-tête comptant des « actions ».

6. **La position est dite, en six langues, par le serveur** : la question du
   brouillon 2 s'ouvre sur « Brouillon 2 sur 3 » au-dessus de la carte
   (`HitlMessages.get_draft_sequence_position`, lu depuis `sequence_index` /
   `sequence_total` du payload). Un brouillon seul n'en dit rien.

7. **Le ticket suit la même identité** : la pré-approbation compare le brouillon
   à l'écran (le payload d'une suite ne porte pas `batch_drafts`), donc
   l'approbation du premier le laisse passer et le second est redemandé —
   « identique à ce qui a été montré → confirmé, sinon redemandé ».

8. **Un nouveau tour commence sans brouillon en relecture**
   (`draft_sequence.draft_turn_reset`, étendu par le routeur comme
   `react_turn_reset`). L'enregistrement d'interruption expire après une
   heure, le checkpoint jamais : un brouillon encore « pendant » y était
   re-présenté par le tour actionnable suivant, et les décisions banquées
   d'une suite abandonnée auraient été exécutées par un tour ultérieur. Une
   reprise HITL ne passe jamais par le routeur, une relecture en cours n'est
   donc pas touchée.

## Conséquences

- Deux e-mails demandés dans un tour : deux cartes, deux questions, deux
  décisions ; le second se modifie ; le résultat dit « 1 envoyé, 1 annulé » si
  c'est ce qui s'est passé.
- Un FOR_EACH « supprime ces 5 e-mails » : inchangé — approbation de la liste,
  puis une confirmation groupée.
- `hitl_dispatch_node.py` a rétréci (ratchet 756 → 698) ; les règles vivent
  dans `draft_sequence.py`, testées sur le vrai graphe avec un checkpointer en
  mémoire (`test_hitl_dispatch_sequence.py`), le prédicat de lot à part
  (`test_pre_approved_lot.py`), l'exécuteur et le rendu chacun de leur côté.
- La compaction reste bloquée pendant toute la suite : `pending_draft_critique`
  est posé jusqu'à la dernière réponse.

## Ce que ce n'est pas

- Un lot FOR_EACH d'envoi montre destinataires et sujets, pas les corps
  générés : c'est le choix existant, hors de cette décision.
- Aucun changement de frontal : la carte affiche déjà le brouillon courant ; les
  champs `sequence_*` sont additifs et ignorés par les lecteurs qui ne les
  connaissent pas.
