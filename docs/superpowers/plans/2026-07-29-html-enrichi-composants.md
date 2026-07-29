# Mode HTML enrichi — composants, styles et intégration sûre : plan d'implémentation

> **Exécution :** inline via `superpowers:executing-plans` (sous-agents interdits — directive
> utilisateur). Les étapes utilisent la syntaxe checkbox (`- [ ]`) pour le suivi.
> **Spec source :** `docs/superpowers/specs/2026-07-29-html-enrichi-composants-design.md`

**Goal :** enrichir sensiblement le mode d'affichage « HTML enrichi » (styles, mise en forme,
vocabulaire de composants) sans aucune régression sur les modes `cards`/`markdown`, le TTS,
les notifications, le streaming ni la frontière XSS.

**Architecture :** tout est additif ou scopé `.lia-response` — la directive de prompt
(`html_response_directive.txt`) expose un vocabulaire de composants que la CSS
(`lia-components.css`) style et que le schéma de sanitisation autorise ; un garde backend
verrouille la synchronisation directive↔CSS ; la copie/partage gagne un aplatissement
HTML→texte partagé côté client.

**Tech stack :** Next.js 16 / React 19 / react-markdown + rehype-sanitize 5 (frontend),
prompt versionné `.txt` (backend), vitest + Playwright hermétique, pytest.

## Global Constraints

- **JAMAIS d'action git** (commit/push/checkout) — l'utilisateur committe lui-même. Chaque
  tâche se termine par un point de contrôle « gates verts + signaler », pas par un commit.
- **Jamais de validation runtime locale** hors conteneurs : navigateur → `lia-web-dev`
  (http://localhost:3100, `docker restart lia-web-dev` OBLIGATOIRE avant toute vérif — pas de
  hot-reload des éditions hôte) ; API → `lia-api-dev` (https://localhost:8000, `curl -sk`).
- **Ordre des plugins intouché** : `[rehypeRaw, [rehypeSanitize, markdownSanitizeSchema],
  rehypeMathInText, rehypeKatex]` (`MarkdownContent.tsx:587-592`) — frontière XSS du
  CLAUDE.md frontend.
- **Gate TTS intouché** : `_should_inject_html_directive` reste `display_mode == "html" and
  route_to == "planner"` (`response_node.py:205`). Aucun changement de code backend hors test.
- **Ratchets shrink-only** : planchers de couverture (`apps/web/vitest.config.ts:95-98` —
  64/58/58/65 global), a11y, hooks, cc, SLOC — jamais baissés ; relever la couverture
  frontend si ≥2 pts de marge après re-mesure.
- **i18n** : parité stricte des clés sur 6 locales (en référence) — hook pre-commit bloquant.
- **Commentaires/docstrings du code en anglais** ; prompts en anglais (fichier versionné).
- **Budget directive** : ≤ 96 lignes (2× l'actuelle de 48).
- Tests frontend : `renderWithProviders` de `@/__tests__/test-utils` (modèle :
  `MarkdownContent.html-indent.test.tsx`) ; mocks via `vi.hoisted` + `vi.mock`.
- Fichiers Python : MyPy strict (hints complets), structlog si logging (aucun prévu),
  Black 100 col.

## Carte des fichiers

| Action | Fichier | Responsabilité |
|--------|---------|----------------|
| Modify | `apps/web/src/lib/rehype-search-highlight.ts` | skip des ligatures d'icônes (T2) |
| Modify | `apps/web/src/components/chat/__tests__/MarkdownContent.search.test.tsx` | test ligatures (T2) |
| Modify | `apps/web/src/styles/lia-components.css` | polish socle + nouveaux composants (T3, T5) |
| Modify | `apps/web/src/lib/markdown-sanitize-schema.ts` | +6 tags inertes (T4) |
| Modify | `apps/web/src/components/chat/__tests__/MarkdownContent.sanitize.test.tsx` | pin des 6 tags (T4) |
| Create | `apps/web/src/components/chat/__tests__/MarkdownContent.rich-components.test.tsx` | rendu des composants (T6) |
| Modify | `apps/api/src/domains/agents/prompts/v1/html_response_directive.txt` | directive réécrite (T7) |
| Create | `apps/api/tests/unit/domains/agents/prompts/test_html_directive_css_sync.py` | garde sync directive↔CSS (T7) |
| Modify | `docs/technical/RESPONSE.md` | § display modes + composants (T8) |
| Create | `docs/architecture/ADR-177-Rich-HTML-Response-Components.md` | ADR (T9) |
| Modify | `docs/architecture/ADR_INDEX.md` | entrée ADR-177 (T9) |
| Modify | `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` | descriptions du mode (T10) |
| Create | `apps/web/src/lib/html-plain-text.ts` | aplatissement HTML→texte partagé (T11) |
| Create | `apps/web/src/lib/__tests__/html-plain-text.test.ts` | tests aplatissement (T11) |
| Modify | `apps/web/src/lib/notification-preview.ts` | refactor sur le module partagé (T11) |
| Create | `apps/web/src/lib/message-clipboard.ts` | copie double-flavor (T11) |
| Create | `apps/web/src/lib/__tests__/message-clipboard.test.ts` | tests copie (T11) |
| Modify | `apps/web/src/components/chat/ChatMessage.tsx:628-632` | branchement copie (T11) |
| Modify | `apps/web/src/components/chat/ShareResponseMenu.tsx:44-75` | partage/export aplatis (T11) |
| Create | `apps/web/e2e/smoke/chat-html-mode-rendering.spec.ts` | e2e hermétique (T12) |
| Modify | `apps/web/vitest.config.ts:70-98` | relèvement des planchers si marge (T13) |

---

### Task 1 : Baseline runtime (Lot 0)

Observation uniquement — aucune écriture. Sert d'étalon avant/après.

- [ ] **Step 1 : redémarrer les conteneurs dev**

```powershell
docker restart lia-web-dev lia-api-dev
```

Attendre que http://localhost:3100 réponde (piège connu : serveur zombie sur :3100 → le
`docker restart` est le remède).

- [ ] **Step 2 : baseline visuelle**

Via le navigateur MCP (chrome-devtools ou playwright) sur http://localhost:3100 : se connecter
avec le compte dev, passer le mode d'affichage sur « HTML enrichi » (Réglages →
Personnalisation → Mode d'affichage), poser une question action (ex. « mes derniers e-mails »)
et capturer la réponse en light, dark, et viewport 390 px. Noter :
(a) le rendu du `code` inline (fond `--lia-surface` = blanc en light — contraste à confirmer) ;
(b) l'aspect des callouts/tables actuels. Conserver les captures pour comparaison en T12.

- [ ] **Step 3 : point de contrôle** — consigner les observations (2-3 lignes) dans le
  message de fin de tâche. Aucun fichier modifié.

---

### Task 2 : Fix ligatures × surlignage de recherche (Lot 1.7)

**Files:**
- Modify: `apps/web/src/lib/rehype-search-highlight.ts:57` (constante `SKIP_CLASSES`)
- Test: `apps/web/src/components/chat/__tests__/MarkdownContent.search.test.tsx`

**Interfaces:** aucune nouvelle — comportement du plugin uniquement.

- [ ] **Step 1 : écrire le test qui échoue** (ajouter au fichier search existant, en
  réutilisant son squelette de render — le fichier existe et rend `MarkdownContent` avec
  `searchHighlight`) :

```tsx
describe('search highlight — icon ligatures', () => {
  it('never injects <mark> inside a Material Symbols icon span', () => {
    const { container } = render(
      '<div class="lia-response">' +
        '<p><span class="material-symbols-outlined">event</span> Prochain event du mois</p>' +
        '</div>',
      'event'
    );
    const icon = container.querySelector('.material-symbols-outlined');
    expect(icon).not.toBeNull();
    // The ligature text must stay a single unbroken text node — a <mark> in the
    // middle would break the font ligature and show the raw word highlighted.
    expect(icon?.querySelector('mark')).toBeNull();
    expect(icon?.textContent).toBe('event');
    // Control: the same word in prose IS highlighted.
    const marks = Array.from(container.querySelectorAll('mark'));
    expect(marks.some(m => m.textContent?.toLowerCase() === 'event')).toBe(true);
  });
});
```

Adapter l'appel `render(content, searchTerm)` à la signature du helper local du fichier (il
rend `<MarkdownContent content={…} searchHighlight={…} />` — reprendre son helper existant).

- [ ] **Step 2 : vérifier l'échec**

```powershell
cd apps/web; pnpm vitest run src/components/chat/__tests__/MarkdownContent.search.test.tsx
```

Attendu : FAIL — un `<mark>` est trouvé dans la span icône.

- [ ] **Step 3 : implémentation minimale** — dans `rehype-search-highlight.ts`, étendre la
  constante :

```ts
const SKIP_CLASSES = [
  'math-inline',
  'math-display',
  'language-math',
  'katex',
  // Material Symbols icons: the text is a font LIGATURE name ("event", "mail"),
  // not prose — a <mark> inserted mid-text breaks the ligature and displays the
  // raw word. Pre-existing latent bug, made frequent by rich-HTML icons (ADR-177).
  'material-symbols-outlined',
];
```

(La logique `isSkippable` matche déjà sur égalité exacte — aucun autre changement.)

- [ ] **Step 4 : vérifier le pass** — même commande, tout le fichier search vert.
- [ ] **Step 5 : point de contrôle** — `pnpm vitest run src/components/chat src/lib` vert ;
  signaler la tâche terminée (pas de commit).

---

### Task 3 : Polish CSS du socle `.lia-response` (Lot 1.1-1.6)

**Files:**
- Modify: `apps/web/src/styles/lia-components.css:7128-7241` (section `.lia-response`)

**Interfaces:**
- Produces: les règles modifiées que T5 étend et que T6/T12 vérifient visuellement.
- La cascade est garantie : `lia-components.css` est importée hors `@layer`
  (`globals.css:6`), les styles non-layerés battent les utilities Tailwind.

- [ ] **Step 1 : appliquer les retouches du socle** — dans la section
  `LIA Response - Rich HTML display mode` :

1. Règle `p` (l. 7149-7151) — ajouter `white-space: normal;` :

```css
.lia-response p {
  margin: 0.6em 0;
  /* Pretty-printed HTML carries source newlines inside <p>; the markdown
     pipeline's `whitespace-pre-wrap` utility would render them as hard
     breaks. Inside .lia-response, whitespace is insignificant — <br> is the
     only intentional line break (the directive says so). */
  white-space: normal;
}
```

2. Règle `pre` (l. 7169-7176) — scoper au chemin legacy (le chemin `language-*` rend
   `CodeBlock`, racine `div` — `CodeBlock.tsx:81`) et passer sur tokens propres :

```css
.lia-response pre:has(> code) {
  background: var(--lia-surface);
  border: 1px solid var(--lia-border);
  color: var(--lia-text);
  padding: 1em;
  border-radius: 8px;
  overflow-x: auto;
  margin: 0.8em 0;
}
```

3. Règle `code` inline (l. 7163-7168) — contraste dans les deux thèmes :

```css
.lia-response code {
  background: var(--lia-surface-active, #f3f4f6);
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
}
```

4. Rythme vertical — ajouter après la règle `.lia-response` racine :

```css
.lia-response > :first-child {
  margin-top: 0;
}
.lia-response > :last-child {
  margin-bottom: 0;
}
```

5. Tables — zébrage + hover distinct + caption (le tag `caption` n'est autorisé qu'en T4 ;
   la règle est inerte d'ici là) :

```css
.lia-response tbody tr:nth-child(even) td {
  background: var(--lia-surface-hover, rgba(0, 0, 0, 0.02));
}
.lia-response tr:hover td {
  background: var(--lia-surface-active, rgba(0, 0, 0, 0.04));
}
.lia-response caption {
  caption-side: top;
  text-align: left;
  font-weight: 600;
  font-size: 0.85em;
  color: var(--lia-text-secondary);
  padding: 0.4em 0.2em;
}
```

(La règle `tr:hover td` REMPLACE l'existante l. 7205-7207.)

6. Callout — titre optionnel :

```css
.lia-response .lia-callout .lia-callout__title {
  font-weight: 600;
  margin: 0 0 0.3em;
}
```

- [ ] **Step 2 : non-régression** —

```powershell
cd apps/web; pnpm vitest run src/components/chat
```

Attendu : PASS (les tests jsdom n'assertent pas la CSS ; ce run garde le composant sain).

- [ ] **Step 3 : vérification visuelle rapide** — `docker restart lia-web-dev`, recharger la
  conversation de T1 : paragraphes sans césures parasites, code inline contrasté, zébrage.
- [ ] **Step 4 : point de contrôle** — signaler (pas de commit).

---

### Task 4 : Extension du schéma de sanitisation (+ tests, support ADR-177)

**Files:**
- Modify: `apps/web/src/lib/markdown-sanitize-schema.ts:66` (`tagNames`)
- Test: `apps/web/src/components/chat/__tests__/MarkdownContent.sanitize.test.tsx`

**Interfaces:**
- Produces: les tags `mark`, `caption`, `abbr`, `time`, `figure`, `figcaption` autorisés —
  consommés par T5 (CSS), T6 (tests de rendu), T7 (directive : `mark`, `caption`, `abbr`).

- [ ] **Step 1 : écrire les tests qui échouent** — ajouter au describe
  « legitimate markup survives » :

```tsx
  it.each([
    ['mark', '<p>avant <mark>décisif</mark> après</p>', 'mark'],
    ['caption', '<table><caption>Comparatif</caption><tbody><tr><td>x</td></tr></tbody></table>', 'caption'],
    ['abbr', '<p><abbr title="Application Programming Interface">API</abbr></p>', 'abbr[title]'],
    ['time', '<p><time datetime="2026-08-12">12 août</time></p>', 'time[datetime]'],
    ['figure', '<figure><figcaption>Légende</figcaption></figure>', 'figure > figcaption'],
  ])('keeps inert enrichment tag <%s> (ADR-177)', (_tag, content, selector) => {
    const { container } = render(<MarkdownContent content={content} />);
    expect(container.querySelector(selector)).not.toBeNull();
  });
```

et au describe « XSS vectors stripped » :

```tsx
  it('drops event handlers on newly allowed tags (ADR-177)', () => {
    const { container } = render(
      <MarkdownContent content={'<mark onmouseover="alert(1)">x</mark>'} />
    );
    const mark = container.querySelector('mark');
    expect(mark).not.toBeNull();
    expect(mark?.getAttribute('onmouseover')).toBeNull();
  });
```

- [ ] **Step 2 : vérifier l'échec**

```powershell
cd apps/web; pnpm vitest run src/components/chat/__tests__/MarkdownContent.sanitize.test.tsx
```

Attendu : FAIL — les 5 sélecteurs sont `null` (tags « unwrapped » par le defaultSchema).
Le test handlers peut déjà être vert une fois le tag autorisé — il pinne l'invariant.

- [ ] **Step 3 : étendre le schéma** — dans `markdown-sanitize-schema.ts` :

```ts
  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    'button',
    // ADR-177: inert enrichment tags for the rich-HTML response vocabulary.
    // None is scriptable and none carries a dangerous attribute (`title` and
    // `dateTime` are already in the defaultSchema '*' attribute list).
    'mark',
    'caption',
    'abbr',
    'time',
    'figure',
    'figcaption',
  ],
```

et compléter le docstring du module (liste « what the legitimate HTML inventory needs ») d'une
ligne : `- inert enrichment tags (ADR-177): mark, caption, abbr, time, figure, figcaption`.

- [ ] **Step 4 : vérifier le pass** — même commande, fichier entier vert (les anciens tests
  prouvent la non-régression de la frontière).
- [ ] **Step 5 : point de contrôle** — `pnpm vitest run src/components/chat` vert ; signaler.

---

### Task 5 : CSS des nouveaux composants (Lot 2 CSS)

**Files:**
- Modify: `apps/web/src/styles/lia-components.css` (fin de la section `.lia-response`)

**Interfaces:**
- Produces: les classes `.lia-callout__title` (T3), `.lia-collapsible`, `.lia-kv`,
  `.lia-columns`, `.lia-steps`, `.lia-stats`/`.lia-stat`(+`__value`/`__label`), et les styles
  `mark`/`kbd`/`abbr` — noms EXACTS consommés par la directive (T7), les tests (T6) et le
  garde de sync (T7). `.lia-chip` et ses variantes existent déjà (l. 570+), rien à ajouter.

- [ ] **Step 1 : ajouter les blocs suivants** à la fin de la section `.lia-response`
  (avant la fin de fichier), et mettre à jour le commentaire d'en-tête de section
  (l. 7117-7126) pour citer ADR-177 :

```css
/* --- Rich-response component vocabulary (ADR-177) ------------------------- */

/* Inline semantics */
.lia-response mark:not([class]) {
  /* :not([class]) keeps the search-highlight <mark> (fixed-class, own style)
     out of this rule. */
  background: color-mix(in srgb, var(--lia-warning) 25%, transparent);
  color: inherit;
  padding: 0.05em 0.25em;
  border-radius: 3px;
}
.lia-response kbd {
  font-family: var(--lia-font-mono);
  font-size: 0.85em;
  padding: 0.1em 0.4em;
  border: 1px solid var(--lia-border);
  border-bottom-width: 2px;
  border-radius: 4px;
  background: var(--lia-surface);
}
.lia-response abbr[title] {
  text-decoration: underline dotted;
  cursor: help;
}
.lia-response .material-symbols-outlined {
  font-size: 1.1em;
  vertical-align: -0.15em;
}

/* Collapsible (details/summary) */
.lia-response .lia-collapsible {
  border: 1px solid var(--lia-border);
  border-radius: var(--lia-radius-md);
  margin: 0.8em 0;
  background: var(--lia-surface);
  overflow: hidden;
}
.lia-response .lia-collapsible summary {
  cursor: pointer;
  padding: 0.6em 1em;
  font-weight: 500;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5em;
}
.lia-response .lia-collapsible summary::-webkit-details-marker {
  display: none;
}
.lia-response .lia-collapsible summary::before {
  content: '';
  width: 0.45em;
  height: 0.45em;
  border-right: 2px solid var(--lia-text-secondary);
  border-bottom: 2px solid var(--lia-text-secondary);
  transform: rotate(-45deg);
  transition: transform var(--lia-transition-fast);
  flex: none;
}
.lia-response .lia-collapsible[open] > summary::before {
  transform: rotate(45deg);
}
.lia-response .lia-collapsible summary:focus-visible {
  outline: 2px solid var(--lia-border-focus);
  outline-offset: -2px;
}
.lia-response .lia-collapsible > :not(summary) {
  margin: 0.6em 1em;
}

/* Key-value list */
.lia-response .lia-kv {
  display: grid;
  grid-template-columns: minmax(6em, max-content) 1fr;
  gap: 0.35em 1.25em;
  margin: 0.8em 0;
}
.lia-response .lia-kv dt {
  color: var(--lia-text-secondary);
  font-size: 0.9em;
  overflow-wrap: anywhere;
}
.lia-response .lia-kv dd {
  margin: 0;
  min-width: 0;
}
@media (max-width: 479px) {
  .lia-response .lia-kv {
    grid-template-columns: 1fr;
    gap: 0.1em;
  }
  .lia-response .lia-kv dd {
    margin-bottom: 0.5em;
  }
}

/* Responsive columns (stacks below min(240px, 100%)) */
.lia-response .lia-columns {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr));
  gap: var(--lia-space-lg);
  margin: 0.8em 0;
  align-items: start;
}
.lia-response .lia-columns > div {
  min-width: 0;
}

/* Numbered steps */
.lia-response ol.lia-steps {
  list-style: none;
  counter-reset: lia-step;
  padding-left: 0;
  margin: 0.8em 0;
}
.lia-response .lia-steps li {
  counter-increment: lia-step;
  position: relative;
  padding-left: 2.4em;
  margin: 0.7em 0;
}
.lia-response .lia-steps li::before {
  content: counter(lia-step);
  position: absolute;
  left: 0;
  top: 0.05em;
  width: 1.6em;
  height: 1.6em;
  border-radius: 50%;
  background: var(--lia-primary-subtle);
  color: var(--lia-primary);
  font-weight: 600;
  font-size: 0.85em;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Stat tiles */
.lia-response .lia-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(120px, 100%), 1fr));
  gap: var(--lia-space-sm);
  margin: 0.8em 0;
}
.lia-response .lia-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.15em;
  padding: 0.8em 0.6em;
  border: 1px solid var(--lia-border);
  border-radius: var(--lia-radius-md);
  background: var(--lia-surface);
  text-align: center;
}
.lia-response .lia-stat__value {
  font-size: 1.35em;
  font-weight: 700;
  color: var(--lia-primary);
  line-height: 1.1;
}
.lia-response .lia-stat__label {
  font-size: 0.8em;
  color: var(--lia-text-secondary);
}
```

Tout est piloté par tokens (`--lia-*`) redéfinis dans `.dark` (l. 133-169) ou par
`color-mix` sur token — **aucun override `.dark` supplémentaire n'est nécessaire** ; le
vérifier visuellement en T12.

- [ ] **Step 2 : non-régression + format**

```powershell
cd apps/web; pnpm vitest run src/components/chat; pnpm prettier --check src/styles/lia-components.css
```

(si prettier signale le fichier, `pnpm prettier --write src/styles/lia-components.css`).

- [ ] **Step 3 : point de contrôle** — signaler.

---

### Task 6 : Tests de rendu des composants riches

**Files:**
- Create: `apps/web/src/components/chat/__tests__/MarkdownContent.rich-components.test.tsx`

**Interfaces:**
- Consumes: les tags T4 et les classes T3/T5 ; le composant `CodeBlock` est mocké.

- [ ] **Step 1 : écrire le fichier de test complet** :

```tsx
/**
 * MarkdownContent — rich-HTML component vocabulary (ADR-177).
 *
 * Pins that every component the HTML response directive advertises renders as
 * real DOM with its classes intact (classes drive all styling), that the
 * language-* code path reaches CodeBlock, and that a truncated stream never
 * leaks raw tag source as visible text.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { markImageLoaded, isImageLoaded } = vi.hoisted(() => ({
  markImageLoaded: vi.fn(),
  isImageLoaded: vi.fn(() => false),
}));
vi.mock('@/lib/image-cache', () => ({ markImageLoaded, isImageLoaded }));
// Alias specifier on purpose: MarkdownContent lazy-imports
// '@/components/chat/CodeBlock' — mocking the same specifier guarantees the
// resolution matches (pattern of the sibling tests mocking '@/lib/image-cache').
vi.mock('@/components/chat/CodeBlock', () => ({
  CodeBlock: ({ language, children }: { language: string; children: string }) => (
    <div data-testid="codeblock" data-language={language}>
      {children}
    </div>
  ),
}));

import { MarkdownContent } from '../MarkdownContent';

const render = (content: string) => renderWithProviders(<MarkdownContent content={content} />);

beforeEach(() => {
  vi.clearAllMocks();
  isImageLoaded.mockReturnValue(false);
});

const RICH_FIXTURE = [
  '<div class="lia-response">',
  '<h2>Synthèse</h2>',
  '<div class="lia-callout lia-callout-success">',
  '<p class="lia-callout__title">Tout est prêt</p>',
  '<p>Corps du callout.</p>',
  '</div>',
  '<p>Statut : <span class="lia-chip lia-chip--green">' +
    '<span class="material-symbols-outlined">check_circle</span>Confirmé</span></p>',
  '<dl class="lia-kv"><dt>Date</dt><dd><strong>12 août</strong></dd>' +
    '<dt>Lieu</dt><dd>Paris</dd></dl>',
  '<div class="lia-columns"><div><h3>Option A</h3><p>a</p></div>' +
    '<div><h3>Option B</h3><p>b</p></div></div>',
  '<ol class="lia-steps"><li>Préparer</li><li>Envoyer</li></ol>',
  '<div class="lia-stats"><div class="lia-stat">' +
    '<span class="lia-stat__value">12</span>' +
    '<span class="lia-stat__label">rendez-vous</span></div></div>',
  '<details class="lia-collapsible" open><summary>Détails</summary><p>corps</p></details>',
  '<p>Raccourci <kbd>Ctrl</kbd>+<kbd>K</kbd>, point <mark>décisif</mark>, ' +
    '<abbr title="Application Programming Interface">API</abbr>.</p>',
  '<pre><code class="language-python">print("x")</code></pre>',
  '</div>',
].join('\n');

describe('MarkdownContent — rich component vocabulary', () => {
  it('renders every advertised component with its classes intact', () => {
    const { container } = render(RICH_FIXTURE);

    expect(screen.getByRole('heading', { name: 'Synthèse', level: 2 })).toBeTruthy();
    expect(
      container.querySelector('.lia-callout.lia-callout-success .lia-callout__title')
        ?.textContent
    ).toBe('Tout est prêt');
    expect(container.querySelector('.lia-chip.lia-chip--green')).not.toBeNull();
    expect(
      container.querySelector('.lia-chip .material-symbols-outlined')?.textContent
    ).toBe('check_circle');

    const kv = container.querySelector('dl.lia-kv');
    expect(kv?.querySelectorAll('dt')).toHaveLength(2);
    expect(kv?.querySelectorAll('dd')).toHaveLength(2);

    expect(container.querySelectorAll('.lia-columns > div')).toHaveLength(2);
    expect(container.querySelectorAll('ol.lia-steps > li')).toHaveLength(2);
    expect(container.querySelector('.lia-stat .lia-stat__value')?.textContent).toBe('12');
    expect(container.querySelector('.lia-stat .lia-stat__label')?.textContent).toBe(
      'rendez-vous'
    );

    const details = container.querySelector('details.lia-collapsible');
    expect(details?.hasAttribute('open')).toBe(true);
    expect(details?.querySelector('summary')?.textContent).toBe('Détails');

    expect(container.querySelectorAll('kbd')).toHaveLength(2);
    expect(container.querySelector('mark')?.textContent).toBe('décisif');
    expect(container.querySelector('abbr')?.getAttribute('title')).toContain('Programming');
  });

  it('routes language-classed code blocks to CodeBlock', async () => {
    render(RICH_FIXTURE);
    const block = await screen.findByTestId('codeblock');
    expect(block.getAttribute('data-language')).toBe('python');
    expect(block.textContent).toContain('print("x")');
  });

  it('never leaks raw tag source when the stream is cut mid-tag', () => {
    // Simulates an SSE snapshot ending in the middle of an opening tag: the
    // HTML tokenizer must drop the incomplete tag, not print it as text.
    const truncated = RICH_FIXTURE.slice(
      0,
      RICH_FIXTURE.indexOf('lia-callout-success') + 8
    );
    const { container } = render(truncated);
    expect(container.textContent).not.toMatch(/<(?:div|p|h2|span)/);
  });

  it('leaves markdown-mode content untouched (control)', () => {
    const { container } = render('**gras** et une liste :\n\n- item');
    expect(container.querySelector('.lia-response')).toBeNull();
    expect(screen.getByText('gras').tagName).toBe('STRONG');
  });
});
```

- [ ] **Step 2 : lancer et déboguer**

```powershell
cd apps/web; pnpm vitest run src/components/chat/__tests__/MarkdownContent.rich-components.test.tsx
```

Attendu : PASS (T4/T5 déjà en place). Si le test tronqué échoue en montrant du texte brut,
c'est un vrai défaut du pipeline à investiguer (systematic-debugging) — ne pas affaiblir
l'oracle.

- [ ] **Step 3 : suite chat complète**

```powershell
cd apps/web; pnpm vitest run src/components/chat
```

- [ ] **Step 4 : point de contrôle** — signaler.

---

### Task 7 : Réécriture de la directive + garde de synchronisation

**Files:**
- Modify: `apps/api/src/domains/agents/prompts/v1/html_response_directive.txt` (remplacement complet)
- Create: `apps/api/tests/unit/domains/agents/prompts/test_html_directive_css_sync.py`

**Interfaces:**
- Consumes: les classes CSS T3/T5 (noms exacts) ; les tags T4.
- Produces: la directive que `response_node.py:2177` charge telle quelle (aucun changement
  de code backend — vérifié : aucun test ne pinne le contenu actuel).

- [ ] **Step 1 : écrire le test-garde (échec attendu : le fichier de la nouvelle directive
  n'existe pas encore sous sa forme enrichie — le test des classes passe déjà sur l'ancienne,
  celui des invariants échoue sur `lia-callout-success`)** :

```python
"""Sync guard: the HTML response directive and the frontend stylesheet.

Every ``lia-*`` class the directive advertises must exist in
``apps/web/src/styles/lia-components.css`` — a class advertised but unstyled
renders as plain markup and the feature dies invisibly (ADR-177). Runs as a
plain unit test (repo checkout is complete in the backend CI job).
"""

import re
from pathlib import Path


def _repo_root() -> Path:
    """Walk up from this file to the repository root (Taskfile.yml marker)."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "Taskfile.yml").exists():
            return parent
    raise AssertionError("repository root (Taskfile.yml) not found")


_ROOT = _repo_root()
_DIRECTIVE = _ROOT / "apps/api/src/domains/agents/prompts/v1/html_response_directive.txt"
_CSS = _ROOT / "apps/web/src/styles/lia-components.css"


def _advertised_classes() -> set[str]:
    directive = _DIRECTIVE.read_text(encoding="utf-8")
    grouped = re.findall(r'class="([^"]+)"', directive)
    return {cls for group in grouped for cls in group.split()}


def test_advertised_lia_classes_exist_in_stylesheet() -> None:
    css = _CSS.read_text(encoding="utf-8")
    lia_classes = {c for c in _advertised_classes() if c.startswith("lia-")}
    assert lia_classes, "directive advertises no lia-* class — directive rewritten?"
    missing = sorted(c for c in lia_classes if f".{c}" not in css)
    assert not missing, f"advertised but unstyled classes: {missing}"


def test_icon_class_exists_in_stylesheet() -> None:
    css = _CSS.read_text(encoding="utf-8")
    if "material-symbols-outlined" in _DIRECTIVE.read_text(encoding="utf-8"):
        assert ".material-symbols-outlined" in css or "material-symbols-outlined" in css


def test_directive_invariants() -> None:
    directive = _DIRECTIVE.read_text(encoding="utf-8")
    assert 'lia-response' in directive
    assert "NEVER emit a <style> block" in directive, "no-inline-style rule dropped"
    assert "lia-callout-success" in directive, "success callout still undocumented"
    assert len(directive.splitlines()) <= 96, "directive over token budget (2x original)"
```

- [ ] **Step 2 : vérifier l'échec ciblé**

```powershell
cd apps/api; .venv/Scripts/pytest tests/unit/domains/agents/prompts/test_html_directive_css_sync.py -v
```

Attendu : `test_directive_invariants` FAIL (« success callout still undocumented » — et le
libellé exact `NEVER emit a <style> block` n'existe pas encore) ; les deux autres PASS.

- [ ] **Step 3 : remplacer intégralement `html_response_directive.txt` par** :

```text
### CRITICAL: HTML OUTPUT FORMAT ###

**OVERRIDE ALL PREVIOUS FORMATTING INSTRUCTIONS.**

You MUST format your ENTIRE response as rich, aesthetic HTML wrapped in `<div class="lia-response">`.
Do NOT use markdown syntax anywhere. Output ONLY pure, well-structured HTML.

Every response MUST use this exact structure:

<div class="lia-response">
<!-- Your HTML content here -->
</div>

Form rules (all styling comes from the application stylesheet — keep in sync
with apps/web/src/styles/lia-components.css):
- NEVER emit a <style> block or style="..." attributes: they are discarded.
- NEVER output raw markdown syntax (no **, no -, no #, no ``` fences).
- Start every block-level tag at column 0 (no leading indentation).
- Use <br> for an intentional line break inside a paragraph; source newlines
  inside <p> are insignificant.

CORE ELEMENTS:
- <p> for text paragraphs — use generously for airy layout
- <strong> for key facts (names, dates, places, amounts); <em> for nuance
- <h2> for major sections, <h3> for subsections
- <ul><li> / <ol><li> for lists — an emoji prefix inside the <li> is welcome
- <blockquote><p> for quotes or personal observations
- <table> with <thead>/<tbody> (plus an optional <caption>) for comparative data
- <pre><code class="language-python"> for code blocks — ALWAYS set a language-*
  class (language-text when unsure): it enables syntax highlighting and a copy
  button. Plain <code> for inline code.
- <hr> between major sections; <a href="..."> for links
- Inline accents: <mark> for one decisive word, <kbd> for keyboard keys,
  <abbr title="..."> for abbreviations, <sub>/<sup> where meaning needs them

RICH COMPONENTS (use these exact class names):

1. Callout — tip, confirmation, warning or error:
<div class="lia-callout lia-callout-info">
<p class="lia-callout__title">Optional title</p>
<p>Body text.</p>
</div>
Variants: lia-callout-info | lia-callout-success | lia-callout-warning | lia-callout-error

2. Chip — inline status/metadata badge, icon optional:
<span class="lia-chip lia-chip--green"><span class="material-symbols-outlined">check_circle</span>Confirmed</span>
Variants: no modifier (neutral) | lia-chip--green | lia-chip--amber | lia-chip--red | lia-chip--indigo
Icon: any valid Material Symbols ligature name (event, mail, schedule, warning, check_circle, ...)

3. Collapsible — secondary detail that would clutter the reply:
<details class="lia-collapsible">
<summary>See details</summary>
<p>Collapsed content.</p>
</details>

4. Key-value list — structured facts about one item:
<dl class="lia-kv">
<dt>Date</dt><dd><strong>August 12, 2026</strong></dd>
<dt>Location</dt><dd>Paris</dd>
</dl>

5. Columns — side-by-side comparison (2-3 blocks, stacks on small screens):
<div class="lia-columns">
<div><h3>Option A</h3><p>...</p></div>
<div><h3>Option B</h3><p>...</p></div>
</div>

6. Steps — a procedure with styled number bullets:
<ol class="lia-steps"><li>First step</li><li>Second step</li></ol>

7. Stat tiles — 2 to 4 key figures at a glance:
<div class="lia-stats">
<div class="lia-stat"><span class="lia-stat__value">12</span><span class="lia-stat__label">meetings</span></div>
</div>

Math formulas (ONLY when you actually express a mathematical or scientific
formula): LaTeX between $...$ inline within a sentence, $$...$$ for a
standalone display equation. Never use math delimiters for plain currency
amounts (write "9$" or "9 USD" as normal text).

RESTRAINT — this is a conversation, not a dashboard:
- At most 2-3 rich components per response, and only where they genuinely help.
- Short answers get light formatting (a few <p> with <strong>), no components.
- Prose leads, components support: never wrap an entire response in one
  table or component.
- Match the component to the content: comparative data -> table or columns;
  facts about one item -> key-value list; procedure -> steps; caveat or
  confirmation -> callout; long secondary detail -> collapsible; headline
  numbers -> stat tiles.
```

- [ ] **Step 4 : vérifier le pass du garde** — même commande qu'au Step 2 : 4 tests PASS.
- [ ] **Step 5 : gates backend rapides**

```powershell
task test:backend:unit:fast
```

Attendu : PASS (le nouveau fichier test est découvert ; `task test:markers` tournera en T13
via `ci:fast` pour la règle F006).

- [ ] **Step 6 : mettre à jour le commentaire de sync CSS** — dans `lia-components.css`
  (l. 7117-7126), le commentaire d'en-tête cite déjà la directive ; y ajouter :
  `Guarded by apps/api/tests/unit/domains/agents/prompts/test_html_directive_css_sync.py.`
- [ ] **Step 7 : point de contrôle** — signaler.

---

### Task 8 : Documentation technique (RESPONSE.md)

**Files:**
- Modify: `docs/technical/RESPONSE.md` (tableau « Concepts Clés » + section Display Modes)

- [ ] **Step 1 : mettre à jour** :

1. Dans le tableau « Concepts Clés », remplacer la ligne « Mode HTML sans `<style>` » par une
   version mentionnant le vocabulaire de composants :

```markdown
| **Mode HTML sans `<style>` + composants (ADR-177)** | En mode HTML enrichi, le LLM n'émet ni bloc `<style>` ni style inline : les règles `.lia-response` vivent dans `lia-components.css`. Depuis ADR-177 la directive expose un vocabulaire de composants (callouts ×4 avec titre, chips, `details` dépliables, listes clé-valeur `dl.lia-kv`, colonnes `lia-columns`, étapes `lia-steps`, tuiles `lia-stats`, code `language-*` → coloration Prism + bouton copier, `mark`/`kbd`/`abbr`) avec une règle de sobriété (2-3 composants max). Sync directive↔CSS verrouillée par `test_html_directive_css_sync.py`. |
```

2. Dans la section détaillant les display modes (chercher « Display Modes » dans le corps),
   ajouter un paragraphe listant les composants et le renvoi vers l'ADR-177 et la spec.

- [ ] **Step 2 : vérifier les liens**

```powershell
task lint:docs
```

- [ ] **Step 3 : point de contrôle** — signaler.

---

### Task 9 : ADR-177 + index

**Files:**
- Create: `docs/architecture/ADR-177-Rich-HTML-Response-Components.md`
- Modify: `docs/architecture/ADR_INDEX.md` (entrée après ADR-176, même format que l'existant)

- [ ] **Step 1 : créer l'ADR** (format ADR-176 : titre, Statut, Date, Décideurs, Contexte,
  Décision, Conséquences, Alternatives) :

```markdown
# ADR-177 : Mode HTML enrichi — vocabulaire de composants et extension du schéma de sanitisation

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Date**: 2026-07-29
**Décideurs**: Équipe LIA (spec 2026-07-29-html-enrichi-composants-design)

## Contexte

Le mode d'affichage `html` fait produire au LLM une réponse `<div class="lia-response">`
via `html_response_directive.txt`, rendue par le pipeline pinné
`[rehypeRaw, [rehypeSanitize, schema], rehypeMathInText, rehypeKatex]`. La directive
n'exploitait qu'une fraction des capacités déjà en place : callouts success/error stylés
mais non documentés, `details`/`dl`/`kbd` autorisés par le schéma mais jamais proposés,
aucune classe `language-*` donc jamais de coloration syntaxique. La frontière XSS
(`markdown-sanitize-schema.ts`) est auditée et pinnée par tests ; l'étendre — même par des
tags inertes — est une décision à tracer.

## Décision

1. **Vocabulaire de composants** documenté dans la directive et stylé dans
   `lia-components.css`, scopé `.lia-response` : callouts ×4 (+ `.lia-callout__title`),
   chips (réutilisation de `.lia-chip` existante), `details.lia-collapsible`, `dl.lia-kv`,
   `div.lia-columns`, `ol.lia-steps`, `div.lia-stats`, code `language-*` (→ `CodeBlock` :
   Prism + copie), icônes Material Symbols, `mark`/`kbd`/`abbr`. Règle de sobriété dans la
   directive (2-3 composants max par réponse).
2. **Schéma de sanitisation étendu de 6 tags inertes** : `mark`, `caption`, `abbr`, `time`,
   `figure`, `figcaption`. Aucun n'est scriptable ; aucun attribut nouveau (title/dateTime
   déjà dans la liste globale du defaultSchema). `script`/`iframe`/`form`/handlers restent
   interdits ; l'ordre des plugins est inchangé. Pinné dans les deux sens par
   `MarkdownContent.sanitize.test.tsx`.
3. **Garde de synchronisation** : `test_html_directive_css_sync.py` (backend, unit) échoue
   si la directive cite une classe `lia-*` absente de la CSS — une classe non stylée est
   une feature qui meurt invisiblement.
4. **Aplatissement client partagé** : `html-plain-text.ts` (multi-ligne) alimente la copie
   double-flavor (`text/html` + `text/plain`), le partage natif et l'export `.md` ;
   `notification-preview.ts` se refonde dessus sans changement de comportement.
5. Le gate d'injection (`display_mode == "html" and route_to == "planner"`) et le pipeline
   de rendu sont **inchangés**.

## Conséquences

- (+) Réponses sensiblement plus travaillées sans nouveau chemin de code : purement
  déclaratif (prompt + CSS + allowlist).
- (+) Dégradation propre : un composant mal formé rend comme du HTML simple ; un tag
  inconnu est « unwrapped » ; TTS/notifications aplatissent génériquement (détection par le
  wrapper porteur d'attribut, strip `<[^>]+>`).
- (−) La directive coûte ~2× plus de tokens sur les tours action en mode html (≤96 lignes,
  gardé par test).
- (−) `:has()` requis pour le scoping du `pre` legacy (baseline navigateurs 2023 ;
  dégradation = double boîte, état antérieur).

## Alternatives considérées

- **Composants React interceptés** (tabs, accordéons animés — pattern ContactPhotoGallery) :
  gain maximal mais complexité streaming/a11y/sanitize élevée — différé (piste future).
- **Ne pas étendre le schéma** : `mark`/`caption`/`abbr` dégradaient en texte nu — coût
  de l'extension quasi nul, bénéfice sémantique et visuel réel.
```

- [ ] **Step 2 : indexer** — dans `ADR_INDEX.md`, ajouter à la suite d'ADR-176 une entrée au
  même format (titre + statut + fichier + résumé d'une ligne). Mettre à jour la ligne du
  CLAUDE.md racine (« ADR index (176 architectural decisions, ADR-176 latest) ») → 177.
- [ ] **Step 3 : vérifier**

```powershell
task lint:docs
```

- [ ] **Step 4 : point de contrôle** — signaler.

---

### Task 10 : i18n — descriptions du mode enrichies (6 locales)

**Files:**
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — bloc `display_mode`
  (fr : l. 1204-1225), clés `info` et `modes.html.description` UNIQUEMENT (les `label` et
  `selected` ne changent pas ; aucune clé ajoutée/supprimée → parité intacte).

- [ ] **Step 1 : lire le bloc `display_mode` des 6 locales** pour réutiliser le libellé
  exact du mode (« HTML enrichi » / « Rich HTML » / etc.) de chaque langue dans les
  nouvelles phrases.
- [ ] **Step 2 : remplacer les deux valeurs** (adapter le nom du mode à chaque `label`) :

| Locale | `modes.html.description` |
|--------|--------------------------|
| fr | `Réponses mises en page : titres, encadrés, badges, sections dépliables, tableaux, colonnes, chiffres clés et code coloré` |
| en | `Laid-out answers: headings, callouts, badges, collapsible sections, tables, columns, key figures and highlighted code` |
| de | `Gestaltete Antworten: Überschriften, Hinweisboxen, Badges, ausklappbare Bereiche, Tabellen, Spalten, Kennzahlen und hervorgehobener Code` |
| es | `Respuestas compuestas: títulos, avisos, insignias, secciones desplegables, tablas, columnas, cifras clave y código resaltado` |
| it | `Risposte impaginate: titoli, riquadri, badge, sezioni espandibili, tabelle, colonne, cifre chiave e codice evidenziato` |
| zh | `排版精美的回复：标题、提示框、徽章、可折叠部分、表格、分栏、关键数字和代码高亮` |

et `info` (phrase du milieu uniquement — conserver les phrases Cartes/Markdown de la locale) :

| Locale | Phrase « HTML enrichi » dans `info` |
|--------|-------------------------------------|
| fr | `Le mode HTML enrichi met en page les réponses avec des composants riches (encadrés, badges, sections dépliables, tableaux, colonnes, chiffres clés, code coloré).` |
| en | `Rich HTML mode lays out answers with rich components (callouts, badges, collapsible sections, tables, columns, key figures, highlighted code).` |
| de | `Der Modus Angereichertes HTML gestaltet Antworten mit reichhaltigen Komponenten (Hinweisboxen, Badges, ausklappbaren Bereichen, Tabellen, Spalten, Kennzahlen, hervorgehobenem Code).` |
| es | `El modo HTML enriquecido compone las respuestas con componentes ricos (avisos, insignias, secciones desplegables, tablas, columnas, cifras clave, código resaltado).` |
| it | `La modalità HTML arricchito impagina le risposte con componenti ricchi (riquadri, badge, sezioni espandibili, tabelle, colonne, cifre chiave, codice evidenziato).` |
| zh | `富 HTML 模式使用丰富组件排版回复（提示框、徽章、可折叠部分、表格、分栏、关键数字、代码高亮）。` |

(Si le `label` d'une locale diffère des noms ci-dessus — ex. de/es/it/zh — reprendre le
`label` verbatim dans la phrase.)

- [ ] **Step 3 : parité + gates**

```powershell
task lint:i18n
```

Attendu : PASS (aucune clé modifiée, seulement des valeurs).

- [ ] **Step 4 : point de contrôle** — signaler.

---

### Task 11 : Aplatissement partagé + copie double-flavor + partage/export

**Files:**
- Create: `apps/web/src/lib/html-plain-text.ts`
- Create: `apps/web/src/lib/__tests__/html-plain-text.test.ts`
- Modify: `apps/web/src/lib/notification-preview.ts` (refactor sur le module partagé —
  comportement STRICTEMENT identique, ses tests existants sont l'oracle et ne changent pas)
- Create: `apps/web/src/lib/message-clipboard.ts`
- Create: `apps/web/src/lib/__tests__/message-clipboard.test.ts`
- Modify: `apps/web/src/components/chat/ChatMessage.tsx:628-632` (handleCopyMessage)
- Modify: `apps/web/src/components/chat/ShareResponseMenu.tsx:44-75` (share + download)

**Interfaces:**
- Produces:
  - `looksLikeHtml(text: string): boolean` (déplacé de notification-preview, ré-exporté)
  - `htmlToPlainText(text: string): string` — multi-ligne, no-op sur markdown/prose
  - `messageToPlainText(content: string): string` — alias sémantique de htmlToPlainText
  - `copyMessageToClipboard(content: string): Promise<void>`

- [ ] **Step 1 : écrire `html-plain-text.test.ts` (échec attendu : module absent)** :

```ts
import { describe, it, expect } from 'vitest';

import { htmlToPlainText, looksLikeHtml } from '../html-plain-text';

const RICH = [
  '<div class="lia-response">',
  '<h2>Synthèse</h2>',
  '<p>Deux points <strong>clés</strong>.</p>',
  '<ul><li>Premier</li><li>Second</li></ul>',
  '<dl class="lia-kv"><dt>Date</dt><dd>12 août</dd></dl>',
  '<p>Icône <span class="material-symbols-outlined">event</span> masquée.</p>',
  '</div>',
].join('\n');

describe('looksLikeHtml', () => {
  it('detects the lia-response wrapper (attribute signal)', () => {
    expect(looksLikeHtml('<div class="lia-response"><p>x</p></div>')).toBe(true);
  });
  it('never flags prose with comparison operators', () => {
    expect(looksLikeHtml('if x<a and b>c then count<b et total>i')).toBe(false);
  });
});

describe('htmlToPlainText', () => {
  it('is a strict no-op on markdown/prose', () => {
    const md = '**gras**\n\n- item\n\nif x<a and b>c';
    expect(htmlToPlainText(md)).toBe(md);
  });

  it('flattens rich HTML to readable multi-line text', () => {
    const out = htmlToPlainText(RICH);
    expect(out).toContain('Synthèse');
    expect(out).toContain('Deux points clés.');
    // List items become bullet lines (mirror of backend html_to_text: "• ").
    expect(out).toMatch(/^• Premier$/m);
    expect(out).toMatch(/^• Second$/m);
    // dt/dd pairs read as "key : value".
    expect(out).toMatch(/Date\s*:\s*12 août/);
    // Icon ligature names are dropped whole.
    expect(out).not.toContain('event');
    // No tag survives; no run of 3+ newlines.
    expect(out).not.toMatch(/<[a-z]/i);
    expect(out).not.toMatch(/\n{3,}/);
  });

  it('decodes the fixed entity set', () => {
    expect(htmlToPlainText('<p>A&nbsp;&amp;&nbsp;B</p>')).toBe('A & B');
  });
});
```

- [ ] **Step 2 : vérifier l'échec**

```powershell
cd apps/web; pnpm vitest run src/lib/__tests__/html-plain-text.test.ts
```

Attendu : FAIL (« Cannot find module '../html-plain-text' »).

- [ ] **Step 3 : créer `html-plain-text.ts`** — déplacer depuis `notification-preview.ts`
  les constantes `TAGS`, `OPEN_TAG_RE`, `CLOSE_TAG_RE`, `VOID_TAG_RE`, `ATTR_TAG_RE`,
  `BLOCK_RE`, `ICON_SPAN_RE`, `ENTITIES` et la fonction `looksLikeHtml` (docstrings
  conservés — ils documentent les pièges mesurés), puis ajouter :

```ts
/**
 * Flatten rich assistant HTML to readable MULTI-LINE plain text.
 *
 * Client-side mirror of the backend's `html_to_text`
 * (`display/components/base.py:609-739`, `preserve_links=False` semantics):
 * same bullets ("• "), same block spacing (headers/paragraphs separated by one
 * empty line, <hr> → "---"), same inline-tag handling (stripped to '', no
 * injected space), same whitespace normalization (≤1 empty line, per-line
 * trim). Extended for the ADR-177 vocabulary the email-oriented backend set
 * lacks: dl/dt/dd ("key : value"), details/summary, caption/figcaption.
 * One deliberate divergence: entities are decoded AFTER tag stripping (the
 * legacy frontend order) so a message QUOTING markup as &lt;div&gt; keeps its
 * literal text instead of being eaten by the strip.
 *
 * Feeds the clipboard text/plain flavor, the native share sheet and the .md
 * export; `toPlainPreview` (notification-preview.ts) builds on it and
 * additionally collapses to a single line for toasts.
 *
 * A strict no-op on Markdown and plain prose (guarded by `looksLikeHtml`).
 */
export function htmlToPlainText(text: string): string {
  if (!text || !looksLikeHtml(text)) return text;
  let out = text.replace(BLOCK_RE, ' ').replace(ICON_SPAN_RE, ' ');
  // Links: keep the text only (backend preserve_links=False).
  out = out.replace(/<a\s+[^>]*>([\s\S]*?)<\/a>/gi, '$1');
  // Block structure BEFORE the generic strip — mirrors base.py steps 4-7.
  out = out.replace(/<h[1-6][^>]*>([\s\S]*?)<\/h[1-6]>/gi, '\n\n$1\n\n');
  out = out.replace(/<\/p>/gi, '\n\n');
  out = out.replace(/<\/div>/gi, '\n');
  out = out.replace(/<br\s*\/?>/gi, '\n');
  out = out.replace(/<hr\s*\/?>/gi, '\n---\n');
  out = out.replace(/<li[^>]*>/gi, '\n• ');
  out = out.replace(/<\/?[ou]l[^>]*>/gi, '\n');
  out = out.replace(/<tr[^>]*>/gi, '\n');
  out = out.replace(/<t[dh][^>]*>/gi, ' ');
  out = out.replace(/<\/t[dh]>/gi, ' | ');
  out = out.replace(/<\/?table[^>]*>/gi, '\n');
  out = out.replace(/<blockquote[^>]*>/gi, '\n> ');
  out = out.replace(/<\/blockquote>/gi, '\n');
  // ADR-177 vocabulary (absent from the backend's email-oriented set):
  out = out.replace(/<\/dt>/gi, ' : ');
  out = out.replace(/<\/(?:dd|dl|summary|details|figcaption|caption)>/gi, '\n');
  // Generic strip — remaining tags (incl. inline strong/em/span) drop to ''.
  out = out.replace(/<[^>]+>/g, '');
  for (const [entity, char] of Object.entries(ENTITIES)) {
    out = out.split(entity).join(char);
  }
  // Whitespace normalization — mirrors base.py step 10.
  out = out.replace(/[ \t]+/g, ' ');
  out = out.replace(/\n{3,}/g, '\n\n');
  const lines = out.split('\n').map(line => line.trim());
  const cleaned: string[] = [];
  let previousEmpty = false;
  for (const line of lines) {
    if (line) {
      cleaned.push(line);
      previousEmpty = false;
    } else if (!previousEmpty) {
      cleaned.push(line);
      previousEmpty = true;
    }
  }
  return cleaned.join('\n').trim();
}
```

- [ ] **Step 4 : refondre `notification-preview.ts`** — supprimer les constantes déplacées,
  importer depuis `./html-plain-text`, et réécrire `toPlainPreview` :

```ts
import { htmlToPlainText, looksLikeHtml } from './html-plain-text';

export function toPlainPreview(text: string, maxLength?: number): string {
  if (!text) return '';
  const flat = looksLikeHtml(text) ? htmlToPlainText(text) : text;
  const out = flat.replace(/\s+/g, ' ').trim();
  if (maxLength === undefined || out.length <= maxLength) return out;
  return `${out.slice(0, maxLength)}...`;
}
```

- [ ] **Step 5 : oracle de non-régression**

```powershell
cd apps/web; pnpm vitest run src/lib/__tests__
```

Attendu : `html-plain-text.test.ts` PASS **et** les tests EXISTANTS de
`notification-preview` PASS **sans aucune modification** — s'ils échouent, ajuster
`htmlToPlainText`, jamais les tests. (Écart connu accepté : `- ` devant les items dans le
préviews single-line — si un test existant pinne l'absence de puce, préserver le
comportement en faisant passer `toPlainPreview` par un chemin sans insertion de puces :
extraire l'insertion `\n• ` derrière un paramètre `{ bullets: boolean }` par défaut `true`,
`toPlainPreview` appelant avec `false`.)

- [ ] **Step 6 : écrire `message-clipboard.test.ts` (échec attendu)** :

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { copyMessageToClipboard, messageToPlainText } from '../message-clipboard';

const HTML = '<div class="lia-response"><h2>Titre</h2><p>Corps</p></div>';

describe('messageToPlainText', () => {
  it('flattens HTML and passes markdown through', () => {
    // Blocks separated by ONE empty line — backend html_to_text semantics.
    expect(messageToPlainText(HTML)).toBe('Titre\n\nCorps');
    expect(messageToPlainText('**md**')).toBe('**md**');
  });
});

describe('copyMessageToClipboard', () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  const write = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.stubGlobal('navigator', { clipboard: { writeText, write } });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('copies markdown content verbatim via writeText', async () => {
    await copyMessageToClipboard('**md**');
    expect(writeText).toHaveBeenCalledWith('**md**');
    expect(write).not.toHaveBeenCalled();
  });

  it('copies HTML content as dual-flavor ClipboardItem', async () => {
    class FakeClipboardItem {
      constructor(public readonly items: Record<string, Blob>) {}
    }
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    await copyMessageToClipboard(HTML);
    expect(write).toHaveBeenCalledTimes(1);
    const item = write.mock.calls[0][0][0] as InstanceType<typeof FakeClipboardItem>;
    expect(Object.keys(item.items).sort()).toEqual(['text/html', 'text/plain']);
    expect(await item.items['text/plain'].text()).toBe('Titre\n\nCorps');
    expect(await item.items['text/html'].text()).toBe(HTML);
  });

  it('falls back to flattened writeText when ClipboardItem is unavailable', async () => {
    vi.stubGlobal('ClipboardItem', undefined);
    await copyMessageToClipboard(HTML);
    expect(writeText).toHaveBeenCalledWith('Titre\n\nCorps');
  });

  it('falls back to flattened writeText when write() rejects', async () => {
    class FakeClipboardItem {
      constructor(public readonly items: Record<string, Blob>) {}
    }
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    write.mockRejectedValueOnce(new Error('denied'));
    await copyMessageToClipboard(HTML);
    expect(writeText).toHaveBeenCalledWith('Titre\n\nCorps');
  });
});
```

- [ ] **Step 7 : créer `message-clipboard.ts`** :

```ts
/**
 * Clipboard/share flattening for assistant messages.
 *
 * In `html` display mode the raw message content is a `lia-response` HTML
 * document; copying it verbatim pastes markup. HTML content is written as a
 * dual-flavor ClipboardItem (text/html for rich targets, text/plain for
 * editors), with a plain-text fallback when ClipboardItem or write() is
 * unavailable (older Firefox, permission denials). Markdown content is copied
 * verbatim — flattening it would destroy intentional formatting.
 */
import { htmlToPlainText, looksLikeHtml } from './html-plain-text';

/** Flatten assistant HTML to readable text; pass anything else through. */
export function messageToPlainText(content: string): string {
  return looksLikeHtml(content) ? htmlToPlainText(content) : content;
}

export async function copyMessageToClipboard(content: string): Promise<void> {
  if (!looksLikeHtml(content)) {
    await navigator.clipboard.writeText(content);
    return;
  }
  const plain = htmlToPlainText(content);
  if (typeof ClipboardItem !== 'undefined' && navigator.clipboard.write) {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([content], { type: 'text/html' }),
          'text/plain': new Blob([plain], { type: 'text/plain' }),
        }),
      ]);
      return;
    } catch {
      // Permission/flavor rejection (Safari, locked-down contexts): the
      // plain-text fallback below still delivers a useful copy.
    }
  }
  await navigator.clipboard.writeText(plain);
}
```

- [ ] **Step 8 : brancher** —

1. `ChatMessage.tsx` (`handleCopyMessage`, l. 628-632) : remplacer
   `await navigator.clipboard.writeText(message.content);` par
   `await copyMessageToClipboard(message.content);` (import ajouté ; try/catch, toast et
   état `copied` existants inchangés).
2. `ShareResponseMenu.tsx` : `navigator.share({ title: 'LIA', text: content })` →
   `navigator.share({ title: 'LIA', text: messageToPlainText(content) })` ; et
   `downloadMarkdown(content, …)` → `downloadMarkdown(messageToPlainText(content), …)`
   (un `.md` rempli de HTML brut n'est pas du markdown lisible ; sur contenu markdown la
   fonction est l'identité). Mettre à jour le docstring des props (`content` n'est plus
   « raw markdown » mais « raw message content (markdown or lia-response HTML) »).

- [ ] **Step 9 : vérifier**

```powershell
cd apps/web; pnpm vitest run src/lib src/components/chat
```

Attendu : PASS intégral (dont les tests existants de ShareResponseMenu/ChatMessage s'il y en
a — s'ils pinnent `writeText(message.content)`, adapter l'assertion au nouveau contrat
est légitime CAR le comportement change par design ; le noter dans le récap).

- [ ] **Step 10 : point de contrôle** — signaler.

---

### Task 12 : E2E hermétique + preuve runtime

**Files:**
- Create: `apps/web/e2e/smoke/chat-html-mode-rendering.spec.ts`
- Consomme : `expectNoOverflow`/`awaitStyledPage` (`e2e/smoke/overflow-report.ts:78-113`),
  squelette routes/SSE de `e2e/smoke/chat-scroll-follow.spec.ts:17-90`.

- [ ] **Step 1 : lire** `e2e/fixtures/` (exports `test`, `expect`, `waitForHydration`,
  `MockRoute`) et le bloc `baseRoutes` COMPLET de `chat-scroll-follow.spec.ts` (l. 85-120,
  incluant l'URL du stream SSE) — reprendre ce squelette verbatim.
- [ ] **Step 2 : écrire la spec** :

```ts
/**
 * Chat — rich-HTML display mode rendering (ADR-177).
 *
 * Hermetic: mocked history + mocked SSE streaming a full `lia-response`
 * document in small chunks (some cut mid-tag). Guards, in a real engine:
 * the components render as DOM (never as raw tag text), the collapsible
 * toggles from the keyboard, and nothing overflows the viewport on mobile.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const NL = String.fromCharCode(10);

const HTML_ANSWER = [
  '<div class="lia-response">',
  '<h2>Synthèse de la journée</h2>',
  '<div class="lia-callout lia-callout-success"><p class="lia-callout__title">Tout est prêt</p><p>Trois créneaux confirmés.</p></div>',
  '<dl class="lia-kv"><dt>Date</dt><dd><strong>12 août</strong></dd><dt>Lieu</dt><dd>Paris</dd></dl>',
  '<div class="lia-stats"><div class="lia-stat"><span class="lia-stat__value">12</span><span class="lia-stat__label">rendez-vous</span></div><div class="lia-stat"><span class="lia-stat__value">3</span><span class="lia-stat__label">urgents</span></div></div>',
  '<table><caption>Comparatif</caption><thead><tr><th>Option</th><th>Durée</th></tr></thead><tbody><tr><td>A</td><td>1 h</td></tr><tr><td>B</td><td>2 h</td></tr></tbody></table>',
  '<details class="lia-collapsible"><summary>Voir le détail</summary><p>Contenu replié.</p></details>',
  '</div>',
].join('');

/** Stream the document in 24-char chunks — several land mid-tag on purpose. */
function sseAnswer(): string {
  const chunks: string[] = [];
  for (let i = 0; i < HTML_ANSWER.length; i += 24) {
    const piece = HTML_ANSWER.slice(i, i + 24).replace(/"/g, String.fromCharCode(92) + '"');
    chunks.push('data: {"type":"token","content":"' + piece + '"}' + NL + NL);
  }
  return chunks.join('') + 'data: {"type":"done","content":"","metadata":null}' + NL + NL;
}

// baseRoutes(...): reprendre VERBATIM le squelette de chat-scroll-follow.spec.ts
// (config, conversation, messages, totals, stream) en remplaçant le corps SSE
// par sseAnswer() et l'historique par une page vide (message_count: 0).

test('rich HTML answer renders as components, keyboard-toggles, and never overflows', async ({
  page,
}) => {
  // …setup routes + navigation + waitForHydration + envoi d'un message,
  // suivant chat-scroll-follow.spec.ts…
  await awaitStyledPage(page, 'chat-html-mode');

  const heading = page.getByRole('heading', { name: 'Synthèse de la journée', level: 2 });
  await expect(heading).toBeVisible();
  // Raw tag source must never be readable anywhere in the thread.
  await expect(page.locator('.lia-response')).toBeVisible();
  expect(await page.locator('body').textContent()).not.toContain('<h2>');

  await expect(page.locator('.lia-callout-success .lia-callout__title')).toHaveText(
    'Tout est prêt'
  );
  await expect(page.locator('.lia-stat__value').first()).toHaveText('12');

  // Keyboard: summary is natively focusable; Enter toggles the details.
  const summary = page.locator('details.lia-collapsible > summary');
  await summary.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('details.lia-collapsible')).toHaveAttribute('open', '');

  await expectNoOverflow(page, 'html-answer desktop');
});

test('mobile 390px: rich components stack without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  // …même setup/stream…
  await awaitStyledPage(page, 'chat-html-mode mobile');
  await expect(page.getByRole('heading', { name: 'Synthèse de la journée' })).toBeVisible();
  await expectNoOverflow(page, 'html-answer mobile');
});
```

(Les `…setup…` sont à instancier depuis le squelette lu au Step 1 — même mécanique de
routes mockées et de GATE ; c'est une transposition, pas une invention.)

- [ ] **Step 3 : exécuter le package e2e**

```powershell
task test:e2e
```

Attendu : PASS, y compris la nouvelle spec. En cas de 500 sur les chunks ou de page non
stylée : piège connu du serveur standalone fantôme / `.next` corrompu → purger `.next` et
relancer (mémoire projet), ne pas conclure à un défaut du code.

- [ ] **Step 4 : preuve runtime réelle** — `docker restart lia-web-dev lia-api-dev`, tour de
  chat réel en mode HTML (même question qu'en T1) : comparer aux captures baseline, light +
  dark + 390 px. La réponse réelle doit exploiter au moins un composant nouveau (sinon,
  reformuler la question pour des données structurées — ex. « compare mes deux prochains
  rendez-vous ») ; vérifier aussi le bouton Copier (collage lisible dans un éditeur texte).
- [ ] **Step 5 : point de contrôle** — signaler avec captures.

---

### Task 13 : Gates finaux + ratchets

**Files:**
- Modify (si marge) : `apps/web/vitest.config.ts:70-98` (planchers globaux)

- [ ] **Step 1 : gates statiques complets**

```powershell
task lint
cd apps/web; pnpm exec tsc --noEmit --incremental false
```

Attendu : PASS (lint inclut i18n, docs, hygiene, ratchets a11y/hooks/cc et le tsc froid).

- [ ] **Step 2 : couverture frontend (commande CI verbatim)**

```powershell
task test:frontend:coverage
```

Relever les valeurs mesurées (statements/branches/functions/lines globales). Référence au
verrouillage précédent (2026-07-28) : 66.40 / 60.13 / 60.52 / 66.96 pour des planchers à
64/58/58/65.

- [ ] **Step 3 : relever les planchers si ≥2 pts de marge** — dans `vitest.config.ts`,
  remonter chaque plancher global à `floor(mesuré − 2)` s'il est supérieur au plancher
  actuel, et mettre à jour le commentaire de mesure daté (même format que l'existant :
  date, nombre de fichiers/tests, valeurs mesurées). Ne JAMAIS baisser une valeur ; ne pas
  toucher aux blocs per-file.
- [ ] **Step 4 : backend**

```powershell
task test:backend:unit:fast
```

(La couverture backend ne bouge pas — seul un fichier de test a été ajouté ; le plancher 62
reste en l'état.)

- [ ] **Step 5 : la totale avant remise**

```powershell
task ci:fast
```

Attendu : PASS intégral (inclut `test:markers` pour le nouveau fichier pytest — règle F006).

- [ ] **Step 6 : récapitulatif final** — message de synthèse : commandes exécutées + statuts,
  couverture avant/après + planchers relevés, captures runtime, liste exacte des fichiers
  modifiés/créés, et rappel des surfaces de release restantes (bump version, CHANGELOG,
  clé FAQ changelog `changelogVersionKeys`, surfaces narratives) qui appartiennent au
  processus de release de l'utilisateur — **aucun commit effectué**.

---

## Self-review du plan (fait à la rédaction)

- **Couverture spec** : Lot 0 → T1 ; Lot 1.1-1.6 → T3, 1.7 → T2 ; Lot 2 CSS → T5,
  directive → T7, schéma → T4 ; Lot 3.1 → T11, 3.2 → T12, 3.3 → T6 (+T2/T4), 3.4 → T10,
  3.5 → T8+T9, 3.6 → T13. Critères d'acceptation 1-7 de la spec ↔ T12/T13. Aucun trou.
- **Placeholders** : les deux `…setup…` de T12 renvoient à un squelette source cité
  ligne à ligne, lu au Step 1 de la tâche — transposition, pas invention.
- **Cohérence des noms** : `lia-callout__title`, `lia-collapsible`, `lia-kv`, `lia-columns`,
  `lia-steps`, `lia-stats`/`lia-stat__value`/`lia-stat__label` identiques dans T3/T5 (CSS),
  T6 (tests), T7 (directive + garde), T12 (e2e). `htmlToPlainText`/`looksLikeHtml`/
  `messageToPlainText`/`copyMessageToClipboard` identiques dans T11 (module, tests,
  branchements).
