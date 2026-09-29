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
| `cosmic/CosmosHero`                                                                       | Server | Hero Cosmos et démonstration partagée dans le planetarium ; CTA propre et lien vers `#features`.                                                                                                                                                 |
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
La variante illustrative rend `InteractiveChatMockup` avec son CTA dans le planetarium. Le même lecteur que
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
  UseCasesSection.tsx           # Même catalogue de scènes, liens vers les chapitres
  TechSection.tsx               # Principes visibles, détails dépliables, chiffres sources
  ArchitectureDiagram.tsx
  LandingCarousel.tsx
  ScreenshotsSection.tsx  PresentationSection.tsx
  constants.ts                  # LANDING_STATS
```
