# ADR-172: Recherche de réglage — indexer ce qui existe, et le dire quand ce n'est pas là

**Statut**: ✅ IMPLEMENTED (2026-07-28) — phase 2 (indexation de l'administration) réalisée par ADR-227 (2026-08-18), qui remplace aussi la coquille accordéons/onglets décrite ici par un master-détail ; la doctrine « observation, jamais verdict » et les constantes de sondage survivent inchangées dans le panneau.
**Date**: 2026-07-28
**Décideurs**: Équipe LIA

## Contexte

La page Réglages empile ses sections en accordéons repliés sur deux onglets
(trois pour un superuser). ADR-171 a rendu la barre d'onglets réellement
collante, ce qui règle l'orientation ; trouver un réglage dont on connaît le nom
restait un défilement à l'aveugle.

Un mécanisme de lien profond existait déjà (`?section=`, table
`lib/settings-sections.ts`), utilisé par la checklist de démarrage, les cartes
du briefing et les notices de connecteur.

### Ce que la table couvrait réellement

La table déclarait **17** jetons. La page rend **43** `<SettingsSection>` :
30 orientées utilisateur, 13 en administration. **Treize sections utilisateur
étaient donc absentes** — et ce sont celles qu'un champ de recherche attire en
premier :

| Absente               | `value`             | Absente             | `value`                   |
| --------------------- | ------------------- | ------------------- | ------------------------- |
| Langue                | `language`          | Mes appareils       | `security-devices`        |
| Fuseau horaire        | `timezone`          | Exporter mes données| `security-export`         |
| Apparence             | `theme`             | Génération d'images | `image-generation`        |
| Police                | `font`              | MCP application     | `admin-mcp-servers`       |
| Mode d'affichage      | `display-mode`      | Panneau de debug    | `debug-panel`             |
| Boucles ouvertes      | `open-loops`        | Export consommation | `user-consumption-export` |
| Authentification forte| `security-auth`     |                     |                           |

Un index limité aux 17 aurait renvoyé **zéro résultat** sur « thème »,
« langue », « mot de passe », « fuseau horaire », « police ».

### Les deux gardes existantes ne voyaient pas ce sens-là

`settings-sections.test.ts` vérifiait chaque entrée **contre** son composant.
Rien ne regardait le sens inverse — une section rendue par la page et inconnue
de la table. De plus, l'assertion d'onglet dérivait le nom du composant **du nom
de fichier** : pour `theme-selector.tsx` l'aiguille valait `<theme-selector `,
qui ne correspond à rien. **Falsifié dans les deux sens** : avec l'ancien code
l'entrée `theme` tombait dans la branche « composant non rendu » et le test
passait **à vide** ; avec le nom lu depuis l'export, la même entrée mal placée
échoue avec `theme: declared "features" tab but rendered in preferences`.

### Trois faits mesurés qui contraignent la conception

1. **L'onglet inactif n'est pas monté.** `TabsContent` n'a pas `forceMount` :
   Radix démonte le panneau inactif. Depuis Préférences, rien ne peut observer
   ce que rendrait Fonctionnalités.
2. **Huit sections utilisateur peuvent ne rien rendre**, et seules deux le sont
   de façon décidable à l'avance (`open-loops` par drapeau `/config`,
   `debug-panel` par droit administrateur + disposition non-superuser). Les six
   autres (`telephony-calls`, `security-auth`, `security-export`,
   `admin-mcp-servers`, `briefing-grid`, `heartbeat`) dépendent de leur propre
   donnée — 404, liste vide, instance sans MFA, ou **requête encore en vol**.
3. **Les locales mélangent deux apostrophes.** Mesuré sur les six fichiers :
   212 apostrophes courbes U+2019 en `fr`, 94 en `it`, 16 en `en`. La
   description `settings.security.auth.description` porte
   « application d’authentification » : elle était **introuvable** en tapant
   `d'authentification`, ce que produit tout clavier.

## Décision

**Périmètre : les 30 sections utilisateur, l'administration différée et
énumérée.** Les 13 sections d'administration ne sont pas indexées ; un superuser
le lit dans l'interface (`settings.search.admin_not_indexed`). Le report n'est
pas une phrase de documentation mais une **liste exécutable** dans
`settings-sections-coverage.guard.test.ts` : la vider EST la phase 2.

**Une garde anti-faux-négatif.** Tout composant rendu dans un panneau doit être
indexé, structurel (conteneur, boundary, en-tête de groupe) ou explicitement
différé — il n'y a pas de quatrième issue, donc une nouvelle section force une
décision au moment où elle est ajoutée. La liste des différés est anti-rot :
une entrée que la page ne rend plus fait échouer le test.

**Deux tables, tenues par le TYPE.** `settings-sections.ts` répond « où ça
atterrit », `settings-search.ts` répond « comment le lecteur l'appelle ». La
seconde est un `Record<SettingsSectionToken, …>` : ajouter un jeton de lien
profond sans métadonnée de recherche **ne compile pas**.

**Une porte ne reflète que la garde que le composant applique vraiment.**
`/config` expose aussi `skills_enabled`, `channels_enabled`, `journals_enabled`,
`rag_spaces_enabled` et `heartbeat_enabled`, mais `SkillsSettings`,
`ChannelSettings`, `JournalsSettings` et `SpacesSettingsSection` **ne les lisent
pas** et rendent quand même. Filtrer dessus aurait caché des sections présentes
à l'écran — le faux négatif que personne ne remarque.

**Les six sections indécidables restent dans l'index**, marquées `runtime`.
Les retirer transformerait « vide aujourd'hui » en « n'existe pas ». Après la
navigation, la page attend la section (première tentative à 150 ms, sondage à
120 ms, échéance à 5 s) puis énonce l'**observation** — « ne s'affiche pas ici,
cette section n'est peut-être pas disponible sur votre compte ». Affirmer
l'indisponibilité serait un mensonge assuré le jour où une connexion est lente.

**Le focus n'appartient qu'au chemin recherche.** `pendingSection` porte un
drapeau `focus`. Un lien `?section=`, un retour OAuth ou le raccourci portrait ne
déplacent pas le curseur — le focus arrivant de façon asynchrone après un
chargement est désorientant. Un résultat choisi le déplace, sur le déclencheur
de l'accordéon (`button[aria-expanded]`, contrat épinglé par le test de
`SettingsSection`). Le défilement honore désormais `prefers-reduced-motion` sur
les deux chemins, ce que `scrollIntoView({behavior:'smooth'})` ignorait alors
que la fonction voisine documentait déjà le piège.

**Le champ vit dans la barre collante, à hauteur constante.** `SCROLL_MARGIN`
est une valeur unique servant toutes les sections, calibrée sur la hauteur
totale du chrome collant. **Mesuré dans Chromium** : barre de y 64 à 161
(hauteur 97), `scroll-margin-top` résolu à 176 px, section liée atterrissant à
exactement 176 — 15 px d'air. `scroll-mt-32` (128) devient `scroll-mt-44` (176).
Une rangée dont la hauteur varierait ferait atterrir chaque lien profond sous la
barre ; résultats, compteurs et notices vivent donc dans une fenêtre en
positionnement absolu.

**La garde e2e mesure le conteneur collant, plus la liste d'onglets.** Avec une
seconde rangée sous les onglets, le bas de `[role="tablist"]` n'est plus le bas
du chrome : l'ancienne assertion aurait réussi pendant qu'une section atterrit
sous le champ de recherche. Le test vérifie en plus que le conteneur dépasse
bien la liste, faute de quoi il mesurerait à nouveau la mauvaise chose sans le
dire.

**Le repli typographique est 1:1, par contrainte.** `normalizeSearchText` replie
désormais les apostrophes (U+2018/U+2019/U+02BC → `'`) et les espaces
insécables (U+00A0/U+202F → espace). Chaque entrée remplace **un point de code
par un point de code** : `findNormalizedMatches` reconstitue les positions
d'origine en sommant `normalizeSearchText(char).length`, donc les trois
surligneurs bâtis dessus ne restent exacts que si le repli conserve la longueur.
Le repli de ligatures (`ß`→`ss`, `œ`→`oe`) est **écarté** pour cette raison —
une seule occurrence mesurée dans le périmètre indexé, traitée en donnée par un
mot-clé allemand plutôt qu'en moteur.

## Conséquences

- Les 13 nouveaux jetons rejoignent la surface URL publique : `?section=theme`,
  `?section=security-auth`… Ajout, jamais renommage.
- Le lot corrige au passage la recherche FAQ, qui partage le normaliseur et
  butait sur les mêmes 212 apostrophes courbes.
- Un scan axe supplémentaire couvre la liste de résultats **ouverte** : il a
  trouvé un contraste de 3,51:1 sur la ligne de description (`/80` d'opacité,
  sous le plancher AA de 4,5:1 en 12 px), corrigé avant livraison.
- La page émet une requête `/config` de plus, seul moyen de filtrer exactement
  la seule section réellement pilotée par un drapeau.

## Alternatives écartées

- **S'en tenir aux 17 jetons déclarés.** Coût réel : « thème », « langue »,
  « mot de passe » sans résultat. Treize entrées de table les rattrapent.
- **Indexer aussi les 13 sections d'administration.** Le gating y est le plus
  fiable du lot (`user.is_superuser`, connu sans requête), mais c'est un
  périmètre distinct ; il est différé de façon énumérée, pas oubliée.
- **`forceMount` sur les panneaux d'onglet** pour connaître l'état réel des
  deux onglets : monterait une trentaine de sections et leurs requêtes à chaque
  visite, pour supprimer une incertitude que le message d'arrivée traite déjà.
- **Filtrer les six sections `runtime`** au jugé : échange un cul-de-sac visible
  contre un faux négatif invisible.
- **Placer le champ hors de la barre collante** : aucun impact sur
  `scroll-margin`, mais le champ redevient inatteignable dès que la page défile,
  ce que la barre collante venait précisément de corriger.
