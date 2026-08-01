# ADR-186 : le fait survit aux mots, mais les mots ont droit à un délai

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Date**: 2026-07-31
**Décideurs**: Équipe LIA
**Révise**: [ADR-180](ADR-180-Peer-Connections.md) §8.4 (effacement à la remise)
**Complète**: [ADR-185](ADR-185-Exact-CRM-Counts-And-Readable-Relayed-Messages.md)

## Contexte

Le relais effaçait le contenu d'un message **à la remise** : le registre
`peer_messages` gardait la ligne, jamais les mots. Conséquence dans le CRM
livré par ADR-185 : la fiche pouvait dire qu'un message avait existé, mais
presque jamais ce qu'il disait.

Pour rendre les messages **reçus** lisibles, ADR-185 avait dû aller les
rechercher dans l'archive de conversation du destinataire — le seul endroit
où le texte livré survivait. Cela a coûté une requête JSONB, un argument de
plancher temporel prouvable, une marge de décalage d'horloge, et une
dégradation à assumer (réinitialiser sa conversation effaçait le texte). Les
messages **envoyés** n'avaient, eux, aucun texte du tout : l'archive de
l'émetteur ne contient qu'un accusé de remise.

Demande produit : que les messages persistent, reçus **et** envoyés, « comme
pour les appels téléphoniques ».

## Décision

**Le précédent invoqué est plus précis qu'il n'y paraît, et c'est lui qu'on
suit.** Les appels ne persistent pas indéfiniment :
`TelephonyRepository.purge_expired` efface `summary`/`structured_data`/
`debrief` passé `expires_at` et **garde la ligne** (audit). Rétention par
défaut : 30 jours.

Les messages relayés adoptent exactement ce contrat.

### 1. Le contenu n'est plus effacé à la remise, il expire

`peer_messages` gagne :

- `delivered_text` — ce que l'assistant du **destinataire** a réellement dit ;
- `expires_at` — posé **à l'enfilement**, pas à la remise : un message qui
  n'est jamais parti doit expirer aussi, et son horizon ne doit pas dépendre
  de ce que le balayage a réussi à faire.

`content` cesse d'être vidé à la livraison. Le balayage peers — qui purgeait
déjà le journal d'accès — devient aussi le faucheur de rétention. **La ligne
survit pour toujours ; les mots, trente jours.**

Ce n'est pas un renoncement à la confidentialité §8.4 : c'est le même
engagement, exprimé par une fenêtre au lieu d'un effacement immédiat, et
piloté par un réglage (`peers_message_retention_days`).

### 2. Chacun lit ses propres mots, jamais ceux de l'autre

- l'émetteur voit sa **directive** (« fais passer à Marie que… ») ;
- le destinataire voit le **texte livré** (« Marie vous fait dire que… »).

Croiser les deux déferait le relais : le destinataire lirait la directive
brute au lieu du rendu de son assistant, et l'émetteur découvrirait le ton et
la personnalité de l'assistant d'en face. C'est le pendant exact de
`objective` / `summary` sur un appel.

### 3. Un message annulé garde sa directive

« Voici ce que vous avez tenté de faire passer, et ce n'est pas parti » vaut
mieux qu'une ligne vide — et ce sont les mots de l'émetteur. Il expire sur le
même horizon que les autres.

### 4. Le chemin d'archive disparaît

Le registre portant désormais les mots, le CRM n'a plus rien à chercher dans
l'archive de conversation. **La requête JSONB, le plancher prouvable et la
marge d'horloge d'ADR-185 sont supprimés** : `relations/peer_messages.py`
passe de 108 à 67 SLOC. La réponse durable était aussi la plus simple.

## Conséquences

**Positives**

- Les messages sont lisibles dans les deux sens, et survivent à une
  réinitialisation de conversation.
- Le module de pont perd un tiers de son code et trois arguments subtils.
- La fenêtre de conservation devient explicite et pilotable, là où
  l'effacement immédiat ne se discutait pas.

**Négatives / assumées**

- **Les messages déjà remis avant cette migration ont perdu leur texte pour
  de bon.** Ils gardent leur date et l'écran le dit — arbitrage explicite :
  garder le chemin d'archive pour eux aurait conservé toute la complexité
  qu'on vient de retirer, pour un historique fini.
- Le contenu vit désormais 30 jours en base. Il est déjà couvert par la purge
  RGPD et l'export (`peer_messages` figure dans `user_data_map` et dans le
  builder, côté émetteur **et** destinataire).
- Supprimer un compte efface la ligne (FK CASCADE), donc les messages
  disparaissent aussi du CRM de l'autre. C'était déjà le cas — le registre
  était déjà l'épine dorsale de la chronologie.

## Alternatives écartées

| Alternative | Pourquoi non |
|---|---|
| Conserver sans limite | Rompt avec le seul précédent de contenu conversationnel daté du produit et rend la fenêtre non pilotable |
| Ne dé-effacer que `content` | L'émetteur serait servi, le destinataire resterait tributaire de son archive — le cas le plus courant |
| Garder l'archive en secours pour l'historique | Conserve JSONB + plancher + marge d'horloge indéfiniment, pour un ensemble de lignes fini et décroissant |
| Montrer à chacun les deux textes | Déferait le relais : le rendu personnalisé d'un assistant n'appartient pas à l'autre utilisateur |
