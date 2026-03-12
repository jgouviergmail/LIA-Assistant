# Landing Page — Documentation technique

> **Version** : 1.0
> **Date** : 2026-03-08
> **Emplacement** : `apps/web/src/app/[lng]/page.tsx` + `apps/web/src/components/landing/`

---

## Table des matieres

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture des composants](#2-architecture-des-composants)
3. [Structure de la page](#3-structure-de-la-page)
4. [Animations et interactions](#4-animations-et-interactions)
5. [Internationalisation (i18n)](#5-internationalisation-i18n)
6. [SEO et OpenGraph](#6-seo-et-opengraph)
7. [Redirect authentifie](#7-redirect-authentifie)
8. [Responsive Design](#8-responsive-design)
9. [Theming](#9-theming)

---

## 1. Vue d'ensemble

La landing page est le point d'entree public de l'application LIA (LIA). Elle sert a :

- **Presenter le produit** : fonctionnalites, architecture, cas d'usage, technologies
- **Convertir les visiteurs** : CTA vers l'inscription (`/register`) et la connexion (`/login`)
- **Rediriger les utilisateurs authentifies** : vers le dashboard automatiquement
- **Renforcer la confiance** : section securite, statistiques chiffrees, badges GDPR/Beta

La page est un composant serveur async (`async function HomePage`) qui initialise l'i18n cote serveur et delegue le rendu a une dizaine de sections modulaires. Les composants interactifs (header, diagramme, compteurs, constellation) sont marques `'use client'`.

---

## 2. Architecture des composants

Tous les composants sont dans `apps/web/src/components/landing/` et reexportes via `index.ts`.

### 2.1 Composants de section (contenu)

| Composant | Fichier | Type | Props | Description |
|-----------|---------|------|-------|-------------|
| `HeroSection` | `HeroSection.tsx` | Server (async) | `lng: string` | Section hero plein ecran avec tagline, badges Beta, CTA principal/secondaire, trust badges (16+ agents, 6 providers, 99+ voices, GDPR), chevron de scroll. Integre `HeroBackground`. |
| `HowItWorksSection` | `HowItWorksSection.tsx` | Server (async) | `lng: string` | Timeline en 4 etapes (question, planification, validation HITL, execution) avec icones colorees et numerotation. Layout horizontal desktop, vertical mobile. |
| `FeaturesSection` | `FeaturesSection.tsx` | Server (async) | `lng: string` | 3 categories de fonctionnalites : **Hero features** (3 cartes avec accent colore : Google Workspace, Web Intelligence, Voice), **Functional features** (13 cartes : langage naturel, multi-agent, proactif, centres d'interet, rappels, memoire, reponses riches, multicanal, personnalites, MCP, langues, MCP Apps, Excalidraw), **Responsible features** (4 cartes : controle, vie privee, simplicite, themes). |
| `ArchitectureDiagram` | `ArchitectureDiagram.tsx` | Client | aucune | Pipeline d'orchestration en 8 noeuds (Query, Router, Planner, Validator, HITL, Orchestrator, Agents, Response). Layout horizontal desktop avec fleches, vertical mobile. Chaque noeud a un degrade de couleur unique. |
| `UseCasesSection` | `UseCasesSection.tsx` | Server (async) | `lng: string` | 5 exemples de requetes utilisateur en cartes alternees gauche/droite avec timeline verticale et dots connecteurs. Chaque carte contient la requete entre guillemets et sa description. |
| `StatsSection` | `StatsSection.tsx` | Client | aucune | 6 statistiques avec compteurs animes : 16+ agents, 50+ tools, 6 providers, 99+ voice languages, 500+ metrics, 6 UI languages. Fond `bg-primary/5`. |
| `SecuritySection` | `SecuritySection.tsx` | Server (async) | `lng: string` | Layout 2 colonnes : visuel bouclier anime a gauche, 4 piliers de securite a droite (controle des donnees, BFF, chiffrement, GDPR). |
| `TechSection` | `TechSection.tsx` | Server (async) | `lng: string` | Grille 2x3 de cartes techniques : LangGraph, LLM providers, apprentissage bayesien, recherche hybride, temps reel, stack technique. Style `glass` avec `hover-lift`. |
| `CtaSection` | `CtaSection.tsx` | Server (async) | `lng: string` | Call-to-action final avec fond degrade bleu/violet, overlay constellation SVG, badge Beta, bouton blanc d'inscription. |

### 2.2 Composants structurels

| Composant | Fichier | Type | Props | Description |
|-----------|---------|------|-------|-------------|
| `LandingHeader` | `LandingHeader.tsx` | Client | `lng: string` | Header fixe avec logo LIA, navigation desktop (4 sections avec scroll spy via `IntersectionObserver`), selecteur de langue, toggle theme, boutons login/register. Menu hamburger mobile avec fermeture via Escape. Effet `glass` au scroll (>20px). |
| `LandingFooter` | `LandingFooter.tsx` | Server (async) | `lng: string` | Footer avec logo, copyright dynamique (annee), version, lien vers la section securite. |

### 2.3 Composants utilitaires

| Composant | Fichier | Type | Props | Description |
|-----------|---------|------|-------|-------------|
| `FadeInOnScroll` | `FadeInOnScroll.tsx` | Client | `children`, `className?`, `delay?: number`, `threshold?: number` | Wrapper d'animation fade-in + slide-up declenche par `IntersectionObserver` (seuil par defaut : 15%). Se declenche une seule fois. Supporte le delai en ms. |
| `AnimatedCounter` | `AnimatedCounter.tsx` | Client | `target: number`, `suffix?: string`, `duration?: number` | Compteur anime de 0 a `target` avec easing cubic (ease-out). Declenche par `IntersectionObserver` (seuil 30%). Duree par defaut : 2000ms. Affichage `tabular-nums`. |
| `ConstellationBackground` | `ConstellationBackground.tsx` | Client | aucune | SVG plein ecran avec 27 noeuds et aretes auto-calculees (seuil de distance < 28 unites). Animation `constellation-pulse` par noeud avec delais decales. Degrade radial subtil en `--color-primary`. |
| `HeroBackground` | `HeroBackground.tsx` | Client | aucune | Image de fond adaptative (theme clair/sombre, genre LIA via `useLiaGender` hook). Clic pour basculer male/femelle (preference persistee en cookie). Overlays semi-transparents + degrades haut/bas pour lisibilite du texte. Transition d'opacite au montage. |
| `ChatMockup` | `ChatMockup.tsx` | Client | aucune | Simulation de conversation LIA dans une fenetre type macOS (3 dots rouge/ambre/vert). 5 bulles animees en sequence : message utilisateur, planification LIA, demande HITL (ambre), approbation utilisateur, confirmation (vert). 3 variantes de bulle : `default`, `hitl`, `success`. |
| `AuthRedirect` | `AuthRedirect.tsx` | Client | `lng: string` | Composant invisible. Verifie l'authentification via `useAuth()`. Si l'utilisateur est connecte, redirige vers `/{lng}/dashboard`. Ne rend rien (`return null`). |

---

## 3. Structure de la page

L'ordre des sections dans `page.tsx` est le suivant :

```
AuthRedirect (invisible, redirect si authentifie)
|
LandingHeader (fixed, z-50)
|
<main>
  1. HeroSection         — plein ecran, ancre implicite (haut de page)
  2. HowItWorksSection   — ancre #how-it-works, fond bg-card
  3. FeaturesSection      — ancre #features
  4. ArchitectureDiagram  — ancre #architecture
  5. UseCasesSection      — ancre #use-cases, fond bg-card
  6. StatsSection         — fond bg-primary/5
  7. SecuritySection      — ancre #security
  8. TechSection          — ancre #technology, fond bg-card
  9. CtaSection           — fond degrade bleu/violet
</main>
|
LandingFooter
```

Le lien "Skip to content" (`sr-only`) pointe vers `#features` pour l'accessibilite.

Le header navigable contient 4 liens d'ancrage : Features, How it works, Security, Technology. Le scroll spy met en surbrillance la section active via `IntersectionObserver` avec `rootMargin: '-20% 0px -70% 0px'`.

---

## 4. Animations et interactions

### 4.1 FadeInOnScroll

- **Mecanisme** : `IntersectionObserver` observe l'element. Au croisement du seuil (`threshold`, defaut 15%), la classe `animate-fade-in-up` est appliquee (definie dans les styles globaux TailwindCSS).
- **Delai** : prop `delay` en ms, applique via `animationDelay` inline.
- **One-shot** : l'animation ne se joue qu'une fois (`unobserve` apres declenchement).
- **Utilisation** : wraps la majorite des cartes et titres de section pour un effet d'apparition progressif au scroll.

### 4.2 AnimatedCounter

- **Mecanisme** : `IntersectionObserver` (seuil 30%) + `requestAnimationFrame` pour interpolation fluide.
- **Easing** : cubic ease-out (`1 - (1 - progress)^3`).
- **Duree** : 2000ms par defaut, configurable.
- **Suffix** : `+` ou vide, ajoute apres le nombre.
- **Utilisation** : `StatsSection` — 6 compteurs (16+, 50+, 6, 99+, 500+, 6).

### 4.3 ConstellationBackground

- **27 noeuds** avec positions (cx, cy), rayons et delais pre-definis.
- **Aretes** calculees statiquement : distance euclidienne < 28 unites entre deux noeuds.
- **Animation** : `constellation-pulse` CSS (pulsation) avec duree = `3 + delay` secondes.
- **Degrade** : `radialGradient` en `--color-primary` avec opacite 8%.
- **Utilisation** : fond derriere la section hero (via HeroSection > ConstellationBackground — non utilise directement dans la page actuelle mais disponible via index.ts).

### 4.4 ChatMockup

- **5 bulles** avec animations `animate-chat-bubble` a delais sequentiels (`delay-300` a `delay-2500`).
- **3 variantes visuelles** : default (bleu/neutre), hitl (ambre), success (vert).
- **Composant Bubble interne** : gere l'alignement (utilisateur a droite, LIA a gauche), icones (User, Bot, ShieldCheck, Check) et styles.
- **Utilisation** : disponible via index.ts, non integre directement dans la page actuelle.

### 4.5 HeroBackground

- **Image adaptative** : via le hook `useLiaGender` qui fournit `liaBackgroundImage` en fonction du theme (clair/sombre) et du genre (male/femelle).
- **Toggle** : clic sur l'image bascule le genre (persistance cookie).
- **Fade-in** : transition d'opacite 700ms au montage (`mounted` state).
- **Overlays** : `bg-background/40` semi-transparent + degrades haut (h-24) et bas (h-32).

### 4.6 Accessibilite des animations

Tous les composants animes respectent `prefers-reduced-motion: reduce` :
- `FadeInOnScroll` : affiche directement sans animation.
- `AnimatedCounter` : affiche la valeur finale instantanement.
- `ConstellationBackground` : n'applique pas les animations CSS.

---

## 5. Internationalisation (i18n)

### 5.1 Mecanisme

- **6 langues** : fr, en, es, de, it, zh (fallback : fr).
- **Route dynamique** : `[lng]` dans l'App Router — ex. `/fr`, `/en/`, `/de`.
- La langue est validee via `validateLanguage(lngParam)` dans `page.tsx`.

### 5.2 Composants serveur

Les composants `async` (HeroSection, FeaturesSection, SecuritySection, etc.) utilisent :
```ts
const { t } = await initI18next(lng);
```
Les cles de traduction suivent le namespace `landing.*` :
- `landing.meta.title` / `landing.meta.description` — metadata SEO
- `landing.hero.*` — hero section (title_line1/2/3, subtitle, badges, CTA, trust)
- `landing.features.*` — fonctionnalites (titre + description par cle)
- `landing.how_it_works.step1-4.*` — etapes du pipeline
- `landing.use_cases.example1-5.*` — cas d'usage (query + description)
- `landing.security.*` — piliers securite
- `landing.tech.*` — elements techniques
- `landing.architecture.*` — noeuds du pipeline
- `landing.stats.*` — labels des compteurs
- `landing.cta.*` — call-to-action final
- `landing.nav.*` — navigation header
- `landing.footer.*` — footer (copyright, version, privacy)
- `landing.chat_mockup.*` — bulles du ChatMockup

### 5.3 Composants client

Les composants `'use client'` (LandingHeader, StatsSection, ArchitectureDiagram, ChatMockup) utilisent :
```ts
const { t } = useTranslation();
```
La langue est propagee via le provider i18n du layout parent (`[lng]/layout.tsx`).

### 5.4 Fichiers de traduction

Les traductions sont dans `apps/web/locales/{lng}/translation.json` pour chaque langue.

---

## 6. SEO et OpenGraph

### 6.1 Metadata dynamique

`page.tsx` exporte `generateMetadata()` qui produit un objet `Metadata` :
```ts
{
  title: t('landing.meta.title'),
  description: t('landing.meta.description'),
}
```
Les balises meta sont donc localisees selon la langue de la route.

### 6.2 Image OpenGraph

Fichier : `apps/web/src/app/[lng]/opengraph-image.tsx`

- **Runtime** : Edge (generation a la volee).
- **Dimensions** : 1200x630 px (standard OG).
- **Format** : PNG.
- **Contenu** : fond degrade (indigo → bleu → violet), logo "L" dans un cercle, tagline localisee en 6 langues, sous-titre, badge "BETA".
- **Taglines** : dictionnaire inline `taglines` avec les 3 lignes + sous-titre par langue (fr, en, es, de, it, zh), fallback sur `fr`.
- **Convention Next.js** : le fichier est auto-detecte par Next.js comme generateur d'image OG pour la route `[lng]`.

---

## 7. Redirect authentifie

Fichier : `apps/web/src/components/landing/AuthRedirect.tsx`

- **Composant client invisible** (`return null`).
- Utilise le hook `useAuth()` pour verifier l'etat d'authentification.
- **Comportement** : si `!isLoading && user` est truthy, redirige immediatement vers `/{lng}/dashboard` via `router.push()`.
- **Position** : premier element rendu dans `page.tsx`, avant le header.
- **Consequence UX** : un utilisateur deja connecte ne voit jamais la landing page.

---

## 8. Responsive Design

### 8.1 Breakpoints

Le projet utilise les breakpoints TailwindCSS avec un breakpoint custom `mobile` :

| Prefix | Usage dans la landing |
|--------|-----------------------|
| (defaut) | Mobile portrait — layout en colonne unique |
| `sm:` | ~640px — grilles 2 colonnes pour features, ajustements padding |
| `mobile:` | Breakpoint custom — passage aux layouts desktop (grilles 3-6 colonnes, navigation horizontale, timeline horizontale) |
| `lg:` | ~1024px — tailles de texte hero (7xl), padding elargi |

### 8.2 Patterns responsives

- **Header** : navigation inline desktop (`hidden mobile:flex`), menu hamburger mobile (`mobile:hidden`).
- **HowItWorksSection** : timeline horizontale desktop (`mobile:grid-cols-4`), verticale mobile (colonne unique avec lignes de connexion).
- **ArchitectureDiagram** : pipeline horizontal desktop (`hidden mobile:flex`), vertical mobile (`flex mobile:hidden`).
- **FeaturesSection** : hero features 3 colonnes (`mobile:grid-cols-3`), functional features jusqu'a 3 colonnes, responsible features 4 colonnes.
- **SecuritySection** : 2 colonnes desktop (`mobile:grid-cols-2`), empilees en mobile.
- **StatsSection** : 6 colonnes desktop (`mobile:grid-cols-6`), 2 colonnes mobile.
- **UseCasesSection** : cartes alternees gauche/droite desktop (48% width), empilees mobile. Timeline verticale visible uniquement desktop.
- **LandingFooter** : horizontal desktop (`mobile:flex-row`), vertical mobile.

### 8.3 Textes adaptatifs

Les tailles de texte du hero s'adaptent : `text-5xl` → `mobile:text-6xl` → `lg:text-7xl`.

---

## 9. Theming

### 9.1 TailwindCSS 4 et OKLCH

Le projet utilise TailwindCSS 4 avec des variables CSS en espace colorimetrique OKLCH. Les classes utilitaires de la landing s'appuient sur le design system global :

- **Couleurs semantiques** : `text-foreground`, `text-muted-foreground`, `bg-background`, `bg-card`, `bg-primary`, `text-primary`, `border-border`, etc.
- **Opacites** : `bg-primary/5`, `bg-primary/10`, `bg-primary/15`, `border-border/60`, etc.
- **Degrades** : `text-gradient-brand` (classe custom pour le texte hero), degrades `from-*/to-*` pour les icones et accents de features.

### 9.2 Dark mode

Le dark mode est gere automatiquement via les variables CSS. Les composants utilisent exclusivement des classes semantiques (`bg-background`, `text-foreground`, etc.) qui s'adaptent au theme actif. Quelques ajustements specifiques :
- `ChatMockup` : variantes `dark:text-amber-300`, `dark:text-green-300` pour les bulles HITL/success.
- `HeroBackground` : l'image de fond change selon le theme (via `useLiaGender` qui fournit des assets differents light/dark).

### 9.3 Effets visuels custom

| Classe | Description |
|--------|-------------|
| `glass` | Effet glassmorphism (`backdrop-blur` + fond semi-transparent) |
| `hover-lift` | Elevation au hover (scale + shadow) |
| `hover-glow` | Glow subtil au hover |
| `animate-fade-in-up` | Animation keyframe fade-in + translate-y |
| `animate-bounce-scroll` | Bounce du chevron hero |
| `animate-chat-bubble` | Apparition sequentielle des bulles chat |
| `constellation-pulse` | Pulsation des noeuds SVG |
| `text-gradient-brand` | Gradient de texte pour le highlight hero |
| `landing-section` | Classe de base pour les sections (espacement, overflow) |

### 9.4 Toggle de theme

Le `ThemeToggle` est integre dans le `LandingHeader` et accessible en permanence (desktop et mobile).

---

## Arborescence des fichiers

```
apps/web/src/
  app/[lng]/
    page.tsx                          # Page principale (Server Component)
    opengraph-image.tsx               # Generateur d'image OG (Edge Runtime)
  components/landing/
    index.ts                          # Barrel exports (18 composants)
    AuthRedirect.tsx                  # Redirect si authentifie
    LandingHeader.tsx                 # Header fixe avec scroll spy
    LandingFooter.tsx                 # Footer avec copyright
    HeroSection.tsx                   # Section hero plein ecran
    HeroBackground.tsx                # Image de fond adaptative (theme + genre)
    HowItWorksSection.tsx             # Timeline en 4 etapes
    FeaturesSection.tsx               # 20 fonctionnalites en 3 categories
    ArchitectureDiagram.tsx           # Pipeline 8 noeuds
    UseCasesSection.tsx               # 5 exemples de requetes
    StatsSection.tsx                  # 6 compteurs animes
    SecuritySection.tsx               # 4 piliers securite
    TechSection.tsx                   # 6 cartes technologies
    CtaSection.tsx                    # Call-to-action final
    FadeInOnScroll.tsx                # Wrapper animation scroll
    AnimatedCounter.tsx               # Compteur anime
    ConstellationBackground.tsx       # Fond SVG constellation
    ChatMockup.tsx                    # Simulation de conversation
```
