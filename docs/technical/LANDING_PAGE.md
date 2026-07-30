# Landing Page — Documentation technique

> Architecture, composants, i18n, SEO et patterns de la vitrine publique de LIA.
>
> Derniere revision : **identite « LIA Cosmos » (ADR-181)** — tout l'espace public re-skinne par scope CSS, choregraphies pilotees par le scroll, sombre par defaut, registre informel dans les 6 langues — au-dessus de la page publique `/more` « Encore + » (33 micro-attentions animees en 6 moments, pause WCAG 2.2.2, gardes de contenu/overflow/axe dediees, helper overflow partage), du durcissement responsive mobile (doctrine min-w-0 + garde overflow e2e sur le cycle d'animation), de la refonte de la FAQ publique (recherche, 6 sections, reponses groupees), de la page /demo partageable + export MP4, de la garde axe clair/sombre des pages publiques, et de la refonte editoriale « la page parle comme le produit » (hero anime 4 actes + recit en 6 chapitres, catalogues depliables, bande transparence, journees par profil).

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

La landing est le point d'entree public de LIA. Ligne editoriale (refonte 2026-07) : **« la page parle comme le produit »** —
le hero anime le produit (4 actes + coulisses), puis un **recit en 6 chapitres** porte les differenciants, chaque chapitre
ouvrant par une **bulle de chat de LIA** (l'humeur de l'avatar est intentionnelle par chapitre : complice sur la
differenciation, posee sur la confiance). Trois niveaux de lecture :

1. **Le recit** (scroll) : chapitres 01-06, bande commodites, bande transparence, cas d'usage, journees par profil.
2. **Le detail** (clic) : chaque chapitre porte un catalogue depliable contenant les fiches detaillees (l'ex-mur de
   fonctionnalites, re-parente — jamais supprime). Contenu conserve dans le DOM replie → SEO intact.
3. **La profondeur** (liens) : /story, /why, /how, /more, audit public, privacy, blog.

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

Tout vit dans `apps/web/src/components/landing/`, la couche editoriale dans `landing/editorial/`.

### 2.1 Recit editorial (`editorial/`)

| Composant | Type | Description |
|-----------|------|-------------|
| `chapters-data.ts` | data | **Source de verite** : config des 6 chapitres (ancre, humeur, nb de benefices, catalogue), `BASICS_CATALOG`, `BASICS_CHIPS`, `FEATURE_ICONS`, et le contrat `REQUIRED_FEATURE_KEYS` (36 fiches). |
| `EditorialChapters` | Server | Orchestre les 6 chapitres (`id="features"` — ancre historique conservee). Visuels alternes : vignette coulisses (01/03/05) / scene de chat complementaire (02/04) — **jamais** les scenes du hero. |
| `ChapterSection` | Server | Layout d'un chapitre : bulle-titre LIA, eyebrow numerote, H2, sous-titre, 3-4 benefices, ligne « Sous le capot », visuel, catalogue depliable (+ `catalogExtra`). |
| `vignettes.tsx` | Server | Figures coulisses decomposees de l'animation hero : `VignetteOrchestration` (fan-out FOR_EACH), `VignetteSpark` (mail×agenda), `VignetteForge` (skill + rail). Decoratives (`aria-hidden` via ScrollStage). |
| `scenes.tsx` | Server | Mini-scenes de chat : `SceneBriefing` (ch. 02), `SceneEdit` (ch. 04 — HITL en mode modification, complementaire du hero). |
| `FeatureCatalog` | Server | Grille des fiches detaillees — reutilise `landing.features.<k>.{title,description}` existants ×6. |
| `SecurityDetail` | Server | L'ex-section Securite & Vie privee, integrale, dans le depliant du ch. 04 (`landing.security.*`). |
| `CatalogDisclosure` | Client | Depliant accessible (bouton natif, `aria-expanded`, contenu DOM replie via `grid-template-rows`, `inert` replie). |
| `ScrollStage` | Client | Declencheur one-shot : les keyframes fill-both des vignettes restent `animation-play-state: paused` jusqu'a l'arrivee au scroll (delais geles par pause → choregraphie au moment de la revelation). Reduced-motion : durees a zero → etat final instantane. |
| `BasicsBand` | Server | « Et tout le reste, evidemment. » — commodites en chips APRES les chapitres (le pic d'attention post-hero n'est jamais depense sur les basiques) + son propre catalogue depliable (9 fiches commodites). |
| `TransparencySection` | Server | « LIA n'a rien a cacher. » (ancre `#transparency`) : compteur de cout reel en motif de marque, 4 preuves (cout / audit public / open source / REX), ligne beta honnete, **CTA intermediaire** au pic de confiance. |
| `DayTimeline` | Client | « Une journee avec LIA. » — 4 profils en onglets × 4 scenes horodatees (remplace les personas, plus riche : 16 scenes). |
| `GallerySection` | Client | Galerie a onglets fusionnant captures (12) et presentation (15 slides) — 2 sections → 1, contenus intacts. |
| `ChapterRail` | Client | Rail fixe desktop (xl+) : 01-05 + ◈ transparence, scroll-spy, vraie `<nav>` de liens ancres (clavier + SR). |
| `Tabs` | Client | Onglets WAI-ARIA generiques (roving tabindex, fleches, Home/End, panneaux `hidden` mais dans le DOM). |

### 2.2 Sections conservees

| Composant | Type | Notes |
|-----------|------|-------|
| `HeroSection` + `InteractiveChatMockup` (+ `mockup/`) | Server + Client | Hero anime « coulisses en verre », 4 actes (orchestration HITL, initiative meteo, telephonie, skill hydratation), **interactif depuis UX P12** : pastilles de scene, pause/relecture, progression — boucle auto conservee sans interaction ; le CTA du composant est masque dans le hero (`withCta={false}`, le hero a le sien). Voir `mockup/scenarios.ts` (cadence : lisibilite d'abord — vitre 7-8,5 s, notes ≥ 4,5 s). Chevron → `#features`. |
| `UseCasesSection` | Server | 6 requetes reelles (la 6e : telephonie) ; vedettes en tete ET en pied (`example1`, `example6`). |
| `TechSection` | Server | « Sous le capot » + **bande des chiffres d'ingenierie** (ex-ProofSection, re-cibles vers l'audience dev : agents, tools, providers, langues, tests, ADRs, releases). |
| `ArchitectureDiagram` | Client | Deux modes d'execution (inchange). |
| `ScreenshotsSection` / `PresentationSection` | Client | Prop `embedded` : rendu carrousel seul dans la galerie ; le mode section autonome reste disponible. |
| `CtaSection` | Server | CTA final : bulle LIA (le personnage a le dernier mot) + copy voix du produit. |
| `LandingHeader` / `LandingFooter` / `AuthRedirect` / `FadeInOnScroll` / `AnimatedCounter` | — | Inchanges (ancre header → `#features`). |

Sections supprimees par la refonte (contenu re-home, pas perdu) : `ProofSection` (→ transparence + TechSection),
`HowItWorksSection` (demonstre en direct par le hero ; cles i18n conservees pour le HowTo JsonLd), `FeaturesSection`
(→ catalogues des chapitres + bande basics), `AudienceSection` (→ DayTimeline), `RexSection` (→ carte p4 de la
transparence + /story), `SecuritySection` (→ depliant du ch. 04).

---

## 3. Structure de la page

```
AuthRedirect | LandingHeader (fixed) | ChapterRail (fixed, xl+)
<main>
   1. CosmosHero           — plein ecran, demo 4 actes au centre du planetarium, chevron vers #features
   2. EditorialChapters    — id features ; 6 chapitres ancres #chapter-{act,know,anticipate,control,grow,connect}
   3. BasicsBand           — ancre #basics, fond bg-card
   4. TransparencySection  — ancre #transparency, fond bg-card, CTA intermediaire
   5. UseCasesSection      — ancre #use-cases (6 exemples)
   6. CosmosDay            — ancre #day (4 profils en onglets), scene epinglee au scroll
   7. GallerySection       — ancre #gallery (captures | slides)
   8. TechSection          — ancre #technology (+ chiffres d'ingenierie)
   9. ArchitectureDiagram  — ancre #architecture
  10. BlogPreviewSection   — ancre #blog
  11. CosmosFinale         — horizon planetaire (sphere + nuages) + bulle LIA
</main>
ScrollScrub ×11 (drivers `--sp`) | LandingFooter
```

`CosmosDarkFirst` (script pre-paint) et `CosmicBackdrop` encadrent la page ; les deux vivent aussi sur les 10 autres
pages publiques. `AuthRedirect`, `TrackView` et les donnees structurees JSON-LD restent sur `/` uniquement.

Skip-link (`sr-only`) → `#features`. Header : 1 ancre (Presentation → `#features`, scroll spy) + 6 pages
(Story, Philosophie, Technique, Blog, FAQ, Encore +).
Rythme visuel : chapitres alternes (fond transparent / `bg-card` borde), visuel gauche/droite alterne sur desktop.

---

## 4. Animations et interactions

- **Hero (InteractiveChatMockup)** : voir `mockup/` — moteur timeline (`useMockupTimeline.ts`, pause/reprise/
  selection de scene), cadre partage (`MockupStage.tsx`), vitre coulisses ; reduced-motion = frames de resolution
  statiques (les pastilles changent d'acte, pause/relecture masques — rien n'anime).
- **Vignettes de chapitres (ScrollStage)** : reutilisent les keyframes du mockup (`chip-pop`, `wire-draw`, `fan-draw`)
  avec `animation-delay` par element ; gating CSS `.scroll-stage:not(.staged) { animation-play-state: paused }` —
  la pause gele aussi le delai, la choregraphie demarre donc a la revelation. One-shot (unobserve).
- **Depliants (CatalogDisclosure)** : transition `grid-template-rows 0fr → 1fr` (animable sans mesure JS),
  `motion-reduce:transition-none`, contenu `inert` quand replie (non tabbable, mais indexable).
- **Onglets (Tabs)** : pattern WAI-ARIA complet — roving tabindex, ArrowLeft/Right avec bouclage, Home/End,
  panneaux `hidden` conserves dans le DOM.
- **Choregraphies au scroll (ADR-181)** : un driver unique `ScrollScrub` ecrit la progression 0→1 de sa section dans
  `--sp` (une seule boucle rAF passive partagee) ; le CSS du scope en tire des fenetres par tuile. **Reversible** :
  reculer defait l'animation. Le CSS defaut `--sp: 1` (etat final) — sans JS, en SEO et sous reduced-motion, la page
  est complete. Les scenes des 6 chapitres reutilisent **leurs propres `animation-delay` inline** (copies une fois dans
  `--d`) : l'ordre d'origine de chaque scene est conserve, le scroll ne fait que le jouer.
- **Scene epinglee (PinnedScene)** : wrapper haut en `dvh` + enfant sticky, progression `--p` ; jamais d'ancetre
  scrollport (doctrine ADR-171). Mobile (≤880px) et reduced-motion retombent sur le flux vertical classique.
- **Contraste par theme** : le jeton primaire **diverge** — sombre = bleu vif + texte encre, clair = bleu profond sous
  blanc. Un jeton unique blanc-sur-bleu-vif mesurait 3,2:1 (sous AA).
- **Reduced motion** : FadeInOnScroll direct, compteurs instantanes, hero statique, vignettes en etat final, `--sp`
  epingle a 1 (kill-switch global de `globals.css` — toute nouvelle classe animee doit s'y inscrire).

---

## 5. Gardes-fous executables

| Garde | Fichier | Ce qu'il empeche |
|-------|---------|------------------|
| **Couverture de contenu** | `editorial/__tests__/editorial-content-coverage.test.ts` | La perte silencieuse d'une fiche : les catalogues des chapitres + basics doivent former une **partition exacte** de `REQUIRED_FEATURE_KEYS` (36 fiches, ni perte ni doublon), chaque fiche ayant icone + title/description dans les 6 locales. Retirer une fiche exige d'editer le contrat. |
| **Contrat i18n editorial** | idem | Cle referencee absente/vide dans une des 6 locales ; resurrection des cles purgees (audience, rex, en-tetes features, extras proof) ; disparition des cles `how_it_works` requises par le HowTo JsonLd. |
| **A11y clavier** | `editorial/__tests__/interactive.test.tsx` | Regression du pattern disclosure (bouton natif, aria-expanded, DOM replie) et du pattern tabs (roles, fleches, bouclage, roving tabindex). |
| **Parite i18n globale** | `scripts/i18n/validate_translations.py` (hook pre-commit) | Toute divergence de cles entre les 6 locales. |
| **Contrat hero** | `landing/__tests__/InteractiveChatMockup.test.tsx` + `mockup/__tests__/scenarios.test.ts` | Timelines mal formees, cles du mockup manquantes, regression reduced-motion, controles (selection de scene, pause/relecture, gel manuel en fin d'acte), CTA duplique dans le hero. |
| **Routes publiques** | `src/lib/__tests__/api-client.public-routes.test.ts` | Ejection des visiteurs anonymes vers /login. |
| **Overflow mobile** | `e2e/smoke/landing-mobile-overflow.spec.ts` | Le retour du debordement horizontal : a 375 px, aucun element en flux ne depasse le bord droit — statiquement, **a chaque battement du cycle d'animation du hero** (horloge Playwright, ~79 s virtuelles : l'oscillation 381↔448 px de 2026-07 etait invisible en capture statique) et apres scroll de chaque section ; passe reflow 320 px (WCAG 1.4.10). |
| **Contenu FAQ groupee** | `src/lib/__tests__/faq-answer-groups.test.ts` | La perte d'un mot lors du regroupement visuel de la reponse « Que puis-je demander ? » : egalite mot-a-mot prouvee sur les 6 locales reelles + repli tel-quel (zh a une q4 differente). |
| **Axe pages publiques** | `e2e/a11y/axe-public-pages.spec.ts` | Violations critical/serious (contraste inclus) sur `/faq` (reponse groupee ouverte), `/demo` et `/more` (scanne animee PUIS en pause via le bouton WCAG 2.2.2), en clair ET en sombre — le theme etant pilote par localStorage (`defaultTheme="light"`), emuler le scheme OS ne suffit pas. |
| **Contrat /more** | `landing/more/__tests__/more-content-coverage.test.ts` + `scenes.test.tsx` | La perte silencieuse d'une attention : 26 cartes en 6 sections, disjointes des 36 fiches majeures (`REQUIRED_FEATURE_KEYS`), chacune avec icone + scene + cles i18n non vides ×6 locales ; apostrophe U+2019 en fr ; **aucun chiffre dans la copie des cartes** (regle anti-derive) ; registre de scenes = partition exacte des cartes. |
| **Overflow mobile /more** | `e2e/smoke/more-overflow.spec.ts` | Le debordement horizontal pendant les cycles des 26 scenes : 375 px par battement d'horloge Playwright section par section, balayage statique des 6 locales, plancher reflow 320 px (helper partage `overflow-report.ts`). |

---

## 6. Internationalisation (i18n)

- 6 langues (fr, en, es, de, it, zh), fallback fr ; parite stricte (hook pre-commit, reference `en`).
- La landing **tutoie** ; les titres a la voix du produit sont **transcrees** par langue, pas traduits.
- Namespaces principaux : `landing.hero.*`, `landing.chat_mockup.*` (hero, 72 cles), `landing.chapters.*`
  (recit : partages + c1..c5 avec benefices/vignettes/scenes), `landing.basics.*`, `landing.transparency.*`,
  `landing.day.*` (4 profils × 4 scenes), `landing.gallery.*`, `landing.rail.*`, `landing.features.<k>.*`
  (fiches detaillees reutilisees), `landing.security.*` (depliant ch. 04), `landing.proof.items.*` (chiffres,
  affiches par TechSection), `landing.use_cases.*` (6 exemples), `landing.cta.*`, `landing.how_it_works.*`
  (**reserve JsonLd** — la section n'existe plus).

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

Depuis ADR-181 les 11 pages publiques portent l'identite : `/` et `/more` et `/demo` en scope complet, les sept pages de
lecture (`/story`, `/why`, `/how`, `/faq`, `/blog` + articles, `/privacy`, `/terms`) en sous-scope `cosmos-calm`. Les
routes de previsualisation `/cosmos/*` qui ont servi a l'arbitrage ont ete **supprimees** a la bascule — pas de code mort.

### `/more` — « Encore + », les petites attentions UX

`app/[lng]/more/page.tsx` (serveur : metadonnees ×6, BreadcrumbJsonLd, header/footer publics) rend
`components/landing/more/MoreContent` : 33 micro-attentions animees en 6 sections « moments » (ecrire, repondre,
imprevus, chercher, quotidien, invisibles), un cran sous les 36 fiches majeures — jamais en doublon (garde de
disjonction). Chaque carte porte une scene decorative (`aria-hidden`) pilotee par `useLoopedTimeline` (timers purs,
jamais `animationend` — jsdom ne le delivre pas), active uniquement dans le viewport ET hors pause : le bouton
pause/lecture (`AnimationPauseToggle`, `aria-pressed`) est le mecanisme WCAG 2.2.2 de la page, et
`prefers-reduced-motion` fige chaque scene sur sa derniere phase (frame de repos concue). Copie native ×6 locales
sous `more.*` ; les chiffres de la bande « Le soin, en chiffres » proviennent exclusivement de `LANDING_STATS`
(protocole de re-mesure par release) — la copie des cartes n'a **aucun** chiffre en dur.

### `/demo` — l'animation du hero en URL partageable

`app/[lng]/demo/page.tsx` rend `InteractiveChatMockup` avec son CTA au centre du **planetarium** (scope cosmos, ni header,
ni footer, ni `AuthRedirect`) —
concu pour etre poste sur les reseaux sociaux et integre dans des publications. Metadonnees dediees (hreflang ×6,
canonical, OG) **sans nouvelle cle i18n** : le titre reutilise `landing.meta.title`, la description reutilise
`landing.chat_mockup.aria`. Un partage social affiche la carte OG statique ; pour l'animation dans le fil, generer un
MP4 depuis cette page. PIEGE Playwright : si `recordVideo.size` differe du viewport, le rescale produit une video
ecrasee horizontalement avec bande grise — enregistrer avec **viewport = recordVideo.size = 1080×1350** (dsf 1), le
contenu agrandi via `transform: scale(2.2)` sur `main > div.w-full` (un zoom body casse le centrage flex), overlay
`nextjs-portal` masque ; puis ffmpeg H.264 (`-ss 1.6 -t 79.2 -crf 20 -pix_fmt yuv420p`). Toujours verifier en
extrayant des frames du MP4 final (`ffmpeg -ss N -vframes 1`), jamais ffprobe seul. Artefacts locaux sous `exports/`,
gitignore.

### FAQ publique (`/faq`)

Refonte 2026-07 au langage visuel de la landing : `PublicFAQContent` (client) — recherche accent-insensible
(`lib/faq-search.ts`, helpers partages avec la FAQ du dashboard), rail de chips d'ancres par section, en-tetes de
section iconises (`components/faq/faq-sections.ts`, registre partage `FAQ_SECTION_ICONS` + `PUBLIC_FAQ_SECTIONS` — 6
sections orientees prospect), accordeons `<details>` natifs, reponses en typographie `prose`. La reponse-fleuve « Que
puis-je demander ? » (~10 k chars) est regroupee **visuellement** en sous-accordeons par domaine via
`lib/faq-answer-groups.ts` — les fichiers de traduction restent intacts (garde de preservation §5).

---

## 9. Responsive, theming

- Breakpoints : grilles en `sm:`/`lg:` (rem) ; `mobile:` (px) reserve aux bascules d'affichage — piege documente.
- **Doctrine largeur intrinseque (post-mortem 2026-07)** : un item de grid/flex a `min-width: auto` — une rangee de
  chips sans wrap, un `truncate`/`whitespace-nowrap` sans `min-w-0` dans la chaine, gonflent la piste au-dela du
  viewport mobile (hero coupe a 381-448 px, chapitre 01 a 412 px ; `html` en `overflow-x: hidden` = contenu **coupe
  en silence**, pas de scrollbar). Regle : `min-w-0` sur les items des grilles 2-colonnes (hero, `ChapterSection`),
  `min-w-0` sur tout element `truncate` en contexte flex (input du mockup, pilules requete, chips backstage/vignettes),
  `flex-wrap` sur les rangees a effectif variable (badges hero, points des carrousels). Garde executable : le spec
  overflow du §5. **La meme classe a mordu hors landing en v1.25.31** : les onglets des reglages, en grille de
  colonnes egales, poussaient leur libelle hors de leur propre bouton faute de `min-w-0` — coupe au bord de
  l'ecran, invisible. La regle vaut donc pour toute grille a colonnes egales, pas seulement pour la landing.
- Chapitres : colonne unique mobile (texte puis visuel), 2 colonnes des `lg:` ; frise DayTimeline verticale mobile
  (ligne + puces), horizontale des `md:` ; rail chapitres `xl:` uniquement ; onglets wrap.
- Theming : classes semantiques OKLCH du design system, variantes `dark:` ponctuelles (bulles, vignettes).
  Verifier clair ET sombre a chaque refonte.

---

## Arborescence (extrait)

```
apps/web/src/components/landing/
  index.ts                       # Barrel exports
  HeroSection.tsx                # Hero (chevron → #features)
  InteractiveChatMockup.tsx  mockup/  # Demo 4 actes + coulisses + controles (scenarios, moteur, stage, actes)
  editorial/
    chapters-data.ts             # Source de verite + contrat REQUIRED_FEATURE_KEYS
    EditorialChapters.tsx        # Les 6 chapitres
    ChapterSection.tsx           # Layout chapitre (bulle-titre LIA)
    vignettes.tsx  scenes.tsx    # Coulisses decomposees / scenes complementaires
    FeatureCatalog.tsx           # Fiches detaillees (reutilise landing.features.*)
    SecurityDetail.tsx           # Ex-section securite (depliant ch. 04)
    CatalogDisclosure.tsx  Tabs.tsx  ScrollStage.tsx  ChapterRail.tsx
    BasicsBand.tsx  TransparencySection.tsx  DayTimeline.tsx  GallerySection.tsx
    __tests__/                   # Gardes-fous (couverture, i18n, a11y)
  UseCasesSection.tsx            # 6 requetes reelles
  TechSection.tsx                # Sous le capot + chiffres d'ingenierie
  ArchitectureDiagram.tsx  ScreenshotsSection.tsx  PresentationSection.tsx  (embedded)
  CtaSection.tsx                 # CTA final (bulle LIA)
  constants.ts                   # LANDING_STATS (chiffres sources)
```
