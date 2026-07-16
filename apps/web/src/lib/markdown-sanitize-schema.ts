// `defaultSchema` comes from rehype-sanitize's OFFICIAL re-export (of its
// hast-util-sanitize dependency). Never import from 'hast-util-sanitize'
// directly: it is a transitive, undeclared dependency — a fresh
// `pnpm install --frozen-lockfile` does not expose it to the app and
// `next build` fails with "Module not found" (only hoisted local
// node_modules masked this).
import { defaultSchema, type Options } from 'rehype-sanitize';

type AttrEntry = string | [string, ...Array<string | number | boolean | RegExp | null | undefined>];

/**
 * Tags on which `defaultSchema` CONSTRAINS `className` to a fixed allow-list
 * (tuple form, e.g. `a` → only `data-footnote-backref`, `h2` → only
 * `sr-only`, `li`/`ol`/`ul` → task-list classes, `code` → language classes,
 * `section` → `footnotes`). A per-tag constraint takes precedence over the
 * `'*'` wildcard, so those classes get silently stripped — observed live: a
 * card title `<a class="lia-card__title">` lost its class and rendered as a
 * default blue link. LIA cards / rich-HTML set arbitrary `.lia-*` classes on
 * these tags, so we drop the constrained `className` tuples and allow
 * `className` freely per tag.
 */
const CONSTRAINED_CLASSNAME_TAGS = ['a', 'code', 'h2', 'li', 'ol', 'section', 'ul'];

function withFreeClassName(tag: string, extra: string[] = []): AttrEntry[] {
  const base = ((defaultSchema.attributes?.[tag] ?? []) as AttrEntry[]).filter(
    entry => !(Array.isArray(entry) && entry[0] === 'className')
  );
  return [...base, 'className' as AttrEntry, ...extra];
}

/**
 * Sanitization schema for assistant-rendered markdown/HTML.
 *
 * The chat pipeline renders LLM output with `rehype-raw` (needed for rich
 * HTML answers and server-generated cards), which historically ran WITHOUT
 * sanitization — the documented XSS anti-pattern: the LLM can relay verbatim
 * third-party content (email bodies, fetched web pages, MCP tool output),
 * and any embedded HTML executed with the user's session.
 *
 * This schema extends the GitHub-style `defaultSchema` with exactly what the
 * legitimate HTML inventory needs (audited across
 * `apps/api/src/domains/agents/display/components/` and the rich-HTML
 * response directive):
 *
 * - `button` tag (card action buttons, `type` + `data-action`)
 * - `className` everywhere, INCLUDING the constrained tags above: `.lia-*`
 *   cards/callouts, KaTeX math spans (sanitize runs BEFORE rehypeMathInText +
 *   rehype-katex, so the math nodes must survive), Material-Symbols icon spans,
 *   code language classes
 * - `style` everywhere: some cards still use inline styles (audited: no
 *   modern browser executes JS from inline CSS — acceptable trade-off)
 * - `data*` wildcard: sentinel/action attributes (`data-registry-id`,
 *   `data-action`, `data-reminder-id`, …) consumed by the React layer
 * - `tel:` links (click-to-call on contact cards; mirrors `urlTransform`)
 * - `<style>` blocks are STRIPPED (not just dropped): messages predating the
 *   externalized `.lia-response` CSS carry an inline `<style>` block whose
 *   text content would otherwise leak into the rendered output
 *
 * Deliberately NOT allowed: `script`, `iframe`, `form`, event handlers.
 * MCP App iframes never go through markdown — the server emits a
 * `<div class="lia-mcp-app" data-registry-id>` sentinel replaced by the
 * dedicated (sandboxed) `McpAppWidget` React component.
 */
export const markdownSanitizeSchema: Options = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), 'button'],
  strip: ['script', 'style'],
  attributes: {
    ...defaultSchema.attributes,
    '*': [...(defaultSchema.attributes?.['*'] ?? []), 'className', 'style', 'data*'],
    // Free className on the tags defaultSchema would otherwise constrain:
    ...Object.fromEntries(CONSTRAINED_CLASSNAME_TAGS.map(t => [t, withFreeClassName(t)])),
    // `a` also needs target/rel for card links opening in a new tab:
    a: withFreeClassName('a', ['target', 'rel']),
    img: [...(defaultSchema.attributes?.img ?? []), 'loading'],
    details: [...(defaultSchema.attributes?.details ?? []), 'open'],
    button: ['type', 'disabled', 'className', 'style', 'data*'],
  },
  protocols: {
    ...defaultSchema.protocols,
    href: [...(defaultSchema.protocols?.href ?? []), 'tel'],
  },
};
