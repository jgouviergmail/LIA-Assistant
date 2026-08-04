# ADR-205 : un statut nomme un ton, il n'écrit pas ses couleurs

- **Statut** : accepté
- **Date** : 2026-08-04
- **Portée** : `lib/status-tone.ts`, `components/ui/badge.tsx`, historiques de notifications, relations, hub Alertes

## Contexte

Trois composants portaient chacun leur propre `Record<string, string>` de
classes Tailwind pour le même travail : rendre une étiquette de statut. Écrire
ces classes à la main a trois conséquences, toutes constatées à l'écran.

**La distinction promise n'existait pas.** Une priorité `high` s'affichait en
`bg-destructive/10` et une priorité `medium` en `bg-warning/10`. Les deux jetons
sont séparés de **23° de teinte en OKLCH** (`--color-destructive` à 27°,
`--color-warning` à 50°) et rendus à 10 % d'opacité : sur un vrai compte —
89 lignes `high` et 113 lignes `medium` — le lecteur ne pouvait pas les
distinguer. Le premier correctif, qui passait par `Badge variant="destructive"`,
n'a rien changé : ce variant est **lui aussi un fond pâle** (`bg-red-100`).

**Ces classes échappaient à la garde de contraste.** `design-contrast.guard.test.ts`
vérifie l'AA de chaque paire réellement produite par le design system, sur
5 thèmes × clair/sombre. Une classe écrite dans un composant n'y figure pas.

**Un statut inconnu tombait sur ce que le repli du `Record` donnait**, ce qui
pouvait afficher en rouge une valeur dont personne n'a jamais dit qu'elle était
urgente.

## Décision

**Un statut nomme un TON ; `Badge` le rend.** `lib/status-tone.ts` expose
`priorityTone`, `outcomeTone` et `directionTone`, qui renvoient un variant de
`Badge` — jamais une classe. Une seule fonction décide, et l'étiquette hérite
de la garde de contraste.

**La hiérarchie est portée par la DENSITÉ, pas par la teinte seule.** `Badge`
gagne un variant `alert`, le seul fond **solide** des statuts
(`bg-destructive text-destructive-foreground`, la paire que
`Button variant="destructive"` utilise déjà et que la garde couvre). Mesuré au
navigateur : le fond de `alert` est à L=32 avec un texte à L=98, quand
`warning` reste une teinte à 10 %. La distinction survit à deux teintes que
l'œil confond — et elle fonctionne encore en niveaux de gris.

**Une valeur inconnue est NEUTRE.** Un statut ajouté plus tard par le backend
ne doit pas arriver en criant : afficher un niveau non reconnu en rouge serait
une affirmation d'urgence que personne n'a faite.

**Une étiquette est un mot, pas une phrase.** `Badge` fixe sa hauteur
(`size="sm"` vaut 16 px) : un objectif d'appel de trois lignes en débordait et
se lisait comme du texte barré. Ce qui est long est mis en valeur par le
**poids typographique**, qui ne suppose rien de la longueur.

## Conséquences

**Un bouton d'action se reconnaît partout.** Le comptage a tranché : `outline`
est utilisé 137 fois, `ghost` 83 — et `softPrimary` une seule, celle qui venait
d'être introduite. Les actions de la fiche relation et les raccourcis du hub
prennent `outline`. La cohérence prime sur l'emphase : un lecteur reconnaît une
action à sa forme partout, ou nulle part.

**Une pastille de compteur est bleue partout** (arbitrage 2026-08-04). Un
compte est une information, et le gris se lisait comme de la décoration. Zéro
compris — une section vide est un fait, pas une autre nature de chose. Seul
l'état **inconnu** (`—`) reste neutre : ce n'est pas un compte.

**La couleur ne porte jamais seule le sens.** Chaque étiquette garde son mot ;
le ton accélère le balayage, il ne le remplace pas.

## Alternatives écartées

**Ajouter une teinte au thème pour « moyenne ».** Une sixième couleur de statut
à faire vivre dans cinq thèmes × clair/sombre, pour un problème que la densité
résout sans rien ajouter à la palette.

**Garder les `Record<string, string>` en les corrigeant.** Cela laisse trois
copies à corriger la prochaine fois, et aucune ne passe par la garde.

## Références

- ADR-061 — un sous-système désactivé est absent, jamais grisé
- ADR-185 — un compte affiché est exact, ou il n'existe pas
- Audit AC-002 — garde de contraste du design system
