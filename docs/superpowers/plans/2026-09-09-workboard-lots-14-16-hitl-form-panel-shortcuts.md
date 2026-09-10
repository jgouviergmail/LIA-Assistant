# Lots 14 à 16 — La carte HITL a une seule forme, le ticket a des panneaux, la personne a ses raccourcis (ADR-276)

> Plan vérifié le 2026-09-09, chaque affirmation lue dans le code avant d'être
> écrite. Il répond aux retours du propriétaire après usage réel (deux
> captures d'écran, douze remarques et une fonctionnalité neuve), après les
> lots 8 à 13 qui avaient traité les treize retours précédents.

## Lot 14 — La forme des messages HITL, seconde passe (captures 1 et 2)

### Ce que les captures montrent, et pourquoi

**Capture 1 (le chat).** La carte est ÉCRITE PAR LE MODÈLE sous
`prompts/v1/hitl_draft_critique_prompt.txt`, qui lui demande un titre, des
lignes de champs et des règles `---`. Le flux passe ensuite par
`_with_markdown_hard_breaks` (`hitl/interactions/draft_critique.py`), qui
ajoute `<br/>` à toute ligne suivie d'UN saut de ligne : une ligne `---`
suivie d'un seul saut devient `---<br/>`, qui n'est plus une règle horizontale
Markdown et s'affiche telle quelle. Et le modèle sépare volontiers les champs
par des lignes vides, donc chaque champ devient un paragraphe du chat avec sa
marge — les « interlignes inutiles ». La FORME de la carte est celle que le
modèle veut bien produire ; corriger le convertisseur ne corrige que la moitié
du problème.

**Capture 2 (le ticket).** `_confirming_plan` (`scheduler/workboard_runner.py`)
compose « question + aperçu détaillé + consigne », alors que la question
porte déjà la carte du modèle : l'e-mail est montré deux fois.

### La décision

**Le renderer écrit la carte, le modèle écrit la question** — la doctrine
d'ADR-274, appliquée au HITL, dans la continuité du lot 13 (qui a donné une
seule grammaire à l'aperçu : Markdown).

- `render_confirmation_card(draft, language, timezone)` dans
  `drafts/preview_renderer.py` : `{emoji} **{titre}**`, ligne vide, l'aperçu
  détaillé du lot 13. L'emoji et le titre viennent du registre d'affichage
  (`drafts/display.py`, `emoji` et `item_label_fields`) ; un titre introuvable
  retombe sur le résumé (`summary_renderer`), jamais sur « ? ».
- `DraftCritiqueInteraction.generate_question_stream` émet la carte AVANT
  le premier jeton du modèle, puis `---` entre deux lignes vides, puis la
  question streamée. Le repli (modèle en échec) émet la carte puis une phrase
  localisée : la question de suppression et son avertissement d'irréversibilité
  pour un type destructif (`_DESTRUCTIVE_CONFIRM_UI`), sinon la phrase
  générique de `_FALLBACK_MESSAGES[DRAFT_CRITIQUE]`.
- Le prompt ne décrit plus aucune carte : « la carte est déjà affichée
  au-dessus de ta réponse ; écris la question de validation seule ». Le prompt
  de repli en ligne suit.
- `draft_fallback_summary.py`, `HitlMessages.get_draft_summary` et
  `_DRAFT_SUMMARIES` — une TROISIÈME copie du vocabulaire de la carte, lue par
  le seul repli — sont supprimés avec leur garde de complétude.
- `_with_markdown_hard_breaks` n'ajoute jamais `<br/>` à une ligne qui est une
  règle horizontale (défense en profondeur : le modèle n'en écrit plus).
- Sur le ticket, `WorkboardMessages.confirming(language, question=)` perd
  `preview` ; `_draft_preview` disparaît ; la borne coupe la question.

### Tests

Carte : en-tête et titre pour les 26 types, repli du titre sur le résumé,
séparateur. Flux : la carte précède le premier jeton, le repli porte la carte
et la phrase, un type inconnu streame sans carte. Convertisseur : une règle
`---` reste une règle. Runner : le commentaire = question + consigne, sans
aperçu doublé ; un lot énumère ses éléments dans la question. Rendu : un test
vitest fait passer un échantillon composé par `MarkdownContent` et attend un
`<hr>` et un `<ul>`.

### Preuve runtime

Dans le conteneur : le flux réel de l'interaction avec un modèle simulé (le
prompt réel chargé), puis `plan_settle` sur l'interruption obtenue.

## Lot 15 — Le ticket, passe de design (dix remarques)

1. **Tuile Registres** : `dashboard.quick_access_compact.actions_sub` →
   « Tracer les actions » ×6.
2. **Mode d'exécution** : libellés « Mode Pipeline » / « Mode ReAct » — ceux
   que l'en-tête du chat porte déjà (`executionMode.toggle.*`) ; plus de
   texte explicatif (`workboard.execution_mode.*_hint` supprimés).
3. **Suivi** : « Notifier l'avancement dans le chat », sans texte explicatif
   (`workboard.form.follow_hint` supprimé).
4. **Panneaux** : chaque section du détail devient un panneau
   (`rounded-lg border border-border/60 p-3`, titre avec icône thème) —
   données, réglages (`FormSection`, un `fieldset` annoncé), dernière
   exécution, coût, étapes, commentaires, historique. Dernière exécution et
   coût côte à côte dans une grille `sm:grid-cols-2`, même hauteur.
5. **Coût** : `workboard.detail.usage` → « Coût » ×6 ; UNE ligne
   `🟠 IN · 🟢 OUT · 🔵 CACHE · 🟣 GOOGLE · coût`, le nombre de runs en
   suffixe du titre.
6. **Historique** : « Rendu » ne dit rien. `returned` → « Rendu au
   propriétaire », `handed_back` (un run qui rend le ticket) → « LIA vous rend
   le ticket », `released` → « Rendu au propriétaire — connexion supprimée ».
7. **Rafraîchissement** : `comment`, `patch` et `runNow` relisent le tableau
   après succès (seuls `create` et `remove` le faisaient) — la réponse à un
   HITL déplace le ticket côté serveur, et un changement de colonne depuis le
   panneau doit mettre à jour les compteurs d'en-tête, qui sont l'agrégat du
   serveur.
8. **Carte** : plus de badge de priorité (l'arête et le fond d'urgent la
   disent) ; le nom de la priorité reste pour un lecteur d'écran (`sr-only`).
9. **Carte** : cloche puis porteur, en tête de carte au-dessus du titre, avec
   le « ⋮ » à droite ; le reste (état du run, étapes, échéance) sous le titre.
10. Le parcours e2e « a card never lays its badges under its actions » est
    rejoué et adapté à la nouvelle géométrie.

## Lot 16 — « Mes raccourcis »

- **Backend** : colonne `users.settings_shortcuts` (JSONB, NULL = aucun),
  migration, lecteur tolérant + schéma strict (≤ 5, slugs uniques,
  `^[a-z0-9-]+$`, ≤ 64 caractères) dans `domains/users/settings_shortcuts.py`,
  `PUT /users/me/settings-shortcuts` (remplacement complet), et la liste
  exposée dans `UserProfile` pour que `useAuth().user` la porte sur chaque
  écran sans requête supplémentaire. Le vocabulaire des sections est celui du
  FRONTEND (`SettingsSectionToken`) : le backend en garde la FORME, le frontend
  filtre à la lecture ce qu'il ne connaît plus.
- **Section** `my-shortcuts` (Préférences / Personnalisation, après
  `chat-shortcuts`) : chaque section DISPONIBLE pour ce compte
  (`buildSettingsShellModel`, mêmes portes que la recherche), groupée comme le
  rail, une case à cocher, cinq au plus (la sixième est `aria-disabled` avec
  le compteur « 5 sur 5 »), enregistrement optimiste avec retour arrière.
- **Dock flottant** `ShortcutsDock`, monté dans la disposition du tableau de
  bord (tous les écrans), rendu seulement avec au moins un raccourci :
  capsule verre (`bg-background/85 backdrop-blur-xl`), cibles de 44 px, icône
  de la section dans la teinte de son groupe, libellé accessible, clic →
  `settingsSectionHref`. Déplaçable (pointeur + flèches) et réductible en
  point de rappel, sans redimensionnement — la mécanique de `useEyesDrag`
  GÉNÉRALISÉE en `useFloatingDrag(rootRef, position, setPosition)`, que les
  yeux réutilisent. Position persistée par appareil (zustand + `persist`,
  clé hors registre de purge comme celle des yeux). Position par défaut : le
  bord droit à mi-hauteur, hors des yeux (au-dessus du composeur) et du
  compagnon (en bas à gauche).
- Locales ×6, gardes des tables de réglages (+1 section), tests du hook, de
  la section et du dock, tests backend (schéma, lecteur, route, rejeu de
  migration).
