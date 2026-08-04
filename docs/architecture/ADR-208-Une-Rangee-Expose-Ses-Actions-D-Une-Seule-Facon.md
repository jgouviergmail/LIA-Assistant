# ADR-208 : une rangée expose ses actions d'une seule façon

- **Statut** : accepté (arbitrage propriétaire 2026-08-05)
- **Portée** : les écrans de réglages à listes et leurs barres d'outils —
  mémoire long terme, centres d'intérêts, journaux personnels, actions
  planifiées, connexions entre utilisateurs, notifications proactives,
  authentification forte

## Contexte

Les trois écrans « éléments dans des catégories » partageaient la même
architecture et **trois patrons d'actions différents**. Mémoire et intérêts
révélaient leurs boutons au survol (`opacity-0 group-hover`) : au clavier, le
focus se posait sur des contrôles **invisibles** — le dépôt connaît pourtant le
patron correct (`group-focus-within`, utilisé ailleurs). Sur mobile, un tap
n'importe où sur la carte (gardé par `window.innerWidth` dans le onClick)
ouvrait un Dialog plein écran d'actions, dupliqué ~70 lignes par écran — et ce
handler avait déjà forcé l'exil du disclosure d'explication hors de sa carte.
Les journaux, eux, montraient leurs actions en permanence. Trois écrans, trois
grammaires, pour le même geste.

Les barres de section avaient les mêmes divergences : le CTA « + Ajouter »
perdait son libellé sur téléphone pendant que « Tout supprimer » gardait le
sien — le bouton destructif devenait le plus lisible de la barre — et
« Exporter » était purement supprimé sous `lg`, une amputation de
fonctionnalité que rien ne justifiait.

## Décision

**1. Les actions d'une rangée passent par `RowActions`** (`ui/row-actions.tsx`).
À partir de `sm` : icônes ghost **toujours visibles**, la suppression portant
son rouge au repos (ADR-207 : un code que le pointeur doit révéler n'est pas un
code — le clavier non plus). Sous `sm` : un « ⋮ » ouvrant un `DropdownMenu`
léger — un tap de moins que l'ancien Dialog, et le déclencheur **nomme la
rangée** (`common.actions_for`), car dix « ⋮ » anonymes se lisent pareil au
lecteur d'écran. Le hover-reveal, le tap-n'importe-où et les trois Dialogs
mobiles sont supprimés.

**2. La barre d'une section à liste passe par `SectionToolbar`**
(`settings/SectionToolbar.tsx`). Le CTA principal est plein et **toujours
labellisé** ; les secondaires existent à toutes les tailles (inline dès `sm`,
menu « ⋯ » en dessous) ; la destruction de masse reste visible partout, même
géométrie que ses voisines.

**3. Ce qui se consulte se replie, ce qui se scanne reste visible.** Les
métriques épistémiques des journaux, les occurrences suivantes d'une routine,
les bloqués et le journal d'accès des connexions passent derrière
`SettingsDisclosure` (badge de compte) ; le niveau L0-L3, le statut et la
prochaine exécution restent en carte. La planification se **synthétise**
(« En semaine à 08:00 », `lib/schedule-label.ts`) au lieu d'énumérer cinq
jours ; la carte d'une routine passe de ~8 lignes toujours visibles à 3.

**4. Un contrôle dupliqué devient un composant.** Fréquence min/max et fenêtre
horaire, copiés trait pour trait entre notifications proactives et intérêts —
avec les quatre Selects **anonymes** dans les deux copies — deviennent
`FrequencyControls` (`MinMaxPerDay`, `HourWindow`), nommés.

## Conséquences

- ~250 lignes de duplication supprimées (3 Dialogs, 2 copies de contrôles) ;
  le disclosure des intérêts revient dans sa carte.
- L'export redevient accessible sur téléphone et tablette (menu « ⋯ »).
- Les trois blocs d'authentification forte partagent le même en-tête
  empilable mobile et le même niveau de titre (`h4`).
- Les connexions se lisent en trois zones (visibilité en carte, découverte et
  demandes, connexions) au lieu de six blocs plats ; le `<select>` natif
  artisanal rejoint le `Select` maison.
- Boutons anonymes nommés : suppression des intérêts bloqués, édition et
  suppression des journaux, les quatre Selects de fréquence.

## Alternatives écartées

**Tout en menu « ⋮ », desktop compris.** Rangées plus épurées, mais chaque
action passe à deux clics là où la densité d'un écran de bureau n'y oblige
pas.

**Conserver le hover-reveal en ajoutant la révélation au focus.** Corrige le
défaut clavier, conserve la divergence des trois grammaires — et un contrôle
invisible au repos reste un contrôle que l'œil ne découvre jamais.

## Références

- ADR-205 — un statut nomme un ton ; ADR-206 — une primitive porte son
  contrat ; ADR-207 — une action a une altitude
