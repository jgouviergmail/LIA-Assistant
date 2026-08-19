# ADR-230: L'historique des versions est une page publique, et les surfaces qui le promettent y mènent

**Statut**: ✅ IMPLEMENTED (2026-08-19)
**Date**: 2026-08-19
**Décideurs**: Propriétaire (arbitrage « page /changelog dédiée » puis « Nouveautés après Présentation ») + Équipe LIA

## Contexte

### 1. La promesse menait à une page qui n'avait pas l'historique

La bande « Tout juste livré » de la landing (ADR-181, bande `#changelog`) cite
les trois dernières versions et propose « **Voir tout l'historique** ». Ce
bouton pointait sur `/faq`.

Or la FAQ **publique** — `components/faq/PublicFAQContent.tsx`, 257 lignes — ne
rend aucun changelog : elle ne connaît que les sections `faq.sections.*`.
L'historique complet n'a jamais existé que dans `components/faq/FAQContent.tsx`
(carte repliable, `changelogVersionKeys`), c'est-à-dire la FAQ **du tableau de
bord, derrière l'authentification**.

Un visiteur non connecté qui suivait la promesse arrivait donc sur une page où
la chose promise était absente. Et il n'y avait aucun recours : les deux pieds
de page annonçaient « Nouveautés » en pointant `/#changelog`, soit le teaser de
trois versions que le lien était censé dépasser. **L'historique complet
n'existait pour lui nulle part.**

Le docstring de `ChangelogSection` affirmait par ailleurs « hands the full
history back to the FAQ » : une documentation décrivant un comportement que le
code n'avait pas, ce que le CLAUDE.md du dépôt classe comme un bug à part
entière.

### 2. Deux listes de pages publiques dérivaient déjà

En instrumentant la nouvelle route, `sitemap.ts` et `robots.ts` se sont révélés
porter chacun **sa propre copie** de la liste des pages publiques. Les copies
avaient déjà divergé : `/more` et `/demo` étaient annoncés dans le sitemap et
**nommés dans aucune règle `allow`** de robots.txt. Ajouter une page signifiait
se souvenir de deux fichiers — et l'oubli s'était donc déjà produit deux fois.

## Décision

### 1. `/changelog` est une page publique de plein droit

`app/[lng]/changelog/page.tsx` + `components/changelog/ChangelogHistory.tsx`,
**composants serveur** : `<details>` natifs, zéro bundle client, contenu rendu
côté serveur donc indexable — ce qui est la moitié de l'intérêt d'une page dont
le métier est d'être trouvable. Même coquille de lecture que `/faq` et `/why`
(scope `cosmos-calm`, `LandingHeader`, `PublicFooter`, canonical + hreflang ×6,
`BreadcrumbJsonLd`).

Source unique inchangée : `lib/changelog.ts` (`CHANGELOG_VERSION_KEYS`, 166
versions) et les traductions `faq.changelog.*`. **Zéro nouvelle clé i18n** — le
titre et le sous-titre de la page réutilisent `faq.changelog.title` et
`faq.changelog.description`, déjà écrites dans les six langues : une seconde
formulation du même objet aurait été une seconde vérité à maintenir.

`groupChangelogBySeries` plie les 166 versions en 28 séries mineures et
**ne trie jamais** : elle replie des suites déjà ordonnées, la liste partagée
restant seule autorité sur l'ordre. Les clés anciennes à deux segments
(`v1_15`) tombent dans la même série que leurs correctifs (`v1_15_1`). Chaque
série est un `section` nommé avec son ancre (`#release-1-30`), surmonté du rail
de chips que la FAQ publique utilise déjà ; seule la version la plus récente
est dépliée d'emblée.

### 2. Les surfaces qui promettent l'historique mènent à la page

- bande landing → `/changelog` (au lieu de `/faq`) ;
- `LandingFooter` et `PublicFooter` → `/changelog` (au lieu de `/#changelog`) :
  un pied de page liste des **pages**, pas des ancres ;
- header de la landing → **reste** l'ancre `#changelog` vers la bande : c'est un
  rail de sections avec scroll-spy, et la bande est une section. La chaîne
  complète est cohérente : header → bande → page.

L'entrée « Nouveautés » du header passe **juste après « Présentation »**
(arbitrage propriétaire 2026-08-19, remplaçant celui du 2026-08-18 « après
Encore + ») : le produit est présenté, puis ce qui vient d'être livré, et
ensuite seulement les pages. Sa contrainte de largeur est inchangée — elle
reste hors de la rangée desktop en dessous de `lg`, la rangée débordant de 96 px
en français à 880 px avec une septième entrée. Les deux tables d'ancres
(`SECTION_ANCHORS` / `TRAILING_ANCHORS`) fusionnent en une seule, ordonnée,
où un drapeau `lgOnly` porte cette exclusion : le concept « trailing » était
devenu faux, et deux tables rendues par quatre blocs quasi identiques
invitaient la divergence.

### 3. Les pages publiques sont déclarées une fois

`lib/public-pages.ts` porte `PUBLIC_PAGES` (chemin, `changeFrequency`,
`priority`), que `sitemap.ts` consomme telle quelle et dont `robots.ts` dérive
ses `allow` — plus le seul motif qu'un sitemap ne peut pas exprimer,
`/blog/*`. Sa liste de locales cesse elle aussi d'être une copie et lit
`i18n/settings`.

`NON_INDEXED_SEGMENTS` nomme, **avec sa raison**, chaque route délibérément
non indexable (zone authentifiée, URL porteuse de jeton, redirection
transitoire). La garde `lib/__tests__/public-pages.test.ts` scanne
`app/[lng]` — même traversée que la garde du gestionnaire 401 — et exige que
chaque route soit d'un côté ou de l'autre. Une page ajoutée sans décision fait
**rougir le test**, au lieu de partir en production invisible des robots.

## Conséquences

- Un visiteur non connecté atteint l'historique complet depuis la bande, depuis
  les deux pieds de page, et par une URL partageable, canonique et sitemappée.
- La page pèse 2,32 Mo bruts / 538 Ko gzip, soit environ 1,5× `/faq`
  (1,53 Mo / 405 Ko) : même ordre de grandeur que l'existant, pour zéro
  JavaScript supplémentaire.
- Le nombre de pages publiques passe de 11 à 12 ; `PUBLIC_ROUTE_SEGMENTS`
  (gestionnaire 401) gagne `changelog` — sa garde de complétude a effectivement
  rattrapé l'oubli pendant l'implémentation.
- `/more` et `/demo` sont enfin autorisés explicitement dans robots.txt, comme
  effet mécanique de la source unique et non comme correctif ponctuel.
- Une release ajoutée à `CHANGELOG_VERSION_KEYS` apparaît désormais sur trois
  surfaces d'un coup, toutes alimentées par la même liste.

## Alternatives écartées

- **Une section changelog dans la FAQ publique** (`/faq#changelog`) : diff
  minimal, mais l'URL ne nomme pas l'historique, elle alourdit une page déjà
  longue, et « tout l'historique » resterait une ancre plutôt qu'une
  destination.
- **Déplier l'accordéon de la FAQ du dashboard depuis un lien** : la FAQ du
  dashboard est derrière l'authentification, donc inaccessible au visiteur qui
  posait le problème.
- **Le header pointant sur `/changelog`** : il perdrait son scroll-spy et
  ferait mentir un arbitrage récent sur la nature de la bande (une section).
- **Regrouper `PUBLIC_PAGES` avec `PUBLIC_ROUTE_SEGMENTS`** : les deux listes
  répondent à des questions différentes — « indexable » n'est pas « accessible
  sans session ». `/reset-password` est la contre-preuve : accessible, jamais
  indexable.

## Références

- [ADR-181](./ADR-181-LIA-Cosmos-Public-Identity.md) — identité de l'espace public, scope
  `cosmos-calm` des pages de lecture
- `docs/technical/LANDING_PAGE.md` §8 — pages publiques et garde 401
- `apps/web/src/lib/changelog.ts` — source unique des versions
- `apps/web/src/lib/public-pages.ts` — source unique des pages publiques
- `apps/web/src/components/__tests__/changelog-destination.test.tsx` — garde des
  destinations promises
