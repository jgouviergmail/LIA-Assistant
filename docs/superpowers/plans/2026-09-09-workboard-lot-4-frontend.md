# Workboard, lot 4 — le tableau à l'écran (ADR-276)

**Statut** : à exécuter. Écrit après les lots 1-3 et leur revue à froid, contre
le code livré et **vérifié fait par fait** (chaque affirmation ci-dessous porte
sa preuve).

Les lots 1-3 ont donné au tableau ses données, son API, son exécution par LIA
et ses six outils de chat. **Il n'a aucun écran.** Mesuré le 2026-09-09 :
`GET https://localhost:3000/dashboard/settings` → **200**,
`GET https://localhost:3000/dashboard/workboard` → **404**. Or le back construit
déjà trois liens vers cet écran (`board_url`, `ticket_url`, et le lien
`?intent=` du chat), et les envoie dans **chaque notification de ticket**. Tant
que ce lot n'est pas livré, une notification de run pointe vers une page qui
n'existe pas.

---

## 1. Ce qui existe et sur quoi ce lot s'appuie (mesuré, pas supposé)

| Ce qui existe | Où | Preuve | Ce que le lot 4 en fait |
|---|---|---|---|
| L'API complète du tableau, 9 routes | `domains/workboard/router.py:50-330` | `response_model` sur les 9 | le hook et le module d'API l'appellent, rien d'autre n'épelle un chemin `/workboard/*` |
| Les totaux EXACTS + `counts_by_status` | `schemas.py:178-190` (`BoardPage`) | ADR-185 | les compteurs de colonne viennent de là, jamais d'un `.length` |
| 21 codes d'erreur stables | `constants.py:181-201` (`WorkboardError`) | énumérés | table code → clé i18n (précédent `peers-error-messages.ts`) |
| Le drapeau d'instance | `routes.py:373` (`workboard_enabled` dans `/config`) | lu | à DÉCLARER dans `AppConfig.features` (absent aujourd'hui) |
| Le compteur du hub | `notifications/schemas.py:162` (`workboard: int`) | lu | à DÉCLARER dans `HubCounts` (absent aujourd'hui) |
| La résolution du chemin sans locale | `apps/web/src/proxy.ts` (Next 16 a renommé `middleware.ts` → `proxy.ts`) | `/dashboard/settings` → 200 | rien à faire : les URL du back sont correctes |
| `usePagedSection` + `HubSection` + `sectionShell` | `hooks/usePagedSection.ts`, `components/notifications/` | 6 sections l'utilisent | la 7e section du hub, sans une ligne de plomberie neuve |
| `RowActions`, `SectionToolbar`, `EmptyState`, `FormSection`, `Skeleton`, `Badge`, `Select`, `Switch`, `useConfirm` | `components/ui/`, `components/settings/` | inventoriés | la carte, la barre, les vides, les formulaires |
| `priorityTone` / `lifecycleTone` | `lib/status-tone.ts:153,192` | lus | à ÉTENDRE (voir §2.5) |
| `LLMUsageBadge` + `formatEuro` | `components/ui/llm-usage-badge.tsx`, `lib/format.ts:43` | lus | le coût d'un run, sans deuxième façon de l'écrire |
| Le registre des sections de réglages | `lib/settings-sections.ts`, `settings-section-registry.tsx`, `lib/settings-search.ts`, `lib/settings-section-icons.ts` | 4 fichiers + 3 gardes | la porte du tableau |
| Le montage d'une rangée d'actions sous une bulle | `ChatMessage.tsx:349` (`PeerMessageActions`) | lu | `WorkboardNotificationActions` au même endroit |
| Les mocks e2e hermétiques | `e2e/fixtures/api-mock.ts`, `dashboard-shell.ts:64` | lus | le parcours du tableau |

---

## 2. Les six risques systémiques trouvés à l'analyse, et leur fermeture

Chacun a été trouvé en LISANT le code, pas en le supposant. Chacun casserait le
lot en silence.

### 2.1 `ticket_url` est un CHEMIN, pas un paramètre de requête

La spec §4.2 dit « `?ticket=<id>` deep link ». **Le back livré dit autre chose** :
`notifications.py:155` construit `f"{board_url()}/{ticket.id}"`, soit
`/dashboard/workboard/<uuid>`. Une page ne servant que `?ticket=` renverrait 404
sur **chaque lien de notification de ticket**.

**Fermeture** : DEUX routes, UN composant.
`app/[lng]/dashboard/workboard/page.tsx` (lit `?ticket=`) et
`app/[lng]/dashboard/workboard/[id]/page.tsx` (passe le segment) montent le même
`WorkboardPage` avec un `initialTicketId`. Aucune duplication, les deux liens
marchent. Un test vérifie les deux entrées.

### 2.2 `useApiQuery` ne sait pas envoyer un paramètre répété

`api-client.ts:51` : `params?: Record<string, string | number | boolean>` et
`buildUrl` fait `String(value)` — un tableau partirait en `"todo,done"`. Or le
board filtre par `status: list[str]` et `priority: list[str]`
(`router.py:53,58`), que FastAPI lit en paramètres RÉPÉTÉS
(`?status=todo&status=done`).

**Fermeture générique** (directive de factorisation) : `RequestConfig.params`
accepte `string | number | boolean | readonly (string|number)[]`, et `buildUrl`
émet une entrée par élément. C'est le contrat FastAPI, il sert tout appelant
futur, et il est couvert par un test dédié. `undefined` reste ignoré.

### 2.3 Trois valeurs de statut et une de priorité tombent en GRIS

`lib/status-tone.ts` : `LIFECYCLE` connaît `done`, `in_progress`, `cancelled`,
mais **pas** `idea`, `todo`, `waiting`, `validating` ; `PRIORITY` connaît
`high/medium/low` mais **pas `urgent`**. Un inconnu retourne `secondary` — le
gris. Or la règle du propriétaire : « les badges gris sont réservés aux éléments
INACTIFS ». Un ticket `urgent` en gris, c'est l'inverse de ce qu'il dit.

**Fermeture, purement ADDITIVE** (aucune valeur existante ne change, donc aucune
régression sur l'historique heartbeat, seul consommateur de `priorityTone`) :

- `urgent → 'alert'`. **`high` reste `alert`** : le commentaire de la table
  porte une mesure (2026-08-05) selon laquelle `destructive/10` et `warning/10`
  « sont du même niveau à l'œil » — rétrograder `high` vers un ton pâle
  ré-introduirait exactement le défaut que cette mesure a fermé. Les deux
  niveaux hauts partagent donc la famille ATTENTION et se distinguent par leur
  MOT, ce que le badge porte déjà.
- `idea → 'secondary'` (inerte par définition : rien ne se passe et rien ne va
  mal — la définition littérale de la famille), `todo → 'default'` (un trait
  vivant sans famille sémantique prend la couleur du thème — la règle du
  propriétaire le prévoit mot pour mot), `waiting → 'warning'` (« demande une
  attention, rien n'est cassé »), `validating → 'info'` (« ça vient de se
  passer »).

**Et la carte ne porte PAS de badge de statut** : la carte est DANS sa colonne,
et sur mobile la colonne est nommée au-dessus — un badge y répéterait l'évidence.
Le statut est porté par le `<select>` natif de la carte, qui est à la fois
l'affichage et l'équivalence clavier que la charte exige. Le badge de priorité
n'est rendu que pour `high` et `urgent` : `medium` est le défaut (une mer
d'ambre sur chaque carte) et `low` est le bas d'échelle silencieux — les deux
sont nommés en toutes lettres dans le panneau et dans le filtre.

### 2.4 Rien ne rafraîchit à la reprise de focus

La spec §13 exclut la synchronisation temps réel « la page se rafraîchit au
focus et après chaque mutation ». Or `useApiQuery` n'écoute **aucun**
`visibilitychange` (vérifié). Un pair qui déplace un ticket resterait invisible
indéfiniment sur un onglet ouvert.

**Fermeture** : `useWorkboard` écoute `visibilitychange` → `refetch` quand
l'onglet redevient visible (précédent `useGeolocation.ts:386`, avec le
`removeEventListener` en nettoyage). Testé : caché → visible déclenche une
relecture, et le nettoyage est prouvé au démontage.

### 2.5 dnd-kit n'est pas installé, et le lockfile a un piège documenté

`node_modules/@dnd-kit` absent. Les versions de la spec existent
(`npm view` : `@dnd-kit/core@6.3.1`, `@dnd-kit/sortable@10.0.0`).
Le piège #1 de `CLAUDE.md` : un `pnpm add` DANS le conteneur laisse le lockfile
de l'hôte périmé et casse le build prod (`--frozen-lockfile`).

**Fermeture** : installation depuis l'HÔTE (le lockfile monorepo est à la racine
de l'hôte), versions ÉPINGLÉES EXACTEMENT (D16), puis `task lint:lockfiles`
comme preuve, puis `pnpm install` dans le conteneur pour son propre arbre.

### 2.6 Le drapeau et le compteur existent côté back mais pas côté front

`AppConfig.features` n'a pas `workboard_enabled` ; `HubCounts` n'a pas
`workboard`. Les deux sont publiés par le back. Un composant qui lirait
`config.features.workboard_enabled` aujourd'hui ne compilerait pas.

**Fermeture** : les deux types déclarés, et le mock e2e `appConfig` reçoit le
drapeau — sinon le parcours e2e du tableau tomberait sur une section absente.

---

## 3. Tâches (ordre TDD)

### Tâche 1 — le socle typé, sans une ligne d'interface

**Fichiers** : `types/workboard.ts` (neuf), `lib/workboard/api.ts` (neuf),
`lib/api-client.ts` (params tableau), `hooks/useAppConfig.ts`,
`hooks/useHubCounts.ts`, `lib/status-tone.ts`.
**Tests d'abord** : `lib/__tests__/api-client-params.test.ts` (un tableau devient
N entrées ; un vide n'en produit aucune ; `undefined` est ignoré ; l'ordre est
conservé), `lib/__tests__/status-tone.test.ts` (les 4 statuts et `urgent`
ajoutés ; **les valeurs existantes inchangées**, assertion explicite).

Les types miroir de `schemas.py` : `TicketRow`, `BoardPage`, `TicketDetail`,
`CommentRow`, `EventRow`, `NeedsMePage`, `DeleteResult`, plus les tuples
`TICKET_STATUSES` (l'ordre des colonnes) et `TICKET_PRIORITIES`. **Une seule
table** : l'ordre des colonnes est celui de `STATUS_ORDER` côté back, et un test
compare les deux listes en dur pour qu'une divergence rougisse.

### Tâche 2 — le réducteur pur du tableau

**Fichier** : `reducers/workboard-reducer.ts` (neuf).
**Tests d'abord** : `reducers/__tests__/workboard-reducer.test.ts`.

État : `{ tickets, countsByStatus, total }`. Actions : `loaded`,
`moved` (optimiste : retire de la colonne source, insère à l'index cible,
renumérote, ajuste les deux compteurs), `moveFailed` (rollback EXACT vers le
`position`/`status` d'avant), `patched` (une ligne remplacée par la réponse
serveur), `removed` (N lignes, le parent et ses enfants).

Ce qui est PROUVÉ par un test, parce que chacun est une manière de mentir :
un déplacement dans la MÊME colonne renumérote sans changer les compteurs ;
un déplacement entre colonnes déplace exactement 1 dans chaque compteur ;
un rollback restaure l'ordre **exact** (pas seulement l'appartenance) ;
un `moved` sur un id inconnu est un no-op (une carte supprimée par un pair) ;
`removed` décrémente le total du nombre RÉEL de lignes supprimées.

### Tâche 3 — le hook

**Fichier** : `hooks/useWorkboard.ts` (neuf).
**Tests d'abord** : `hooks/__tests__/useWorkboard.test.tsx`.

`useWorkboard(filters)` → `{ tickets, countsByStatus, total, firstLoad,
loading, error, isUnavailable, refetch, move, patch, comment, runNow,
remove, create }`. Chaque verbe rend `{ ok, errorCode }` — jamais une
exception à attraper chez l'appelant (précédent `useMeetings`).
`firstLoad` dérivé de l'ABSENCE de données, jamais de `error` (le défaut mesuré
sur `PeerConnectionsSettings`). Rafraîchissement au focus (§2.4).
`isUnavailable` sur 404 (drapeau éteint), comme `useMeetingList`.

### Tâche 4 — le tableau et ses cartes

**Fichiers** : `components/workboard/{Board,Column,TicketCard,StatusSelect,
BoardFilters,WorkboardPage}.tsx`, `lib/workboard/errors.ts`.
**Tests d'abord** : un fichier par composant sous `components/workboard/__tests__/`.

- **Board `lg`+** : 7 colonnes dans UN conteneur `overflow-x-auto` (le `body` ne
  défile jamais latéralement), en-tête de colonne = nom + compteur EXACT.
- **Sous `lg`** : un `<select>` natif de colonne + précédent/suivant, la même
  liste, le même réducteur, le même appel `move`. Aucun dnd sur mobile — le
  capteur tactile de dnd-kit prend une contrainte d'activation
  (`delay` + `tolerance`) pour qu'un doigt qui fait défiler ne démarre jamais un
  glisser.
- **Carte** : titre, badge de priorité (`high`/`urgent` seulement, §2.3), puce
  d'assignation (moi / LIA / le nom du pair), échéance (`destructive` si en
  retard), enfants faits/total, état du run (badge `waiting`, badge d'échec avec
  le message borné, indicateur en cours), cloche de suivi (son propre côté),
  `RowActions` : ouvrir, statut `<select>`, supprimer (propriétaire).
- **Le glisser ET le `<select>` appellent LA MÊME mutation** — une seule
  implémentation de « déplacer », donc une seule façon de se tromper.
- Les annonces dnd-kit (`screenReaderInstructions`, `announcements`) viennent des
  locales : un lecteur d'écran doit entendre la colonne d'arrivée, pas un index.

### Tâche 5 — le panneau de détail

**Fichiers** : `components/workboard/{TicketDetailPanel,TicketForm,CommentThread,
TicketHistory}.tsx`.

Champs éditables selon les droits du §8 de la spec (un pair ne touche ni titre
ni description) ; enfants avec ajout en ligne ; fil de commentaires ; historique ;
dernier run (issue, coût via `LLMUsageBadge`, « Exécuter maintenant », « Terminer
dans le chat » quand `waiting`) ; suppression.
Le panneau est un `Dialog` (rôle `dialog`, focus piégé, `Esc`), ce que la charte
exige et que `role="dialog"` bricolé sur un `div` ne donne pas.

### Tâche 6 — les portes : réglages, hub, chat

- `components/settings/WorkboardSettings.tsx` + les 4 fichiers de registre.
  La section porte : la porte vers le tableau, `closed_hide_days`, et le volume
  des lignes cachées quand l'API le publie. Auto-gardée sur
  `features.workboard_enabled` (précédent `MeetingsSettings`).
- `NotificationsHub` : une 7e section `workboard` sur `/workboard/needs-me`,
  via `usePagedSection` + `sectionShell` — zéro plomberie neuve.
- `components/chat/WorkboardNotificationActions.tsx` monté en `ChatMessage.tsx`
  à côté de `PeerMessageActions` : « Ouvrir le ticket », « Ouvrir le tableau »,
  et pour `waiting` « Terminer dans le chat » (`?intent=`, chemin existant).
  Auto-gardé sur `metadata.type === 'proactive_workboard'`.
- **Aucune entrée d'en-tête** (D15) : l'en-tête est à sept destinations, son
  maximum mesuré. Un test le VÉRIFIE, pour que ce soit une décision et non un
  oubli.

### Tâche 7 — i18n ×6, e2e, ratchets

`workboard.*`, `settings.workboard.*`, `notifications_hub.sections.workboard.*`
dans les six locales (parité stricte, zh sans pluriel dupliqué).
E2E hermétique : parcours du tableau, 390 px sans débordement horizontal, axe sur
le tableau et le panneau. Ratchets relevés APRÈS mesure (≥ 2 pts de marge).

---

## 4. Plan de test (enrichi pendant l'implémentation, déroulé à la revue)

**Unitaire (vitest)**
- `api-client` : paramètre tableau → N entrées, vide → aucune, ordre conservé,
  `undefined` ignoré, scalaires inchangés.
- `status-tone` : les 5 ajouts ; **et une assertion que chaque valeur
  préexistante est inchangée** (le test de non-régression du seul consommateur).
- réducteur : les 6 cas du §Tâche 2.
- `useWorkboard` : premier chargement vs rafraîchissement (`aria-busy`, pas de
  démontage), 404 → `isUnavailable`, `visibilitychange` → relecture, nettoyage
  au démontage, chaque verbe rend `{ok, errorCode}`, rollback après un `move`
  refusé.
- carte : nom accessible en `en` ET `fr` ; le `<select>` de statut déplace ;
  la cloche bascule le bon côté ; la carte d'un pair n'offre pas « supprimer » ;
  un ticket en retard porte le ton `destructive` ; le badge de priorité n'est
  rendu que pour `high`/`urgent`.
- tableau : 7 colonnes, compteurs EXACTS venus de `counts_by_status` (jamais
  `.length`) — un test donne un total supérieur à la page pour le prouver ;
  vide « aucun ticket » vs vide « le filtre ne rend rien » (`reason`).
- responsive : sous `lg`, le sélecteur de colonne remplace les colonnes et
  `move` est appelé avec les mêmes arguments que le glisser.
- panneau : droits par côté, « Exécuter maintenant » absent si l'assigné n'est
  pas LIA, `waiting` montre le lien `?intent=`.
- chat : la rangée ne se monte que sur `proactive_workboard` ; les trois liens ;
  `waiting` seul porte « Terminer dans le chat ».
- hub : la section lit `/workboard/needs-me`, le badge vient de `HubCounts`.
- registre des réglages : les 3 gardes existantes passent avec la nouvelle
  section (jeton, accordéon, recherche, icône).
- en-tête : la table de navigation ne contient PAS `workboard` (D15).

**E2E (Playwright, hermétique)**
- parcours : ouvrir le tableau, créer, déplacer par le `<select>`, commenter,
  supprimer avec la carte de confirmation ;
- 390 px : aucun débordement horizontal du `body`, le sélecteur de colonne
  fonctionne ;
- axe sur le tableau ET sur le panneau ouvert ;
- une bulle `proactive_workboard` rend ses trois actions et `?intent=` envoie
  exactement UN message.

**Portes complètes** : `task lint:frontend`, `pnpm exec tsc --noEmit
--incremental false`, `pnpm test:coverage`, les 3 ratchets, `task lint:i18n`,
`task lint:lockfiles`, puis les portes back inchangées.

**Preuve runtime** (conteneur, jamais en local) : le tableau répond 200 sur
`/dashboard/workboard` et sur `/dashboard/workboard/<id>`, un ticket créé depuis
l'écran apparaît, un déplacement persiste après rechargement.

---

## 5. Ce que ce lot ne fait pas

Pas de crochet de suppression de connexion (lot 5), pas de source heartbeat
(lot 6). Pas de synchronisation temps réel entre deux navigateurs (§13 de la
spec) : la page relit au focus et après chaque mutation.
