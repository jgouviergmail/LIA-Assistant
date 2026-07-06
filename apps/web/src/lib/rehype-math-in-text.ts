/**
 * rehype-math-in-text — render `$…$` / `$$…$$` math that lives inside RAW HTML.
 *
 * WHY THIS EXISTS
 * ---------------
 * The assistant is instructed (backend `html_response_directive`) to emit its
 * ENTIRE answer as HTML wrapped in `<div class="lia-response">`. Any formula
 * the model writes therefore sits inside a raw HTML block (`<p>…$$x$$…</p>`).
 *
 * `remark-math` operates on the MARKDOWN AST and treats raw HTML blocks as
 * opaque — and it runs BEFORE `rehype-raw` expands that HTML into real nodes.
 * So math buried in HTML is never tokenized and renders as literal `$$…$$`
 * text. (Pure-markdown math still works via remark-math; only HTML-wrapped
 * math was broken — which is 100% of real responses.)
 *
 * This rehype plugin runs at the HAST level, AFTER `rehype-raw` has expanded
 * the HTML into element + text nodes, so it sees the delimiters inside the
 * (now real) `<p>` text. It converts each math run into the marker element
 * `rehype-katex` consumes (`<span class="math-inline|math-display">TEX</span>`)
 * and leaves currency (`9$`) as literal text. `rehype-katex` (running right
 * after) renders the markers. It covers BOTH the HTML-wrapped and the
 * pure-markdown paths uniformly.
 *
 * SCOPE / CONTRACT
 * ----------------
 * - `\[…\]` / `\(…\)` and ```` ```latex ```` are already canonicalized to
 *   `$$`/`$` upstream by `normalizeMathDelimiters` (string level, before
 *   markdown), so only `$`/`$$` reach this plugin.
 * - Text inside `<code>`, `<pre>`, `<script>`, `<style>` and any element
 *   already carrying a math/katex class is left untouched (skip set).
 * - Inline `$…$` follows MathJax delimiter rules (opening `$` not followed by
 *   whitespace; closing `$` not preceded by whitespace, not followed by a
 *   digit) so dollar amounts stay literal.
 * - The tokenizer is a single left-to-right pass: an UNCLOSED `$$` (common
 *   mid-stream) is emitted as literal text and never mis-paired into an empty
 *   inline `$…$` — avoiding a streaming flash.
 *
 * SECURITY
 * --------
 * The plugin reads only already-sanitized text nodes and emits a fixed-class
 * `<span>` wrapping a plain text child (never interpreted as markup). The XSS
 * posture is identical to the existing `remark-math` → `rehype-katex` path,
 * which already runs (by design) after the sanitize boundary.
 *
 * Types are declared locally (structural subset of hast) on purpose: it keeps
 * the plugin dependency-free — no `@types/hast` devDependency, no pnpm
 * lockfile-sync step — for a small, self-contained transform.
 */

interface TextNode {
  type: 'text';
  value: string;
}

interface ElementNode {
  type: 'element';
  tagName: string;
  properties?: Record<string, unknown> | null;
  children: HastNode[];
}

type HastNode = TextNode | ElementNode | { type: string; children?: HastNode[]; value?: string };

/** Tags whose text content must never be treated as math. */
const SKIP_TAGS = new Set(['code', 'pre', 'script', 'style']);

/** Classes marking an element whose text was already turned into math. */
const MATH_CLASSES = ['math-inline', 'math-display', 'language-math', 'katex'];

type Segment =
  | { kind: 'text'; value: string }
  | { kind: 'inline'; value: string }
  | { kind: 'display'; value: string };

const isWhitespace = (ch: string | undefined): boolean => ch !== undefined && /\s/.test(ch);
const isDigit = (ch: string | undefined): boolean => ch !== undefined && ch >= '0' && ch <= '9';

/** Index of the first `$` of the next unescaped `$$` at/after `start`, or -1. */
function findClosingDouble(value: string, start: number): number {
  for (let j = start; j < value.length - 1; j++) {
    if (value[j] === '$' && value[j - 1] !== '\\' && value[j + 1] === '$') return j;
  }
  return -1;
}

/**
 * Index of the closing `$` for an inline run whose first content char is at
 * `openIdx`, applying MathJax rules, or -1 when the run is not math (e.g.
 * currency). Closes greedily at the first valid single `$` (which matches the
 * former escapeCurrencyDollars semantics); a `$$` display run can never reach
 * here because it is always consumed at the OPENING scan, so no `$$`-guard is
 * needed — and guarding here would mis-slice adjacent inline runs (`$a$$b$`).
 */
function findClosingSingle(value: string, openIdx: number): number {
  for (let j = openIdx + 1; j < value.length; j++) {
    if (value[j] !== '$') continue;
    if (value[j - 1] === '\\') continue; // escaped dollar, not a delimiter
    const before = value[j - 1];
    const after = value[j + 1];
    if (!isWhitespace(before) && !isDigit(after)) return j;
  }
  return -1;
}

/**
 * Split a text-node value into literal / inline-math / display-math segments.
 * Single left-to-right pass; `\[`/`\(` are already `$`/`$$` by this point.
 */
function tokenizeMath(value: string): Segment[] {
  const out: Segment[] = [];
  let buf = '';
  const flush = (): void => {
    if (buf) {
      out.push({ kind: 'text', value: buf });
      buf = '';
    }
  };

  const n = value.length;
  let i = 0;
  while (i < n) {
    const c = value[i];

    // Escaped dollar → literal `$`.
    if (c === '\\' && value[i + 1] === '$') {
      buf += '$';
      i += 2;
      continue;
    }

    if (c === '$') {
      // Display math: $$…$$
      if (value[i + 1] === '$') {
        const close = findClosingDouble(value, i + 2);
        if (close !== -1) {
          flush();
          out.push({ kind: 'display', value: value.slice(i + 2, close).trim() });
          i = close + 2;
          continue;
        }
        // Unclosed `$$` → literal (never re-parsed as two inline `$`).
        buf += '$$';
        i += 2;
        continue;
      }

      // Inline math: $…$ under MathJax delimiter rules.
      const afterOpen = value[i + 1];
      if (afterOpen !== undefined && !isWhitespace(afterOpen)) {
        const close = findClosingSingle(value, i + 1);
        if (close !== -1) {
          flush();
          out.push({ kind: 'inline', value: value.slice(i + 1, close) });
          i = close + 1;
          continue;
        }
      }

      // Lone / currency `$` → literal.
      buf += '$';
      i += 1;
      continue;
    }

    buf += c;
    i += 1;
  }

  flush();
  return out;
}

function isElement(n: HastNode): n is ElementNode {
  return n.type === 'element' && typeof (n as ElementNode).tagName === 'string';
}

function isText(n: HastNode): n is TextNode {
  return n.type === 'text' && typeof (n as TextNode).value === 'string';
}

function classListOf(el: ElementNode): string[] {
  const cn = el.properties?.className;
  if (Array.isArray(cn)) return cn.map(String);
  if (typeof cn === 'string') return cn.split(/\s+/);
  return [];
}

function isSkippable(el: ElementNode): boolean {
  if (SKIP_TAGS.has(el.tagName)) return true;
  const classes = classListOf(el);
  return MATH_CLASSES.some(m => classes.includes(m));
}

function segmentToNode(seg: Segment): HastNode {
  if (seg.kind === 'text') return { type: 'text', value: seg.value };
  const className = seg.kind === 'display' ? 'math-display' : 'math-inline';
  return {
    type: 'element',
    tagName: 'span',
    properties: { className: [className] },
    children: [{ type: 'text', value: seg.value }],
  };
}

/** Recursively convert `$`/`$$` runs in text nodes into math marker spans. */
function transform(node: HastNode, skip: boolean): void {
  const children = (node as ElementNode).children;
  if (!Array.isArray(children)) return;

  const next: HastNode[] = [];
  for (const child of children) {
    if (isText(child)) {
      // Fast path: no `$` at all → nothing to do (the vast majority of text).
      if (skip || !child.value.includes('$')) {
        next.push(child);
        continue;
      }
      // A `$` is present: tokenize and re-emit. Even an all-text result is
      // re-emitted so an escaped `\$` is normalized to a literal `$`
      // consistently (markdown escape semantics), not only when math is nearby.
      for (const seg of tokenizeMath(child.value)) next.push(segmentToNode(seg));
    } else if (isElement(child)) {
      transform(child, skip || isSkippable(child));
      next.push(child);
    } else {
      next.push(child);
    }
  }

  (node as ElementNode).children = next;
}

/**
 * rehype plugin. Place AFTER `rehype-raw` + `rehype-sanitize` and BEFORE
 * `rehype-katex`: `[rehypeRaw, [rehypeSanitize, schema], rehypeMathInText,
 * rehypeKatex]`.
 */
export default function rehypeMathInText() {
  return (tree: { type: string; children?: HastNode[]; [key: string]: unknown }): void => {
    transform(tree as HastNode, false);
  };
}
