# ADR-206 : une primitive porte son contrat, et un écran vide a une porte de sortie

- **Statut** : accepté
- **Date** : 2026-08-05
- **Portée** : `components/ui/{field,input,textarea,skeleton,loading-spinner,search-input,alert,pagination,empty-state}.tsx`, `eslint.config.mjs`, `styles/globals.css`, réglages Langue / Fuseau, page de retour OAuth

## Contexte

Un audit UX/UI transversal a mesuré quatre écarts que les gardes en place ne
pouvaient pas voir, chacun pour une raison différente.

**La garde d'accessibilité mesurait une fraction de l'interface.** `jsx-a11y`
n'inspecte que les éléments DOM natifs. Sans table de correspondance, tout ce qui
passe par `<Input>`, `<Label>`, `<Button>` lui est invisible : la baseline
affichait `0` en ne regardant que le HTML écrit à la main. La table a été
essayée puis **rejetée** — la règle analyse chaque élément isolément, donc un
`<Label htmlFor="x">` voisin d'un `<Input id="x">` lui apparaît comme un champ
sans étiquette : 96 signalements, dont tous les cas échantillonnés étaient du
code correct. Le dépôt documentait déjà cette limite dans `login-form.tsx`
(« static analysis cannot resolve it across elements »).

**Une erreur de saisie était visible sans être annoncée.** `aria-invalid`
n'apparaissait nulle part dans les 643 fichiers : `Input` peignait une bordure
rouge et un paragraphe rouge, sans lien programmatique entre le champ et son
message. WCAG 3.3.1 et 1.3.1 sont tous deux de niveau A. L'identité du champ
venait par ailleurs du **texte de l'étiquette** (`label.toLowerCase()`), donc
deux champs homonymes partageaient un `id` et l'identifiant changeait de langue.

**Les primitives parlaient anglais.** `LoadingSpinner` annonçait « Loading… »
par défaut sur ses ~90 appels, `Skeleton` posait un `role="status"` par
rectangle — 24 régions live pour un tableau de cinq lignes — et `CardSkeleton`
peignait `bg-white`, soit une carte blanche sur le thème sombre. `Pagination`
gardait des libellés **français** en valeurs par défaut.

**Un état vide était un cul-de-sac.** Sept états vides, quatre remplissages
verticaux, deux tailles d'icône, quatre manières d'atténuer une icône — et
surtout **un seul des sept proposait une action**.

## Décision

**Le contrat d'un champ vit dans une seule place.** `ui/field.tsx` expose
`useFieldA11y` (identité par `useId`, `aria-invalid`, `aria-describedby`
**additif** — un indice déjà posé par l'appelant survit à l'erreur) et
`FieldFrame`, qui rend l'étiquette avec la primitive `Label` au lieu d'un
`<label>` dont les classes en étaient déjà la copie exacte.

**Le nom accessible des contrôles du design system se garde sur le DOM RENDU**,
pas dans ESLint. `form-control-names.guard.test.tsx` ne signale que ce qu'une
analyse statique peut trancher sans deviner : un contrôle sans `label`, sans
`aria-label`, sans `aria-labelledby` et sans `id` n'a **aucun** mécanisme
capable de le nommer. Un `placeholder` n'en est pas un — il disparaît à la
saisie. 27 contrôles ont été nommés, la garde est à zéro et sa liste de gel
est vide.

**Une primitive n'invente jamais une chaîne, et la contrainte de rendu décide
comment.** `LoadingSpinner`, `alert`, `pagination` et `search-input` résolvent
leurs libellés depuis la locale active. `Skeleton` ne le peut pas —
`dashboard/{settings,spaces}/loading.tsx` sont des composants **serveur** de
l'App Router — donc il devient **décoratif** (`aria-hidden`) et n'annonce que si
l'appelant lui passe un libellé déjà traduit : une région live par section, non
plus une par rectangle.

**Un écran vide a une porte de sortie, et le type l'impose.** `ui/empty-state.tsx`
n'accepte `variant="page"` qu'avec une `action`. `reason` sépare « rien n'existe
encore » de « le filtre n'a rien trouvé », qui appellent des mots et des sorties
différents.

**L'état sélectionné se dit, il ne se désactive pas.** Poser `disabled` sur le
bouton que l'utilisateur vient d'activer le retire du parcours de tabulation et
le **défocalise** : le focus retombe sur `<body>`. Les sélecteurs de langue et de
fuseau portent `aria-current` et gardent leur garde dans le gestionnaire — c'est
la garde, jamais l'attribut, qui empêche la double soumission (règle déjà écrite
dans `apps/web/CLAUDE.md`, constatée sur `PeerConnectionsSettings` le
2026-07-31).

**Un jeton réclamé par un utilitaire doit exister.** Huit composants demandaient
`ring-offset-background` sans que `--color-ring-offset-background` soit déclaré :
Tailwind n'émettait rien et l'écart retombait sur son **blanc** natif, soit un
halo blanc autour de chaque contrôle focalisé sur le thème sombre.

## Le même statut porte le même ton, partout

ADR-205 a réglé UNE famille de statuts — la priorité des notifications. Toutes
les autres surfaces continuaient de décider seules, et le même sens portait
jusqu'à trois couleurs : « fonctionne » était bleu sur les serveurs MCP et les
actions programmées, vert sur les sources Drive, les documents et les espaces,
et **gris** sur les appels récents — où `failed` et `completed` étaient, de ce
fait, la même pastille. « En cours » était `info` sur Drive, `outline` sur les
actions et les documents, et une teinte bleue écrite à la main sur les appels.

**Le vocabulaire de cycle de vie est partagé, donc la table l'est aussi.**
`error`, `completed`, `active`, `syncing`, `pending` veulent dire la même chose
d'où qu'ils viennent : `lifecycleTone` les fait tomber dans cinq familles —
`success` (ça marche), `info` (ça se passe maintenant), `destructive` (ça a
échoué), `warning` (à surveiller, rien n'est cassé), `secondary` (inerte). Un
écran n'ajoute une correspondance que si son domaine nomme réellement autre
chose (`callOutcomeTone` : un interlocuteur qui décline est un fait, pas une
panne — donc neutre, jamais rouge).

**`alert` reste le seul fond solide**, réservé à la hiérarchie de priorité :
`lifecycleTone` ne le renvoie jamais, et un test l'énonce.

**Tout variant de `Badge` vient d'un jeton.** `success` et `destructive`
peignaient `green-100` / `red-100`, valeurs fixes hors des cinq thèmes et hors
de la garde de contraste — et `lifecycleTone` route la majorité des statuts
vers ces deux-là précisément. Le commentaire qui les justifiait (« fonds opaques
pour éviter que le dégradé transparaisse ») décrivait un risque disparu :
mesuré, `Card variant="gradient"` n'a **aucun** site d'appel. Les deux paires
résultantes étaient déjà couvertes par la garde.

**Le bouton qui confirme dit ce qu'il fait.** `AlertDialogAction` rendait
`buttonVariants()` sans variant : le bouton qui valide une suppression
irréversible sortait dans le même bleu que « Enregistrer », et n'acceptait
aucune prop `variant` — de sorte que le seul moyen de le rendre rouge était de
réécrire les classes sur place. Dix-sept sites l'ont fait, et ils ont dérivé
aussitôt : trois oubliaient `text-destructive-foreground` (le libellé gardait
`text-primary-foreground`, dont le contraste n'était la responsabilité de
personne) et un atteignait `bg-orange-600`, hors thème et hors garde. Le variant
est désormais une prop résolue par `buttonVariants`. Deux niveaux de destruction
côte à côte (« tout supprimer sauf les épinglés » / « tout supprimer ») se
distinguent par `warning` et `destructive`, deux paires que la garde couvre.

**Le déclencheur et la confirmation ne portent pas le même poids.** Les icônes
de suppression en bout de ligne restent `ghost` : dix-huit boutons rouges pleins
dans une liste diluent le signal au lieu de le porter. C'est la confirmation,
elle, qui doit être rouge.

## Conséquences

- Un `aria-label` **redondant** avec le texte visible est retiré, non traduit :
  le bouton de langue est nommé par ce qu'il affiche, donc localisé par
  construction et conforme à WCAG 2.5.3 (*Label in Name*).
- Une clé déjà présente est réutilisée avant d'en créer une : `common.loading`,
  `common.close`, `common.search`, `settings.search.clear`. Deux clés seulement
  ont été ajoutées (`common.pagination.label`, `common.pagination.page_info`).
- Le squelette des réglages ne dessine plus les sections réservées aux
  administrateurs, et adopte la géométrie de la page réelle : il promettait un
  contenu que la plupart des comptes ne voient jamais, avec des gouttières en
  double qui décalaient la page à l'arrivée du contenu.
- La prop `error` de `Input`/`Textarea` reste **inutilisée** : les erreurs de
  formulaire passent aujourd'hui par `toast.error` (331 appels, 5 s). Le contrat
  est désormais correct pour le jour où elles reviendront en ligne — c'est un
  chantier distinct.

## Alternatives écartées

**Mapper les composants dans `jsx-a11y`.** Mesuré : 96 signalements, échantillon
intégralement composé de code correct. Geler cela aurait figé du bruit et masqué
les vrais cas.

**Rendre le spinner muet par défaut.** Séduisant contre le bavardage, mais dix
suites de tests s'appuient sur son `role="status"` comme signal de chargement —
ce rôle est l'information, pas un détail d'implémentation. Seule la chaîne
anglaise devait partir.

**Migrer les 27 champs vers la prop `label` de `Input`.** Plus court, mais
`FieldFrame` ajoute `space-y-2` : 27 champs auraient bougé. `htmlFor`/`id`
corrige l'accessibilité à rendu strictement identique.

## Références

- ADR-205 — un statut nomme un ton, il n'écrit pas ses couleurs
- ADR-061 — un sous-système désactivé est absent, jamais grisé
- Audit AC-002 — garde de contraste du design system
