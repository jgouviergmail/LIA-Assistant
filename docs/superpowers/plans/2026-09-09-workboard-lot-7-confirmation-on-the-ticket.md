# Lot 7 — La confirmation se joue sur le ticket (ADR-276)

> **LIVRÉ le 2026-09-09** (D52–D57 de l'ADR). Trois écarts par rapport au plan,
> chacun trouvé en écrivant : (1) le flux n'émet JAMAIS de chunk
> `hitl_interrupt` — la capture lit `hitl_interrupt_metadata` +
> `hitl_interrupt_complete`, et le moteur soldait `success` un run arrêté sur
> une clarification ; (2) la sonde « question pendante » lisait le point de
> reprise LangGraph et aurait écarté tous les tickets suivants du compte après
> le premier « À confirmer » — elle lit désormais la clé Redis du chat ; (3)
> une réaffectation sans note est REFUSÉE (`workboard_answer_required`) plutôt
> que traitée comme un amendement vide. Le verrou d'empreinte vit dans
> `nodes/draft_preapproval.py` (ratchets de taille et de CC du nœud).
>
> Plan vérifié le 2026-09-09, chaque affirmation lue dans le code avant d'être
> écrite. Le lot répond à trois demandes du propriétaire : une colonne
> « À confirmer » qui n'apparaît que si une confirmation attend, une réponse
> écrite sur le ticket, et un traitement qui reprend tout seul selon la réponse.

## 1. Ce qui existe, et ce qui manque

**Aujourd'hui, un run de ticket ne rencontre jamais d'interruption HITL pour un
brouillon** : la porte des effets (`effects/gate.py`) REFUSE tout outil de
politique `draft` ou `confirm` quand la source est hors tour (`scheduled`), avant
même que le brouillon soit construit. Le modèle raconte alors son intention en
prose, le run se solde `waiting` avec le nom de l'outil refusé, et la
notification propose de « terminer dans le chat ». Ce refus a une raison
mesurée (ADR-276 amendant ADR-263) : sur le chemin des routines, une
interruption de brouillon restait sur le fil et le message suivant de la
personne était lu comme sa décision.

**Deux faits structurants, vérifiés :**

- **La conversation est 1:1 avec l'utilisateur** (`conversation.id = user_id`).
  Chaque run partage donc le fil LangGraph du chat. Une interruption laissée
  pendante détournerait le prochain message du chat ; c'est pourquoi le run
  efface la clé HITL Redis (`_clear_pending_question`). Le point de reprise
  LangGraph, lui, est écarté dès que le chat envoie une nouvelle entrée : une
  reprise « à la LangGraph » n'est donc fiable que si personne n'a parlé entre
  temps — inacceptable comme mécanisme.
- **Rien en production n'installe de contexte d'exécution hors graphe.** Le
  contexte est découvert par `get_runtime(LiaRuntimeContext)` ; seul le harnais
  de test le pose à la main, par un mécanisme interne de LangGraph. Exécuter un
  brouillon hors graphe (« rejeu direct ») créerait ce mécanisme en production
  — le piège n° 2 de la revue du lot 3, sous une autre forme.

**Ce que fait le chat, et que le lot réutilise :** un outil `confirm` dont la
confirmation manque devient un brouillon `DraftType.TOOL_CALL`
(`effects/runtime.py`, `confirmation_draft`) ; un outil `draft` construit son
brouillon ; `hitl_dispatch_node` interrompt avec
`{type: draft_critique, draft_id, draft_type, draft_content, tool_name}` ; la
personne confirme ; `response_node` exécute par `execute_draft_if_confirmed`,
sous une portée `approved=True` portant `draft_digest` — « ce qui s'exécute est
ce qui a été montré » (ADR-092). `effects/digest.py::draft_digest` est cette
empreinte, une implémentation.

## 2. Le mécanisme

**Le run DEMANDE, le ticket PORTE le brouillon, l'approbation l'exécute dans le
graphe par le chemin du chat, sous verrou d'empreinte.**

1. **La porte laisse un run de ticket demander.** Le refus hors tour ne vaut
   que pour une origine qui ne peut pas porter de brouillon (une routine). Une
   origine `workboard` (`current_origin()`) : `confirm` → le brouillon
   `TOOL_CALL` du chat ; `draft` → passage, l'outil construit le sien. La
   critique de brouillon interrompt alors, comme dans le chat.
2. **Le run capture l'interruption** au lieu de la jeter : `_one_attempt` lit
   le chunk `hitl_interrupt_metadata` (`action_requests[0]`) et le solde porte
   `pending_action = {draft_id, draft_type, draft_content, tool_name,
   question}`. La clé HITL du fil est effacée comme aujourd'hui : la personne
   répond sur le ticket.
3. **Le ticket passe en « À confirmer »** (`TicketStatus.CONFIRMING`, entre
   `waiting` et `validating`), **rendu à la personne**, `pending_action` stocké
   (colonne JSONB, migration), et un commentaire de LIA présente la
   confirmation : la question qu'elle aurait posée dans le chat, l'**aperçu
   détaillé** du brouillon (`render_detailed_preview`, le même que le chat) et
   comment répondre. La colonne n'est dessinée que si son compte est non nul.
4. **La personne répond par un commentaire et confie le ticket à LIA.** À cette
   réaffectation, le service lit les commentaires du DÉTENTEUR depuis
   `asked_at` et classe la réponse, sans appel modèle, par un lexique dans les
   six langues :
   - **accord** (« oui », « ok », « vas-y », « d'accord », « yes », « ja »…)
     → `todo` + LIA, `pending_action.approved = true` ;
   - **refus** (« non », « annule », « no », « nein »…) → `cancelled` + la
     personne, `pending_action` effacé ;
   - **tout le reste est un amendement** → `todo` + LIA, `pending_action`
     effacé, et la réponse entre dans le prochain brief comme les mots du
     détenteur — jamais ceux d'un pair, la règle de sécurité du brief tient.
   Le balayage prend ensuite le ticket → `in_progress`, comme toujours.
5. **Le rejeu, dans le graphe.** Le balayage réclame un ticket `todo` + LIA
   dont `pending_action.approved` est vrai : le brief dit « la personne a
   approuvé cette action exacte, exécute-la avec exactement ces arguments »
   (contenu cité), et `RunOrigin.approved_draft = {draft_type, digest}` est
   publié. Quand l'outil reconstruit son brouillon, `hitl_dispatch_node` compare
   `draft_digest(draft_content)` à l'empreinte approuvée AVANT d'interrompre :
   identique → `draft_action_result = confirm`, `response_node` exécute par le
   chemin du chat, avec le vrai contexte et la portée approuvée ; différent →
   interruption, capture, « À confirmer » de nouveau avec le NOUVEL aperçu.
   **Rien ne s'exécute sans surveillance qui ne soit identique à ce qui a été
   montré.** Résultat → `validating` + rendu à la personne, `pending_action`
   effacé.

**Limite énoncée :** un brouillon à contenu long (un corps de courriel) est
rarement reproduit à l'octet près par le modèle ; la personne verra alors un
second aperçu à confirmer. Le brief cite le contenu exact pour maximiser la
fidélité ; un compteur mesure les non-correspondances.

## 3. Indépendance avec le chat

**Un ou plusieurs tickets en « À confirmer » ne bloquent rien dans le chat**, par
construction : le brouillon vit sur le ticket, la clé HITL du fil est effacée,
et la reprise ne dépend d'aucun point de reprise du fil. Dans l'autre sens, une
question HITL pendante DANS LE CHAT continue de suspendre les runs de tickets
(`SKIPPED_BUSY`) : un run ne doit pas marcher sur une question que la personne
est en train de répondre. Les deux sens sont testés.

## 4. Ce que le lot touche

| Couche | Changement |
|---|---|
| vocabulaire | `TicketStatus.CONFIRMING`, `TICKET_STATUSES` front, six langues, ton, icône, garde de synchronisation |
| base | `workboard_tickets.pending_action` JSONB nullable, migration `02d23dd84146` → nouvelle tête |
| porte | refus hors tour limité aux origines sans ticket ; `RunOrigin.approved_draft` |
| run | capture de l'interruption ; solde `confirming` ; brief de rejeu ; effacement au succès |
| nœud HITL | comparaison d'empreinte avant l'interruption (`_handle_draft_critique`, CC 29 : la comparaison est une fonction pure appelée, jamais une branche ajoutée) |
| service | classification à la réaffectation, transitions, événements |
| brief | commentaires du détenteur depuis le dernier run |
| écran | colonne conditionnelle, wording, icône ; le panneau montre l'aperçu par le commentaire |
| heartbeat | `confirming` rejoint les tickets arrêtés sur la personne |
| notification | genre `CONFIRMING`, six langues, lien vers le ticket |

## 5. Plan de test

- **Porte** : une routine reste refusée ; un run de ticket obtient le brouillon
  `TOOL_CALL` pour `confirm` et le passage pour `draft` ; une origine approuvée
  avec la BONNE empreinte passe, une empreinte différente non.
- **Capture** : l'interruption remplit `pending_action` ; sans interruption,
  rien ; la clé Redis est effacée.
- **Solde** : `confirming` + rendu + commentaire contenant la question, l'aperçu
  et la consigne ; six langues.
- **Classification** : accord, refus, amendement dans les six langues ; un
  commentaire d'un PAIR est ignoré ; l'absence de commentaire vaut amendement
  vide → `todo` + LIA sans approbation (LIA redemandera).
- **Rejeu** : empreinte identique → exécution par `execute_draft_if_confirmed`
  et ligne d'effet `approved` ; empreinte différente → nouvelle confirmation ;
  compteur de non-correspondance incrémenté.
- **Indépendance** : N tickets `confirming` et un tour de chat ordinaire ; une
  question pendante dans le chat → `SKIPPED_BUSY`.
- **PostgreSQL** : la migration en rejeu, `pending_action` écrit et effacé,
  les transitions.
- **Navigateur** : la colonne absente sans ticket, présente avec un ; le
  panneau ; l'affectation à LIA depuis un ticket `confirming`.
- **Preuve runtime** en conteneur, sur le compte de dev, avec un outil
  `confirm` réel.

## 6. Ce que ce lot ne fait pas

Pas de fil LangGraph par ticket (la conversation reste 1:1). Pas d'exécution de
brouillon hors graphe. Pas de classification par modèle : un lexique, et tout
le reste est un amendement que LIA relit.
