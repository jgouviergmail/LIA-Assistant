# Workboard, lot 5 — ce qu'une connexion qui s'en va emporte (ADR-276)

**Statut** : à exécuter. Écrit après le lot 4, contre le code livré et vérifié
fait par fait.

Un ticket peut être confié à une personne connectée. Les lots 1 à 4 ont livré
l'attribution, ses droits, sa notification et son écran. **Ce qui manque est la
fin de la relation** : aujourd'hui, si la connexion est retirée, refusée ou
bloquée, le ticket reste attribué à quelqu'un qui n'a plus accès au tableau.

## 1. Ce qui existe déjà, mesuré

| Ce qui existe | Où | État |
|---|---|---|
| `WorkboardService.release_pair(a, b)` | `service.py:846` | **complet et testé, sans AUCUN appelant en production** |
| `WorkboardRepository.list_held_between` | `repository.py:482` | complet, parcourt UNE direction ; `release_pair` fait les deux |
| L'événement `assigned` avec sa raison | `service.py:866` | `{"to_kind": "human", "reason": "connection_removed"}` déjà écrit |
| Les points de sortie d'une relation | `peers/service.py` | `respond_request` (:377), `remove_connection` (:418), `block_peer` (:448) |
| La file d'événements pairs | `peers/service.py:79` (`pending_events`) | le service accumule, le routeur dispatche (`router.py:64`) |
| La notification pairs des deux côtés | `peers/notifications.py:109` | `dispatch_peer_events`, `_recipients` |
| La couture de notification proactive | `domains/shared/proactive_sink.py` | livrée au lot 3, `occurrence` ajoutée à la revue |

**Le fait décisif** : `release_pair` est du code MORT. Un `git grep` ne trouve
que des tests. C'est exactement ce que `CLAUDE.md` interdit de laisser
(« Dead code is deleted, not kept "for later" ») — ce lot le câble.

## 2. Le piège d'architecture, à traiter en premier

`workboard/service.py` importe `peers/repository` (lignes 116 et 289, imports
LOCAUX). Le ratchet de couplage **compte les imports locaux comme des arêtes** :
`workboard → peers` existe donc déjà.

Faire appeler `WorkboardService.release_pair` depuis `peers/service.py` ou
`peers/router.py` créerait `peers → workboard → peers` : **un cycle**, que
cacher dans une fonction ne ferait que masquer.

**La solution est la couture déjà employée deux fois** (`consultation_sink`,
`proactive_sink`) : un module de `domains/shared/` porte le contrat, le
workboard s'y installe à l'import, `peers` appelle la couture sans importer
personne. Et — leçon d'ADR-270, répétée au lot 3 — **le démarrage DÉCLARE ce
câblage et refuse une couture muette** : un effet de bord d'import que personne
ne déclare est un no-op silencieux le jour où quelqu'un réordonne un module.

## 3. Tâches (ordre TDD)

### Tâche 1 — la couture

**Fichiers** : `domains/shared/peer_release_sink.py` (neuf),
`domains/workboard/release_adapter.py` (neuf),
`infrastructure/startup/registries.py` (l'étape déclarée).
**Tests d'abord** : `tests/unit/domains/shared/test_peer_release_sink.py` —
rien d'installé ⇒ no-op qui répond « 0 ticket » plutôt que de lever ; une fois
installé, chaque champ arrive NOMMÉ ; le démarrage refuse une couture muette.

Contrat (nommé, jamais `**Any`) : `release_tickets_between(db, user_a, user_b)
-> int`, qui rend le nombre de tickets rendus.

### Tâche 2 — les trois sorties de relation appellent la couture

**Fichiers** : `peers/service.py`.
**Tests d'abord** : `tests/unit/domains/peers/test_connection_release.py`.

- `remove_connection`, `block_peer` et `respond_request(accepted=False)` **sur
  une connexion déjà acceptée** appellent la couture.
- Un refus d'une demande JAMAIS acceptée ne libère rien : aucun ticket n'a pu
  être confié, et un appel y serait une requête pour rien.
- **Le sens est symétrique** : la paire est la connexion, donc les tickets des
  DEUX côtés reviennent à leur propriétaire (le double de repository doit être
  sensible à la direction — le piège du lot 1, qui a doublé les lignes).
- La libération est dans la MÊME transaction que la rupture : une connexion
  rompue dont les tickets restent attribués est pire que les deux ensemble.

### Tâche 3 — les deux côtés sont prévenus, et une seule fois

**Fichiers** : `peers/notifications.py` ou le nouvel adaptateur.
**Tests d'abord** : les destinataires, et le contenu.

- Chaque côté est notifié **une fois**, avec le nombre de tickets rendus.
- **Rien n'est envoyé quand rien n'a été rendu** : « 0 ticket vous est revenu »
  est du bruit.
- L'événement `assigned` porte déjà `reason: connection_removed` — la
  notification le dit en mots, elle ne le déduit pas.
- L'action est REVENDIQUÉE dans le registre comme toute notification proactive,
  avec son `occurrence` : deux côtés = deux actes, jamais un rejeu (la leçon de
  la revue du lot 3).

### Tâche 4 — export et purge, sur PostgreSQL

**Tests d'abord** : `tests/integration/domains/workboard/test_peer_lifecycle_db.py`.

- Une connexion retirée rend les tickets des deux côtés, en une transaction ;
- l'export reste borné par côté (chaque compte reçoit les tickets de SON
  tableau) ;
- la suppression de compte continue de libérer explicitement (§5.1), et les
  deux chemins ne se marchent pas dessus ;
- **aucune action de clé étrangère n'est déclenchée** par la libération : c'est
  un `UPDATE`, et le piège mesuré au lot 1 (ordre des cascades vs `CHECK`
  croisé) reste fermé parce qu'aucune colonne croisée ne subsiste.

### Tâche 5 — l'écran dit ce qui est revenu

**Fichiers** : `components/workboard/TicketCard.tsx` (déjà prêt : un assigné
inconnu rend `{kind: 'unknown'}`), la section de réglages.
**Tests d'abord** : la carte d'un ticket rendu montre « Moi » et non « Quelqu'un
d'autre ».

Rien de neuf n'est attendu ici : le lot 4 a prévu le cas où la connexion a
disparu avant le rafraîchissement. La tâche est de le VÉRIFIER, pas de le
construire.

## 4. Plan de test

**Unitaire** : la couture (installée / muette / refus au démarrage) ; les trois
sorties de relation ; le sens symétrique ; le refus d'une demande jamais
acceptée ; une notification par côté et aucune quand rien n'a bougé ; la
revendication de registre avec son `occurrence`.

**Intégration PostgreSQL** : la libération des deux côtés en une transaction ;
l'export par côté ; la purge de compte inchangée ; l'absence de toute action de
clé étrangère.

**Preuve runtime en conteneur, sur les DEUX comptes de la paire de dev** :
un ticket confié au pair apparaît sur son tableau ; la connexion retirée le rend
au propriétaire ; les deux comptes reçoivent une notification portant LEUR
propre compte.

> **Corrigé pendant l'exécution.** Ce plan attendait aussi « deux lignes
> proactives soldées » dans le registre. C'était faux : `dispatch_peer_events`
> appelle `NotificationDispatcher` directement, sans passer par la couture qui
> revendique un effet, donc AUCUN des quatre genres d'événement de pair n'a
> jamais laissé de ligne dans `agent_effects`. Constat daté du 2026-09-09,
> laissé hors de ce lot avec sa raison écrite dans l'ADR : un événement de pair
> n'a aucun des trois auteurs qu'ADR-263 distingue, et pas de clé de run unique.

## 5. Ce que ce lot ne fait pas

Pas de source heartbeat (lot 6). Pas de délégation entre comptes (D7 la refuse
et ce lot ne l'ouvre pas). Pas de re-attribution automatique à la reconnexion :
un ticket rendu reste au propriétaire, qui le confie à nouveau s'il le veut.


---

## 6. Ce que l'exécution a réellement livré (2026-09-09)

Trois défauts trouvés par la revue, dont deux qu'aucun outil n'a signalés :

1. **`block_peer` lisait le statut APRÈS `transition_status`**, qui venait de le
   réécrire en `removed` : la libération était donc toujours sautée, pour toute
   paire. Seul le test PostgreSQL l'a vu — en unitaire, un `MagicMock` garde le
   statut qu'on lui a donné.
2. **Une libération à moitié écrite était commitée en annonçant « 0 ».** Mesuré
   sur un vrai serveur : le tableau meurt après un ticket sur deux, la couture
   avale, la notification dit zéro, et le `commit` de l'appelant écrit la
   moitié mutée. Corrigé par un SAVEPOINT dans l'adaptateur, et pinné par un
   test d'intégration et deux tests unitaires — dont le double de session, qui
   était un `object()` nu et n'aurait jamais pu voir le défaut.
3. **Une fuite `AsyncMock` non attendue (F028)** dans `TestRemovalAndBlock` :
   la couture est installée pour tout le processus, donc le vrai tableau
   recevait une session factice. Fermée par une fixture `_quiet_board`.

Preuve runtime du 2026-09-09, deux comptes connectés, `remove_connection` réel :
`released={A: 2, B: 1}`, trois tickets rendus (`assignee=None`, `follow=False`),
le quatrième — celui que personne ne partageait — intact, trois événements
`assigned` d'acteur `None` et de raison `connection_removed`, la paire à
`removed`, et les deux phrases reçues : « 2 tickets du tableau vous sont
revenus. » / « 1 ticket du tableau vous est revenu. »
