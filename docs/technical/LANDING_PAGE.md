# Landing Page — Documentation technique

> Architecture, composants, i18n, SEO et patterns de la vitrine publique de LIA.
>
> Derniere revision : **démonstration produit partagée et lecture progressive** — six scènes contextuelles communes au hero, aux cas d’usage et aux chapitres ; catalogue visuel hiérarchisé sans perte de contenu ; explications d’ingénierie à la demande, dans l’identité « LIA Cosmos » (ADR-181).

La carte « décision dans des limites claires » présente la bascule JEV comme
facultative : LIA fournit les choix permis, vérifie le résultat et garde les
autorisations et confirmations. Les textes correspondants existent dans les six
locales et restent une explication de conception, sans promesse de gain de
latence ni de certification réglementaire.

---

## Table des matieres

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture des composants](#2-architecture-des-composants)
3. [Structure de la page](#3-structure-de-la-page)
4. [Animations et interactions](#4-animations-et-interactions)
5. [Gardes-fous executables](#5-gardes-fous-executables)
6. [Internationalisation (i18n)](#6-internationalisation-i18n)
7. [SEO et OpenGraph](#7-seo-et-opengraph)
8. [Pages publiques et garde 401](#8-pages-publiques-et-garde-401)
9. [Responsive, theming](#9-responsive-theming)

---

## 1. Vue d'ensemble

La landing est le point d’entrée public de LIA. La démonstration suit une intention jusqu’à son résultat :
une demande, les éléments de contexte utiles, puis ce que la personne récupère. Les six scènes sont des
**exemples illustratifs**, pas des sessions réelles ni une mesure de temps ou de coût. Elles sont définies une
seule fois et réutilisées dans le hero, le parcours de cas d’usage et les illustrations des chapitres.

Trois niveaux de lecture :

1. **Le résultat** : choisir une situation, voir ce que LIA rapproche et ce qu’elle produit ; les chapitres
   développent les bénéfices avec la même illustration, puis viennent les fonctions courantes.
2. **Le détail à la demande** : chaque chapitre ouvre un catalogue visuel. Un index de capacités mène à une
   illustration et à une description complète à la fois. Les explications « Ce qui rend cela possible » se
   déplient séparément ; elles relient les choix techniques à leur utilité.
3. **La profondeur** : la section ingénierie présente les principes en langage courant, puis les choix
   détaillés dans des dépliants. Les pages /story, /why, /how, /more, l’audit public et le blog prolongent la lecture.

Principes non negociables :

- **Zero perte d'information** : contrat executable `REQUIRED_FEATURE_KEYS` (voir §5).
- **Zero survente** : chaque phrase mappe une fonctionnalite livree ; pas de superlatifs invérifiables ; la beta et les
  abonnements a venir sont affiches (l'honnetete est le positionnement).
- **Regle d'or des chiffres** : toute statistique publique vit dans `constants.ts` (`LANDING_STATS`), source canonique
  documentee. Le score d'audit affiche vit dans `landing.transparency.p2_t` (×6) — a mettre a jour avec `auditScore`.
- **Registre** : la landing tutoie (6 langues, transcreation — jamais de traduction litterale des titres a la voix du produit).
  Depuis ADR-181 le tutoiement couvre **tout** l'espace public, y compris les guides markdown (`why/how/story`) et les
  formes polies de l'allemand (`Sie`), de l'espagnol (`usted`) et du chinois (`您`).
- **Identite (ADR-181)** : l'habillage passe par un **scope CSS** `.cosmos` qui redefinit les jetons du design system —
  les sections de contenu ne sont jamais editees pour changer de peau ; le sous-scope `cosmos-calm` sert les pages de
  lecture. Toute animation est en `transform`/`opacity`, sans dependance nouvelle.

---

## 2. Architecture des composants

Les composants vivent dans `apps/web/src/components/landing/`. La démonstration partagée est dans `demo/`,
le récit et son catalogue dans `editorial/`, l’habillage dans `cosmic/`.

### 2.1 Démonstration partagée (`demo/`)

| Composant                | Type        | Description                                                                                                                                                                                                                                           |
| ------------------------ | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `demo/scenes.ts`         | data        | `PRODUCT_SCENES` déclare les six identifiants, leurs icônes, leurs sources de contexte et leurs clés i18n. Autorité commune au lecteur, aux cas d’usage et aux chapitres.                                                                             |
| `demo/scene-tones.ts`    | data        | Accents cohérents par scène : repère du chapitre, sélection et résultat partagent le même ton, avec variantes contrastées claires et sombres.                                                                                                         |
| `demo/ProductScene.tsx`  | Client      | Illustration d’une scène : demande, sources, résultat et limite explicite. `phase` choisit le niveau de révélation ; omise, elle donne directement l’état complet utilisé par les chapitres. `ProductResult` adapte la forme du résultat au scénario. |
| `demo/useProductDemo.ts` | Client hook | Révélation en trois phases de la scène choisie ; s’arrête sur le résultat. Pause, reprise, relecture, changement de scène, arrêt hors du viewport, nettoyage des temporisateurs et observation de `prefers-reduced-motion`.                           |
| `InteractiveChatMockup`  | Client      | Navigation nommée dans les six scènes, étapes de lecture, pause/relecture et explication dépliable du bénéfice. Le hero fournit son propre CTA (`withCta={false}`) ; la page de démonstration conserve celui du lecteur.                              |

| Scène      | Contexte rapproché                            | Résultat illustré                      | Chapitre     |
| ---------- | --------------------------------------------- | -------------------------------------- | ------------ |
| `decision` | Documents, e-mails, décisions de réunion      | Préparation d’une décision             | `act`        |
| `day`      | Agenda, engagements, actualité                | Journal personnel à écouter            | `know`       |
| `watch`    | Routine configurée, mail attendu, projet      | Suivi déclenché par une condition      | `anticipate` |
| `call`     | Disponibilités, préférences, accord           | Appel délégué et résultat              | `control`    |
| `research` | Recherche web, connaissances, comparaison     | Recherche structurée et livrable       | `grow`       |
| `relay`    | Connexion acceptée, périmètre partagé, agenda | Proposition transmise entre assistants | `connect`    |

L’explication technique ne masque plus le déroulement de la tâche. Les anciennes scènes autonomes des chapitres
et l’ancien moteur du mockup ont été remplacés par ce rendu commun.

### 2.2 Récit et catalogue (`editorial/`)

| Composant                                  | Type             | Description                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------ | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `chapters-data.ts`                         | data             | Configuration des chapitres, association `scene` partagée avec les liens des cas d’usage, ordre éditorial des capacités, `BASICS_CATALOG`, `BASICS_CHIPS`, `FEATURE_ICONS` et inventaire `REQUIRED_FEATURE_KEYS`. Les capacités différenciantes précèdent les fonctions courantes ; le compte est dérivé du code. |
| `EditorialChapters`                        | Server           | Orchestre les six chapitres sous l’ancre historique `features` et rend le `ProductScene` complet désigné par `chapter.scene`.                                                                                                                                                                                     |
| `ChapterSection`                           | Server           | Titre, sous-titre, bénéfices courts, illustration partagée, explication « Ce qui rend cela possible » en `<details>`, puis catalogue dépliable. Les détails techniques restent disponibles dans le même dépliant.                                                                                                 |
| `FeatureCatalog`                           | Server           | Traduit les titres, descriptions complètes, légendes et noms de commandes avant de transmettre ces données sérialisables à `FeatureExplorer`. Réutilise les textes `landing.features.*`.                                                                                                                          |
| `FeatureExplorer`                          | Client           | Index de titres iconisés en deux colonnes, de hauteur bornée et défilable ; un panneau détaillé visible à la fois, avec illustration, texte intégral et boutons précédent/suivant. L’ordre vient du catalogue du chapitre. Tous les panneaux textuels restent dans le DOM.                                        |
| `FeatureScenes.ts` / `FeatureIllustration` | data / rendu SVG | Correspondance explicite entre chaque capacité et une famille d’illustration. Le SVG décoratif du panneau actif représente son usage ou son résultat ; sa légende est localisée séparément.                                                                                                                       |
| `SecurityDetail`                           | Server           | Détails de sécurité et de vie privée conservés dans le catalogue du chapitre `control` (`landing.security.*`).                                                                                                                                                                                                    |
| `CatalogDisclosure`                        | Client           | Catalogue replié à l’arrivée ; bouton natif, `aria-expanded`, contenu conservé dans le DOM via `grid-template-rows`, `inert` une fois replié. Une ancre `#chapter-…-detail` ouvre le catalogue ciblé.                                                                                                             |
| `BasicsBand`                               | Server           | Fonctions courantes après les chapitres : chips et catalogue propre, avec le même explorateur visuel.                                                                                                                                                                                                             |
| `PromiseSection`                           | Server           | Trois promesses entre le hero et les scénarios : écosystème, confiance, disponibilité sur les écrans.                                                                                                                                                                                                             |
| `TransparencySection`                      | Server           | Preuves de confiance, coûts, audit public, open source, retour d’expérience et CTA intermédiaire (`#transparency`).                                                                                                                                                                                               |
| `DayTimeline`                              | Client           | Journées par profil en onglets ; version verticale de repli pour `CosmosDay` sur mobile et en mouvement réduit.                                                                                                                                                                                                   |
| `GallerySection`                           | Client           | Galerie à onglets de captures réelles et de présentation. La présentation est sélectionnée à l’arrivée ; `ScreenshotsSection` et `PresentationSection` partagent `LandingCarousel`.                                                                                                                               |
| `ChapterRail`                              | Client           | Rail fixe desktop (`xl+`) dérivé des chapitres, puis transparence ; liens d’ancre nommés, suivi de la section active.                                                                                                                                                                                             |
| `Tabs`                                     | Client           | Onglets WAI-ARIA génériques : roving tabindex, flèches, Home/End, panneaux `hidden` conservés dans le DOM.                                                                                                                                                                                                        |

Le remaniement conserve l’inventaire complet de `REQUIRED_FEATURE_KEYS`, sans doublon entre chapitres et fonctions
courantes. Une présentation plus compacte ne raccourcit ni ne supprime les descriptions. Le compteur de chaque
catalogue est calculé depuis sa liste, jamais recopié dans la traduction.

### 2.3 Autres sections

| Composant                                                                                 | Type   | Notes                                                                                                                                                                                                                                            |
| ----------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `cosmic/CosmosHero`                                                                       | Server | Hero Cosmos et démonstration partagée ; le planetarium ne l'entoure que si `LANDING_PLANETARIUM_ENABLED` (`landing/constants.ts`, ÉTEINT depuis le 2026-10-01, décision du propriétaire — composant, styles et tests conservés) ; CTA propre et lien vers `#features`. |
| `UseCasesSection`                                                                         | Server | Parcours visuel des mêmes six scènes, placé avant les chapitres : intention, contexte et résultat. Chaque carte est un lien vers le chapitre retrouvé dans `CHAPTERS` par son champ `scene`.                                                     |
| `TechSection`                                                                             | Server | Quatre principes lisibles — relier le contexte, organiser le travail, vérifier, rendre l’action lisible — puis choix d’ingénierie détaillés et schéma d’architecture dans le dépliant facultatif. Les chiffres restent issus de `LANDING_STATS`. |
| `ArchitectureDiagram`                                                                     | Client | Comparaison lisible de Pipeline et ReAct : trois étapes par parcours, exemples concrets et garanties communes. Met en avant rapidité, contrôle et fiabilité, sans ratio de tokens ; rendue dans le dépliant facultatif de `TechSection`.         |
| `LandingCarousel`                                                                         | Client | Carrousel partagé de la galerie : ratio de l’actif, fond ambiant, flèches visibles, vignettes à scroll-snap, clavier et swipe, légende `aria-live`, plein écran optionnel pour les captures.                                                     |
| `cosmic/CosmosFinale`                                                                     | Server | CTA final dans l’horizon Cosmos.                                                                                                                                                                                                                 |
| `LandingHeader` / `LandingFooter` / `AuthRedirect` / `FadeInOnScroll` / `AnimatedCounter` | —      | Navigation publique, redirection des comptes connectés, révélations et compteurs.                                                                                                                                                                |
| `LandingEyes`                                                                             | Client | Personnage public chargé dynamiquement, surface `landing`, Smiley, position distincte du chat, petit par défaut avec choix explicites respectés. Aucun compte requis ; ses signaux de chat sont au repos.                                        |

---

## 3. Structure de la page

```
AuthRedirect | LandingHeader (fixed) | ChapterRail (fixed, xl+)
<main>
   1. CosmosHero           — démonstration partagée, choix parmi six scènes
   1b. LandingVideoSection — vidéo de l'opérateur, montée seulement si LANDING_MEDIA_BASE_URL répond (§10)
   2. PromiseSection       — trois promesses
   3. UseCasesSection      — mêmes situations, liens vers leurs chapitres
   4. EditorialChapters    — features ; chapter-{act,know,anticipate,control,grow,connect}
   5. BasicsBand           — basics
   6. TransparencySection  — transparency, CTA intermédiaire
   7. CosmosDay            — day, journées par profil
   8. GallerySection       — gallery, captures réelles et présentation
   9. TechSection          — technology, principes puis détails et architecture à la demande
  10. ChangelogSection     — changelog
  11. BlogPreviewSection   — blog
  12. CosmosFinale         — CTA final
</main>
ScrollScrub (transparency, gallery, changelog) | LandingFooter | LandingEyes
```

`CosmosDarkFirst` (script avant affichage) et `CosmicBackdrop` encadrent la page et sont partagés avec les autres
pages publiques. La landing monte aussi `AuthRedirect`, `TrackView` et ses données structurées JSON-LD.

Skip-link (`sr-only`) → `#features`. Le header propose les ancres Présentation et Nouveautés, ainsi que les
pages Story, Philosophie, Technique, Blog, FAQ et Encore + ; voir la table `SECTION_ANCHORS` pour leur ordre.
Rythme visuel : chapitres alternes (fond transparent / `bg-card` borde), visuel gauche/droite alterne sur desktop.

---

## 4. Animations et interactions

- **Démonstration** : `useProductDemo` révèle demande → contexte → résultat pour la scène sélectionnée. Le résultat
  reste affiché, sans passage automatique à une autre scène. Une nouvelle sélection ou une relecture repart du
  début ; pause et reprise gardent la scène choisie. Hors du viewport, la progression s’arrête. Les boutons
  portent des noms traduits ; la sélection est annoncée par `aria-pressed`, la phase par `aria-current="step"`.
- **Chapitres** : `ProductScene` sans `phase` rend le résultat complet, identique à celui du lecteur. La révélation
  de section passe par `FadeInOnScroll` ; aucune seconde chorégraphie ne reconstruit la scène.
- **Catalogues** : `CatalogDisclosure` est replié par défaut ; transition `grid-template-rows`, contenu `inert`
  lorsqu’il est replié. À l’intérieur, `FeatureExplorer` propose un tablist à roving tabindex : gauche/droite,
  haut/bas selon les deux colonnes, Home/End. Les boutons précédent/suivant conservent le focus et la position
  courante est annoncée poliment. Seul l’index interne défile pour rendre le titre choisi visible.
- **Explications** : des `<details>` natifs ouvrent le mécanisme du chapitre ou de la démonstration. La section
  ingénierie utilise un dépliant général puis un dépliant par sujet ; il contient aussi le schéma d’architecture.
  Les textes longs restent présents.
- **Onglets génériques** : `Tabs` conserve le pattern WAI-ARIA des journées et de la galerie ; panneaux `hidden`
  maintenus dans le DOM.
- **Chorégraphies au scroll (ADR-181)** : `ScrollScrub` reste limité aux sections déclarées dans la page. Il écrit
  `--sp` via la boucle rAF partagée ; le CSS utilise un état final par défaut. Les chapitres, les cas d’usage et
  les cartes techniques ne dépendent plus d’un ordre d’animation piloté par cet indice.
- **Scène épinglée** : `PinnedScene` reste utilisé par `CosmosDay` avec progression `--p`. Mobile et mouvement
  réduit reviennent à `DayTimeline` dans le flux ; aucun ancêtre scrollport ne doit casser le sticky.
- **Mouvement réduit** : la démonstration affiche immédiatement l’état complet, conserve les six choix et masque
  pause/relecture. Aucun temporisateur d’animation n’est programmé. Les transitions des panneaux sont coupées,
  `FadeInOnScroll` révèle directement et les compteurs donnent leur état final.
- **Contraste par thème** : le jeton primaire diverge entre fond sombre et fond clair ; vérifier les deux modes,
  notamment les petits libellés, les bordures de sélection et les focus visibles.
- **Fond « attention + espace latent » (landing seule)** : `AttentionBackdrop` monte, sur un `requestIdleCallback`
  (jamais avant le premier rendu ; là où l'API manque — WebKit —, après l'événement `load`), un `<canvas>` fixe à la taille du viewport dessiné par
  `lib/landing/attention-background.ts` — un nuage d'embeddings qui se regroupe au fil du scroll, et une colonne
  de tokens à droite où chaque `main .landing-section` devient un repère `§n`, la ligne de lecture y avançant au
  fil du scroll (le module sait tracer les courbes de quatre têtes d'attention ; la landing les désactive,
  `attentionHeads: false`, et garde la barre seule — demande du propriétaire, 2026-10-02) ; `destroy()` au démontage (aucun canvas, écouteur ni frame après une navigation). Il rejoint les
  couches de `CosmicBackdrop` en `z-index: -1` (au-dessus du grain, sous tout le contenu, aucun contexte
  d'empilement ajouté) ; sous la portée `.cosmos-attention`, les bandes de section deviennent transparentes, les
  cartes gardent leur fond. Libellés dessinés traduits (`landing.cosmos.attention.*`) ; thème lu sur la classe
  `dark` de `<html>` à chaque frame ; sous 768 px, **pas de colonne d'attention** (pas la place), la couche
  latente reste. **Le fond ne bouge que là où il coûte peu** (règle du propriétaire, 2026-10-02) : le module
  chronomètre ses frames animées et, si la médiane de trente frames (après cinq de mise en route) dépasse 5 ms
  (15 % du fil principal à 30 i/s), il se fige pour la session. Mesuré le 2026-10-02 : 0,97 ms sur un i9 de
  bureau (barre seule ; 2,7 ms avec les courbes), 3,6 ms sur un téléphone émulé à CPU ×4 (couche latente seule).
  **Figé veut dire immobile** : sous `prefers-reduced-motion`, quand le visiteur met la page en pause, ou quand
  l'appareil est trop lent, le module dessine UNE image fixe — la formation et la ligne de lecture là où elles
  sont — et ne la redessine qu'à un changement de thème ou de mise en page, jamais au scroll ni au pointeur (un
  redessin au pointeur recalculait le graphe des voisins à 30 i/s : plus cher, figé, que l'animation elle-même).
- **Mettre les animations en pause (WCAG 2.2.2)** : la nébuleuse, les nuages de la planète et le fond animé de la
  landing démarrent seuls et durent plus de cinq secondes ; le décoratif n'est pas exempté (seul l'essentiel
  l'est) et `prefers-reduced-motion` est une préférence du système, pas un contrôle de la page. Chaque page
  cosmos porte donc un bouton de pause (`MotionToggle`, `aria-pressed`, nom stable `landing.motion.pause`) dans
  son en-tête — dans le menu mobile sous `sm`, seul dans un coin sur `/demo` qui n'a pas d'en-tête. L'état tient
  en UN attribut, `data-motion="paused"` sur `<html>` (`lib/landing/motion-pause.ts`) : la feuille de style met
  en pause toutes les animations de la portée `.cosmos`, le canvas le lit à chaque frame, les scènes de `/more`
  le partagent (leur bouton et celui de l'en-tête sont un seul interrupteur). Le choix est mémorisé pour le
  visiteur (localStorage, chaque accès protégé) et réappliqué par `CosmicBackdrop` au chargement de chaque page.
- **Couches fixes du cosmos** : `.cosmos` ne porte **pas** de fond — il n'est pas un contexte d'empilement, donc un
  fond posé sur lui se peint au-dessus des couches en `z-index` négatif de `CosmicBackdrop` (nébuleuse, étoiles,
  grain), qui ont ainsi été invisibles sur toutes les pages cosmos jusqu'au 2026-10-02. La nébuleuse fixe peint
  le ciel (`--cosmos-sky`) sur tout le viewport. `isolation: isolate` les aurait révélées aussi, mais aurait fait passer le
  lecteur vidéo (hors de la portée, z 10/40) au-dessus du header (z 50, dedans).
  `PublicFooter` porte donc le fond de la page (`bg-background`). Celui de la landing (`.landing-footer`) est
  transparent et **posé sur la planète du final, qui continue réellement dessous** : le globe dépasse la section
  (`.cosmos-finale`, rognée sur les côtés seulement) d'une portée que le footer, remonté par-dessus, recouvre, et
  le conteneur de la landing (`.landing-page.cosmos-home`, une classe et non `:has()`, absent de certains moteurs
  encore en usage) rogne ce qui dépasse la fin de la page. Une copie de la surface sous le footer a été essayée et
  abandonnée : les nuages animés et la lueur du globe ne se recopient pas, la jonction se voyait. Sous le pied du
  globe (téléphone, où 220vw est plus court que le footer), le fond cosmos prend le relais, de la même teinte.
  Les colonnes de liens reposent sur un **bandeau en verre dépoli** un peu plus sombre (`.landing-footer-band`,
  `--cosmos-footer-veil`, `--cosmos-footer-blur`) qui naît 6rem au-dessus du footer et s'éteint juste avant la
  ligne de copyright ; son masque efface la teinte ET le flou le long d'une rampe smoothstep (une rampe linéaire
  courte se lit comme un trait). Le footer est au plan z 30, après le rail des chapitres et avant les yeux de LIA
  (qui restent devant) ; le rail s'efface quand le footer entre à l'écran (sous le verre, ses liens n'étaient plus
  cliquables). Le fondu est vérifié par mesure, pas seulement à l'œil : profil de luminance ligne à ligne sur des
  bandes sans texte, en clair et sombre, à 1920 et 390 px — aucun saut au-delà de 1,6 niveau hors en-tête et filet
  du copyright. Le **contraste** l'est aussi : en clair, le ciel de la nébuleuse (`--cosmos-sky`) est un cran plus
  soutenu que `--cosmos-bg` (visible, il rendait la page trop lumineuse), ce qui a fait tomber l'encre atténuée à
  4,4:1 sur le verre du footer et 3,5:1 sous un trait du canvas (mesuré le 2026-10-03) ; `--cosmos-mut` a été
  réaccordé dans les deux thèmes, et `styles/__tests__/cosmos-contrast.guard.test.ts` compose le sol, le ciel, la
  lueur, le verre et le trait du canvas pour tenir les deux encres à 4,5:1. Le fond qui masquait les orbites derrière la
  démo du hero n'est dessiné qu'avec le planétarium (`.cosmos-hero-demo`, bords fondus) : éteint, la démo repose
  sur le ciel comme les autres cartes.

---

## 5. Gardes-fous executables

| Garde                      | Fichier                                                                    | Ce qu'il empeche                                                                                                                                                                                                                                                                                                                                                                        |
| -------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Couverture de contenu**  | `editorial/__tests__/editorial-content-coverage.test.ts`                   | La perte silencieuse d'une fiche : les catalogues des chapitres + basics doivent former une **partition exacte** de `REQUIRED_FEATURE_KEYS` (ni perte ni doublon), chaque fiche ayant icone + title/description dans les 6 locales, et chaque `catalog_hint` / `detail_hint` portant `{{count}}` (un chiffre tape a la main y est refuse). Retirer une fiche exige d'editer le contrat. |
| **Compte des catalogues**  | `editorial/__tests__/catalog-hint.test.tsx`                                | Un `catalog_hint` qui annonce un nombre de fiches different de celui du catalogue : `ChapterSection` et `BasicsBand` interpolent `count` depuis la longueur du catalogue, jamais depuis la copie.                                                                                                                                                                                       |
| **Contrat i18n editorial** | `editorial/__tests__/editorial-content-coverage.test.ts`                   | Cle referencee absente/vide dans une des 6 locales ; resurrection des cles purgees (audience, rex, en-tetes features, extras proof) ; disparition des cles `how_it_works` requises par le HowTo JsonLd.                                                                                                                                                                                 |
| **A11y clavier**           | `editorial/__tests__/interactive.test.tsx`                                 | Regression du pattern disclosure (bouton natif, aria-expanded, DOM replie) et du pattern tabs (roles, fleches, bouclage, roving tabindex).                                                                                                                                                                                                                                              |
| **Parite i18n globale**    | `scripts/i18n/validate_translations.py` (hook pre-commit)                  | Toute divergence de cles entre les 6 locales.                                                                                                                                                                                                                                                                                                                                           |
| **Démonstration partagée** | `landing/__tests__/InteractiveChatMockup.test.tsx`                         | Sélection clavier et focus, résultat conservé, pause/relecture, suspension hors écran, nettoyage au démontage, mouvement réduit sans minuterie, noms français/anglais, explications à la demande et rendu complet commun aux chapitres.                                                                                                                                                 |
| **Catalogue visuel**       | `editorial/__tests__/FeatureCatalog.test.tsx`                              | Conservation de tous les textes, une fiche visible à la fois, index et navigation nommés en français/anglais, focus clavier, correspondance complète capacité/illustration et légendes dans les six langues.                                                                                                                                                                            |
| **Routes publiques**       | `src/lib/__tests__/api-client.public-routes.test.ts`                       | Ejection des visiteurs anonymes vers /login.                                                                                                                                                                                                                                                                                                                                            |
| **Overflow mobile**        | `e2e/smoke/landing-mobile-overflow.spec.ts`                                | Débordement horizontal sur mobile : rendu initial, progression de la démonstration, sections et catalogues ouverts, balayage des locales et reflow à 320 px. Une capture statique seule ne couvre pas les états révélés.                                                                                                                                                                |
| **Contenu FAQ groupee**    | `src/lib/__tests__/faq-answer-groups.test.ts`                              | La perte d'un mot lors du regroupement visuel de la reponse « Que puis-je demander ? » : egalite mot-a-mot prouvee sur les 6 locales reelles + repli tel-quel (zh a une q4 differente).                                                                                                                                                                                                 |
| **Axe pages publiques**    | `e2e/a11y/axe-public-pages.spec.ts`                                        | Violations critical/serious (contraste inclus) sur `/faq` (reponse groupee ouverte), `/demo` et `/more` (scanne animee PUIS en pause via le bouton WCAG 2.2.2), en clair ET en sombre — le theme etant pilote par localStorage (`defaultTheme="light"`), emuler le scheme OS ne suffit pas.                                                                                             |
| **Pause des animations**   | `landing/cosmic/__tests__/MotionToggle.test.tsx` + `lib/landing/__tests__/motion-pause.test.ts` | Le mécanisme WCAG 2.2.2 des pages cosmos : bouton natif au nom stable, `aria-pressed` porteur de l'état, clavier, toutes les instances sur l'unique état de `<html>`, choix retenu (et tenu quand le stockage refuse), scènes de `/more` sur le même interrupteur ; le canvas ne redessine plus en pause ni pour le pointeur ou le défilement. |
| **Contraste cosmos**       | `styles/__tests__/cosmos-contrast.guard.test.ts` | Les encres du cosmos (corps et atténuée) à 4,5:1 sur le sol, le ciel, la lueur de la nébuleuse, le verre du pied de page et le trait du canvas, dans les deux thèmes — composés comme le navigateur les empile, depuis les valeurs de `globals.css`. |
| **Contrat /more**          | `landing/more/__tests__/more-content-coverage.test.ts` + `scenes.test.tsx` | La perte silencieuse d'une attention : toutes les cartes des 6 sections, disjointes des fiches majeures (`REQUIRED_FEATURE_KEYS`), chacune avec icone + scene + cles i18n non vides ×6 locales ; apostrophe U+2019 en fr ; **aucun chiffre dans la copie des cartes** (regle anti-derive) ; registre de scenes = partition exacte des cartes.                                           |
| **Overflow mobile /more**  | `e2e/smoke/more-overflow.spec.ts`                                          | Le debordement horizontal pendant les cycles de toutes les scenes : 375 px par battement d'horloge Playwright section par section, balayage statique des 6 locales, plancher reflow 320 px (helper partage `overflow-report.ts`).                                                                                                                                                       |

---

## 6. Internationalisation (i18n)

- 6 langues (fr, en, es, de, it, zh), fallback fr ; parite stricte (hook pre-commit, reference `en`).
- La landing **tutoie** ; les titres a la voix du produit sont **transcrees** par langue, pas traduits.
- Namespaces principaux : `landing.hero.*`, `landing.product_demo.*` (scènes, sources, phases, commandes et
  limites), `landing.editorial.*` (parcours et dépliants), `landing.chapters.*` (c1..c6, bénéfices et mécanismes),
  `landing.catalog_explorer.*` (navigation et légendes), `landing.engineering.*` (principes et bénéfices),
  `landing.tech.*` (choix techniques détaillés), `landing.features.<k>.*` (textes intégraux conservés).
- Les autres surfaces conservent `landing.basics.*`, `landing.transparency.*`, `landing.day.*`,
  `landing.gallery.*`, `landing.rail.*`, `landing.security.*`, `landing.proof.items.*` et `landing.cta.*`.
  `landing.how_it_works.*` reste réservé au HowTo JsonLd ; la section historique n’existe plus.
- Les limites montrées dans les scènes font partie du contrat éditorial : condition d’une routine configurée
  dans les réglages, spécialistes en lecture seule, connexion entre assistants sur le même serveur et données
  explicitement partagées. Les exemples ne garantissent ni exhaustivité des sources, ni délai, ni coût chiffré.

---

## 7. SEO et OpenGraph

- `generateMetadata()` : title/description localises + hreflang ×6 + OG/Twitter (inchange).
- JsonLd : `SoftwareApplicationJsonLd` (featureList ← `LANDING_STATS`), `HowToJsonLd` (← `landing.how_it_works.*`).
- **Contenu depliable et onglets restent dans le DOM** (disclosure replie + panneaux `hidden`) : les descriptions
  detaillees et tous les onglets sont crawlables.
- `public/llms.txt` a maintenir en coherence avec `LANDING_STATS`.

---

## 8. Pages publiques et garde 401

`PUBLIC_ROUTE_SEGMENTS` + test invariant `api-client.public-routes.test.ts` (voir historique v1.21.17). Le test de
completude scanne `app/[lng]` : **toute nouvelle page publique doit etre ajoutee au tableau** (dernier ajout : `more`).

Depuis ADR-181 les 12 pages publiques portent l'identite : `/` et `/more` et `/demo` en scope complet, les huit pages de
lecture (`/story`, `/why`, `/how`, `/faq`, `/changelog`, `/blog` + articles, `/privacy`, `/terms`) en sous-scope
`cosmos-calm`. Les
routes de previsualisation `/cosmos/*` qui ont servi a l'arbitrage ont ete **supprimees** a la bascule — pas de code mort.

### `/more` — « Encore + », les petites attentions UX

`app/[lng]/more/page.tsx` (serveur : metadonnees ×6, BreadcrumbJsonLd, header/footer publics) rend
`components/landing/more/MoreContent` : les micro-attentions de `more-data.ts`, animees en 6 sections « moments » (ecrire, repondre,
imprevus, chercher, quotidien, invisibles), un cran sous les fiches majeures — jamais en doublon (garde de
disjonction). Chaque carte porte une scene decorative (`aria-hidden`) pilotee par `useLoopedTimeline` (timers purs,
jamais `animationend` — jsdom ne le delivre pas), active uniquement dans le viewport ET hors pause : le bouton
pause/lecture (`AnimationPauseToggle`, `aria-pressed`) est le mecanisme WCAG 2.2.2 de la page, et
`prefers-reduced-motion` fige chaque scene sur sa derniere phase (frame de repos concue). Copie native ×6 locales
sous `more.*` ; les chiffres de la bande « Le soin, en chiffres » proviennent exclusivement de `LANDING_STATS`
(protocole de re-mesure par release) — la copie des cartes n'a **aucun** chiffre en dur.

### `/demo` — la démonstration en URL partageable

`app/[lng]/demo/page.tsx` conserve une URL publique sans header, footer ni redirection d’authentification.
La variante illustrative rend `InteractiveChatMockup` avec son CTA, dans le planetarium quand le hero le dessine
(même commutateur `LANDING_PLANETARIUM_ENABLED` : les deux surfaces ne divergent jamais). Le même lecteur que
le hero permet de choisir une scène, de la mettre en pause et de la rejouer ; il reste sur son résultat.
Le choix de variante dans `lib/showroom-config.ts` peut rendre à la place le parcours `GuidedShowroom` :
ce parcours guidé est distinct des illustrations éditoriales.

Les métadonnées localisées gardent canonical, hreflang et carte OpenGraph statique. Pour un export vidéo,
parcourir explicitement les scènes voulues : attendre ne déclenche plus une boucle automatique. Utiliser la même
taille pour le viewport et `recordVideo.size` afin d’éviter la déformation. Ajuster le cadrage et la durée au
parcours enregistré, puis vérifier des images extraites du MP4 final ; les anciens paramètres d’export d’un
cycle complet ne décrivent plus la démonstration. Les artefacts locaux restent sous `exports/`, ignoré par Git.

### FAQ publique (`/faq`)

Refonte 2026-07 au langage visuel de la landing : `PublicFAQContent` (client) — recherche accent-insensible
(`lib/faq-search.ts`, helpers partages avec la FAQ du dashboard), rail de chips d'ancres par section, en-tetes de
section iconises (`components/faq/faq-sections.ts`, registre partage `FAQ_SECTION_ICONS` + `PUBLIC_FAQ_SECTIONS` — 6
sections orientees prospect), accordeons `<details>` natifs, reponses en typographie `prose`. La reponse-fleuve « Que
puis-je demander ? » (~10 k chars) est regroupee **visuellement** en sous-accordeons par domaine via
`lib/faq-answer-groups.ts` — les fichiers de traduction restent intacts (garde de preservation §5).

### Historique des versions (`/changelog`)

`app/[lng]/changelog/page.tsx` (serveur : metadonnees ×6 avec canonical + hreflang, BreadcrumbJsonLd, header/footer
publics, sous-scope `cosmos-calm`) rend `components/changelog/ChangelogHistory` — **composant serveur**, accordeons
`<details>` natifs, zero bundle client, indexable.

La page existe parce que la promesse « Voir tout l'historique » de la bande `#changelog` pointait vers `/faq`, ou
`PublicFAQContent` **ne rend aucun changelog** : l'historique n'a jamais existe que dans la FAQ du dashboard
(`FAQContent`, derriere l'authentification). Un visiteur non connecte n'avait donc acces a l'historique complet nulle
part. `components/__tests__/changelog-destination.test.tsx` epingle desormais la destination des trois surfaces qui la
promettent (bande landing, `LandingFooter`, `PublicFooter`).

Source unique inchangee : `lib/changelog.ts` (`CHANGELOG_VERSION_KEYS`, inventaire des releases) et les traductions
`faq.changelog.*` deja ecrites ×6 — **aucune nouvelle cle i18n**, le titre et le sous-titre de la page reutilisent
`faq.changelog.title` / `faq.changelog.description`. `groupChangelogBySeries` plie la liste par serie mineure
(`v1.30`, `v1.29`…) **sans jamais retrier** : la liste reste seule autorite sur l'ordre. Chaque serie est un `section`
nomme avec son ancre (`#release-1-30`) et un rail de chips en tete de page. La dernière version est ouverte à
l’arrivée ; les versions précédentes sont repliées et se déplient à la demande.

Le header de la landing garde, lui, son ancre vers la bande `#changelog` : c'est un rail de sections avec scroll-spy
(la bande est une section, pas une page) et la contrainte de saturation a 880 px est gardee par
`e2e/smoke/landing-nav-row.spec.ts`. Son entree « Nouveautes » se place **juste apres « Presentation »** (arbitrage
proprietaire 2026-08-19, remplacant « apres Encore + » du 2026-08-18) : `SECTION_ANCHORS` est desormais **une seule
table ordonnee** ou un drapeau `lgOnly` porte l'exclusion de la rangee saturee — `TRAILING_ANCHORS` et ses deux blocs de
rendu ont disparu (`components/landing/__tests__/LandingHeader.test.tsx` epingle l'ordre, la classe responsive et la
parite du menu mobile). Les deux pieds de page, qui listent des **pages**, pointent sur `/changelog`.

Les pages publiques sont declarees **une seule fois** dans `lib/public-pages.ts` (`PUBLIC_PAGES` : chemin,
`changeFrequency`, `priority`) : `sitemap.ts` la consomme telle quelle, `robots.ts` en derive ses `allow` (plus le seul
motif qu'un sitemap ne sait pas exprimer, `/blog/*`) et lit `languages` au lieu d'une copie des six locales. Les deux
fichiers portaient chacun sa liste et avaient **deja diverge** : `/more` et `/demo` etaient sitemappes sans figurer dans
aucune regle `allow`. `NON_INDEXED_SEGMENTS` nomme, avec sa raison, chaque route volontairement non indexable, et
`lib/__tests__/public-pages.test.ts` scanne `app/[lng]` pour exiger que toute route soit d'un cote ou de l'autre (meme
traversee que la garde 401 ci-dessus).

---

## 9. Responsive, theming

- Breakpoints : grilles en `sm:`/`lg:` (rem) ; `mobile:` (px) reserve aux bascules d'affichage — piege documente.
- **Doctrine largeur intrinseque (post-mortem 2026-07)** : un item de grid/flex a `min-width: auto` — une rangee de
  chips sans wrap, un `truncate`/`whitespace-nowrap` sans `min-w-0` dans la chaine, gonflent la piste au-dela du
  viewport mobile (hero coupe a 381-448 px, chapitre 01 a 412 px ; `html` en `overflow-x: hidden` = contenu **coupe
  en silence**, pas de scrollbar). Regle : `min-w-0` sur les items des grilles 2-colonnes (hero, `ChapterSection`),
  `min-w-0` sur les colonnes des scènes, les titres du catalogue et tout élément tronqué en contexte flex,
  `flex-wrap` sur les rangees a effectif variable (badges hero, points des carrousels). Garde executable : le spec
  overflow du §5. **La meme classe a mordu hors landing en v1.25.31** : les onglets des reglages, en grille de
  colonnes egales, poussaient leur libelle hors de leur propre bouton faute de `min-w-0` — coupe au bord de
  l'ecran, invisible. La regle vaut donc pour toute grille a colonnes egales, pas seulement pour la landing.
- Chapitres : colonne unique mobile (texte puis visuel), 2 colonnes des `lg:` ; frise DayTimeline verticale mobile
  (ligne + puces), horizontale des `md:` ; rail chapitres `xl:` uniquement ; onglets wrap.
- Theming : classes semantiques OKLCH du design system, variantes `dark:` ponctuelles (bulles, illustrations).
  Verifier clair ET sombre a chaque refonte.

---

## 10. La vidéo de la landing — un média déclaré par l'opérateur (ADR-330)

Entre le hero et la promesse, une section vidéo n'existe **que si le serveur en cours nomme un répertoire de
médias** : `LANDING_MEDIA_BASE_URL` (lue à la requête, jamais cuite dans l'image — les pages publiques sont
prégénérées et neutres, B03). Le répertoire porte un `manifest.json` (schéma `lib/landing/media.ts` : affiche,
renditions avec leur `type` négocié par le navigateur et un `minWidth` facultatif, rapport d'image, durée, carte
des temps, crédit `https`, drapeau « généré par IA ») ; `GET /api/landing-media` le lit derrière un délai de 3 s et
un cache de 5 min (60 s pour un échec), résout chaque nom NU sous ce seul répertoire, et répond `{ video: null }`
pour tout le reste. `components/landing/video/LandingVideo.tsx` monte alors la section (`#video`, `data-testid`
`landing-video`) — un **emplacement** vide au ratio du clip et la légende ; **l'élément `<video>` lui-même
appartient à la visite** (amendement ADR-330 du 2026-10-01) : `LandingVideoHost`, monté par la mise en page
racine `app/[lng]/layout.tsx` autour de chaque page, garde UN élément, que la section lui confie par contexte
(`landing-video-context.tsx`) ; le lecteur (`LandingVideoPlayer.tsx`, `data-testid` `landing-video-player`,
`data-mode`) est **cadré** sur l'emplacement en coordonnées document (`lib/landing/frame-placement.ts`,
re-mesuré par `ResizeObserver` et au redimensionnement — il défile avec la page, rien à chaque scroll),
**amarré** en bas à gauche (vignette, pause, son, « Revenir à la vidéo » en `Link` vers `/{lng}#video`, fermer)
tant que la musique joue sans cadre à l'écran — autre page publique ou landing défilée —, **caché** muet ou en
pause sans cadre ; il n'existe que sur les pages publiques déclarées (`lib/landing/player-routes.ts`, chaque
route sous `app/[lng]` nommée d'un côté par un test) et s'arrête, en pause puis démonté, sur la connexion, le
dashboard, `/share`. Un changement de langue remonte la mise en page : le lecteur note `{ time, sound }` en
session (`lib/landing/player-session.ts`, deux minutes) et reprend là. Politique de lecture inchangée (en
boucle, sources attachées à 600 px du viewport, lecture **à l'entrée en vue**, jamais sous
`prefers-reduced-motion` ni `Save-Data` ; **le son est voulu par défaut** — décision du propriétaire,
2026-10-01 — avec repli muet sur `NotAllowedError` seul, le bouton son l'indique ; une vidéo muette se met en
pause hors champ ou onglet masqué et reprend au retour ; « pas d'emplacement » se lit « hors champ ») ; aucune
rendition lisible → section et lecteur se retirent. Sous la vidéo : la mention « Vidéo générée par IA » et le
crédit (lien externe, `sr-only` « nouvelle fenêtre »), six langues sous `landing.video.*` (`close` compris).

**Les titres battent sur une carte des temps**, pas sur un micro : `scripts/assets/encode_landing_video.py`
analyse la bande son hors ligne (flux spectral, tempo par fenêtre, suivi dynamique, chaque temps calé sur son
attaque **puis avancé de l'avance de la fenêtre d'analyse** — `ONSET_LEAD_MS`, 72,9 ms, calibré sur une piste de
clics synthétique passée par les fonctions mêmes de l'encodeur : biais 0,0 ms, écart-type 0,5 ms — et **la mesure
votée localement** sur ±16 temps dans la bande basse, `bar_flags`, testé : une égalité ou un passage où personne ne
joue la mesure n'en ouvre aucune, parce qu'un compte depuis le début de la pièce se décale à chaque temps que le
suiveur insère ou saute dans un breakdown) en triplets `[ms, poids, mesure]`, dans un fichier dont le nom porte
l'empreinte du master ET la version de l'analyse (`-beats-v2.json`, `BEAT_ANALYSIS_VERSION` : tout le répertoire est
servi immuable un an) ; la page la charge par `/api/landing-media/beats` dès que la vidéo joue avec le son (pas
quand le son est seulement voulu) et `lib/landing/beat-sync.ts` lit l'horloge de l'image présentée
(`requestVideoFrameCallback`, `mediaTime` ancré sur `expectedDisplayTime` quand le navigateur le donne, repli
`currentTime`), calcule la valeur une image d'écran en avance (`BEAT_PAINT_LEAD_MS`, 16 ms : ce qu'un rappel écrit
n'est peint qu'au vsync suivant) et écrit ses propriétés sur le document (`:root`, `data-beat` pendant la
lecture) : `--beat` (chaque temps), `--beat-bar` (les temps forts seuls), `--beat-hue` (±8° sur un cycle de
quatre mesures), `--beat-progress` et `--beat-turn-0..2` (l'enveloppe du dernier temps de chaque « tour » : le
temps n de la carte revient à la ligne n mod 3, `BEAT_TURNS`) ; les lignes du `h1` du hero (son animation
d'entrée `cosmos-rise`, figée en `forwards`, possède le `transform` du `h1` lui-même) **battent chacune leur
tour** (`.cosmos-hero-title`, `--beat-turn-<n>`, chaque ligne gardant sa propre relâche — demande du
propriétaire, 2026-10-02) et chaque `h2` de **toute page cosmos visitée** lit `--beat`, en `transform` seul —
6 px et 4,5 % sur un temps fort (`--beat-lift`, `--beat-scale`, un seul endroit à régler), plancher 60 % de
l'amplitude pour le temps le plus faible (`BEAT_WEIGHT_FLOOR`), attaque 12 ms, relâche 180 ms, origine selon
l'alignement du titre. **Six effets** s'y ajoutent, son actif seulement, `transform`/`opacity` seuls, rien en
mouvement réduit (choix du propriétaire, 2026-10-01) : le halo de la vidéo (une lueur radiale sans forme,
légère au repos, qui s'intensifie et s'élargit au temps et à la mesure — elle remplace un anneau qui lisait
`--cosmos-glow-violet` hors de `.cosmos` et ne s'est jamais dessiné), le battement du logo du header (`.landing-logo`), la respiration des mots fantômes (sur
leur cadre, le mot gardant la dérive du scroll), le point d'étape actif de la maquette de chat
(`.cosmos-demo-step-dot`), le numéro actif du rail des chapitres (`.cosmos-chapter-rail`), la dérive de
teinte du dégradé signature (`hue-rotate(var(--beat-hue))` sur `.cosmos-grad-text`) et **les yeux de LIA qui
sautent entre deux temps et retombent, écrasés, sur le suivant** (quatrième propriété du pilote,
`--beat-progress` : arc en `sin(π·progress)`, squash depuis les pieds sur l'enveloppe du temps, saut plus haut
après une mesure — sur la racine `.lia-eyes`, que ni le déplacement ni le rig ne transforment). Cadrée, la
vidéo **se fond dans la page** (demande du propriétaire, 2026-10-02) : son cadre est masqué sur ses quatre bords
le long d'une smoothstep (`--edge`, `clamp(0.75rem, 2vw, 1.5rem)` : une fine bande intérieure — plus large, il rognait l'image ; c'est
le halo, dehors, qui fait la transition), le halo l'entoure en permanence
(plus ample en clair, où un fond lumineux avale une lueur — ses couleurs y sont un peu plus légères) sans
jamais élargir la page — placé en coordonnées document, au-dessus du `body` qui rogne l'axe horizontal, il
faisait défiler un écran de 375 px sur 407 (mesuré par les parcours e2e) : le lecteur vit donc dans une
**scène** (`.landing-video-stage`) posée à l'origine du document, qui rogne l'axe horizontal seul
(`overflow-x: clip`, aucun conteneur de défilement) ; amarré, il est fixe et rien ne le rogne —, et l'emplacement
de la section ne dessine plus de boîte (bordure, fond, ombre) — il ne fait que réserver la place, sans quoi le
rectangle effacé par le fondu réapparaissait dessous ; amarrée, la vignette garde ses bords nets. Le fond
« attention + espace latent » (§4) s'éclaire aussi sur le temps : il lit `--beat` sur `<html>` et relève
l'intensité de ses deux couches d'au plus 52,5 %, jamais quand il est figé.

**Plusieurs vidéos, l'une après l'autre** (amendement ADR-330 du 2026-10-03) : le manifeste reste en version 1 et
gagne `next`, la liste des vidéos qui suivent la première dans l'ordre de lecture (au plus `LANDING_MEDIA_MAX_NEXT`),
chacune soumise aux règles de la première. Une version 2 a été écartée : le fichier est lu à l'exécution par le build
que tourne chaque déploiement, et un lecteur antérieur ignore la clé inconnue — il continue de jouer la première vidéo
seule, en boucle —, si bien qu'un même répertoire sert l'ancien et le nouveau code. `/api/landing-media` répond
`{ video, next }` et la carte des temps se demande par rang (`/api/landing-media/beats?video=N`). L'hôte tient le
RANG de la vidéo que porte le lecteur : une vidéo seule boucle, l'une de plusieurs se termine et `ended` passe à la
suivante (puis revient à la première) sur le même élément, qui continue avec le son qu'il avait ; la légende crédite
la vidéo en cours, la carte des temps est la sienne, la reprise de session note `{ video, time, sound }` et ne
s'applique qu'une fois par montage. Une liste re-téléchargée identique est celle déjà tenue : revenir sur la landing
ne recharge plus ce qui joue. Encodage d'une vidéo suivante : `--append` (ajoutée après celles du manifeste de
`--out`, ses provenances à côté des leurs), jamais de variante plus haute que le master (un master 720p n'alimente
que la paire 720p, offerte à toutes les largeurs) et `--copy-h264` quand le master est déjà un H.264 web — mesuré
sur `StopShipping` (1,04 Mbit/s) : le réencoder perdait 7 points de VMAF à débit égal, l'AV1 CRF 42 garde 94,0 à
0,78 Mbit/s.

Le même script écrit les quatre renditions (AV1 et H.264, 1080p pour ≥ 900 px, 720p pour les téléphones), l'affiche,
le manifeste et `PROVENANCE.json`, avec l'empreinte du master dans chaque nom — un cache immuable d'un an est alors
sûr. En dev, un répertoire de fixtures sous `apps/web/public/landing-media-dev/` (ignoré par git) tient lieu
d'origine : `LANDING_MEDIA_BASE_URL=https://localhost:3000/landing-media-dev`. Preuve hermétique :
`e2e/smoke/landing-video.spec.ts` (origine simulée par `page.route` avec des réponses `206` aux requêtes Range —
sans elles le pipeline média de Chromium cale —, clip de deux secondes sous `e2e/fixtures/media/`). Deux mesures
qui ne se devinent pas : la politique d'autoplay est **émulée** (le shell headless ne refuse rien, même sous
`--autoplay-policy=user-gesture-required`) sur un **événement d'entrée réel** (`pointerdown`/`keydown`), jamais sur
`navigator.userActivation` — chaque `evaluate` de Playwright, donc chaque `expect`, vaut un geste pour Chromium
(mesuré : `isActive` faux du chargement au premier `evaluate`, vrai cinq secondes après chacun) ; et le scan axe
attend la fin des animations d'entrée (`FadeInOnScroll`), car scanné en plein fondu il composite un texte translucide
sur le fond et rapporte 61 violations de contraste que personne ne voit.

## 11. Les illustrations du blog — des variantes prégénérées (ADR-330)

Mesuré 2026-10-01 : 28 PNG de 2752×1536 à 6-9 Mo redimensionnés par l'optimiseur sur le Pi (0,4-0,6 s par
variante froide, 4,8 s quand quatorze cartes arrivent ensemble), des réponses `/_next/image` sans extension que
Cloudflare ne met jamais en cache, et une image de partage de 8 Mo refusée par X. Désormais
`apps/web/scripts/build-article-images.mjs <masters>` écrit, par article, quatre WebP (`480, 768, 1024, 1536`) et
un JPEG 1200×675 (`<slug>-og.jpg`) dans `public/articles/` ; `lib/blog/article-images.ts` est l'unique lieu des
noms et des `sizes` (cartes de l'index, grille de la landing, hero de l'article) ; `ArticleIllustration` dessine un
`<img srcset sizes>` (`loading`/`fetchpriority` selon la position) et la page d'article préannonce son hero par
`preload` de React 19. Les masters ne sont pas versionnés (l'historique git garde les 28 d'origine : `git show
<commit>:apps/web/public/articles/<slug>.png`). La garde `data/__tests__/blog-article-images.guard.test.ts` refuse
un slug sans son jeu complet, avec une liste en attente qui ne peut que rétrécir.

---

## Arborescence (extrait)

```
apps/web/src/components/landing/
  InteractiveChatMockup.tsx      # Lecteur à six scènes, commandes et explication à la demande
  demo/
    scenes.ts                   # Catalogue commun des scènes
    ProductScene.tsx             # Illustration et résultat, animés ou complets
    useProductDemo.ts            # Phases, pause, visibilité, mouvement réduit
  cosmic/
    CosmosHero.tsx  CosmosFinale.tsx
    CosmosDay.tsx  ScrollScrub.tsx  PinnedScene.tsx
    AttentionBackdrop.tsx        # Fond animé (lib/landing/attention-background.ts), landing seule
  editorial/
    chapters-data.ts             # Ordre éditorial, scene par chapitre, contrat de contenu
    EditorialChapters.tsx        # Chapitres et scènes partagées
    ChapterSection.tsx           # Bénéfices, mécanisme à la demande, catalogue
    FeatureCatalog.tsx           # Traductions côté serveur
    FeatureExplorer.tsx          # Index accessible et fiche complète
    FeatureScenes.ts            # Capacité → famille d’illustration
    FeatureIllustration.tsx      # Illustrations SVG décoratives
    SecurityDetail.tsx
    CatalogDisclosure.tsx  Tabs.tsx  ChapterRail.tsx
    PromiseSection.tsx  BasicsBand.tsx  TransparencySection.tsx
    DayTimeline.tsx  GallerySection.tsx
    __tests__/                  # Contenu, i18n, catalogue et interactions
  video/
    LandingVideoSection.tsx      # Libellés côté serveur (landing.video.*)
    LandingVideo.tsx             # Section montée sur le descripteur de /api/landing-media, commandes, pilule
    use-landing-video.ts         # Descripteur, mouvement réduit, « proche » / « en vue », page chargée
  UseCasesSection.tsx           # Même catalogue de scènes, liens vers les chapitres
  TechSection.tsx               # Principes visibles, détails dépliables, chiffres sources
  ArchitectureDiagram.tsx
  LandingCarousel.tsx
  ScreenshotsSection.tsx  PresentationSection.tsx
  constants.ts                  # LANDING_STATS
```
