# ADR-171: `position: sticky` était inopérant dans toute l'application

**Statut**: ✅ IMPLEMENTED (2026-07-28)
**Date**: 2026-07-28
**Décideurs**: Équipe LIA

## Contexte

Le socle CSS déclarait, depuis l'origine du projet :

```css
html,
body {
  overflow-x: hidden;
}
```

L'intention est légitime : empêcher qu'un enfant trop large produise un
défilement horizontal sur mobile. L'effet de bord ne l'est pas.

La spécification CSS Overflow impose que, lorsqu'un seul axe vaut autre chose
que `visible`, l'autre axe soit **calculé à `auto`**. `body` obtient donc
`overflow-y: auto` et devient un **conteneur de défilement**. Or ce conteneur
n'est jamais défilé — sa hauteur suit son contenu, le défilement de la page
appartient au viewport. Tout descendant en `position: sticky` s'ancre alors sur
un scrollport immobile : il ne colle jamais.

Trois mesures, prises dans Chrome contre le serveur de développement :

1. **Styles calculés.** `body` : `overflow-x: hidden`, **`overflow-y: auto`**,
   `document.scrollingElement === html`. Le conteneur de défilement parasite
   existe bien.

2. **Sur un élément réel de l'application.** Le header de `/privacy`
   (`position: sticky; top: 0` — confirmé par `getComputedStyle`) mesuré
   pendant un défilement de page :

   | `scrollY` | `header.getBoundingClientRect().top` | attendu si collant |
   | --------- | ------------------------------------ | ------------------ |
   | 0         | 0                                    | 0                  |
   | 400       | **−400**                             | 0                  |
   | 1200      | **−1200**                            | 0                  |
   | 2000      | **−2000**                            | 0                  |

   Le header suit le document au pixel près : il n'est pas collant, il ne l'a
   jamais été.

3. **Falsification dans les deux sens.** La même sonde, `body` passé à
   `overflow-x: clip` puis à `visible` : `overflow-y` redevient `visible`, le
   header se fixe à `0` et une barre déclarée `top: 64px` se fixe à `64`. Le
   comportement se rétablit dès que `body` cesse d'être un scrollport, et
   uniquement à cette condition.

Trois surfaces réclamaient ce comportement sans jamais l'obtenir :
`app/[lng]/dashboard/layout.tsx` (le header du dashboard), `app/[lng]/privacy`
et `app/[lng]/terms`. Le défaut est resté invisible parce qu'aucune garde ne
mesurait une position pendant un défilement — et parce que la landing, elle,
avait contourné le problème sans le diagnostiquer, avec un
`position: fixed` (`LandingHeader.tsx`).

## Décision

`body` clippe désormais en `clip` et non plus en `hidden` :

```css
html {
  overflow-x: hidden;
} /* propagé au viewport : clippe la page */
body {
  overflow-x: clip;
} /* clippe SANS créer de scrollport */
```

`overflow: clip` clippe le débordement **sans** établir de conteneur de
défilement : `overflow-y` reste `visible`, et `position: sticky` retrouve le
viewport comme scrollport de référence.

Le repo utilisait déjà cette propriété pour cette raison exacte, sur les bulles
de conversation (`globals.css`, « clip horizontal overflow without creating a
scroll container »). La présente décision généralise ce raisonnement au socle.

## Conséquences

**Voulues.** Les trois headers deviennent réellement collants, et la barre
d'onglets de la page Réglages peut l'être (l'évolution qui a fait découvrir le
défaut).

**Neutres — mesuré, pas supposé.**

- `document.scrollingElement.scrollWidth − clientWidth` vaut **0 avant comme
  après**, y compris avec un enfant de 3 000 px injecté : les gardes de reflow
  (`axe-journeys`, `landing-mobile-overflow`, `dashboard-header-reachability`)
  conservent exactement le même verdict.
- Les éléments `position: fixed` (modales, toasts, compagnon flottant) gardent
  un rectangle identique : `clip` ne clippe pas un descendant dont le bloc
  conteneur est le viewport.
- Les `sticky` vivant dans un conteneur à défilement **interne** — le bouton
  « revenir en bas » du chat, l'entête de l'overlay d'onboarding — ne sont pas
  concernés : leur scrollport est ce conteneur, pas `body`.

**Dégradation gracieuse.** Un moteur qui ignorerait `overflow: clip` retombe sur
`visible` pour `body` ; le clipping reste assuré par `html`, propagé au
viewport. Aucun scénario ne perd le clipping.

**Risque assumé.** Un contenu focalisé au clavier peut désormais se retrouver
sous un header collant lors du défilement automatique du navigateur — c'est le
comportement de tout header collant. Les surfaces qui reçoivent un défilement
programmé portent un `scroll-margin-top` (les sections de réglages, les
sections de la landing en portaient déjà un).

## Alternatives écartées

- **Laisser `hidden` et positionner les barres en `fixed`** (ce que fait la
  landing) : contourne le symptôme, laisse trois headers cassés, et impose de
  recalculer largeur et réservation d'espace à chaque redimensionnement.
- **Retirer purement `overflow-x` de `body`** : fonctionne (mesuré), mais perd
  un filet de sécurité au niveau `body` sans contrepartie ; `clip` conserve le
  clipping et supprime le scrollport.
- **Ne rien faire** : la page Réglages ne peut pas offrir d'onglets persistants,
  et trois surfaces continuent de mentir sur leur propre comportement — ce que
  la doctrine du repo qualifie de bug (« un docstring qui décrit un
  comportement que le code n'a pas est un bug »).
