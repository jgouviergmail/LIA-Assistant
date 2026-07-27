# ADR-164: Quels tours alimentent la mémoire, les intérêts et les journaux

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA
**Amende**: ADR-079 (journaux, auto-évaluation différée), ADR-139 (boucles ouvertes)

## Contexte

Question posée : « les échanges simples en mode chat ne sont-ils pas traités
pour la mémoire, les centres d'intérêt et les journaux ? »

L'audit du 2026-07-27 a montré que le chemin conversationnel nominal
fonctionne — `tests/agents/test_response_node.py:488` le prouvait déjà — et que
`user_msg_is_trivial` n'est pas un filtre « échange simple » : il exige ≤ 15
caractères **et** le match d'un motif d'acquiescement.

Mais **rien ne mesurait ces décisions**. Chaque saut était journalisé en `debug`
et aucun agrégat n'existait. Quatre défauts ont vécu dans cet angle mort :

**D1 — les canaux externes n'alimentaient ni les journaux ni la psyché.**
`inbound_handler` appelait `stream_chat_response` avec `user_memory_enabled`
seul ; les deux autres paramètres retombaient sur leur défaut de signature
(`False`) alors que les colonnes valent `true` en base. Une conversation
Telegram n'a jamais alimenté un journal, quoi que l'utilisateur ait activé.

**D2 — un flux HITL avec brouillon n'extrayait rien du tout.** Le tour riche
s'arrête sur `interrupt()` **avant** `response_node` ; le tour de confirmation
sortait par le chemin rapide brouillon **avant** la planification. Sur
« envoie un mail à Marie pour lui dire que je déménage à Lyon », la séquence
complète ne produisait aucune mémoire, aucun intérêt, aucune entrée de journal —
et le prompt d'extraction ciblant le *dernier* message utilisateur, aucun tour
ultérieur ne rattrapait.

**D3 — le défaut inverse.** Au refus HITL de niveau outil, un `HumanMessage`
**fabriqué** est injecté dans l'état, dont le corps est un bloc d'instructions
localisé pour le LLM de réponse. Assez long pour échapper à l'heuristique de
trivialité, il devenait la cible de l'extraction : un embedding et jusqu'à
quatre appels LLM dépensés à analyser les consignes de l'assistant, avec le
risque de les écrire dans la mémoire long terme ou le journal.

**D7 — l'heuristique s'appliquait à des entrées qui ne sont pas des messages.**
`get_or_compute_embedding` testait la trivialité de **toute** entrée, y compris
le **nom de personne** que lui passe `person_tools._fetch_person_memories`. Les
motifs livrés contiennent `fine`, `cool`, `top`, `bien`, `super`, `parfait` — des
patronymes réels. Un contact nommé Fine ou Bien perdait tous ses souvenirs, sans
message d'erreur : l'utilisateur en concluait que LIA avait oublié.

## Décision

### 1. Toute décision d'extraction est comptée

`post_response_extraction_scheduled_total{kind, outcome}` couvre les six
sous-systèmes et huit issues. Les compteurs sont posés sur les branches
**existantes** : aucune n'est ajoutée, car
`_schedule_post_response_extractions` est à CC 41 et le cliquet de complexité
est décroissant seulement. Les deux gardes disjonctives (`A or B`) sont
départagées dans un helper, pour que la métrique reste précise sans complexifier
l'appelant.

### 2. La trivialité ne gouverne que le conversationnel

`get_or_compute_embedding` exige désormais `is_conversational` en mot-clé
**obligatoire**. Un défaut silencieux est exactement ce qui a laissé juger un
nom de personne « trivial » ; quatre appelants seulement existent, chacun se
prononce. `person_tools` et le heartbeat passent `False`.

**Ordre imposé** : ce cloisonnement précède l'extension des motifs aux six
langues. L'inverse aurait aggravé D7, puisque `vale` (es), `bene` (it) et `gut`
(de) sont eux aussi des patronymes attestés — ils sont **délibérément exclus**,
avec la justification inscrite au-dessus de la table de motifs.

### 3. Les canaux forwardent les mêmes préférences que le web

Un résolveur unique (`domains/channels/preferences.py`) sert les deux points
d'entrée — route entrante et rappel HITL — qui dupliquaient la même résolution.
Cette duplication **est** la cause de D1 : quand les journaux et la psyché sont
arrivés, seul le chat web a appris à les transmettre. Les paramètres sont
obligatoires côté handler ; un défaut optionnel aurait reproduit l'omission au
prochain appelant. Fermeture par défaut : sans ligne utilisateur chargée, on
n'écrit ni journal ni psyché.

Le coût est assumé : les canaux passent par `await_run_id_tasks`, donc deux
tâches de plus sont attendues avant l'envoi de la réponse.

### 4. Le tour de confirmation d'un brouillon est un vrai tour

Le chemin rapide planifie désormais les extractions avant de retourner. Le
correctif est exact et non approximatif parce que la reprise d'un brouillon est
un `Command(resume=...)` **sans injection de message** : au chemin rapide, le
dernier message de l'état est encore la demande d'origine. Aucune logique de
sélection à inventer. `psyche_appraisal` vaut `None` (aucun appel LLM n'a eu
lieu pour s'auto-évaluer) et la réponse est la confirmation courte.

### 5. Les messages fabriqués sont marqués, jamais reconnus au texte

`additional_kwargs[SYNTHETIC_MESSAGE_KEY]` — même mécanisme que
`proactive_notification`. Le classement par correspondance de chaîne est exclu :
l'échafaudage existe en six langues. Les trois extracteurs répétaient la même
boucle de recherche du dernier message humain ; elle vit maintenant dans
`domains/shared/extraction_targets.py`, ce qui **abaisse** les trois points
chauds (mémoire 69 → 67, journal 76 → 74) au lieu de les grossir.

Seul le message de refus **enrichi** est marqué. Les deux branches de repli
injectent la réponse brute de l'utilisateur : c'est une parole véritable, elle
reste une cible légitime.

## Alternatives écartées

- **Extraire aussi le libellé du refus** — il n'existe dans l'historique
  qu'enchâssé dans le message échafaudé. Le récupérer supposerait de parser ce
  message, c'est-à-dire exactement le classement par chaîne que la règle
  interdit. Accepté comme limite : sur un refus, l'extraction porte sur la
  demande d'origine.
- **Un défaut `is_conversational=True`** — écarté : le défaut silencieux est le
  mécanisme même du défaut D7.
- **Ajouter une branche pour distinguer les causes des gardes disjonctives** —
  écarté : +1 CC sur un point chaud à 41, pour une information qu'un helper
  fournit sans coût.

## Conséquences

**Positives** : le rapport valeur/coût des six extractions devient mesurable ;
les journaux et la psyché fonctionnent enfin sur les canaux ; un flux d'action
avec confirmation nourrit la mémoire au lieu de la laisser vide ; les
acquiescements des quatre langues non couvertes cessent de payer un embedding et
jusqu'à quatre appels LLM ; un contact au patronyme malheureux retrouve ses
souvenirs.

**Attente à calibrer** : le prompt mémoire exclut délibérément la « logistique
transitoire » — rendez-vous, réservations, envois — qui constitue l'essentiel
des tours HITL. Le gain de D2 profite donc surtout aux **journaux et aux
intérêts**, et à la minorité de tours portant un fait durable en plus de
l'action.

**Négatives** : deux tâches d'extraction supplémentaires sont attendues avant la
réponse sur les canaux (plafond 15 s) — latence perçue à mesurer en production
via le nouveau compteur.
