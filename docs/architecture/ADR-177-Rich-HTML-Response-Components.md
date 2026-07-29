# ADR-177 : Mode HTML enrichi — vocabulaire de composants et extension du schéma de sanitisation

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Date**: 2026-07-29
**Décideurs**: Équipe LIA (spec `docs/superpowers/specs/2026-07-29-html-enrichi-composants-design.md`)

## Contexte

Le mode d'affichage `html` (`User.response_display_mode`) fait produire au LLM une
réponse `<div class="lia-response">` via la directive `html_response_directive.txt`,
injectée sur les tours action (`_should_inject_html_directive` :
`display_mode == "html" and route_to == "planner"`), rendue par le pipeline pinné
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

## Alternatives considérées

- **Composants React interceptés** (tabs, accordéons animés — pattern
  `ContactPhotoGallery`) : gain maximal mais complexité streaming/a11y/sanitize
  élevée — différé (piste future).
- **Ne pas étendre le schéma** : `mark`/`caption`/`abbr` dégradaient en texte nu —
  coût de l'extension quasi nul, bénéfice sémantique et visuel réel.
- **`<progress>`/`<meter>` natifs** : stylage cross-browser pénible, aucun besoin
  mesuré — écartés (YAGNI).
