# ADR-161: Un flux SSE muet doit rendre la main — chien de garde client et reprise automatique

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA
**Amende**: ADR-117 (runs en arrière-plan, rattachement)

## Contexte

Le 2026-07-27, une réponse visible sur ordinateur restait bloquée sur
« Génération de la réponse… » sur mobile, indéfiniment.

Côté serveur, rien à signaler : les six flux se sont terminés normalement
(`sse_stream_completed`, `chat_run_producer_completed`), et la réponse était
persistée en base. Les géo-IP séparent nettement les deux appareils — les quatre
tours détournés viennent d'une IP mobile, les deux derniers d'une IP fixe.

Le blocage est entièrement côté client, et tient à trois faits qui se
verrouillent mutuellement :

1. `ChatSSEClient.readSseStream` faisait `await reader.read()` **sans aucun
   délai de garde** ; l'`AbortController` ne servait qu'au bouton « stop ».
   Quand un OS mobile gèle un onglet en arrière-plan, cette promesse n'est ni
   résolue ni rejetée.
2. `isTyping` dérive de `status === 'streaming'`. Sans `done` ni rejet, le
   statut ne bouge plus.
3. `handleVisibilityChange` — le gestionnaire qui, au retour au premier plan,
   recharge l'historique et appelle `checkAndResumeActiveRun()` (ADR-117) —
   **sort immédiatement si `isTyping`**. Son commentaire l'assume : « the
   isTyping guard already skips this when a stream is active ».

Le raisonnement supposait `isTyping` ⟺ flux vivant. C'est faux dès que la
connexion meurt en silence : le garde censé protéger un flux actif verrouillait
la seule issue de secours. Confirmation par les logs : **zéro** appel à
`/runs/active` ou `/runs/{id}/stream` sur toute la période.

## Décision

### 1. Un budget de silence borne chaque lecture

`readWithStallGuard` court `reader.read()` contre un minuteur de
`CHAT_SSE_STALL_TIMEOUT_MS` (90 s par défaut, surchargeable via
`NEXT_PUBLIC_CHAT_SSE_STALL_TIMEOUT_MS`). À l'expiration, le lecteur est annulé
— ce qui libère la socket — et une `ChatStreamError` typée `StreamStalledError`
est levée, porteuse de la clé i18n `errors.chat.stream_stalled` (les 6 langues).

Le serveur émet un battement toutes les `SSE_HEARTBEAT_INTERVAL` secondes (15 s
en production) : le budget vaut donc **six battements manqués**. Assez long pour
ne jamais se déclencher sur un tour simplement lent, assez court pour qu'un
onglet gelé se débloque dès que ses minuteurs repartent — car les minuteurs JS
gèlent avec l'onglet et expirent au réveil, ce qui est exactement le moment
utile.

### 2. Un flux mort déclenche une tentative de reprise

Dans `useChat`, `StreamStalledError` quitte d'abord l'état `streaming` (c'est
`isTyping` qui bloque le gestionnaire de visibilité), **puis** appelle
`checkAndResumeActiveRun()`. Le run continuant côté serveur, `/runs/active` le
retrouve et le rattachement rejoue le backlog. Quand il n'y a rien à rejoindre,
le message localisé s'affiche au lieu d'une bulle vide.

Le garde `isTyping` de `handleVisibilityChange` est **conservé** : il protège
légitimement un flux vivant. C'est la prémisse « `isTyping` implique vivant »
qui est corrigée à la source, en garantissant qu'un flux mort quitte cet état.

## Conséquences

- Un tour dont chaque battement serveur mettrait plus de 90 s à arriver serait
  interrompu à tort. Le battement est indépendant du travail du graphe et n'a
  jamais dépassé son intervalle en production ; le seuil est réglable si un
  déploiement place un intermédiaire qui tamponne les événements.
- Le minuteur est armé et désarmé à chaque lecture ; un test vérifie qu'aucun
  minuteur ne survit à une fin normale de flux — un minuteur fuité avorterait le
  tour **suivant**.

## Références

- `apps/web/src/lib/api/chat.ts` (`readWithStallGuard`)
- `apps/web/src/lib/constants.ts` (`CHAT_SSE_STALL_TIMEOUT_MS`)
- `apps/web/src/hooks/useChat.ts` (branche `StreamStalledError`)
- `apps/web/src/lib/api/__tests__/chat.test.ts` (« stalled stream watchdog »)
- `apps/web/src/hooks/__tests__/useChat.test.ts` (« a stalled stream leaves typing AND tries to reattach »)
