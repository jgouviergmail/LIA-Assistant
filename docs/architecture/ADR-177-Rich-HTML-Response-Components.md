# ADR-177 : Mode HTML enrichi — vocabulaire de composants et extension du schéma de sanitisation

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Date**: 2026-07-29
**Décideurs**: Équipe LIA (spec `docs/superpowers/specs/2026-07-29-html-enrichi-composants-design.md`)

## Contexte

Le mode d'affichage `html` (`User.response_display_mode`) fait produire au LLM une
réponse `<div class="lia-response">` via la directive `html_response_directive.txt`,
injectée sur les tours action (`_should_inject_html_directive` :
`display_mode == "html" and route_to == "planner"` — élargie le 2026-09-17 aux
tours conversationnels dès qu'aucune voix n'écoute, voir l'amendement), rendue
par le pipeline pinné
`[rehypeRaw, [rehypeSanitize, schema], rehypeMathInText, rehypeKatex]`.

La directive n'exploitait qu'une fraction des capacités déjà en place : callouts
success/error stylés mais non documentés, `details`/`dl`/`kbd` autorisés par le
schéma de sanitisation mais jamais proposés au modèle, aucune classe `language-*`
donc jamais de coloration syntaxique. La frontière XSS
(`apps/web/src/lib/markdown-sanitize-schema.ts`) est auditée et pinnée par tests ;
l'étendre — même par des tags inertes — est une décision à tracer.

## Décision

1. **Vocabulaire de composants** documenté dans la directive et stylé dans
   `lia-components.css`, scopé `.lia-response` : callouts ×4 (+ `.lia-callout__title`),
   chips (réutilisation de `.lia-chip` existante + icônes Material Symbols),
   `details.lia-collapsible`, `dl.lia-kv`, `div.lia-columns`, `ol.lia-steps`,
   `div.lia-stats`, code `language-*` (→ `CodeBlock` : Prism + bouton copier),
   accents inline `mark`/`kbd`/`abbr`. Règle de sobriété dans la directive
   (2-3 composants max par réponse) ; budget de la directive plafonné à 96 lignes.
2. **Schéma de sanitisation étendu de 6 tags inertes** : `mark`, `caption`, `abbr`,
   `time`, `figure`, `figcaption`. Aucun n'est scriptable ; aucun attribut nouveau
   (`title`/`dateTime` sont déjà dans la liste globale du defaultSchema).
   `script`/`iframe`/`form`/handlers restent interdits ; l'ordre des plugins est
   inchangé. Pinné dans les deux sens par `MarkdownContent.sanitize.test.tsx`.
3. **Garde de synchronisation** : `test_html_directive_css_sync.py` (backend, unit)
   échoue si la directive cite une classe `lia-*` absente de la CSS — une classe
   non stylée est une feature qui meurt invisiblement (doctrine ADR-085 appliquée
   au couple prompt/CSS). Le même garde plafonne la longueur de la directive.
4. **Préservation des classes par les overrides de rendu** : les composants `ol`/`ul`
   de `MarkdownContent` préservent désormais les classes `lia-*` (même contrat que
   `p`/`a`) — sans quoi `ol.lia-steps` perdait sa classe au rendu.
5. **Aplatissement client partagé** : `html-plain-text.ts` (multi-ligne, miroir des
   sémantiques de `html_to_text` backend) alimente la copie double-flavor
   (`text/html` + `text/plain`), le partage natif et l'export `.md` ;
   `notification-preview.ts` se refonde dessus sans changement de comportement.
6. **Surlignage de recherche × ligatures** : les spans `material-symbols-outlined`
   sont exclues du surlignage (`rehype-search-highlight`) — un `<mark>` inséré dans
   un nom de ligature cassait l'icône (bug latent pré-existant, rendu fréquent par
   les icônes du vocabulaire).
7. Le gate d'injection (TTS-safe) et le pipeline de rendu sont **inchangés**.

## Conséquences

- (+) Réponses sensiblement plus travaillées sans nouveau chemin de code : purement
  déclaratif (prompt + CSS + allowlist).
- (+) Dégradation propre : un composant mal formé rend comme du HTML simple ; un tag
  inconnu est « unwrapped » ; TTS/notifications aplatissent génériquement (détection
  par le wrapper porteur d'attribut, strip générique).
- (−) La directive coûte ~2× plus de tokens sur les tours action en mode html
  (≤96 lignes, plafonné par test).
- (−) `:has()` requis pour le scoping du `pre` legacy (baseline navigateurs 2023 ;
  dégradation = double boîte, l'état antérieur).
- (~) **Limite connue, mesurée le 2026-07-29** : sur un tour action dont le contenu
  provient d'une **skill** (ex. weather-dashboard), le LLM de synthèse ignore parfois
  la directive et répond en Markdown malgré son injection (loggée). Le rendu reste
  correct (ReactMarkdown) mais sans la mise en page `lia-response`. Comportement
  pré-existant à cette ADR, non aggravé par elle ; piste : renforcer l'autorité de
  la directive sur le chemin skill (hors périmètre ici).

## Amendement 2026-09-17 — la directive suit l'écoute, pas le type de tour

La garde `route_to == "planner"` avait été posée pour la voix : sans tour
planificateur, la réponse du chat est lue telle quelle par la synthèse vocale
progressive, et du HTML y ferait lire des balises. Mais elle ne lisait pas la
préférence vocale : un compte en mode `html` dont la voix est désactivée
recevait du Markdown sur chaque tour conversationnel (mesuré sur une instance
de dev : 30 % des tours d'une semaine), sans qu'aucune voix n'écoute jamais.

La garde devient `display_mode == "html" and (route_to == "planner" or not
voice_enabled)` : la directive n'est retenue que là où une voix lirait du
balisage — un tour conversationnel d'un compte dont les réponses parlées sont
actives. La préférence est celle que lit le coordinateur vocal pour démarrer
la synthèse progressive (`users.voice_enabled`, lue sur le profil chargé par
le flux), portée par le contexte d'exécution typé (`LiaRuntimeContext.voice_enabled`,
accesseur `runtime_voice_enabled`, ADR-231) : la garde d'affichage et le
déclencheur vocal lisent le même drapeau et ne peuvent pas diverger. Un tour
action reste en HTML quelle que soit la préférence, comme avant. Coût : la
directive (~1 500 jetons) est désormais payée sur les tours conversationnels
des comptes `html` sans voix — le choix explicite de ce mode.

## Amendement 2026-09-17 (b) — le mode HTML est une page composée, pas une prose balisée

Constat propriétaire, capture à l'appui : en mode `html`, des réponses outillées (agenda,
météo) rendues en `<p>` + `dl.lia-kv` seulement — un rendu « quasi identique au Markdown ».
Mesuré sur une instance de dev : 5 réponses HTML du jour, 0 callout, 0 stats, 0 chip, 0 `<h2>`,
4 `lia-kv` ; sur la production, 41 réponses HTML en 14 jours portaient 46 callouts, 34 tuiles,
19 chips. Deux causes, toutes deux dans la directive : l'heuristique 1 (« au plus 2-3
composants ; une réponse concise est un `<p>` sans widget ») autorisait la sobriété sur
toute réponse, et rien n'interdisait au modèle d'imiter la forme des réponses précédentes
de la conversation — mesuré : après une première réponse en `lia-kv`, les suivantes
reprennent `lia-kv` là où une conversation vierge donnait tuiles et colonnes.

**Quand une personne choisit le HTML, elle demande une mise en page soignée** : la
directive impose désormais une page COMPOSÉE pour toute réponse porteuse de données —
un `<p>` d'accroche avec le fait clé en `<strong>`, une section par facette (`<h2>` dès
deux facettes) chacune dans le composant qui lui va (chiffres → tuiles, statuts → chips,
métadonnées → `lia-kv` dans sa section jamais en corps entier, procédure → étapes,
comparaison → colonnes ou table), et un callout de clôture dès qu'il y a conseil, réserve
ou suite ; seule une salutation, une réponse d'une phrase ou une question en retour reste
un `<p>`. Une nouvelle heuristique 3 fixe que la forme suit LES DONNÉES de la réponse et
jamais la forme des réponses précédentes. L'exemple canonique est réécrit comme une page
composée. Le budget de lignes (≤ 96, `test_html_directive_css_sync.py`) et la garde
directive↔CSS tiennent. Mesuré après (instance de dev, compte de preuve, conversation
vierge puis suite salutation → fiche → météo → chiffres, en pipeline comme en ReAct) :
chaque réponse à données porte `<h2>` + callout + tuiles ou chips, la salutation reste un
`<p>`. Coût : la directive passe de 74 à 80 lignes (~+150 jetons par tour `html`).

## Amendement 2026-09-25 — un tableau garde des colonnes lisibles, et devient des cartes sur un écran étroit

Constat propriétaire : des tableaux trop larges pour l'écran, des colonnes trop étroites
pour leur contenu, sur ordinateur comme sur téléphone. **La cause était la feuille de
style, pas le modèle.** `globals.css` imposait `white-space: nowrap` aux trois premières
colonnes et n'autorisait le retour à la ligne qu'à partir de la quatrième, en coupant les
mots ; la règle `.lia-response table` (hors couche) imposait la largeur mais n'annulait
jamais ce `nowrap`. Mesuré au navigateur sur une comparaison à cinq colonnes : 908 px dans
une bulle de 341 px, « Prix » et « Avis » écrasées à 40 px, une ligne haute de 869 px ;
dans une bulle de bureau de 976 px, « Prix » encore à 42 px. La position d'une colonne ne
dit rien de son contenu.

- **Les cellules passent à la ligne aux frontières de mots** et aucune colonne n'est plus
  étroite que `8em` ; une URL ou un identifiant (`a`, `code`) peut se couper n'importe où
  plutôt que d'élargir sa colonne. La police des tableaux Markdown passe de 10 px à `0.9em`.
  Un garde de feuille de style (`styles/__tests__/chat-tables.guard.test.ts`) refuse tout
  retour du `nowrap` sur une cellule et toute règle décidée par la position d'une colonne.
- **Un tableau qui déborde un conteneur de moins de 480 px devient une pile de cartes**
  (arbitrage propriétaire) : une carte par ligne, chaque valeur sous le nom de sa colonne.
  `ResponsiveTable` décide (`data-stacked` sur le cadre, écrit avant la première peinture
  par un effet de mise en page) ; le plugin `rehype-table-labels`, après l'assainissement,
  écrit le nom de la colonne sur chaque cellule (`data-label`, `colspan`/`rowspan` suivis
  sur une grille bornée) et les rôles ARIA explicites, qu'un tableau `display: block` perd
  sous WebKit. La décision a une hystérésis : dessiné en cartes, le tableau tient, et le
  relire comme « il tient » le ferait clignoter — la largeur naturelle est celle mesurée
  quand il était encore un tableau. Au-delà de 480 px, un tableau qui déborde encore défile
  avec le repère du bloc de code (barre visible, fondu en bord).
- **La bulle d'un tableau a une largeur définie.** Elle est un élément transversal d'une
  colonne flex (`flex-col items-end`) : `flex: 0 0 95%` réglait sa HAUTEUR, sa largeur
  suivait son contenu, et un tableau empilé — étroit — gardait sa bulle étroite et restait
  empilé à toute largeur (mesuré : 381 px sur un écran de 1280 px après un aller-retour
  téléphone). La règle devient `width: 95%`.
- Au passage : les éléments de tableau transmettent enfin `colspan`, `rowspan`, la classe
  du modèle et l'alignement GFM (porté par `data-align`, jamais par un style inline, qu'une
  carte ne pourrait pas défaire) ; un `style` libre du modèle n'est pas transmis
  (`white-space: nowrap` inline recréerait le défaut). Ces éléments sont définis au niveau
  du module : dans la table `components` reconstruite à chaque rendu, un tableau changeait
  de type à chaque jeton streamé et se remontait. La légende (`caption`), titre du tableau,
  prend la couleur du texte : le ton secondaire mesurait 4,4:1 sous le plancher de 4,5:1.

Aucun jeton de plus : la directive n'a pas bougé. Vérifié dans l'application de dev à 360,
390 (clair et sombre), 768 et 1280 px : aucun débordement de page, aucune violation axe,
aucune colonne sous 94 px en tableau ; spec e2e `chat-html-mode-rendering.spec.ts` étendue
(bureau, téléphone, aller-retour).

## Alternatives considérées

- **Composants React interceptés** (tabs, accordéons animés — pattern
  `ContactPhotoGallery`) : gain maximal mais complexité streaming/a11y/sanitize
  élevée — différé (piste future).
- **Ne pas étendre le schéma** : `mark`/`caption`/`abbr` dégradaient en texte nu —
  coût de l'extension quasi nul, bénéfice sémantique et visuel réel.
- **`<progress>`/`<meter>` natifs** : stylage cross-browser pénible, aucun besoin
  mesuré — écartés (YAGNI).
