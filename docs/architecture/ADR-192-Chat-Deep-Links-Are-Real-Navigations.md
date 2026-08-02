# ADR-192 : un lien profond du chat porte une demande, pas une transition de vue

**Statut**: ✅ IMPLEMENTED (2026-08-01)
**Date**: 2026-08-01
**Décideurs**: Équipe LIA
**Complète**: [ADR-191](ADR-191-Reachable-Capabilities-And-Invoked-Directives.md) (capacité garantie par une directive), [ADR-173](ADR-173-Card-Intent-Autosend.md) (`?intent=` auto-envoyé), [ADR-190](ADR-190-Overview-Scope-And-Full-Contact-Card.md) (portée du 360°)

## Contexte

Le 2026-08-01, après le déploiement de la v1.27.5, un point 360° lancé sur un
pair puis sur un second **reste figé sur le premier**, essai après essai.

### Ce que la mesure établit

**Le backend reçoit exactement ce que le navigateur lui envoie.** La table
`conversation_messages` de production contient quatre lignes consécutives
portant **la même phrase**, au caractère près. Le cache de traduction sémantique
(clé = SHA256 de la requête) enregistre **trois succès de cache** sur ces mêmes
requêtes : un succès de cache n'est possible que si la chaîne reçue est
identique. Le défaut est donc intégralement côté navigateur — aucune couche
serveur n'est en cause.

**L'href de l'application est jetée.** Reproduction hermétique, bundle de
production, navigation client réelle depuis la page Relations : un clic qui
pousse `/dashboard/chat?draft=Appelle Paul Martin…` aboutit sur
`/dashboard/chat?intent=…Marie Dupont…&capability=person_overview&subject=Marie Dupont`.
Cette URL est **impossible à fabriquer** par le code — `chatIntentHref` est une
fonction pure de ses arguments et le clic ne lui a jamais passé ces valeurs.
C'est donc le routeur, et non la page, qui a choisi l'URL : **il restaure les
paramètres de requête de l'entrée qu'il détient déjà pour cette route**.

**Trois causes plausibles écartées par l'expérience, pas par raisonnement :**

| Hypothèse | Expérience | Résultat |
|---|---|---|
| Le prérendu statique de `/[lng]/dashboard/chat` | Route forcée dynamique (0 entrée au manifeste de prérendu) | Défaut **inchangé** |
| Notre propre nettoyage d'URL (`clearIntent`) | Première visite sans query, donc sans aucun nettoyage | Empoisonne **quand même** |
| La réécriture i18n du locale par défaut | Même parcours en `en`, où l'URL porte son locale et n'est pas réécrite | Défaut **identique** |

**Le défaut ne se voit que sur navigation client.** La spécification e2e
existante n'a rien vu parce qu'elle utilise `page.goto` — un chargement de
document complet, qui reconstruit le routeur depuis l'URL. Le parcours réel est
un `router.push` vers une route déjà visitée dans la session.

### Portée réelle

Ce n'est pas un défaut du 360°, c'est un défaut de **tous** les liens profonds du
chat : cartes du briefing, exemples de la FAQ, actions rapides des relations,
débriefs téléphoniques, engagements des réglages — treize points d'appel.

Le cas dangereux n'est pas le mauvais texte. C'est qu'un lien de
**pré-remplissage** (`?draft=`, qui ne doit jamais envoyer) revienne en
`?intent=` périmé — donc **auto-envoyé** (ADR-173). Le clic exécute alors une
demande que l'utilisateur n'a pas faite.

## Décision

**Un lien profond du chat est une navigation réelle, jamais un `router.push`.**

Un `?intent=` n'est pas une transition de vue : c'est une demande qui doit
arriver telle qu'elle a été construite. L'application cesse donc de dépendre de
la comptabilité d'URL du routeur et rend le **navigateur** seul maître de
l'adresse — la page du chat démarre alors sur la barre d'adresse, pas sur une
entrée de cache.

Une **implémentation unique**, `openChatDeepLink` (`lib/chat-deep-link.ts`),
sert les treize points d'appel. Un helper par surface aurait laissé chacune
diverger ; c'est la même doctrine que `placement_domain` (ADR-191) ou
`fold_name` (ADR-185) — une question, une réponse.

**Uniforme, et non réservé aux intentions auto-envoyées** : puisqu'un `?draft=`
peut revenir en `?intent=`, corriger seulement les commandes laisserait ouverte
la seule voie qui exécute sans consentement.

**Le nettoyage du paramètre passe par l'API History**, pas par `router.replace`.
Un `replace` qui ne fait que retirer des paramètres est avalé — même mécanisme,
vu de l'autre côté : c'est ce qui laissait `?intent=` dans l'URL et faisait
qu'un **rechargement de page rejouait la demande**. Ce défaut, mesuré la veille
et consigné sans explication, est le même que celui-ci ; il se ferme avec lui.
`window.history.replaceState` est la voie supportée par Next pour mettre à jour
la requête sans naviguer, et le routeur y synchronise `useSearchParams` — le
verrou anti-doublon se réarme donc exactement comme avant.

**Une garde CI** (`check_code_hygiene.py::chat_deep_link`) refuse tout
`router.push(chatIntentHref(…))` ou `router.push(chatDraftHref(…))` : une
garantie qui repose sur la discipline de treize appelants n'est pas une
garantie. La garde a été vérifiée voyante — réintroduire l'ancien appel la fait
rougir.

**Le helper lui-même est épinglé par un test** : chaque appelant simule
`openChatDeepLink` et vérifie l'href reçue, ce qui est un bon oracle du **quoi**
et un oracle aveugle du **comment**. Si la fonction redevenait un `router.push`,
tous ces tests resteraient verts. `lib/__tests__/chat-deep-link.test.ts` est donc
le seul endroit qui vérifie la porte elle-même.

## Conséquences

**Coût, mesuré** sur le bundle de production : ~155 ms et un repeint de la
coquille par lien profond (108–214 ms sur trois exécutions), contre une
navigation SPA. Les arrivées externes — notifications, liens reçus par courriel
— payaient déjà ce prix. Le plus perceptible reste les cartes du briefing,
aujourd'hui instantanées ; sur le bouton 360°, les 155 ms se noient dans une
réponse qui met plusieurs secondes à arriver.

**Ce qui n'est pas perdu** : le message part exactement une fois ; l'historique,
l'indicateur de tâche en cours et la session se resynchronisent depuis le
serveur, comme à toute arrivée externe.

**Écarté explicitement** :

- **Un transport interne** (magasin one-shot de session, URL réservée aux liens
  externes) garderait tout instantané, mais ajoute un mécanisme parallèle à
  maintenir et deux sources de vérité à réconcilier sur la même page. À
  reconsidérer si les 155 ms gênent à l'usage.
- **`experimental.staleTimes`** : essayé, sans effet sur le défaut.
- **Corriger seulement `?intent=`** : laisse ouverte la voie qui exécute sans
  consentement.

**Assumé** : le correctif traite la conséquence dans notre code, pas la cause
dans le routeur — celle-ci n'est pas à notre portée. Le choix est donc de **ne
plus en dépendre** pour ce qui porte une demande, et le prix est un rechargement
de page par lien profond.

## Références

- `apps/web/src/lib/chat-deep-link.ts` — l'implémentation unique et sa mesure
- `apps/web/src/hooks/useDeepLinkParams.ts` — le nettoyage par l'API History
- `apps/web/e2e/smoke/chat-360-two-people.spec.ts` — la preuve navigateur
- `scripts/audit/check_code_hygiene.py` — la garde de non-retour
