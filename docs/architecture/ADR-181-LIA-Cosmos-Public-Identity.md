# ADR-181 : Identité « LIA Cosmos » — re-skin scopé de tout l'espace public, chorégraphies pilotées par le scroll

**Statut**: ✅ IMPLEMENTED (2026-07-30) — bascule complète (landing + 10 pages publiques), previews supprimés
**Spec maître**: `docs/superpowers/specs/2026-07-30-lia-cosmos-landing-design.md` (arbitrages propriétaire signés)

## Contexte

La landing éditoriale (six chapitres, ADR v1.27.1) portait un habillage sobre sans
identité visuelle forte ni lien entre le défilement et la narration. Le propriétaire a
arbitré une refonte inspirée des sites « scroll-driven » modernes : identité cosmique
(palette LIA intensifiée bleu → violet → cyan sur quasi-noir), tout l'espace public
aligné, **zéro dépendance d'animation nouvelle**, contenu réel réutilisé à 100 %, et un
site qui répond au défilement de bout en bout — sans régression d'accessibilité ni de
performance (la prod sert depuis un RPi5).

## Décision

**Re-skin par scope CSS, pas par réécriture** : une classe `.cosmos` redéfinit les
variables `--color-*` du design system Tailwind (fond, cartes, primaire, anneaux…) —
les sections réelles se rhabillent **sans une seule édition de composant de contenu** ;
les surfaces portalées (menus Radix) échappent volontairement au scope et gardent le
thème applicatif. Sous-scope **`cosmos-calm`** pour les pages de lecture (story, why,
how, faq, blog, privacy, terms) : fond atténué, cartes quasi opaques, aucun mot fantôme,
aucune chorégraphie.

**Primitives maison** (`components/landing/cosmic/`) : boucle de scroll unique en rAF
passif (`useCosmosScroll`), driver `ScrollScrub` écrivant la progression de section dans
`--sp` (défaut CSS 1 → rendu final sans JS/SEO ; reduced-motion épingle 1), scène
épinglée `PinnedScene` (sticky, `--p`, fallback vertical mobile/reduced),
`Planetarium` (8 planètes-fonctionnalités sur 3 ellipses autour du vrai mockup),
mots fantômes `GhostWord` (frame masquée + dérive), `CosmosDarkFirst` (script pre-paint
inline : pas de préférence stockée → sombre, le toggle gagne — même technique que
next-themes). Les scènes des chapitres sont **scrubbées en réutilisant leurs délais
inline existants** (copiés une fois dans `--d`, fenêtres proportionnelles sur `--sp`) —
l'ordre original de chaque scène est préservé, le scroll joue la partition dans les
deux sens.

**Accessibilité AA par construction et par thème** : le jeton primaire diverge par
thème (sombre = bleu vif `#4f8dfd` sous texte encre ≈5,5:1 ; clair = bleu profond
`#2c56c4` sous blanc ≈6,5:1 et comme `text-primary` sur chips teintées ≥4,9:1) — un
seul jeton blanc-sur-bleu-vif mesurait 3,2:1. Prouvé par balayage axe e2e sur `/`,
`/faq`, `/demo`, `/more` dans les DEUX thèmes.

**Registre tutoyé** : les surfaces publiques passent au registre informel en fr/de/es
(~1 150 chaînes converties par scripts curatés + audits à zéro résidu ; it l'était
déjà) — l'interlocuteur d'un exemple téléphonique reste vouvoyé (ce n'est pas
l'utilisateur).

**Gardes** : e2e pin mesuré **pendant** le scroll (doctrine ADR-171), overflow mobile
375/320 sur 6 locales à travers le cycle d'animation complet (le garde distingue
désormais débordement de LAYOUT — toujours bloquant — et projection 3D transitoire
d'une chorégraphie clippée ou décoration `aria-hidden`+`pointer-events:none`),
balayage axe des deux thèmes.

## Alternatives écartées

- **Bibliothèque d'animation (GSAP/Framer)** : zéro dépendance arbitré ; transform/
  opacity + variables CSS suffisent et restent tuables par reduced-motion pur CSS.
- **Dupliquer les sections pour les rhabiller** : double maintenance du contenu ×6
  langues ; le scope de variables re-skinne sans fork.
- **IntersectionObserver one-shot par tuile** : non réversible et déjà source du
  conflit visuel avec les révélations legacy ; un driver unique par section ne crée
  qu'un écouteur de scroll partagé.
- **Halos en pseudo-éléments `z-index:-1`** : structurellement cassés sous les
  contextes d'empilement (transform/backdrop-filter) — retenu : box-shadow coloré,
  qui ne peint que hors boîte.
- **Garder `/` classique et exposer Cosmos en option** : deux identités à maintenir ;
  la bascule remplace, les previews sont supprimés (pas de code mort).
