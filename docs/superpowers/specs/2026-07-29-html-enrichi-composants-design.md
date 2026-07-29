# Spec — Mode HTML enrichi : composants, styles et intégration sûre

- **Date** : 2026-07-29
- **Statut** : validée sur le principe (périmètre B complet), en attente de relecture finale
- **ADR associée** : ADR-177 (extension du schéma de sanitisation — tags inertes)
- **Périmètre** : mode d'affichage `response_display_mode = "html"` uniquement ; les modes `cards` et `markdown` sont structurellement hors d'atteinte des changements (tout est scopé `.lia-response` ou purement additif).

## 1. Contexte et objectif

Le mode « HTML enrichi » fait produire au LLM une réponse HTML complète enveloppée dans
`<div class="lia-response">`, via la directive `apps/api/src/domains/agents/prompts/v1/html_response_directive.txt`
injectée sur les tours action (`display_mode == "html"` et `route_to == "planner"`,
`response_node.py::_should_inject_html_directive`). Le rendu passe par le pipeline pinné
`[rehypeRaw, [rehypeSanitize, markdownSanitizeSchema], rehypeMathInText, rehypeKatex]`
(`apps/web/src/components/chat/MarkdownContent.tsx`).

**Constat vérifié** : la directive n'exploite qu'une fraction des capacités déjà en place
(CSS `.lia-response` = 113 lignes ; callouts success/error stylés mais non documentés ;
`details/summary`, `dl/dt/dd`, `kbd`, `sub/sup` déjà autorisés par le schéma mais jamais proposés ;
aucune coloration syntaxique faute de classe `language-*`). Objectif : améliorer sensiblement
le style, la mise en forme et le vocabulaire de composants du mode HTML enrichi, sans aucune
régression technique ni fonctionnelle.

## 2. Décisions actées

1. **Périmètre B complet** (Lots 0-3 ci-dessous), incluant copie double-flavor et e2e hermétique.
2. **ADR-177 courte** documentant l'extension du schéma de sanitisation (la frontière XSS est
   touchée, même par des tags inertes — précédent ADR-160/161).
3. **Description du mode dans les réglages enrichie à la release** (6 locales, parité stricte).
4. Approche C (composants React interactifs interceptés — tabs, accordéons animés) : **hors
   périmètre**, consignée comme piste future dans l'ADR.

## 3. Design

### Lot 0 — Baseline runtime (préalable, aucune écriture)

- Capture visuelle avant/après en conteneur dev (`docker restart lia-web-dev` obligatoire avant
  toute validation navigateur) : réponse HTML enrichie réelle, light + dark, desktop + ≤430px.
- Confirmer le contraste du `code` inline (fond `--lia-surface` = blanc en light) sur la bulle.
- Confirmer l'élément racine rendu par `CodeBlock` (attendu : `div`) — conditionne le sélecteur
  `:has(> code)` du Lot 1.
- Vérifier qu'aucun test backend ne pinne le contenu de `html_response_directive.txt`.

### Lot 1 — Corrections et polish du socle (frontend uniquement)

Tout en CSS scopé `.lia-response` (cascade prouvée : `lia-components.css` est importée hors
`@layer` dans `globals.css:6`, les styles non-layerés battent les utilities Tailwind), sauf le
correctif search-highlight (TS) :

1. `.lia-response p { white-space: normal; }` — un HTML pretty-printé avec retours à la ligne
   dans un `<p>` ne produit plus de césures parasites (l'utility `whitespace-pre-wrap` posée par
   l'override `p` reste active en Markdown/Cards, non scopés `.lia-response`).
2. `.lia-response pre` scopé `:has(> code)` — le style « boîte de code legacy » ne s'applique
   plus quand `CodeBlock` (racine `div`) prend le relais ; dégradation acceptable sans `:has`
   (double boîte legacy, comportement actuel).
3. Contraste du code inline : token adapté (`--lia-surface-active` ou `--lia-primary-subtle`),
   correct dans les deux thèmes via tokens.
4. Rythme vertical : `.lia-response > :first-child { margin-top: 0 }`,
   `.lia-response > :last-child { margin-bottom: 0 }`, harmonisation des marges h2/h3/tables.
5. Tables : zébrage `tbody tr:nth-child(even)`, style `caption` (dépend du Lot 2 schéma).
6. Callouts : padding/typo affinés + `.lia-callout__title` (l'override `p` de MarkdownContent
   préserve les classes `lia-*`).
7. **Fix search-highlight × ligatures** : ajouter `material-symbols-outlined` aux classes
   skippées de `apps/web/src/lib/rehype-search-highlight.ts` (`SKIP_CLASSES`) + test — bug
   latent pré-existant (un terme de recherche égal à un nom de ligature casse l'icône), rendu
   plus fréquent par le Lot 2.

### Lot 2 — Vocabulaire de composants

**Markup canonique** (documenté dans la directive, stylé dans la CSS, couvert par les tests) :

```html
<!-- Callouts (4 variantes : info, success, warning, error) -->
<div class="lia-callout lia-callout-success">
  <p class="lia-callout__title">Titre optionnel</p>
  <p>Corps du message…</p>
</div>

<!-- Chips inline (variantes existantes : --green, --amber, --red, --indigo + neutre) -->
<span class="lia-chip lia-chip--green">
  <span class="material-symbols-outlined">check_circle</span>Confirmé</span>

<!-- Bloc dépliable -->
<details class="lia-collapsible">
  <summary>Voir le détail</summary>
  <p>Contenu replié…</p>
</details>

<!-- Liste clé-valeur -->
<dl class="lia-kv">
  <dt>Date</dt><dd><strong>12 août 2026</strong></dd>
  <dt>Lieu</dt><dd>Paris</dd>
</dl>

<!-- Colonnes responsives (comparaisons) -->
<div class="lia-columns">
  <div>…colonne A…</div>
  <div>…colonne B…</div>
</div>

<!-- Étapes numérotées stylisées -->
<ol class="lia-steps"><li>Première étape</li><li>Deuxième étape</li></ol>

<!-- Tuiles de chiffres clés -->
<div class="lia-stats">
  <div class="lia-stat"><span class="lia-stat__value">12</span><span class="lia-stat__label">rendez-vous</span></div>
</div>

<!-- Code avec coloration syntaxique + bouton copier (CodeBlock existant) -->
<pre><code class="language-python">print("hello")</code></pre>

<!-- Inline : mark, kbd, abbr, sub/sup ; tables avec <caption> -->
```

**Directive** (`html_response_directive.txt`, réécriture compacte — elle coûte des tokens à
chaque tour action, budget ≈ 2× la version actuelle maximum) :

- Documente le vocabulaire ci-dessus avec une ligne d'usage par composant (« quand l'utiliser »).
- **Règle de sobriété** : 2-3 composants riches maximum par réponse, adaptés au contenu ; une
  réponse courte reste légère.
- Règles de forme : jamais de `<style>` ni de `style=""` inline (inchangé) ; balises à la
  colonne 0 de préférence (le dedent `stripHtmlBlockIndent` tolère l'indentation) ; `<br>` pour
  un saut de ligne volontaire dans un paragraphe ; toujours une classe `language-*` sur les
  blocs de code (`language-text` par défaut) ; icônes = noms de ligatures Material Symbols
  valides uniquement.
- Math : inchangé (`$…$` / `$$…$$`, géré par rehypeMathInText post-sanitize).

**Schéma de sanitisation** (`markdown-sanitize-schema.ts`, ADR-177) :

- Ajout aux `tagNames` : `mark`, `caption`, `abbr`, `time`, `figure`, `figcaption` — tous
  inertes (aucun comportement scriptable, aucun attribut dangereux nouveau ; `title` est déjà
  dans la liste globale d'attributs du defaultSchema). Comportement actuel : « unwrap » silencieux.
- Aucun autre changement : `script`/`iframe`/`form`/handlers restent interdits, `<style>` strippé,
  protocoles inchangés, ordre des plugins intouché.
- Tests sanitize étendus **dans les deux sens** : chaque tag ajouté survit ; les vecteurs
  d'attaque restent strippés (dont tentative de `<mark onmouseover=…>`).

**CSS** (`lia-components.css`, section `.lia-response` étendue) :

- Nouveaux blocs : `.lia-callout__title`, `.lia-collapsible` (bord, chevron animé, focus-visible
  natif sur `summary`), `.lia-kv` (grid `auto 1fr`), `.lia-columns`
  (`repeat(auto-fit, minmax(min(240px, 100%), 1fr))` — repli mobile garanti), `.lia-steps`
  (compteurs CSS), `.lia-stats`/`.lia-stat`, `.lia-response mark/kbd/abbr/caption`.
- 100 % tokens (`--lia-*`) + overrides `.dark` pour toute teinte codée en dur (imiter les chips) ;
  `max-width: 100%` systématique ; aucun sélecteur dépendant d'un nombre d'enfants (dégradation
  propre en streaming partiel).
- Commentaires « Keep in sync » mis à jour des deux côtés (CSS ↔ directive).

### Lot 3 — Intégration, preuves, ratchets

1. **Copie double-flavor** : util `message-clipboard.ts` — si le contenu est du HTML (réutiliser
   la détection de `notification-preview.ts`), écrire `ClipboardItem` `{text/html, text/plain}`
   (plain = aplatissement complet sans troncature), fallback `writeText(plain)` si
   `ClipboardItem` indisponible ; branché sur `handleCopyMessage` (`ChatMessage.tsx`). Vérifier
   au passage le menu **partage/export** (même fichier) : s'il exporte le contenu brut, réutiliser
   le même util.
2. **E2E hermétique** : `apps/web/e2e/smoke/chat-html-mode-rendering.spec.ts` — SSE mocké
   streamant une réponse `lia-response` riche (fixture avec tous les composants) : rendu effectif
   (jamais de texte brut `<h2>…`), zéro overflow horizontal (harnais overflow-report existant),
   scan axe sur la région du message.
3. **Tests frontend** : `MarkdownContent.rich-components.test.tsx` (chaque composant rend avec
   ses classes ; `details open` ; chemin `language-*` → CodeBlock ; HTML tronqué mi-stream ne
   rend jamais de texte brut) + extensions sanitize + test search-highlight ligatures.
4. **i18n** : description du mode enrichie dans les réglages — bloc du sélecteur de mode
   d'affichage (`fr/translation.json` ≈ l. 1207-1217 : `info` + option « HTML enrichi ») — dans
   les **6 locales** (parité stricte pré-commit).
5. **Docs** : ADR-177 + `ADR_INDEX.md` ; `docs/technical/RESPONSE.md` (§ modes + composants) ;
   `docs/INDEX.md` si nouvelle entrée.
6. **Gates et ratchets** : `task lint`, `task test:frontend:coverage`, `task ci:fast` ; preuve
   runtime en conteneurs (tour de chat réel en mode HTML via lia-api-dev + lia-web-dev, light +
   dark + mobile) ; re-mesure de la couverture frontend → **relever les planchers** de
   `apps/web/vitest.config.ts` si ≥2 pts de marge (jamais de baisse) ; aucun autre ratchet
   (a11y, hooks, cc, SLOC backend) impacté par nature — le vérifier via `task lint`.

## 4. Edge cases couverts (vérifiés sur pièces)

| Cas | Comportement | Preuve |
|-----|--------------|--------|
| Streaming partiel | parse5 abandonne un tag incomplet en fin de flux, auto-ferme les éléments ouverts ; composants choisis sans dépendance au nombre d'enfants | pipeline rehype-raw ; bug d'indentation déjà fixé + testé |
| TTS / notifications / push | Détection via le `div` porteur d'attribut puis strip générique `<[^>]+>` — nouveaux tags inclus | `plain_text.py`, `notification-preview.ts` |
| Historique (mode html) | Neutralisation générique des réponses précédentes | `message_filters.py::filter_for_llm_context` |
| Dark mode | Tokens redéfinis dans `.dark` ; nouvelles teintes dures avec override `.dark` explicite | `lia-components.css:133-169` |
| Mobile ≤430px | `minmax(min(240px,100%),1fr)`, chips en wrap, tables sous wrapper `overflow-x-auto` (override `table` actif aussi sur le HTML brut) | `MarkdownContent.tsx` |
| Messages legacy | `<style>` inline toujours strippé sans fuite de texte ; anciens callouts inchangés | test sanitize existant |
| Modes cards/markdown | Aucun changement : styles scopés `.lia-response`, directive gated, schéma additif | contrôles dans les tests |
| ReAct | `route_to ∈ {planner, response}` indépendant du mode d'exécution — couvert | `query_intelligence.py:109` |
| KaTeX / recherche | Post-sanitize, inchangés ; ligatures désormais skippées du surlignage | `rehype-search-highlight.ts` |
| Voix (tours action html) | Aplatissement TTS testé (`test_tts_text_sanitization.py`), générique | inchangé |

## 5. Risques résiduels et mitigations

- **Sur-usage des composants par le modèle** → règle de sobriété explicite dans la directive ;
  validation sur tours de chat réels (Lot 0 baseline / Lot 3 preuve) ; ajustable sans code.
- **Coût tokens de la directive** (tours action seulement) → budget ≤2× l'actuelle, mesuré.
- **`:has()`** → baseline navigateurs 2023+ ; dégradation = double boîte legacy (état actuel).
- **Police d'icônes bloquée (offline/adblock)** → la ligature s'affiche en texte ; identique aux
  cartes actuelles, assumé.

## 6. Critères d'acceptation

1. Une réponse HTML enrichie réelle (conteneurs dev) affiche les nouveaux composants correctement
   en light, dark, desktop et mobile — captures à l'appui.
2. Tous les tests existants restent verts sans modification d'assertion ; les nouveaux tests
   couvrent chaque composant, chaque tag ajouté au schéma, et le fix ligatures.
3. `task lint`, `task test:frontend:coverage`, `task ci:fast` verts — sorties citées.
4. Copier un message HTML colle du texte lisible (et du HTML riche là où le collage le supporte).
5. Parité i18n 6 locales (hook pré-commit vert).
6. Planchers de couverture relevés si la marge le permet (≥2 pts), jamais baissés.
7. ADR-177 rédigée, indexée ; RESPONSE.md à jour ; commentaires de synchronisation à jour.
