# ADR-210 : un intent consommé ne se rejoue pas, quel que soit ce qui ressuscite son URL

**Statut**: ✅ IMPLEMENTED (2026-08-05)
**Date**: 2026-08-05
**Décideurs**: Équipe LIA
**Complète**: [ADR-192](ADR-192-Chat-Deep-Links-Are-Real-Navigations.md) (liens profonds = vraies navigations), [ADR-173](ADR-173-Card-Intent-Autosend.md) (`?intent=` auto-envoyé), [ADR-191](ADR-191-Reachable-Capabilities-And-Invoked-Directives.md) (directives invoquées)

## Contexte

Le 2026-08-05, en production v1.27.12 : une action de carte du dashboard —
« Prépare une réponse au mail “Confirmation de votre commande Samsung…” » —
s'exécute correctement au clic, puis **se ré-exécute à l'identique** quand
l'utilisateur revient sur la page chat. La table `conversation_messages` porte
la phrase deux fois, à 27 secondes d'intervalle, chaque occurrence suivie d'un
« Annuler » tapé par l'utilisateur. Les logs API sont nominaux : le backend a
exécuté deux requêtes qu'il a réellement reçues. Le déclenchement est
intégralement côté navigateur.

### Ce que la mesure établit

C'est le **quatrième mode de défaillance** du même sous-système, et il est
d'une autre nature que les trois précédents. Les règles 1-3 de
`useDeepLinkParams` (lire en live, nettoyer par l'History API, ne nettoyer
qu'une fois consommé) policent toutes **le support** — l'URL et l'entrée
d'historique de session. Or, mesuré au navigateur sur l'application :

- Depuis ADR-192, un clic d'action est une **vraie navigation**
  (`window.location.assign`). L'URL `?intent=…` devient donc une **visite de
  premier rang dans la base d'historique du navigateur** — omnibox, tuiles
  « sites les plus visités », restauration de session, favoris.
- `history.replaceState` réécrit l'**entrée de session** ; il n'atteint jamais
  la base de visites. L'arbre interne du routeur App conservé dans
  `history.state` garde d'ailleurs lui aussi les paramètres d'origine
  (`__PAGE__?{"intent":…}`) après nettoyage — constaté au débogueur.
- **Tout rechargement complet d'une URL portant encore `?intent=` ré-exécute
  la demande** : document neuf, verrou neuf, paramètre présent. Reproduit :
  deux bulles utilisateur identiques après un second chargement de la même
  URL. C'est exactement la forme d'une résurrection par l'omnibox, une
  restauration d'onglet ou un favori.

Le nettoyage du support ne peut pas gagner cette course : chaque durcissement
du support (capture au mount → lecture live ; `router.replace` →
History API ; nettoyage à l'arrivée → nettoyage à la consommation) a été
contourné par une nouvelle voie de résurrection que l'application ne contrôle
pas.

### La contrainte qui borne la solution

Le backend émet lui-même des liens `?intent=` **durables et volontairement
rejouables** : le lien « Run it now » d'une action planifiée en mode
propose-first (`scheduled_action_executor.py`) vit dans une notification et
chaque clic — cette semaine ou dans un mois — est un consentement. Toute
solution qui rendrait *l'URL* à usage unique casserait ce contrat.

## Décision

**L'idempotence est posée au point de consommation, pas sur le support.**

1. Chaque **clic** frappe un identifiant à usage unique : `chatIntentHref`
   ajoute `&iid=<uuid>` frappé à l'appel. Deux clics sur la même action
   restent deux exécutions (deux iid).
2. La consommation est enregistrée dans un **registre borné** (`localStorage`,
   FIFO de 50, partagé entre onglets et sessions —
   `lib/intent-replay-guard.ts`) au moment exact où `clearIntent` retire les
   paramètres de l'URL : les deux écritures ensemble *sont* la consommation.
3. Une URL qui se représente avec un **iid déjà consommé** est une
   résurrection : elle n'expose jamais d'intent à envoyer — pas même un rendu
   — et **dégrade en brouillon visible** dans le composer (`replayedIntent` →
   `resolveInitialMessage`), jamais en abandon silencieux. La directive
   (`capability`/`subject`) n'est pas conservée : l'utilisateur n'a pas
   re-consenti à un appel d'outil garanti.
4. Un intent **sans iid** garde le contrat historique clic-=-consentement :
   c'est le canal des liens durables émis par le backend.
5. Le registre **échoue ouvert** : sans stockage (navigation privée), le
   comportement redevient celui d'avant cet ADR — une demande ré-exécutée se
   rattrape, une demande silencieusement perdue non.

## Conséquences

- Le rejeu mesuré en production disparaît quel que soit son vecteur —
  omnibox, restauration de session, favori, ou la comptabilité d'entrées du
  routeur App (ADR-192) : la garde est indifférente à ce qui ressuscite l'URL.
- Le harnais hermétique bundle-prod gagne `chat-intent-replay.spec.ts` :
  résurrection par chargement complet, aller-retour client par-dessus
  l'entrée empoisonnée, rechargement — une seule exécution ; et le contrat
  sans-iid épinglé (chaque arrivée exécute).
- Les mocks chat des specs sont factorisés dans `e2e/fixtures/chat.ts`
  (même doctrine que la fixture relations : deux copies d'un contrat ne
  restent pas égales).
- `resolveInitialMessage` quitte la page pour `lib/chat-initial-message.ts`
  avec sa priorité testée : `?draft=` > intent rejoué > brouillon persisté.
- Envisagé, non retenu : transport par `sessionStorage` (URL toujours propre —
  incompatible avec les liens backend et avec la preuve e2e d'ADR-192) ;
  registre par valeur + TTL (bloque un re-clic légitime) ; clé d'idempotence
  propagée au backend (surdimensionné pour un message de chat — consigné ici
  si un cinquième mode l'exige un jour).
