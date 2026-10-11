/**
 * The data cards an assistant answer ends on, apart from the words before them.
 *
 * In the two card display modes (`cards`, `html_cards`) the response node
 * appends the server-rendered data cards AFTER the model's answer
 * (`final_content + "\n\n" + cards`), and the message is stored exactly that
 * way — so the chat can fold them under one disclosure, for a new answer and a
 * reloaded history alike, without a server change.
 *
 * The split is conservative by construction: it only recognises a tail made
 * entirely of the roots the card renderer writes, starting on a line of its
 * own, outside any HTML block or code fence, after words that stay visible.
 * Anything else — an answer of cards alone, a HITL draft card (`lia-draft`,
 * `lia-draft-result`), an interactive widget after the cards, a sentence after
 * them, a tail it cannot balance — returns `null` and renders as before.
 *
 * Linear: the tags are matched once, then walked backward from the end.
 */

import { endsAtTopLevel, TAG, VOID_ELEMENTS } from './message-markdown';

/** An answer split into the words shown and the cards folded. */
export interface TrailingCards {
  /** Everything before the cards, trailing blank lines removed. */
  prose: string;
  /** The card block, as stored. */
  cards: string;
}

/**
 * The top-level elements the card renderer writes, by tag name, keyed on the
 * element's FIRST class (`display/card_collection.py`, `html_renderer.py`,
 * `components/base.py`): a bound card, a multi-domain / correlated / nested /
 * empty block, the response wrapper and its separator, the « see more » fold.
 */
const CARD_ROOTS: Readonly<Record<string, ReadonlySet<string>>> = {
  div: new Set([
    'lia-card-binding',
    'lia-response-wrapper',
    'lia-multi-domain',
    'lia-correlated',
    'lia-nested-list',
    'lia-empty',
  ]),
  hr: new Set(['lia-response-separator']),
  details: new Set(['lia-card-collection']),
};

const CLASS_ATTRIBUTE = /\sclass="([^"]*)"/;

function isCardRoot(tag: string, name: string): boolean {
  const roots = CARD_ROOTS[name.toLowerCase()];
  const firstClass = CLASS_ATTRIBUTE.exec(tag)?.[1].trim().split(/\s+/)[0];
  return roots !== undefined && firstClass !== undefined && roots.has(firstClass);
}

/**
 * Where the contiguous run of top-level card roots that ends the answer starts.
 *
 * @returns The offset of the first root of the run, or null when the answer
 *   does not END on card roots or its tail cannot be balanced.
 */
function cardTailStart(content: string): number | null {
  const tags = [...content.matchAll(TAG)];
  let depth = 0;
  let start: number | null = null;
  let gapEnd = content.length;
  for (let index = tags.length - 1; index >= 0; index -= 1) {
    const match = tags[index];
    const [tag, closing, name = '', selfClosing] = match;
    const at = match.index;
    // Between two top-level elements of the tail, only blank space.
    if (depth === 0 && content.slice(at + tag.length, gapEnd).trim()) break;
    gapEnd = at;
    if (selfClosing || VOID_ELEMENTS.has(name.toLowerCase())) {
      if (depth > 0) continue;
      if (!isCardRoot(tag, name)) break;
      start = at;
    } else if (closing) {
      depth += 1;
    } else {
      depth -= 1;
      // An element opened and never closed: the tail is not one we can fold.
      if (depth < 0) return null;
      if (depth === 0) {
        if (!isCardRoot(tag, name)) break;
        start = at;
      }
    }
  }
  // Still inside an element: the card tail closes more than it opened.
  return depth > 0 && start === null ? null : start;
}

/**
 * The words of an answer and the data cards it ends on, when they can be told
 * apart with certainty.
 *
 * @param content - The assistant message as stored.
 * @returns The two parts, or null when the answer must render unchanged.
 */
export function splitTrailingCards(content: string): TrailingCards | null {
  const start = cardTailStart(content);
  if (start === null || start === 0 || content[start - 1] !== '\n') return null;
  const before = content.slice(0, start);
  if (!before.trim() || !endsAtTopLevel(before)) return null;
  return { prose: before.trimEnd(), cards: content.slice(start) };
}
