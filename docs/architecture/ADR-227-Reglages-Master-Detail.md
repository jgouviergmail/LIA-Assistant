# ADR-227: Réglages en master-détail — le rail est la carte, le panneau est le territoire

**Statut**: ✅ IMPLEMENTED (2026-08-18)
**Date**: 2026-08-18
**Décideurs**: Propriétaire (arbitrage sur maquette haute fidélité) + Équipe LIA

## Contexte

La page Réglages empilait **51 sections en accordéons repliés** sur deux onglets
(trois pour un superuser), groupées par intercalaires. ADR-171 avait rendu la
barre d'onglets collante, ADR-172 avait ajouté la recherche rapide — deux
palliatifs au même problème structurel : **la navigation et le contenu se
disputaient le même axe vertical**. Rien n'était scannable, aucune description
n'était visible avant ouverture, ouvrir deux sections créait des kilomètres de
défilement, et l'onglet Administration restait hors de portée de la recherche
(phase 2 d'ADR-172, différée).

Trois pistes ont été maquettées et arbitrées par le propriétaire sur maquette
haute fidélité interactive (rangées de navigation, hub de cartes,
master-détail) ; la troisième, hybridée avec le hub en écran d'accueil, a été
retenue — le patron vers lequel Linear, Slack, Notion et Stripe ont tous
convergé pour des réglages riches.

### Faits mesurés qui contraignent la conception

1. **La page écrivait deux layouts complets à la main** (~330 lignes dupliquées,
   un par valeur du drapeau superuser) — chaque section ajoutée devait l'être
   deux fois, et deux gardes parsaient la SOURCE de la page par regex pour
   tenir les tables alignées.
2. **`SettingsSection` est le chokepoint des 50 composants de section**, et sa
   branche `collapsible={false}` rendait déjà exactement la forme « panneau »
   (carte ouverte en permanence, ancre `settings-section-<value>` incluse).
3. **Huit sections utilisateur peuvent ne rien rendre** (gate de capacité, de
   drapeau ou de donnée), et six ne sont pas décidables avant montage — la
   doctrine « observation, jamais verdict » d'ADR-172 doit survivre au
   changement de coquille.
4. **Toutes les sections de l'onglet actif montaient d'un coup** (requêtes
   incluses) ; l'onglet inactif était démonté par Radix.

## Décision

### 1. Une coquille master-détail rendue DEPUIS les tables

Un rail (`SettingsRail`) liste chaque section visible — groupée par onglet puis
par groupe, dans l'ordre de `SETTINGS_SECTIONS` (l'ordre reste le tie-break de
la recherche) — à côté d'un panneau (`SettingsPane`) qui monte **une** section,
résolue par deux nouveaux registres à complétude compilée :
`SETTINGS_SECTION_ICONS` (`Record<token, LucideIcon>`, prouvé contre l'icône
que chaque composant passe réellement à `<SettingsSection>`, alias lucide
résolus) et `SETTINGS_SECTION_REGISTRY` (`Record<token, {feature?, render}>`,
prouvé contre `declaredIn` par identité de fonction). Sans sélection, le
panneau affiche la **Vue d'ensemble** (`SettingsOverview`) : les sections en
cartes — icône, titre, **description enfin visible** — sous de vrais titres h2
(le rail, volontairement, n'émet pas de titres : ils doubleraient le plan du
document). Zéro fetch sur la vue d'ensemble, à dessein : les résumés d'état
sur cartes sont un lot ultérieur soumis à arbitrage.

La page ne liste plus rien à la main : **une section existe si et seulement si
les tables la déclarent** — la classe de dérive que les gardes de parsing
attrapaient est morte par construction, et les deux layouts dupliqués avec
elle. Les gardes de parsing (`settingsPageBlocks`, `componentGroupsIn`, le
guard de couverture) sont supprimées ; les directions encore signifiantes
(fichier existant, `value` déclaré, clés i18n appelées, trois onglets
couverts) restent testées contre la source.

### 2. Le mode panneau est un contexte, pas 50 modifications

`SettingsShellModeProvider value="pane"` force la branche non-repliable de
`SettingsSection` (avec `tabIndex={-1}` : cible de focus programmable). Les 50
sites d'appel sont inchangés ; hors provider, le comportement accordéon
d'origine demeure (les tests unitaires des sections en dépendent). La
calibration `scroll-mt-44` d'ADR-171/172 et `SettingsTabsBar` sont supprimées :
ouvrir une section défile la fenêtre en haut, il n'y a plus de chrome collant à
esquiver.

### 3. `?section=` devient l'état de sélection (contrat URL élargi)

Le jeton reste l'API de lien profond des 17+ appelants et des retours OAuth —
mais il n'est **plus nettoyé** : la sélection l'écrit
(`history.replaceState`), un rechargement ou un partage retombe sur le même
panneau, la vue d'ensemble l'efface, un jeton inconnu est retiré et atterrit
sur la vue d'ensemble. Une navigation routeur vers l'URL nue (l'entrée
« Réglages » de la nav) referme le panneau.

### 4. Phase 2 d'ADR-172 réalisée : l'administration est indexée

Les **15 jetons admin** rejoignent `SETTINGS_SECTIONS` et
`SETTINGS_SEARCH_META` (gate `superuser`, 4 groupes, mots-clés ×6 locales).
`ADMIN_TAB_DEFERRED` est vidée avec son guard, l'invariant « phase 1 » remplacé
par son dual (« les trois onglets sont couverts »), et la notice
`admin_not_indexed` — devenue fausse — supprimée du composant et des 6 locales.
Liens profonds et recherche couvrent désormais toute la surface.

### 5. Absence honnête, inline et récupérable

Le panneau reprend la doctrine et les constantes d'ADR-172 (150/120/5000 ms) :
il sonde l'ancre de la section et, passé le délai, remplace le toast par un
**`EmptyState` inline** (formulation observation, clé
`settings.search.unavailable` réutilisée, action « Voir tous les réglages ») —
et **continue de sonder**, si bien qu'une section dont la requête répond tard
remplace le message au lieu de ne jamais paraître. Un gate décidable qui dit
non (jeton admin pour un compte standard, debug sans droit) **ne monte pas**
le composant — ses requêtes partiraient pour être rejetées — et aboutit au
même message.

### 6. Focus : un compteur à cliquet

Seul un choix dans la recherche déplace le focus (contrat ADR-172). Le panneau
reçoit un compteur monotone `focusRequest` et n'honore chaque valeur
**qu'une fois** (`focusHonoredRef`) : sans le cliquet, toute sélection au rail
postérieure à une recherche re-volait le focus — défaut trouvé en revue,
épinglé par test avant correction.

### 7. Mobile : drill-down sous `lg`

Sous `lg` (le breakpoint du chrome dashboard), le rail est l'écran d'accueil ;
une sélection le remplace par le panneau et son bouton retour ; la vue
d'ensemble est une surface desktop. `100dvh` (pas `vh` — garde maison) borne
le rail collant desktop.

## Comportement réseau changé, assumé

Une seule section monte à la fois : ses requêtes partent **à sa sélection**,
plus au chargement de l'onglet (~20 sections × requêtes). C'est un gain de
latence initiale et de trafic, encadré par les specs e2e réécrites ; la seule
contrepartie est qu'un changement de section re-fetch (les sections gèrent
déjà leurs états de chargement).

## Preuves

- Unitaires : 5 709 tests verts (446 → 452 fichiers), dont modèle de coquille,
  rail, vue d'ensemble, panneau (fixtures déterministes : `chat-shortcuts`
  rend toujours, `haptics` rend null en jsdom), page intégrée (7 parcours),
  registres (106 assertions contre la source), cliquet de focus.
- E2E hermétiques contre build prod standalone : liens profonds (nouveau
  contrat URL), recherche (focus, admin superuser, négatif compte standard,
  320 px), rail (sticky desktop, drill-down 390 px, admin), blocs repliés et
  débordement connecteurs (inchangés — le contenu des sections n'a pas bougé),
  scans axe (landing, panneau routines, popup recherche, **drill-down téléphone
  ×2**).
- Ratchets verrouillés après gain : CC frontend (la page réécrite sort des
  hotspots), a11y 0, react-hooks inchangé.

## Suivis (non faits, décisions explicites)

- **Résumés d'état sur les cartes de la vue d'ensemble** : ajoutent des
  requêtes au chemin d'accueil — arbitrage propriétaire requis.
- **Mode accordéon de `SettingsSection`** : plus aucune surface de production
  ne le rend ; conservé pour les tests unitaires des sections. Candidat à une
  suppression dédiée (elle churnerait ~10 fichiers de tests pour zéro valeur
  utilisateur immédiate).
- **Routes réelles par section** (`/settings/theme`) : meilleur bouton retour
  navigateur, mais touche au routage — `?section=` suffit au besoin actuel.
