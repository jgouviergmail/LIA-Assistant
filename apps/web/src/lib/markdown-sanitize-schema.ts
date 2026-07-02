import { defaultSchema } from 'hast-util-sanitize';
import type { Options } from 'rehype-sanitize';

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
 * - `className` everywhere: `.lia-*` cards/callouts + KaTeX math spans
 *   (sanitize runs BEFORE rehype-katex, so the math nodes must survive)
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
    a: [...(defaultSchema.attributes?.a ?? []), 'target', 'rel'],
    img: [...(defaultSchema.attributes?.img ?? []), 'loading'],
    details: [...(defaultSchema.attributes?.details ?? []), 'open'],
    button: ['type', 'disabled'],
  },
  protocols: {
    ...defaultSchema.protocols,
    href: [...(defaultSchema.protocols?.href ?? []), 'tel'],
  },
};
