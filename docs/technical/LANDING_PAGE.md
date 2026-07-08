# Landing Page — Documentation technique

> Architecture, composants, i18n, SEO et patterns de la vitrine publique de LIA.
>
> Derniere revision : v1.21.17 (refonte hero/preuve/diagramme, page /story, fix visiteurs anonymes).

---

## Table des matieres

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture des composants](#2-architecture-des-composants)
3. [Structure de la page](#3-structure-de-la-page)
4. [Animations et interactions](#4-animations-et-interactions)
5. [Internationalisation (i18n)](#5-internationalisation-i18n)
6. [SEO et OpenGraph](#6-seo-et-opengraph)
7. [Pages publiques et garde 401](#7-pages-publiques-et-garde-401)
8. [Responsive Design](#8-responsive-design)
9. [Theming](#9-theming)

---

## 1. Vue d'ensemble

La landing page est le point d'entree public de l'application LIA. Elle sert a :

- **Montrer le produit** : demo de conversation animee dans le hero (3 scenarios refletant les vrais modes d'affichage), diagramme fidele des deux modes d'execution, cas d'usage
- **Prouver la qualite** : bande de preuve (chiffres d'ingenierie sources du codebase), section Retour d'experience renvoyant vers la page `/story`
- **Convertir les visiteurs** : CTA vers l'inscription (`/register`) et la connexion (`/login`)
- **Rediriger les utilisateurs authentifies** : vers le dashboard automatiquement

La page est un composant serveur async (`async function HomePage`) qui initialise l'i18n cote serveur et delegue le rendu a 14 sections modulaires. Les composants interactifs (header, demo chat, diagramme, compteurs, screenshots) sont marques `'use client'`.

**Regle d'or des chiffres** : toute statistique publique vit dans `constants.ts` (`LANDING_STATS`), dont la docstring documente la source canonique de chaque nombre dans le codebase (ex. providers = le `Literal ProviderType`, tools = les `ToolManifest`). Ne jamais inliner un chiffre dans une cle i18n sans le sourcer.

La page `/story` (retour d'experience, 6 langues) suit le pattern des guides /why et /how : contenu markdown `story.{lng}.md` charge par `StoryContent`, TOC, hreflang, sitemap, robots.

---

## 2. Architecture des composants

Tous les composants sont dans `apps/web/src/components/landing/` et reexportes via `index.ts`.

### 2.1 Composants de section (contenu)

| Composant | Fichier | Type | Props | Description |
|-----------|---------|------|-------|-------------|
| `HeroSection` | `HeroSection.tsx` | Server (async) | `lng: string` | Hero scinde : colonne texte (badges BETA/Open Source + version/date de mise a jour, tagline 3 lignes, sous-titres, 2 CTA, trust badges 19+/7/99+/GDPR) et colonne demo (`ChatMockup`). Fond ambient (3 halos degrades + fade bas), plus d'image de fond. |
| `ProofSection` | `ProofSection.tsx` | Client | `lng: string` | Bande de preuve (ancre `#proof`, cible du chevron hero) : 8 chiffres verifiables (agents, tools, providers, langues vocales, tests, ADRs, releases, score d'audit) + teaser vers `/story`. Compteurs `AnimatedCounter`, valeur finale rendue en SSR. |
| `HowItWorksSection` | `HowItWorksSection.tsx` | Server (async) | `lng: string` | Timeline en 4 etapes (question, planification, validation HITL, execution). |
| `ScreenshotsSection` | `ScreenshotsSection.tsx` | Client | aucune | Carrousel de 12 captures dans un cadre adapte au format portrait (`h-[480px] mobile:h-[620px]`, `object-contain` — les captures font ~0.65-0.88 de ratio), fleches au hover, vignettes desktop, dots mobile. |
| `FeaturesSection` | `FeaturesSection.tsx` | Server (async) | `lng: string` | 3 etages : **Hero features** (4 cartes accentuees : connecteurs, smart home, web intelligence, voix), **5 groupes fonctionnels** (conversation, personnalite, proactivite — avec la carte Briefing du jour —, creation, extensibilite) en grille `sm:grid-cols-2 lg:grid-cols-3`, **Responsible features** (6 cartes). Breakpoints rem uniquement : le variant custom `mobile:` (px) ne s'ordonne pas fiablement contre `sm:` sur la meme propriete. |
| `ArchitectureDiagram` | `ArchitectureDiagram.tsx` | Client | aucune | Diagramme des deux modes d'execution, fidele a la topologie LangGraph (ADR-070) : entree Requete → Routeur, fourche « ou » vers deux panneaux cote a cote — Pipeline (5 etapes numerotees verticales, etape Approbation surlignee ambre, badge « 4 a 8x moins de tokens ») et ReAct (boucle Raisonne → Agit → Observe, badge « autonomie maximale ») — convergence vers Reponse (streaming token par token). Vertical sur mobile. |
| `PresentationSection` | `PresentationSection.tsx` | Client | aucune | Carrousel de 15 slides (`/presentation/slide-XX.png`). |
| `UseCasesSection` | `UseCasesSection.tsx` | Server (async) | `lng: string` | 5 exemples : 1 carte vedette pleine largeur + grille 2x2. Plus de zigzag/timeline (gaspillait 50% de la largeur). |
| `AudienceSection` | `AudienceSection.tsx` | Server (async) | `lng: string` | 4 personas (freelance, famille, developpeur, administrateur). |
| `RexSection` | `RexSection.tsx` | Server (async) | `lng: string` | Retour d'experience (ancre `#story`) : eyebrow, titre, citation signature, 4 KPIs durables (lignes de code, ~100% IA, tests, audit), corps, CTA vers `/story`. |
| `SecuritySection` | `SecuritySection.tsx` | Server (async) | `lng: string` | Visuel bouclier + 4 piliers de securite. |
| `TechSection` | `TechSection.tsx` | Server (async) | `lng: string` | Intro « systeme d'orchestration » (2 paragraphes, sans redondance avec le diagramme) + grille de cartes techniques (LangGraph, 7 providers, bayesien, recherche hybride, temps reel, stack, rich skills, HITL). |
| `BlogPreviewSection` | `BlogPreviewSection.tsx` | Server (async) | `lng: string` | Apercu des articles de blog. |
| `CtaSection` | `CtaSection.tsx` | Server (async) | `lng: string` | CTA final degrade bleu/violet, note « production 24/7, beta gratuite », lien philosophie. |

### 2.2 Composants structurels

| Composant | Fichier | Type | Props | Description |
|-----------|---------|------|-------|-------------|
| `LandingHeader` | `LandingHeader.tsx` | Client | `lng: string` | Header fixe : ancre Presentation (scroll spy) + 5 liens de pages dans l'ordre **Story, Philosophie, Technique, Blog, FAQ**, selecteur de langue, toggle theme, login/register. Menu hamburger mobile. Effet `glass` au scroll. |
| `LandingFooter` | `LandingFooter.tsx` | Server (async) | `lng: string` | 4 colonnes (Produit, Ressources — meme ordre que le header —, Legal, Communaute), copyright + version. |

### 2.3 Composants utilitaires

| Composant | Fichier | Type | Props | Description |
|-----------|---------|------|-------|-------------|
| `FadeInOnScroll` | `FadeInOnScroll.tsx` | Client | `children`, `className?`, `delay?`, `threshold?` | Fade-in + slide-up via `IntersectionObserver`. Seuil par defaut **0.01** + `rootMargin: '0px 0px -10% 0px'` — un seuil fractionnel type 0.15 exigeait des centaines de px visibles sur les sections hautes (features ~3900px) avant de reveler quoi que ce soit. One-shot. |
| `AnimatedCounter` | `AnimatedCounter.tsx` | Client | `target`, `suffix?`, `duration?`, `locale?` | **Rend la valeur finale au premier rendu** (SSR, no-JS, crawlers voient les vrais chiffres) puis anime 0 → target a l'intersection. Formatage localise optionnel via `toLocaleString(locale)` (ex. 10 000 vs 10,000). |
| `ChatMockup` | `ChatMockup.tsx` | Client | aucune | Demo de conversation du hero. **3 scenarios en rotation**, chacun refletant un vrai mode d'affichage avec son chip de barre de titre : HITL (email humoristique, carte brouillon, boutons Envoyer/Modifier, approbation), Cartes HTML (carte meteo riche + bulle d'initiative proactive inter-domaines), Markdown (recherche multi-agents, reponse en liste numerotee). Boucle par timeouts (`STEP_TIMINGS`/`holdMs` par scenario), fondu entre scenarios. `prefers-reduced-motion` : scenario 1 statique, sans boucle. `role="img"` + aria localise, boutons decoratifs en `<span>`. |
| `ConstellationBackground` | `ConstellationBackground.tsx` | Client | aucune | SVG constellation (disponible via index.ts). |
| `AuthRedirect` | `AuthRedirect.tsx` | Client | `lng: string` | Invisible ; redirige les utilisateurs authentifies vers `/{lng}/dashboard`. |

Composants supprimes en v1.21.17 : `HeroBackground` (image de fond remplacee par la demo ; le hook `useLiaGender` reste utilise par le dashboard et le chat) et `StatsSection` (remplace par `ProofSection`).

---

## 3. Structure de la page

L'ordre des sections dans `page.tsx` :

```
AuthRedirect (invisible, redirect si authentifie)
|
LandingHeader (fixed, z-50)
|
<main>
   1. HeroSection          — plein ecran, demo chat, chevron vers #proof
   2. ProofSection         — ancre #proof, fond bg-primary/5
   3. HowItWorksSection    — ancre #how-it-works
   4. ScreenshotsSection   — ancre #screenshots, fond bg-card
   5. FeaturesSection      — ancre #features
   6. ArchitectureDiagram  — ancre #architecture
   7. PresentationSection  — ancre #presentation
   8. UseCasesSection      — ancre #use-cases, fond bg-card
   9. AudienceSection      — personas
  10. RexSection           — ancre #story, fond bg-card
  11. SecuritySection      — ancre #security
  12. TechSection          — ancre #technology
  13. BlogPreviewSection   — ancre #blog
  14. CtaSection           — fond degrade bleu/violet
</main>
|
LandingFooter
```

Le lien "Skip to content" (`sr-only`) pointe vers `#features`.

Navigation header : 1 ancre (Presentation → `#how-it-works`, scroll spy `IntersectionObserver` avec `rootMargin: '-20% 0px -70% 0px'`) + 5 pages : `/story`, `/why`, `/how`, `/blog`, `/faq`.

---

## 4. Animations et interactions

### 4.1 FadeInOnScroll

- `IntersectionObserver`, seuil 0.01 + `rootMargin '0px 0px -10% 0px'` : la section se revele des que son bord franchit les 90% bas du viewport, quelle que soit sa hauteur.
- Prop `delay` en ms (`animationDelay` inline). One-shot (`unobserve` apres declenchement).

### 4.2 AnimatedCounter

- Premier rendu = valeur finale (pas de « 0+ » pour les crawlers/captures pleine page). A l'intersection (seuil 30%), `requestAnimationFrame` anime 0 → target avec easing cubic ease-out (2000ms par defaut).
- `locale` optionnel pour le formatage (`ProofSection` passe la langue i18n active pour les milliers).

### 4.3 ChatMockup (demo du hero)

- `SCENARIOS` : tableau de scenarios `{chip, steps: [{kind, at}], holdMs}`. Kinds : `user`, `planning`, `status`, `hitl`, `approve`, `done`, `weather`, `initiative`, `markdown`.
- Sequencement par `setTimeout` (un timer par etape + hold + fondu de 600ms), rotation infinie scenario 1 → 2 → 3 → 1.
- Indicateur de frappe (3 points) entre le message utilisateur et la premiere reponse LIA.
- Cartes fideles au produit : `WeatherCard` (header degrade, temperature, 3 creneaux matin/apres-midi/soir), `MarkdownReply` (liste numerotee, noms en gras, notes ★), carte brouillon HITL (objet d'email + boutons Envoyer/Modifier avec effet « presse » a l'approbation).
- Le chip de la barre de titre change avec le scenario : HITL / Cartes HTML / Markdown (cles `landing.chat_mockup.chip_*`).

### 4.4 Accessibilite des animations

Tous les composants animes respectent `prefers-reduced-motion: reduce` :
- `FadeInOnScroll` : affiche directement sans animation.
- `AnimatedCounter` : valeur finale instantanee.
- `ChatMockup` : scenario 1 rendu statique en entier, pas de boucle.
- Boucle `RefreshCw` du diagramme : `motion-safe:animate-spin` uniquement.

---

## 5. Internationalisation (i18n)

### 5.1 Mecanisme

- **6 langues** : fr, en, es, de, it, zh (fallback : fr). Route dynamique `[lng]`, validee via `validateLanguage`.
- **Registre editorial** : la landing francaise **tutoie** (decision v1.21.17, appliquee sur tout le namespace `landing.*`) ; la FAQ applicative vouvoie. Ne pas melanger.

### 5.2 Composants serveur

Les composants `async` utilisent `const { t } = await initI18next(lng);`. Namespaces `landing.*` principaux :
- `landing.meta.*` — metadata SEO
- `landing.hero.*` — hero (title_line1/2/3, subtitle, badges, CTA, trust)
- `landing.chat_mockup.*` — demo : scenario 1 (`user_message`, `lia_planning`, `lia_hitl`, `draft_subject`, `btn_send`, `btn_edit`, `user_approve`, `lia_done`), scenario 2 (`s2_user_message`, `s2_card_*`, `s2_slot_*`, `s2_initiative`), scenario 3 (`s3_user_message`, `s3_status`, `s3_md_*`), chips (`chip_hitl`, `chip_cards`, `chip_markdown`), `aria`
- `landing.proof.*` — bande de preuve (`title`, `items.*`, `audit_value`, `rex_teaser`, `rex_link`)
- `landing.features.*` — fonctionnalites (dont `briefing`)
- `landing.how_it_works.step1-4.*` — etapes
- `landing.use_cases.example1-5.*` — cas d'usage
- `landing.rex.*` — retour d'experience (`eyebrow`, `title`, `quote`, `kpis.{lines,ai,tests,audit}.{value,label}`, `body`, `cta`)
- `landing.architecture.*` — diagramme (`nodes.*` dont `reason`/`tools`/`observe`, `pipeline_label/badge/desc`, `react_label/badge/desc`, `or_label`, `response_hint`)
- `landing.security.*`, `landing.tech.*`, `landing.cta.*`, `landing.nav.*` (dont `story`), `landing.footer.*` (dont `story`)

Le namespace `story.*` (top-level) porte la page /story : `meta.*`, `breadcrumb`, `hero.*`, `toc.*`.

### 5.3 Composants client

`'use client'` (LandingHeader, ProofSection, ArchitectureDiagram, ChatMockup, ScreenshotsSection, PresentationSection) : `const { t } = useTranslation();` via le provider du layout parent.

### 5.4 Fichiers de traduction

`apps/web/locales/{lng}/translation.json` — parite stricte des cles imposee par le hook pre-commit (reference : `en`).

---

## 6. SEO et OpenGraph

### 6.1 Metadata dynamique

`generateMetadata()` produit title/description localises + `alternates.languages` (hreflang ×6 + x-default) + OpenGraph/Twitter. Idem pour `/story`, `/why`, `/how`, `/blog`.

### 6.2 JsonLd

`components/seo/JsonLd.tsx` : `WebSiteJsonLd`, `OrganizationJsonLd` (sameAs → `github.com/jgouviergmail/LIA-Assistant`), `SoftwareApplicationJsonLd` (featureList derivee de `LANDING_STATS`, `softwareVersion` = `APP_VERSION` — jamais en dur), `HowToJsonLd`, breadcrumbs. Serialisation via `serializeJsonLd` (echappement `<`).

### 6.3 Image OpenGraph

`app/[lng]/opengraph-image.tsx` — Edge runtime, 1200x630, taglines localisees ×6.

### 6.4 llms.txt

`public/llms.txt` : resume du produit a destination des crawlers IA (features, architecture, liens — dont /story). A maintenir en coherence avec `LANDING_STATS` a chaque release.

---

## 7. Pages publiques et garde 401

Le `AuthProvider` du layout racine sonde `/auth/me` sur chaque page ; pour un visiteur anonyme la reponse est 401. Le handler 401 de `api-client.ts` redirige vers `/login` **sauf** si `isPublicPath(pathname)` est vrai.

- `PUBLIC_ROUTE_SEGMENTS` (api-client.ts) : liste nommee et documentee des segments publics (pages auth + `/why`, `/how`, `/story`, `/blog`, `/faq`, `/privacy`, `/terms`) ; `isPublicPath` matche avec ou sans prefixe de langue + la racine.
- **Invariant executables** : `src/lib/__tests__/api-client.public-routes.test.ts` (31 tests) epingle les comportements public/protege, refuse le matching par prefixe (`/blogus`), et **scanne `app/[lng]/`** : tout repertoire de page hors ensemble authentifie (`dashboard`, `account-inactive`) doit etre couvert — ajouter une page publique sans mettre a jour la liste fait echouer la CI.
- Historique : avant v1.21.17 la liste ne couvrait que login/register/racine — tout visiteur anonyme ouvrant /why, /how, /blog ou /faq etait ejecte vers /login au bout de quelques secondes (invisible pour les developpeurs, toujours porteurs d'un cookie de session).

`AuthRedirect` reste le pendant inverse (utilisateur connecte → dashboard).

---

## 8. Responsive Design

### 8.1 Breakpoints

| Prefix | Usage dans la landing |
|--------|-----------------------|
| (defaut) | Mobile portrait — colonne unique |
| `sm:` | ~640px — grilles 2 colonnes |
| `lg:` | ~1024px — grilles 3-4 colonnes, hero scinde (`lg:grid-cols-[1.05fr_0.95fr]`), texte 7xl |
| `mobile:` | Breakpoint custom 880px (px) — navigation horizontale, hauteurs du cadre screenshots |

**Piege connu** : `mobile:` est declare en px, les breakpoints par defaut en rem — quand les deux ciblent la meme propriete, l'ordre d'emission CSS n'est pas garanti par la valeur. Pour les grilles, utiliser exclusivement les breakpoints rem (`sm:`/`lg:`), reserver `mobile:` aux bascules d'affichage (`hidden mobile:flex`).

### 8.2 Patterns responsives

- **HeroSection** : colonne unique mobile (texte centre, demo dessous), scinde a partir de `lg:`.
- **ProofSection** : `grid-cols-2 sm:grid-cols-4 mobile:grid-cols-8`.
- **ArchitectureDiagram** : panneaux empiles mobile, cote a cote avec divider « ou » a partir de `sm:`.
- **FeaturesSection** : `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3` (groupes), `lg:grid-cols-4` (hero features).
- **UseCasesSection** : vedette pleine largeur + `sm:grid-cols-2`.
- **Header** : navigation inline (`hidden mobile:flex`), hamburger (`mobile:hidden`).

### 8.3 Textes adaptatifs

Hero : `text-5xl` → `mobile:text-6xl` → `lg:text-7xl`.

---

## 9. Theming

### 9.1 TailwindCSS 4 et OKLCH

Classes semantiques du design system (`bg-background`, `text-foreground`, `bg-card`, `bg-primary/5`, `border-border/60`, `text-gradient-brand`, degrades `from-*/to-*`).

### 9.2 Dark mode

Gere par les variables CSS + variantes `dark:` ponctuelles (bulles HITL/success/initiative du ChatMockup, badges du diagramme). Verifie visuellement en clair ET en sombre a chaque refonte.

### 9.3 Effets visuels custom

| Classe | Description |
|--------|-------------|
| `glass` | Glassmorphism (`backdrop-blur` + fond semi-transparent) |
| `hover-lift` / `hover-glow` | Elevation / glow au hover |
| `animate-fade-in-up` | Fade-in + translate-y |
| `animate-bounce-scroll` | Bounce du chevron hero |
| `animate-chat-bubble` | Apparition des bulles de la demo |
| `text-gradient-brand` | Gradient de texte hero |
| `landing-section` | Base des sections (espacement, overflow) |

### 9.4 Toggle de theme

`ThemeToggle` integre au `LandingHeader` (desktop et mobile).

---

## Arborescence des fichiers

```
apps/web/src/
  app/[lng]/
    page.tsx                          # Page principale (Server Component)
    opengraph-image.tsx               # Image OG (Edge Runtime)
    story/page.tsx                    # Page /story (pattern guides why/how)
  components/landing/
    index.ts                          # Barrel exports (18 composants)
    AuthRedirect.tsx                  # Redirect si authentifie
    LandingHeader.tsx                 # Header fixe (Story avant Philosophie)
    LandingFooter.tsx                 # Footer 4 colonnes
    HeroSection.tsx                   # Hero scinde texte + demo
    ChatMockup.tsx                    # Demo 3 scenarios (HITL / cartes / markdown)
    ProofSection.tsx                  # Bande de preuve (8 chiffres + teaser /story)
    HowItWorksSection.tsx             # Timeline 4 etapes
    ScreenshotsSection.tsx            # Carrousel captures (cadre portrait)
    FeaturesSection.tsx               # 4 hero cards + 5 groupes + responsible
    ArchitectureDiagram.tsx           # Deux modes (pipeline numerote / boucle ReAct)
    PresentationSection.tsx           # Carrousel 15 slides
    UseCasesSection.tsx               # 1 vedette + grille 2x2
    AudienceSection.tsx               # 4 personas
    RexSection.tsx                    # Retour d'experience (KPIs + CTA /story)
    SecuritySection.tsx               # 4 piliers securite
    TechSection.tsx                   # Sous le capot
    BlogPreviewSection.tsx            # Apercu blog
    CtaSection.tsx                    # CTA final
    FadeInOnScroll.tsx                # Animation scroll (seuil 0.01 + rootMargin)
    AnimatedCounter.tsx               # Compteur (valeur finale en SSR)
    ConstellationBackground.tsx       # Fond SVG constellation
    constants.ts                      # LANDING_STATS (chiffres sources)
  components/guides/
    StoryContent.tsx                  # Contenu /story (TOC + GuideMarkdown)
  data/guides/
    story.{fr,en,de,es,it,zh}.md      # Retour d'experience (6 langues)
```
