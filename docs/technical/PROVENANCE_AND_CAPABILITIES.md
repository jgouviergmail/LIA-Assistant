# Provenance des conclusions & carte des capacités

> Deux domaines transverses ajoutés le 2026-08-04 : `domains/shared` (provenance)
> et `domains/capabilities` (carte). Décisions associées : **ADR-201**, **ADR-204**.

## 1. Provenance — `domains/shared`

### Le problème

LIA écrit des souvenirs, des entrées de journal et des centres d'intérêt à
partir de ce que le lecteur lui dit. Sans provenance, une conclusion est une
affirmation sans source : impossible de la vérifier, impossible de la corriger
là où elle est née.

Recopier le message d'origine dans la conclusion est pire que rien : le contenu
d'une conversation supprimée survivrait ailleurs. Régénérer l'explication par
le modèle est pire encore : c'est une reconstruction plausible, pas une trace.

### Le schéma

```
provenance_references
├── id                 UUID (PK)
├── user_id            UUID → users(id)            ON DELETE CASCADE
│
│   -- Le SUJET : exactement un des trois (contrainte CHECK)
├── journal_entry_id   UUID → journal_entries(id)  ON DELETE CASCADE
├── memory_id          UUID → memories(id)         ON DELETE CASCADE
├── interest_id        UUID → interests(id)        ON DELETE CASCADE
│
│   -- La SOURCE : pierre tombale, jamais résurrection
├── conversation_id    UUID → conversations(id)    ON DELETE SET NULL
├── message_id         UUID → conversation_messages(id) ON DELETE SET NULL
│
├── outcome            ENUM(origin | evidence | contradiction)
└── created_at         TIMESTAMPTZ
```

Deux asymétries volontaires :

| Lien | Politique | Pourquoi |
| --- | --- | --- |
| vers le **sujet** | `CASCADE` | supprimer un souvenir doit supprimer sa provenance : elle n'a plus d'objet |
| vers la **source** | `SET NULL` | supprimer une conversation doit **vider** la référence, pas la détruire — le lecteur voit « ce signal a été supprimé » plutôt qu'une trace de ce qu'il a effacé |

`CASCADE` côté source aurait fait disparaître jusqu'à la mention qu'une source
ait existé, ce qui se lit comme « LIA a inventé cela ».

### La borne

`PROVENANCE_MAX_REFERENCES_PER_SUBJECT = 5`. `ProvenanceRepository.record`
élague les plus anciennes à l'écriture. Une provenance non bornée est une
seconde copie de l'historique, qui grossit exactement au rythme de l'usage.

La borne est **publiée** dans la réponse (`ProvenanceResponse.kept_at_most`) :
ce que le système applique, il le dit (ADR-184).

### Les producteurs

Un seul module, `shared/provenance_capture.py`, appelé par trois domaines :

| Producteur | Fichier | Sujet |
| --- | --- | --- |
| extraction de journal | `journals/extraction_service.py` | `journal_entry_id` |
| extraction de souvenir | `agents/services/memory_extractor.py` | `memory_id` |
| application d'action | `interests/services/action_applier.py` | `interest_id` |

### Les routes

```
GET /api/v1/journals/{id}/provenance
GET /api/v1/memories/{id}/provenance
GET /api/v1/interests/{id}/provenance
```

Chacune renvoie `ProvenanceResponse` : la liste des références résolues
(`is_tombstone` quand la source a disparu) et `kept_at_most`.

### RGPD

`provenance_references` est classée `_PURGED_FULL` dans `users/user_data_map.py`
et purgée **explicitement, avant ses sujets**, dans `build_purge_statements`. La
cascade aurait suffi techniquement — mais l'inventaire RGPD ne l'aurait pas
listée, et ce que l'inventaire ne liste pas, personne ne vérifie.

### Côté lecteur

`ProvenanceDisclosure` (partagé) rend un bloc replié « Pourquoi LIA pense
cela ? » sous chaque souvenir et chaque entrée de journal : les signaux, leur
date, leur rôle, et un bouton « Corriger » qui ouvre le flux d'édition existant
du sujet. On corrige la conclusion, pas la trace.

---

## 2. Carte des capacités — `domains/capabilities`

### Le problème

Savoir « ce que LIA sait faire pour moi » demandait de sonder sept sous-systèmes
via sept hooks côté client : douze requêtes au montage, et douze occasions pour
deux réponses de se contredire sur la même question.

### La sonde

```python
CapabilityProbe(key: str, available: bool, active: bool, detail: int | None)
```

| Champ | Sens | Règle |
| --- | --- | --- |
| `available` | l'instance offre-t-elle cette capacité ? | `False` ⇒ **absente du payload** (gate-keeper, ADR-061) |
| `active` | est-elle réellement utilisable pour ce compte ? | c'est la promesse de la carte |
| `detail` | ce qu'elle contient | `None` = **pas de décompte**, jamais `0` |

`resolve_capabilities` agrège par `asyncio.gather`, **chaque sonde sur sa propre
session** (`get_db_context()` — `AsyncSession` n'est pas sûre en concurrence).
`_count` dégrade à `0` sur échec : une carte qui refuse de se dessiner parce
qu'une table était injoignable est pire qu'une carte avec un nœud éteint.

`_from_user` lit voix, proactivité et personnalité **sur la ligne
authentifiée** : re-requêter ce que la ligne affirme déjà laisserait la carte
contredire toutes les autres surfaces sur le même fait.

### La route

```
GET /api/v1/capabilities  →  CapabilityMap { nodes, live, total }
```

`live` et `total` décrivent **les nœuds offerts**, et rien d'autre : ils ne
peuvent donc pas contredire la liste. Aucun champ n'est un niveau, un XP, un
score, un pourcentage, un rang, un badge ou une série — un test l'énonce comme
contrainte de schéma.

### Le rendu

| Fichier | Rôle |
| --- | --- |
| `constellation-layout.ts` | placement déterministe sur deux anneaux, `figureOutline` (ordre **angulaire**), `backdropStars` (champ semé, graine fixe) |
| `ConstellationSky.tsx` | le dessin — champ profond, poussière, orbites, figure, noyau. **Entièrement `aria-hidden`** |
| `CapabilityConstellation.tsx` | les étoiles : un `<Link>` par capacité, nom traduit énonçant l'état |
| `CapabilityList.tsx` | la même carte en liste (téléphone) |
| `CapabilityMapView.tsx` | choisit selon `useMediaQuery('(min-width: 1024px)')` |
| `capability-state.ts` | met l'état en mots — **une seule fois pour les deux surfaces** |

Trois règles que le rendu ne peut pas enfreindre :

1. **le dessin est décoratif, la couche atteignable est faite de liens.** Un
   `<circle>` avec un `onClick` aurait le même rendu et serait inutilisable
   sans souris ;
2. **la scène garde sa nuit dans les deux thèmes.** Les jetons `--capability-*`
   sont indépendants du thème, anneau de focus compris (`--color-ring`
   s'inverse en quasi-noir en thème clair : focus invisible sur fond sombre) ;
3. **l'immobilité ne coûte pas d'information.** `prefers-reduced-motion` tait
   le mouvement, garde le graphique.

### Deux pièges de peinture, documentés parce qu'ils sont invisibles aux tests

- **`hsl(var(--primary))` est un idiome Tailwind v3.** Ce dépôt est en v4, où
  le jeton est `--color-primary: oklch(…)`. `hsl(oklch(…))` est invalide, et un
  `fill` invalide **retombe sur noir**. Aucun test de rôle ne le voit : une
  étoile noire a le même nom accessible qu'une étoile bleue ;
- **`--cosmos-*` n'existe que sous `.cosmos`**, la classe de la landing. Le
  tableau de bord ne la porte pas : le dégradé qui lit ce jeton ne peint rien.

`__tests__/constellation-figure.test.ts` lit la feuille de style et refuse les
deux. Ces deux pièges valent pour tout SVG ou dégradé ajouté hors de la landing.

### Où l'on entre

La carte n'a **pas de créneau de navigation** : la barre d'en-tête est à sa
largeur limite avec six destinations, et la carte est un endroit qu'on visite,
pas un endroit où l'on vit. Sa porte est la barre d'accès rapide du tableau de
bord (`QuickAccessCompact`), visible sans défilement ; un test de parcours
navigateur garde cette porte, parce qu'une carte que personne n'atteint est une
carte qui n'existe pas.

---

## 3. Étiquettes de statut — `lib/status-tone.ts`

Toute étiquette d'état de l'application (priorité d'une notification, rôle d'un
signal de provenance, sens d'un message) **nomme un ton** et laisse `Badge` le
rendre. Trois composants portaient auparavant leur propre table de classes pour
ce même travail — voir **ADR-205** pour la décision complète.

| Fonction | Entrée | Tons |
| --- | --- | --- |
| `priorityTone` | `low` / `medium` / `high` | `secondary` / `warning` / **`alert`** |
| `outcomeTone` | `origin` / `evidence` / `contradiction` | `info` / `success` / `warning` |
| `directionTone` | `sent` / `received` | `info` / `success` |

Deux règles portent la conception :

- **la hiérarchie vient de la DENSITÉ, pas de la teinte seule.** `alert` est le
  seul fond *solide* des statuts. Mesuré au navigateur : son fond est à L=32
  avec un texte à L=98, quand `warning` reste une teinte à 10 % d'opacité. Les
  jetons `--color-destructive` (27°) et `--color-warning` (50°) ne sont séparés
  que de 23° en OKLCH — à opacité égale, l'œil les confond ;
- **une valeur inconnue est neutre.** Un statut ajouté plus tard par le backend
  ne doit pas arriver en criant.

`alert` réutilise la paire `bg-destructive` / `text-destructive-foreground`,
celle que `Button variant="destructive"` emploie déjà et que
`design-contrast.guard.test.ts` couvre sur 5 thèmes × clair/sombre.

**Une étiquette est faite pour un mot.** `Badge` fixe sa hauteur (`size="sm"`
vaut 16 px) : une phrase de trois lignes en déborde et se lit comme du texte
barré. Ce qui est long se met en valeur par le poids typographique.

**Un bouton d'action se reconnaît à sa forme.** Le style bordé (`outline`) est
employé 137 fois dans l'application ; toute nouvelle action l'adopte, plutôt que
d'introduire une variante qui n'existerait qu'à un seul endroit.
